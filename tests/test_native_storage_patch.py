"""Compile native lifetime regressions using the functions shipped by the patch."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware/lvgl-modern"))
import container_prepare_storage as patch


class NativeStoragePatchTests(unittest.TestCase):
    def test_repeated_or_missing_anchor_is_rejected(self):
        for source in ("missing", "anchor anchor"):
            with self.assertRaisesRegex(ValueError, "unexpected pinned"):
                patch.replace_once(source, "anchor", "replacement")

    def test_builder_inserts_cleanup_before_heap_sweep(self):
        original = "def update_main():\n    pass\n\ndef build_sdkconfig():\n    pass\n"
        generated = patch.patch_builder(original)
        writes = []
        namespace = {"MAIN_PATH": "main.c", "read_file": lambda *args: "    gc_sweep_all();",
                     "write_file": lambda path, value: writes.append(value)}
        exec(generated, namespace)
        namespace["update_main"]()
        value = writes[0]
        self.assertLess(value.index("mp_machine_hw_spi_bus_deinit_all();"), value.index("gc_sweep_all();"))
        self.assertLess(value.index("mp_lcd_rgb_bus_deinit_all();"), value.index("gc_sweep_all();"))
        self.assertLess(value.index(patch.LV_ROOT_RESET), value.index("gc_sweep_all();"))
        namespace["read_file"] = lambda *args: value
        with self.assertRaisesRegex(ValueError, "unexpected pinned ESP32"):
            namespace["update_main"]()

    def test_native_slot_and_finalizer_lifecycle(self):
        compiler = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
        if compiler is None:
            self.skipTest("requires a C compiler; run this test in the pinned build container")
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "storage_patch_under_test.h").write_text("\n".join((
                patch.SPI_REGISTER, patch.SPI_REMOVE, patch.SPI_DEINIT_ALL,
                patch.SD_SPI_RELEASE, patch.SD_DEINIT,
                "static void reset_lv_roots(void) {\n" + patch.LV_ROOT_RESET + "\n}",
                patch.patch_lvgl_roots("""void mp_lv_init_gc() {
    static bool mp_lv_roots_initialized = false;
    if (!mp_lv_roots_initialized) {
        mp_lv_roots = MP_STATE_VM(mp_lv_roots) = m_new0(lv_global_t, 1);
        mp_lv_roots_initialized = true;
    }
}"""))), encoding="utf-8")
            binary = work / "native-lifecycle"
            command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-g",
                       "-fsanitize=address,undefined", "-I", str(work),
                       str(ROOT / "tests/fixtures/native_storage_lifecycle.c"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn("native storage lifecycle: passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
