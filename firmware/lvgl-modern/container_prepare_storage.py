"""Opt-in native SPI/SD and RGB lifetime fixes for the pinned ESP32 fork.

Keep the qualified wrapper unchanged. This wrapper is a separate, hash-bound
build input; no board wiring or geometry belongs in these native fixes.
"""

from pathlib import Path
import sys

import container_prepare


def replace_once(value, old, new):
    if value.count(old) != 1:
        raise ValueError("unexpected pinned native source: " + old[:90])
    return value.replace(old, new, 1)


def replace_function(value, signature, replacement):
    start = value.index(signature)
    body = value.index("{", start)
    depth = 1
    end = body + 1
    while depth:
        depth += (value[end] == "{") - (value[end] == "}")
        end += 1
    return value[:start] + replacement.strip() + value[end:]


SPI_REGISTER = r'''
void mp_machine_hw_spi_bus_add_device(mp_machine_hw_spi_device_obj_t *device)
{
    mp_machine_hw_spi_bus_obj_t *bus = device->spi_bus;
    for (uint8_t i = 0; i < bus->device_count; ++i) {
        if (bus->devices[i] == device) return;
    }
    if (bus->device_count == UINT8_MAX) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("too many SPI devices"));
    }
    bus->devices = m_realloc(bus->devices, (bus->device_count + 1) * sizeof(*bus->devices));
    bus->devices[bus->device_count++] = device;
}
'''

SPI_REMOVE = r'''
void mp_machine_hw_spi_bus_remove_device(mp_machine_hw_spi_device_obj_t *device)
{
    mp_machine_hw_spi_bus_obj_t *bus = device->spi_bus;
    uint8_t i = 0;
    while (i < bus->device_count && bus->devices[i] != device) ++i;
    if (i == bus->device_count) return;
    for (++i; i < bus->device_count; ++i) bus->devices[i - 1] = bus->devices[i];
    bus->devices[--bus->device_count] = NULL;
    if (bus->device_count == 0) bus->deinit(bus);
}
'''

SPI_DEINIT_ALL = r'''
void mp_machine_hw_spi_bus_deinit_all(void)
{
    if (machine_hw_spi_bus_objs == NULL) return;
    for (int i = 0; i < MICROPY_HW_SPI_MAX; ++i) {
        if (machine_hw_spi_bus_objs[i] != NULL) {
            machine_hw_spi_bus_deinit_internal(machine_hw_spi_bus_objs[i]);
        }
    }
    // Objects stay allocated until gc_sweep_all runs their finalizers. Every
    // hardware device is already inactive, so those finalizers are harmless.
    machine_hw_spi_bus_objs = NULL;
}
'''

SD_SPI_RELEASE = r'''
static void sd_spi_deinit_callback(mp_machine_hw_spi_device_obj_t *device) {
    sdcard_card_obj_t *self = (sdcard_card_obj_t *)device;
    if (self->sdspi_handle != -1) {
        check_esp_err(sdspi_host_remove_device(self->sdspi_handle));
        self->sdspi_handle = -1;
    }
    self->flags = 0;
    self->spi_device.active = false;
}
'''

SD_DEINIT = r'''
static mp_obj_t sd_deinit(mp_obj_t self_in) {
    sdcard_card_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->spi_device.spi_bus != NULL) {
        sd_spi_deinit_callback(&self->spi_device);
        mp_machine_hw_spi_bus_remove_device(&self->spi_device);
    } else if (self->flags & SDCARD_CARD_FLAGS_HOST_INIT_DONE) {
        if (self->host.flags & SDMMC_HOST_FLAG_DEINIT_ARG) {
            check_esp_err(self->host.deinit_p(self->host.slot));
        } else {
            check_esp_err(self->host.deinit());
        }
        self->flags = 0;
    }
    return mp_const_none;
}
'''

LV_ROOT_RESET = """    mp_lv_roots = MP_STATE_VM(mp_lv_roots) = NULL;
    MP_STATE_VM(mp_lv_user_data) = NULL;"""


def patch_spi(value):
    value = replace_once(value,
        "static mp_machine_hw_spi_bus_obj_t *machine_hw_spi_bus_objs[MICROPY_HW_SPI_MAX];",
        "MP_REGISTER_ROOT_POINTER(mp_obj_t *tartlab_spi_buses);\n"
        "#define machine_hw_spi_bus_objs MP_STATE_VM(tartlab_spi_buses)")
    for signature, replacement in (
        ("void mp_machine_hw_spi_bus_deinit_all(void)", SPI_DEINIT_ALL),
        ("void mp_machine_hw_spi_bus_add_device(", SPI_REGISTER),
        ("void mp_machine_hw_spi_bus_remove_device(", SPI_REMOVE),
        ("static void machine_hw_spi_device_deinit_internal(", r'''
static void machine_hw_spi_device_deinit_internal(mp_machine_hw_spi_device_obj_t *self)
{
    machine_hw_spi_device_deinit_callback(self);
    mp_machine_hw_spi_bus_remove_device(self);
}''')):
        value = replace_function(value, signature, replacement)
    value = replace_once(value,
        "    int cs = (int)mp_obj_get_int(self->cs);",
        "    self->active = false;\n    self->user_data = NULL;\n"
        "    int cs = (int)mp_obj_get_int(self->cs);")
    value = replace_once(value,
        "    if (1 <= host && host <= MICROPY_HW_SPI_MAX) {",
        "    if (machine_hw_spi_bus_objs == NULL) {\n"
        "        machine_hw_spi_bus_objs = m_new0(mp_obj_t, MICROPY_HW_SPI_MAX);\n"
        "    }\n    if (1 <= host && host <= MICROPY_HW_SPI_MAX) {")
    value = replace_once(value, "        self->host = host;",
        "        self->host = host;\n        self->device_count = 0;\n"
        "        self->devices = NULL;\n        self->state = MP_SPI_STATE_STOPPED;")
    value = replace_once(value, "    self->bits =  (uint8_t)args[ARG_bits].u_int;",
        "    self->bits =  (uint8_t)args[ARG_bits].u_int;\n"
        "    self->active = false;\n"
        "    self->phase = (uint8_t)args[ARG_phase].u_int;\n"
        "    self->polarity = (uint8_t)args[ARG_polarity].u_int;\n"
        "    self->firstbit = (uint8_t)args[ARG_firstbit].u_int;")
    return value


def patch_sd(value):
    value = replace_once(value, "    mp_obj_base_t base;", """    // The registered device pointer must point at the allocation's GC head.
    union {
        mp_obj_base_t base;
        mp_machine_hw_spi_device_obj_t spi_device;
    };""")
    value = replace_once(value, "    mp_machine_hw_spi_device_obj_t spi_device;\n} sdcard_card_obj_t;",
                         "} sdcard_card_obj_t;")
    value = replace_once(value, "static esp_err_t sdcard_ensure_card_init", SD_SPI_RELEASE +
                         "\nstatic esp_err_t sdcard_ensure_card_init")
    value = replace_once(value,
        "static esp_err_t sdcard_ensure_card_init(sdcard_card_obj_t *self, bool force) {",
        "static esp_err_t sdcard_ensure_card_init(sdcard_card_obj_t *self, bool force) {\n"
        "    if (!(self->flags & SDCARD_CARD_FLAGS_HOST_INIT_DONE)) return ESP_ERR_INVALID_STATE;")
    value = replace_once(value,
        "    sdcard_card_obj_t *self = mp_obj_malloc_with_finaliser(sdcard_card_obj_t, &machine_sdcard_type);",
        "    sdcard_card_obj_t *self = mp_obj_malloc_with_finaliser(sdcard_card_obj_t, &machine_sdcard_type);\n"
        "    self->flags = 0;\n    self->sdspi_handle = -1;\n"
        "    self->spi_device.spi_bus = NULL;\n    self->spi_device.active = false;\n"
        "    self->spi_device.deinit = sd_spi_deinit_callback;")
    value = replace_once(value,
        "        mp_machine_hw_spi_bus_add_device(&self->spi_device);",
        "        // ESP-IDF returns a device handle; transactions must use it.\n"
        "        self->host.slot = self->sdspi_handle;\n"
        "        self->spi_device.active = true;\n"
        "        mp_machine_hw_spi_bus_add_device(&self->spi_device);")
    return replace_function(value, "static mp_obj_t sd_deinit(", SD_DEINIT)


def patch_rgb(value):
    value = replace_once(value, "    static mp_lcd_rgb_bus_obj_t **rgb_bus_objs;",
        "    MP_REGISTER_ROOT_POINTER(mp_obj_t *tartlab_rgb_buses);\n"
        "    #define rgb_bus_objs MP_STATE_VM(tartlab_rgb_buses)")
    value = replace_function(value, "    void mp_lcd_rgb_bus_deinit_all(void)", """
    void mp_lcd_rgb_bus_deinit_all(void)
    {
        while (rgb_bus_count != 0) {
            rgb_del(rgb_bus_objs[rgb_bus_count - 1]);
        }
        rgb_bus_objs = NULL;
    }""")
    value = replace_once(value, "            rgb_bus_lock_release(&self->tx_color_lock);",
        "            rgb_bus_lock_release(&self->tx_color_lock);\n"
        "            // Keep the panel, events and buffers alive until the worker exits.\n"
        "            while (self->copy_task_handle != NULL) vTaskDelay(1);")
    value = replace_once(value, "                rgb_bus_objs[j - i + 1] = rgb_bus_objs[j];",
                         "                rgb_bus_objs[j - 1] = rgb_bus_objs[j];")
    return value


def patch_builder(value):
    start = value.index("def update_main():")
    end = value.index("def build_sdkconfig", start)
    # Applied by the upstream builder after MicroPython has been fetched.
    hook = '''def update_main():
    data = read_file('esp32', MAIN_PATH)
    anchor = '    gc_sweep_all();'
    if data.count(anchor) != 1 or 'mp_machine_hw_spi_bus_deinit_all();' in data:
        raise ValueError('unexpected pinned ESP32 soft-reset hook')
    data = data.replace(anchor, ''' + repr("""    // Stop native resources while their Python objects and callbacks exist.
    extern void mp_machine_hw_spi_bus_deinit_all(void);
    mp_machine_hw_spi_bus_deinit_all();
    #if SOC_LCD_RGB_SUPPORTED
    extern void mp_lcd_rgb_bus_deinit_all(void);
    mp_lcd_rgb_bus_deinit_all();
    #endif
    // Custom VM roots survive mp_init; clear both copies before the next VM.
    extern void *mp_lv_roots;
""" + LV_ROOT_RESET + "\n    gc_sweep_all();") + ''')
    write_file(MAIN_PATH, data)


'''
    return value[:start] + hook + value[end:]


def patch_lvgl_roots(value):
    return replace_once(value, """    static bool mp_lv_roots_initialized = false;
    if (!mp_lv_roots_initialized) {
        mp_lv_roots = MP_STATE_VM(mp_lv_roots) = m_new0(lv_global_t, 1);
        mp_lv_roots_initialized = true;
    }""", """    // The ESP32 reset hook explicitly clears this custom VM root.
    if (MP_STATE_VM(mp_lv_roots) == NULL) {
        MP_STATE_VM(mp_lv_roots) = m_new0(lv_global_t, 1);
    }
    mp_lv_roots = MP_STATE_VM(mp_lv_roots);""")


def install(source):
    transforms = {
        "micropy_updates/esp32/machine_hw_spi.c": patch_spi,
        "micropy_updates/esp32/machine_sdcard.c": patch_sd,
        "ext_mod/lcd_bus/esp32_src/rgb_bus.c": patch_rgb,
        "ext_mod/lcd_bus/esp32_src/rgb_bus_rotation.c": lambda value: replace_once(value,
            '        LCD_DEBUG_PRINT("rgb_bus_copy_task - STOPPED\\n")',
            '        LCD_DEBUG_PRINT("rgb_bus_copy_task - STOPPED\\n")\n'
            '        self->copy_task_handle = NULL;\n        vTaskDelete(NULL);'),
        "builder/esp32.py": patch_builder,
        "gen/lvgl_api_gen_mpy.py": patch_lvgl_roots,
        "gen/python_api_gen_mpy.py": patch_lvgl_roots,
    }
    # Validate every anchor first; mismatched source must not be partly patched.
    changes = {source / path: transform((source / path).read_text(encoding="utf-8"))
               for path, transform in transforms.items()}
    for path, value in changes.items():
        path.write_text(value, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    try:
        install(Path.cwd())
        raise SystemExit(container_prepare.main())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
