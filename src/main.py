import sys


SEARCH_PATHS = [
    "/device",
    "/lib",
    "/",
    "/files/user",
]
for path in reversed(SEARCH_PATHS):
    if path not in sys.path:
        sys.path.insert(0, path)

import ujson
from tartlabutils import default_settings, diagnostics, ensure_layout, init_logs, load_settings, log, log_exception, \
    mark_app_failed, mark_boot_failed, mark_boot_route_started, save_settings
from tartlabutils.platform import get_platform, set_platform


def _recovery(reason):
    log("Entering recovery: " + reason)
    if "/recovery" not in sys.path:
        sys.path.insert(0, "/recovery")
    import recovery
    recovery.run(reason)


def _ensure_repos():
    from tartlabutils.state import REPOS_FILE, path_kind, write_json
    if path_kind(REPOS_FILE) == 0:
        # This is a compatibility fallback for an unprovisioned development board.
        # Releases must migrate or generate an installed version before promotion.
        write_json(REPOS_FILE, {
            "dbver": 1,
            "list": [{
                "name": "TartLab",
                "repo": "tdhoward/tartlab",
                "installed_version": "unknown",
            }],
        })


def _select_mode(settings, platform, start_launcher=None):
    start_mode = settings.get("STARTUP_MODE", "BUTTON")
    if start_mode == "RECOVERY":
        settings["STARTUP_MODE"] = "BUTTON"
        save_settings(settings)
        return "RECOVERY"
    if platform.capabilities.get("lvgl_ui", False):
        if start_mode != "BUTTON":
            settings["STARTUP_MODE"] = "BUTTON"
            save_settings(settings)
        if start_launcher is None:
            from tartlabutils.modern_launcher import run_startup_launcher
            start_launcher = run_startup_launcher
        selected = start_launcher(platform)
        if selected not in ("IDE", "APP"):
            raise ValueError("modern launcher returned an invalid route")
        return selected
    if start_mode == "BUTTON":
        return "IDE" if platform.ide_button_value() == 1 else "APP"
    settings["STARTUP_MODE"] = "BUTTON"
    save_settings(settings)
    return start_mode


def _restore_modern_brightness(platform, settings):
    if not platform.capabilities.get("lvgl_ui", False):
        return
    from tartlabutils.modern_power import restore_normal_brightness
    restore_normal_brightness(platform, settings)


def _start_ide_mode(platform, settings, start_ide):
    log("Starting IDE")
    _restore_modern_brightness(platform, settings)
    mark_boot_route_started("IDE")
    enter_ui_mode = getattr(platform, "enter_ui_mode", None)
    if enter_ui_mode is not None:
        enter_ui_mode()
    if start_ide is None:
        import ide
        start_ide = ide.main
    start_ide()


def _show_startup_error(platform, display, settings):
    try:
        _restore_modern_brightness(platform, settings)
    except Exception:
        try:
            if platform.capabilities.get("lvgl_ui", False):
                platform.set_brightness(1.0)
        except Exception:
            pass
    show_error = getattr(platform, "show_error", None)
    if show_error is not None:
        try:
            show_error()
        except Exception:
            pass
    elif display is not None:
        try:
            display.fill(0xF800)
        except Exception:
            pass


def run(platform=None, start_ide=None, start_app=None, start_recovery=None,
        start_launcher=None):
    display = None
    settings = None
    start_mode = None
    app_started = False
    try:
        ensure_layout()
        init_logs()
        log("System startup")
        log(ujson.dumps(diagnostics()))
        _ensure_repos()

        if platform is None:
            platform = get_platform()
        else:
            set_platform(platform)
        display = platform.display
        clear_display = getattr(platform, "clear_display", None)
        if clear_display is not None:
            clear_display()
        elif display is not None:
            display.fill(0)

        try:
            settings = load_settings()
        except OSError:
            settings = default_settings()
            log("No settings file found.")

        start_mode = _select_mode(settings, platform, start_launcher)
        if start_mode == "RECOVERY":
            (start_recovery or _recovery)("startup_mode")
        elif start_mode == "IDE":
            _start_ide_mode(platform, settings, start_ide)
        else:
            log("Starting APP")
            _restore_modern_brightness(platform, settings)
            enter_game_mode = getattr(platform, "enter_game_mode", None)
            if enter_game_mode is not None:
                enter_game_mode()
            if start_app is None:
                from tartlabutils.launcher import launch_selected_app
                start_app = launch_selected_app
            mark_boot_route_started("APP")
            app_started = True
            start_app()
    except Exception as error:
        try:
            log_exception(error)
        except Exception:
            sys.print_exception(error)
        if app_started:
            try:
                mark_app_failed(error)
            except Exception as state_error:
                try:
                    sys.print_exception(state_error)
                except Exception:
                    pass
            try:
                log("Selected APP failed; falling back to IDE")
                _start_ide_mode(platform, settings, start_ide)
                return
            except Exception as ide_error:
                try:
                    log_exception(ide_error)
                    mark_boot_failed(ide_error)
                except Exception:
                    sys.print_exception(ide_error)
                _show_startup_error(platform, display, settings)
                (start_recovery or _recovery)("startup_error")
                return
        try:
            mark_boot_failed(error)
        except Exception:
            try:
                sys.print_exception(error)
            except Exception:
                pass
        _show_startup_error(platform, display, settings)
        (start_recovery or _recovery)("startup_error")


run()
