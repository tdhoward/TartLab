"""Prepare the pinned ESP-IDF container for lvgl_micropython's merger."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


LCD_BUS_DMA_API = r'''
#ifdef ESP_IDF_VERSION
static mp_obj_t mp_lcd_bus_allocate_buffer(mp_obj_t size_obj, mp_obj_t caps_obj)
{
    mp_int_t size = mp_obj_get_int(size_obj);
    uint32_t caps = (uint32_t)mp_obj_get_int(caps_obj);
    if (size <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer size must be positive"));
    }
    void *buffer = heap_caps_calloc(1, (size_t)size, caps);
    if (buffer == NULL) {
        mp_raise_msg_varg(
            &mp_type_MemoryError,
            MP_ERROR_TEXT("Not enough memory available (%d)"),
            size
        );
    }
    mp_obj_array_t *view = MP_OBJ_TO_PTR(
        mp_obj_new_memoryview(BYTEARRAY_TYPECODE, (size_t)size, buffer)
    );
    view->typecode |= 0x80;
    return MP_OBJ_FROM_PTR(view);
}
static MP_DEFINE_CONST_FUN_OBJ_2(
    mp_lcd_bus_allocate_buffer_obj, mp_lcd_bus_allocate_buffer
);

static mp_obj_t mp_lcd_bus_free_buffer(mp_obj_t buffer_obj)
{
    if (!mp_obj_is_type(buffer_obj, &mp_type_memoryview)) {
        mp_raise_TypeError(MP_ERROR_TEXT("buffer must be a memoryview"));
    }
    mp_obj_array_t *view = MP_OBJ_TO_PTR(buffer_obj);
    if (view->items != NULL) {
        heap_caps_free(view->items);
        view->items = NULL;
        view->len = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(
    mp_lcd_bus_free_buffer_obj, mp_lcd_bus_free_buffer
);
#endif
'''


def _replace_once(value: str, old: str, new: str, description: str) -> str:
    if value.count(old) != 1:
        raise ValueError(f"unexpected pinned lcd_bus source: {description}")
    return value.replace(old, new, 1)


def install_dma_buffer_api(source: Path) -> None:
    """Add independent capability-bound buffers to the pinned lcd_bus module."""
    path = source / "ext_mod/lcd_bus/modlcd_bus.c"
    value = path.read_text(encoding="utf-8")
    function_anchor = (
        "MP_DEFINE_CONST_FUN_OBJ_KW(mp_lcd_bus_allocate_framebuffer_obj, 3, "
        "mp_lcd_bus_allocate_framebuffer);\n"
    )
    value = _replace_once(
        value,
        function_anchor,
        function_anchor + "\n" + LCD_BUS_DMA_API + "\n",
        "allocate-framebuffer function anchor",
    )
    globals_anchor = (
        "    { MP_ROM_QSTR(MP_QSTR__pump_main_thread),  "
        "MP_ROM_PTR(&mp_lcd_bus__pump_main_thread_obj)       },\n"
    )
    globals_replacement = globals_anchor + (
        "\n    #ifdef ESP_IDF_VERSION\n"
        "        { MP_ROM_QSTR(MP_QSTR_allocate_buffer),     "
        "MP_ROM_PTR(&mp_lcd_bus_allocate_buffer_obj)         },\n"
        "        { MP_ROM_QSTR(MP_QSTR_free_buffer),         "
        "MP_ROM_PTR(&mp_lcd_bus_free_buffer_obj)             },\n"
        "    #endif\n"
    )
    value = _replace_once(
        value,
        globals_anchor,
        globals_replacement,
        "module-globals anchor",
    )
    path.write_text(value, encoding="utf-8", newline="\n")


def prepare_python_environment(source: Path, target: Path) -> None:
    """Expose the official container's Python environment at the expected path."""
    if not source.is_dir():
        raise ValueError(f"ESP-IDF Python environment not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if target.resolve() != source.resolve():
            raise ValueError(f"unexpected existing Python environment link: {target}")
        return
    if target.exists():
        raise ValueError(f"Python environment target already exists: {target}")
    os.symlink(source, target, target_is_directory=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-env", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a build command is required after --")

    expected = Path.home() / ".espressif/python_env"
    prepare_python_environment(args.python_env, expected)
    install_dma_buffer_api(Path.cwd())
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
