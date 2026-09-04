import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from modern_firmware import check_lock, docker_command, validate_lock
from phase5_benchmark import device_program, sample_summary, validate_result


def load_modern_rendering():
    path = ROOT / "src/lib/tartlabutils/modern.py"
    spec = importlib.util.spec_from_file_location("phase5_modern", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_lilygo_platform(modern):
    path = ROOT / "boards/lilygo_t_display_s3_pro/runtime/t_display_s3_pro_modern.py"
    spec = importlib.util.spec_from_file_location("phase5_lilygo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_modern_factory(modern):
    package = types.ModuleType("tartlabutils")
    package.__path__ = []
    board_path = ROOT / "src/lib/tartlabutils/board.py"
    board_spec = importlib.util.spec_from_file_location(
        "tartlabutils.board", board_path)
    board = importlib.util.module_from_spec(board_spec)
    factory_path = ROOT / "src/lib/tartlabutils/modern_factory.py"
    factory_spec = importlib.util.spec_from_file_location(
        "phase5_modern_factory", factory_path)
    factory = importlib.util.module_from_spec(factory_spec)
    adapter_path = ROOT / "src/lib/tartlabutils/modern_st7796.py"
    adapter_spec = importlib.util.spec_from_file_location(
        "tartlabutils.modern_st7796", adapter_path)
    adapter = importlib.util.module_from_spec(adapter_spec)
    with mock.patch.dict(sys.modules, {
        "tartlabutils": package,
        "tartlabutils.board": board,
        "tartlabutils.modern": modern,
        "tartlabutils.modern_st7796": adapter,
    }):
        board_spec.loader.exec_module(board)
        adapter_spec.loader.exec_module(adapter)
        factory_spec.loader.exec_module(factory)
    return factory, package, adapter


class FakePointerDriver:
    PRESSED = 1
    RELEASED = 0

    def __init__(self, **kwargs):
        self.pointer_options = kwargs


class FakeI2CDevice:
    def __init__(self, chip_id=0x00A8):
        self.chip_id = chip_id
        self.status = bytearray(28)
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))

    def read(self, num_bytes=None, buf=None):
        if self.writes[-1] != b"\xD2\x04":
            raise AssertionError("identity read did not follow D2 04 command")
        target = buf if buf is not None else bytearray(num_bytes)
        target[:] = bytes((0, 0, self.chip_id & 0xFF,
                           self.chip_id >> 8))
        return target if buf is None else None

    def write_readinto(self, write_data, read_data):
        command = bytes(write_data)
        if command == b"\xD2\x04":
            read_data[:] = bytes((0, 0, self.chip_id & 0xFF,
                                  self.chip_id >> 8))
        elif command == b"\x00":
            read_data[:] = self.status
        else:
            raise AssertionError(f"unexpected I2C command: {command!r}")


def load_cst226_driver():
    pointer = types.ModuleType("pointer_framework")
    pointer.PointerDriver = FakePointerDriver
    pointer.lv = types.SimpleNamespace(
        DISPLAY_ROTATION=types.SimpleNamespace(_0=0))
    micropython = types.ModuleType("micropython")
    micropython.const = lambda value: value
    machine = types.ModuleType("machine")
    machine.Pin = types.SimpleNamespace(OUT=1, IN=2, PULL_UP=3)
    fake_time = types.ModuleType("time")
    fake_time.sleep_ms = lambda milliseconds: None
    path = ROOT / "firmware/lvgl-modern/drivers/cst226.py"
    spec = importlib.util.spec_from_file_location("phase5_cst226", path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {
        "pointer_framework": pointer,
        "micropython": micropython,
        "machine": machine,
        "time": fake_time,
    }):
        spec.loader.exec_module(module)
    return module


class ModernFirmwareReferenceLockTests(unittest.TestCase):
    def test_reference_pins_complete_source_and_toolchain(self):
        lock = check_lock()
        submodules = {
            item["path"]: item for item in lock["source"]["submodules"]
        }
        self.assertEqual(set(submodules), {
            "lib/SDL",
            "lib/esp-idf",
            "lib/lvgl",
            "lib/micropython",
            "lib/pycparser",
        })
        self.assertEqual(submodules["lib/micropython"]["version"], "1.27.0")
        self.assertEqual(submodules["lib/lvgl"]["version"], "9.4.0")
        self.assertEqual(submodules["lib/esp-idf"]["version"], "5.5.1")
        container = lock["toolchain"]["container"]
        self.assertEqual(container["platform"], "linux/amd64")
        self.assertTrue(container["manifest_digest"].startswith("sha256:"))

    def test_reference_is_reproducible_and_hardware_qualified(self):
        lock = check_lock()
        self.assertEqual(
            lock["status"],
            "research-only-reproducible-hardware-qualified")
        missing = lock["capability_gate"][
            "required_before_hardware_qualification"]
        present = lock["capability_gate"]["present_in_reference"]
        payload = lock["capability_gate"]["present_in_application_payload"]
        self.assertIn("cst226-input-driver", present)
        self.assertIn("public-direct-surface-api", payload)
        self.assertIn("exclusive-ui-game-ownership-transitions", payload)
        self.assertNotIn("public-direct-surface-api", missing)
        self.assertEqual(missing, [])
        self.assertEqual(
            [item["gate"] for item in lock["capability_gate"][
                "hardware_evidence"]],
            ["lifecycle", "comparative-benchmarks"],
        )
        result = lock["result"]
        self.assertTrue(result["byte_identical"])
        self.assertEqual(result["independent_clean_builds"], 2)
        self.assertEqual(
            result["sha256"],
            "187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab",
        )
        self.assertEqual(lock["target"]["repl"], "USB_SERIAL_JTAG")
        self.assertIn("native-usb-repl", present)

    def test_lock_rejects_a_moving_source_ref(self):
        lock = check_lock()
        invalid = copy.deepcopy(lock)
        invalid["source"]["commit"] = "main"
        with self.assertRaisesRegex(ValueError, "full lowercase Git commit"):
            validate_lock(invalid)

    def test_lock_rejects_a_changed_submodule_pin(self):
        lock = check_lock()
        invalid = copy.deepcopy(lock)
        invalid["source"]["submodules"][0]["commit"] = "0" * 39
        with self.assertRaisesRegex(ValueError, "full lowercase Git commit"):
            validate_lock(invalid)

    def test_build_command_is_digest_pinned_and_cannot_flash(self):
        lock = check_lock()
        command = docker_command(lock, ROOT / "build/phase5/reference-source")
        image = next(item for item in command if item.startswith("espressif/idf@"))
        self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")
        self.assertIn("--platform", command)
        self.assertIn("IDF_GIT_SAFE_DIR=/project", command)
        self.assertIn("SOURCE_DATE_EPOCH=1782211759", command)
        self.assertIn("DISPLAY=st7796", command)
        self.assertIn("--partition-size=4194304", command)
        self.assertIn("--enable-uart-repl=n", command)
        self.assertIn("--enable-cdc-repl=n", command)
        self.assertIn("--enable-jtag-repl=y", command)
        self.assertIn(
            "INDEV=/tartlab/firmware/lvgl-modern/drivers/cst226.py", command)
        self.assertIn(
            "/tartlab/firmware/lvgl-modern/container_prepare.py", command)
        self.assertNotIn("deploy", command)
        self.assertNotIn("--octal-flash", command)
        self.assertFalse(any(item.startswith("PORT=") for item in command))

    def test_checked_in_phase5_json_has_stable_format(self):
        paths = [
            ROOT / "firmware/lvgl-modern/reference.lock.json",
            ROOT / "firmware/lvgl-modern/reference/provenance.json",
            ROOT / "profiles/lvgl-modern.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                rendered = json.dumps(data, indent=2, sort_keys=False) + "\n"
                self.assertEqual(path.read_text(encoding="utf-8"), rendered)

    def test_item3_application_adapter_sources_are_hash_bound(self):
        check_lock()
        profile = json.loads(
            (ROOT / "profiles/lvgl-modern.json").read_text(encoding="utf-8"))
        inputs = profile["application_adapter"]["inputs"]
        self.assertEqual({item["path"] for item in inputs}, {
            "src/lib/tartlabutils/board.py",
            "src/lib/tartlabutils/modern.py",
            "src/lib/tartlabutils/modern_factory.py",
            "src/lib/tartlabutils/modern_st7796.py",
            "boards/lilygo_t_display_s3_pro/runtime/t_display_s3_pro_modern.py",
        })


class CST226ReferenceDriverTests(unittest.TestCase):
    def test_initialization_checks_identity_and_configures_polling(self):
        module = load_cst226_driver()
        device = FakeI2CDevice()
        driver = module.CST226(device)
        self.assertEqual(driver.pointer_options["startup_rotation"], 0)
        self.assertEqual(device.writes, [
            b"\xD1\x0E",
            b"\xD2\x04",
            b"\xFE\x01",
            b"\xFA\x00",
            b"\xEC\x00",
        ])

    def test_first_contact_is_reported_to_pointer_framework(self):
        module = load_cst226_driver()
        device = FakeI2CDevice()
        driver = module.CST226(device)
        device.status[1] = 0x12
        device.status[2] = 0x45
        device.status[3] = 0x36
        device.status[5] = 1
        self.assertEqual(driver._get_coords(), (driver.PRESSED, 0x123, 0x456))
        device.status[0] = 0xAB
        self.assertIsNone(driver._get_coords())

    def test_wrong_controller_identity_is_rejected(self):
        module = load_cst226_driver()
        with self.assertRaisesRegex(RuntimeError, "CST226 not detected"):
            module.CST226(FakeI2CDevice(chip_id=0x1234))


class FakeModernBus:
    def __init__(self):
        self.callback = None
        self.auto_complete = True
        self.transfers = []
        self.allocations = []
        self.freed = []
        self.deinit_calls = 0

    def register_callback(self, callback):
        self.callback = callback

    def tx_color(self, *values):
        self.transfers.append(values)
        if self.auto_complete:
            self.complete()

    def complete(self):
        if self.callback is not None:
            self.callback()

    def allocate_framebuffer(self, size, flags):
        self.allocations.append((size, flags))
        return bytearray(size)

    def free_framebuffer(self, buffer):
        self.freed.append(buffer)

    def deinit(self):
        self.deinit_calls += 1


class FakeModernPanel:
    def __init__(self):
        self.params = []

    def set_params(self, command, params=None):
        self.params.append((command, bytes(params or b"")))


class FakeLVDisplay:
    def __init__(self, bus):
        self.bus = bus
        self.events = []
        self.flush_ready_calls = 0
        self.rotation = 1

    def get_horizontal_resolution(self):
        return 480

    def get_vertical_resolution(self):
        return 222

    def get_rotation(self):
        return self.rotation

    def add_event_cb(self, callback, event, user_data):
        self.events.append((callback, event, user_data))

    def begin_flush(self):
        for callback, unused_event, unused_data in self.events:
            callback(None)

    def flush_ready(self):
        self.flush_ready_calls += 1


class FakeLVScreen:
    def __init__(self):
        self.invalidations = 0
        self.background = None

    def set_style_bg_color(self, color, unused_selector):
        self.background = color

    def invalidate(self):
        self.invalidations += 1


class FakeModernLVGL:
    EVENT = types.SimpleNamespace(FLUSH_START=91)
    DISPLAY_ROTATION = types.SimpleNamespace(_0=0, _90=1, _180=2, _270=3)

    def __init__(self, display, bus):
        self.display = display
        self.bus = bus
        self.screen = FakeLVScreen()
        self.refreshes = 0

    def refr_now(self, display):
        self.refreshes += 1
        display.begin_flush()
        self.bus.complete()

    def screen_active(self):
        return self.screen


class FakeTaskHandler:
    def __init__(self):
        self.disables = 0
        self.enables = 0

    def disable(self):
        self.disables += 1

    def enable(self):
        self.enables += 1


class FakeModernInput:
    def __init__(self):
        self.enabled = []

    def enable(self, enabled):
        self.enabled.append(enabled)


class ModernRenderingAdapterTests(unittest.TestCase):
    def prepare(self):
        module = load_modern_rendering()
        bus = FakeModernBus()
        panel = FakeModernPanel()
        lv_display = FakeLVDisplay(bus)
        lvgl = FakeModernLVGL(lv_display, bus)
        tasks = FakeTaskHandler()
        pointer = FakeModernInput()
        controller = module.ModernDisplayController(
            bus, panel, lv_display, lvgl, tasks, pointer,
            offset_y=49, allocation_flags=3,
            buffer_allocator=bus.allocate_framebuffer,
            buffer_free=bus.free_framebuffer)
        return module, bus, panel, lv_display, lvgl, tasks, pointer, controller

    def test_ui_to_game_to_ui_transition_drains_and_redraws(self):
        (module, unused_bus, unused_panel, lv_display, lvgl, tasks,
         pointer, controller) = self.prepare()

        surface = controller.acquire_game()
        self.assertIs(surface, controller.surface)
        self.assertEqual(controller.owner, module.GAME_OWNER)
        self.assertEqual(tasks.disables, 1)
        self.assertEqual(pointer.enabled, [False])
        self.assertEqual(lv_display.flush_ready_calls, 1)

        controller.acquire_ui()
        self.assertEqual(controller.owner, module.UI_OWNER)
        self.assertEqual(tasks.enables, 1)
        self.assertEqual(pointer.enabled, [False, True])
        self.assertEqual(lvgl.screen.invalidations, 1)
        self.assertEqual(lv_display.flush_ready_calls, 2)

    def test_failed_game_transition_restores_ui_task_and_input(self):
        (module, unused_bus, unused_panel, unused_lv_display, lvgl, tasks,
         pointer, controller) = self.prepare()

        def fail_refresh(unused_display):
            raise RuntimeError("synthetic refresh failure")

        lvgl.refr_now = fail_refresh
        with self.assertRaisesRegex(RuntimeError, "synthetic refresh failure"):
            controller.acquire_game()
        self.assertEqual(controller.owner, module.UI_OWNER)
        self.assertEqual(tasks.disables, 1)
        self.assertEqual(tasks.enables, 1)
        self.assertEqual(pointer.enabled, [False, True])

    def test_direct_surface_uses_public_panel_and_native_bus_apis(self):
        (unused_module, bus, panel, unused_lv_display, unused_lvgl,
         unused_tasks, unused_pointer, controller) = self.prepare()
        surface = controller.acquire_game()
        bus.transfers.clear()
        panel.params.clear()

        pixels = bytes(range(24))
        surface.write(pixels, 7, 11, 4, 3)

        self.assertEqual(panel.params, [
            (0x2A, b"\x00\x07\x00\x0a"),
            (0x2B, b"\x00\x3c\x00\x3e"),
        ])
        self.assertEqual(bus.transfers, [
            (0x2C, pixels, 7, 60, 10, 62, 1, True),
        ])
        self.assertFalse(surface.busy)

    def test_async_direct_transfer_blocks_reuse_until_completion(self):
        (module, bus, unused_panel, unused_lv_display, unused_lvgl,
         unused_tasks, unused_pointer, controller) = self.prepare()
        surface = controller.acquire_game()
        bus.auto_complete = False
        pixels = bytearray(8)

        surface.write(pixels, 0, 0, 2, 2, wait=False)
        self.assertTrue(surface.busy)
        with self.assertRaises(module.DisplayOwnershipError):
            surface.write(pixels, 0, 0, 2, 2, wait=False)
        bus.complete()
        self.assertFalse(surface.busy)

    def test_direct_surface_rejects_wrong_owner_bounds_and_size(self):
        (module, unused_bus, unused_panel, unused_lv_display, unused_lvgl,
         unused_tasks, unused_pointer, controller) = self.prepare()
        surface = controller.surface
        with self.assertRaises(module.DisplayOwnershipError):
            surface.write(bytearray(2), 0, 0, 1, 1)
        controller.acquire_game()
        with self.assertRaisesRegex(ValueError, "outside"):
            surface.write(bytearray(2), 480, 0, 1, 1)
        with self.assertRaisesRegex(ValueError, "expected 8"):
            surface.write(bytearray(2), 0, 0, 2, 2)

    def test_direct_buffer_allocation_is_explicit_and_reusable(self):
        (unused_module, bus, unused_panel, unused_lv_display, unused_lvgl,
         unused_tasks, unused_pointer, controller) = self.prepare()
        surface = controller.acquire_game()
        buffer = surface.allocate_buffer(8, 5)
        self.assertEqual(len(buffer), 80)
        self.assertEqual(bus.allocations, [(80, 3)])
        surface.free_buffer(buffer)
        self.assertEqual(bus.freed, [buffer])

    def test_platform_exposes_lvgl_and_logical_game_touch(self):
        (module, unused_bus, panel, lv_display, lvgl, unused_tasks,
         unused_pointer, controller) = self.prepare()

        class Pointer:
            PRESSED = 7

            def __init__(self):
                self.points = [(7, 20, 100), None]

            def _get_coords(self):
                return self.points.pop(0)

        pointer = Pointer()
        platform = module.ModernPlatform(
            controller, panel, pointer, lvgl=lvgl)
        lv_display.rotation = lvgl.DISPLAY_ROTATION._270
        platform.enter_game_mode()

        self.assertIs(platform.lvgl, lvgl)
        self.assertEqual(platform.read_game_touch(), (100, 201))
        self.assertIsNone(platform.read_game_touch())
        platform.enter_ui_mode()
        with self.assertRaises(module.DisplayOwnershipError):
            platform.read_game_touch()

    def test_platform_clear_display_flushes_black_before_returning(self):
        (module, unused_bus, panel, unused_lv_display, lvgl, unused_tasks,
         pointer, controller) = self.prepare()
        platform = module.ModernPlatform(
            controller, panel, pointer, lvgl=lvgl)
        lvgl.color_hex = lambda value: value

        platform.clear_display()

        self.assertEqual(lvgl.screen.background, 0)
        self.assertEqual(lvgl.screen.invalidations, 1)
        self.assertEqual(lvgl.refreshes, 1)
        self.assertFalse(controller.transfer_pending)

    def test_platform_deinit_releases_registered_native_objects_once(self):
        (module, bus, unused_panel, unused_lv_display, unused_lvgl,
         unused_tasks, unused_pointer, controller) = self.prepare()

        class NativeInput:
            def __init__(self):
                self.delete_calls = 0

            def delete(self):
                self.delete_calls += 1

        class Input(FakeModernInput):
            _indevs = []

            def __init__(self):
                super().__init__()
                self._indev_drv = NativeInput()
                self._indevs.append(self)

        class Panel(FakeModernPanel):
            def __init__(self):
                super().__init__()
                self.finalize_calls = 0

            def __del__(self):
                self.finalize_calls += 1

        pointer = Input()
        panel = Panel()
        platform = module.ModernPlatform(controller, panel, pointer)
        self.assertFalse(platform.capabilities["ide_button"])

        platform.deinit()
        platform.deinit()

        self.assertEqual(pointer.enabled, [False])
        self.assertEqual(pointer._indev_drv.delete_calls, 1)
        self.assertEqual(pointer._indevs, [])
        self.assertEqual(panel.finalize_calls, 1)
        self.assertEqual(bus.deinit_calls, 1)

    def test_pinned_board_factory_uses_native_dual_dma_and_swapped_lvgl(self):
        modern = load_modern_rendering()
        module = load_lilygo_platform(modern)
        factory, tartlabutils_package, st7796_adapter = \
            load_modern_factory(modern)
        bus = FakeModernBus()
        display = FakeLVDisplay(bus)
        screen = FakeLVScreen()
        panels = []
        pointers = []
        spi_calls = []

        class Panel(FakeModernPanel):
            def __init__(self, **kwargs):
                super().__init__()
                self.options = kwargs
                self.events = []
                panels.append(self)

            def reset(self):
                self.events.append("reset")

            def init(self):
                self.events.append("init")

            def set_color_inversion(self, value):
                self.events.append(("invert", value))

            def set_rotation(self, value):
                self.events.append(("rotation", value))

            def set_backlight(self, value):
                self.events.append(("backlight", value))

        class Pointer(FakeModernInput):
            def __init__(self, device, **kwargs):
                super().__init__()
                self.device = device
                self.options = kwargs
                self.register_writes = []
                pointers.append(self)

            def _write_reg(self, register, value):
                self.register_writes.append((register, value))

        class I2CBus:
            def __init__(self, **kwargs):
                self.options = kwargs

        class I2CDevice:
            def __init__(self, **kwargs):
                self.options = kwargs

        class Handler(FakeTaskHandler):
            pass

        lvgl = types.ModuleType("lvgl")
        lvgl.COLOR_FORMAT = types.SimpleNamespace(
            RGB565_SWAPPED="rgb565-swapped")
        lvgl.DISPLAY_ROTATION = types.SimpleNamespace(_0=0, _90=1, _270=3)
        lvgl.EVENT = types.SimpleNamespace(FLUSH_START=91)
        lvgl.display_get_default = lambda: display
        lvgl.screen_active = lambda: screen
        lvgl.color_hex = lambda value: value
        lvgl.refr_now = lambda unused: None

        machine = types.ModuleType("machine")
        machine.SPI = types.SimpleNamespace(Bus=lambda **kwargs: (
            spi_calls.append(kwargs), "native-spi")[1])
        lcd_bus = types.ModuleType("lcd_bus")
        lcd_bus.MEMORY_INTERNAL = 1
        lcd_bus.MEMORY_DMA = 2
        lcd_bus.SPIBus = lambda **kwargs: bus
        lcd_bus.allocate_buffer = bus.allocate_framebuffer
        lcd_bus.free_buffer = bus.free_framebuffer
        st7796 = types.ModuleType("st7796")
        st7796.STATE_LOW = 0
        st7796.STATE_PWM = -1
        st7796.BYTE_ORDER_BGR = 8
        st7796.ST7796 = Panel
        cst226 = types.ModuleType("cst226")
        cst226.I2C_ADDR = 0x5A
        cst226.BITS = 8
        cst226.CST226 = Pointer
        i2c = types.ModuleType("i2c")
        i2c.I2C = types.SimpleNamespace(Bus=I2CBus, Device=I2CDevice)
        task_handler = types.ModuleType("task_handler")
        task_handler.TaskHandler = Handler

        with mock.patch.dict(sys.modules, {
            "tartlabutils": tartlabutils_package,
            "tartlabutils.modern_st7796": st7796_adapter,
            "cst226": cst226,
            "i2c": i2c,
            "lcd_bus": lcd_bus,
            "lvgl": lvgl,
            "machine": machine,
            "st7796": st7796,
            "task_handler": task_handler,
        }):
            platform = factory.create_platform(module.BOARD_CONFIG)

        self.assertEqual(spi_calls, [
            {"host": 1, "mosi": 17, "miso": 8, "sck": 18}])
        self.assertEqual(bus.allocations[:2], [(23040, 3), (23040, 3)])
        self.assertEqual(panels[0].options["color_space"], "rgb565-swapped")
        self.assertFalse(panels[0].options["rgb565_byte_swap"])
        self.assertEqual(
            (panels[0].options["offset_x"], panels[0].options["offset_y"]),
            (0, 49))
        self.assertEqual(pointers[0].options, {
            "reset_pin": 13, "interrupt_pin": 21, "startup_rotation": 0})
        self.assertEqual((platform.width, platform.height), (480, 222))
        self.assertTrue(platform.capabilities["exclusive_display_ownership"])
        self.assertTrue(platform.capabilities["panel_scroll"])
        self.assertEqual(screen.background, 0)
        self.assertEqual(screen.invalidations, 1)
        self.assertEqual(
            [event for event in panels[0].events if event[0] == "backlight"],
            [("backlight", 0), ("backlight", 100)])
        platform.keep_touch_awake()
        self.assertEqual(pointers[0].register_writes, [(0xFE, 0x01)])

    def test_generic_modern_adapter_has_no_board_factory(self):
        module = load_modern_rendering()
        self.assertFalse(hasattr(module, "create_t_display_s3_pro_platform"))

    def test_t_display_board_payload_declares_typed_pins_and_drivers(self):
        module = load_lilygo_platform(load_modern_rendering())
        board = module.BOARD_CONFIG
        pins = {item["type"]: item for item in board["pins"]}
        self.assertEqual(board["id"], "lilygo_t_display_s3_pro")
        self.assertEqual(pins["BUTTON"]["number"], 12)
        self.assertEqual(pins["BACKLIGHT"]["number"], 48)
        self.assertEqual(board["display"]["driver"], "st7796.ST7796")
        self.assertEqual(
            board["display"]["adapter"],
            "tartlabutils.modern_st7796")
        self.assertEqual(
            board["display"]["scroll"]["qualified_rotations"], (270,))
        self.assertEqual(board["touch"]["driver"], "cst226.CST226")

    def test_modern_ide_progress_supports_binding_without_anim_enum(self):
        module = load_modern_rendering()

        class Widget:
            def __init__(self, unused_parent=None):
                self.size = None
                self.alignment = None
                self.background = None
                self.radius = None
                self.text = "Text"

            def set_style_bg_color(self, *unused):
                self.background = unused[0]

            def set_style_border_width(self, *unused):
                pass

            def set_style_border_color(self, *unused):
                pass

            def set_style_radius(self, radius, unused_selector):
                self.radius = radius

            def set_text(self, value):
                self.text = value

            def align(self, *values):
                self.alignment = values

            def set_size(self, width, height):
                self.size = (width, height)

        class Bar(Widget):
            def __init__(self):
                super().__init__()
                self.values = []

            def set_range(self, *unused):
                pass

            def set_value(self, value, animation):
                self.values.append((value, animation))

        bar = Bar()
        lvgl = types.SimpleNamespace(
            ALIGN=types.SimpleNamespace(
                BOTTOM_MID=1, TOP_MID=2, CENTER=3, TOP_RIGHT=4),
            obj=Widget,
            label=lambda unused_parent: Widget(),
            bar=lambda unused_parent: bar,
            color_hex=lambda value: value,
            screen_load=lambda unused_screen: None,
        )
        controller = types.SimpleNamespace(acquire_ui=lambda: None)
        controller.surface = types.SimpleNamespace(width=480, height=222)

        view = module.ModernIDEView(controller, lvgl)
        self.assertEqual(view._status.text, "")
        self.assertEqual(bar.size, (420, 20))
        view.show_update_progress("TEST", 1, 3)
        view.show_app_error()
        view.show_app_error()

        self.assertEqual(bar.values, [(1, False)])
        self.assertEqual(view._app_error_indicator.size, (14, 14))
        self.assertEqual(view._app_error_indicator.alignment, (4, -12, 12))
        self.assertEqual(view._app_error_indicator.background, 0xFF0000)
        self.assertEqual(view._app_error_indicator.radius, 7)


class Phase5BenchmarkHarnessTests(unittest.TestCase):
    def test_device_program_is_micropython_compatible_source(self):
        source = device_program(3, 2)
        compile(source, "<phase5-benchmark>", "exec")
        self.assertIn("SAMPLES = 3", source)
        self.assertIn("SWITCHES = 2", source)
        self.assertNotIn("__SAMPLES__", source)

    def test_legacy_program_removes_unreachable_async_transfer_branch(self):
        universal = device_program(3, 2)
        legacy = device_program(3, 2, "legacy")
        compile(legacy, "<phase5-legacy-benchmark>", "exec")
        self.assertLess(len(legacy), len(universal))
        self.assertNotIn("LEGACY_SPECIALIZATION", legacy)
        self.assertNotIn("while surface.busy:", legacy)
        self.assertIn(
            "transfer_region(transport, 0, 0, width, height)", legacy)

    def test_device_program_rejects_unknown_profile(self):
        with self.assertRaisesRegex(ValueError, "unsupported benchmark profile"):
            device_program(3, 2, "unknown")

    def test_benchmark_result_locks_geometry_clock_and_regions(self):
        result = {
            "schema": 1,
            "profile": "modern",
            "runtime": {"configured_display_spi_hz": 60_000_000},
            "matrix": {
                "logical_width": 480,
                "logical_height": 222,
                "full_frame_bytes": 213_120,
                "color_format": "RGB565_BE_symmetric_test_assets",
                "transport_rows": 24,
                "raw_transport_buffer_count": 1,
                "pipeline_buffer_count": 2,
                "samples": 3,
                "mode_switches": 2,
                "raw_buffer_storage": "native-internal-dma",
                "pipeline_buffer_storage": "native-internal-dma",
            },
            "raw_transfers": {
                "full": {"width": 480, "height": 222,
                         "coverage_percent": 100,
                         "submission":
                         "ten-24-row-or-final-shorter-transfers"},
                "dirty_50": {"width": 240, "height": 222,
                             "coverage_percent": 50,
                             "submission":
                             "two-240x111-dirty-rectangle-transfers"},
                "dirty_25": {"width": 120, "height": 222,
                             "coverage_percent": 25,
                             "submission": "one-dirty-rectangle-transfer"},
                "dirty_10": {"width": 48, "height": 222,
                             "coverage_percent": 10,
                             "submission": "one-dirty-rectangle-transfer"},
            },
        }
        validate_result(result, "modern")
        invalid = copy.deepcopy(result)
        invalid["raw_transfers"]["dirty_10"]["width"] = 47
        with self.assertRaisesRegex(ValueError, "dirty_10"):
            validate_result(invalid)

    def test_sample_summary_reports_median_and_interpolated_p95(self):
        self.assertEqual(sample_summary([10, 20, 30, 40]), {
            "samples": 4,
            "minimum": 10,
            "median": 25.0,
            "p95": 38.5,
            "maximum": 40,
        })


if __name__ == "__main__":
    unittest.main()
