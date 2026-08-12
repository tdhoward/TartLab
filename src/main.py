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
    mark_boot_failed, save_settings
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


def _select_mode(settings, platform):
    start_mode = settings.get("STARTUP_MODE", "BUTTON")
    if start_mode == "BUTTON":
        return "IDE" if platform.ide_button_value() == 1 else "APP"
    settings["STARTUP_MODE"] = "BUTTON"
    save_settings(settings)
    return start_mode


def run(platform=None, start_ide=None, start_app=None, start_recovery=None):
    display = None
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
        if display is not None:
            display.fill(0)

        try:
            settings = load_settings()
        except OSError:
            settings = default_settings()
            log("No settings file found.")

        start_mode = _select_mode(settings, platform)
        if start_mode == "RECOVERY":
            (start_recovery or _recovery)("startup_mode")
        elif start_mode == "IDE":
            log("Starting IDE")
            if start_ide is None:
                import ide
                start_ide = ide.main
            start_ide()
        else:
            log("Starting APP")
            if start_app is None:
                from tartlabutils.launcher import launch_selected_app
                start_app = launch_selected_app
            start_app()
    except Exception as error:
        try:
            log_exception(error)
            mark_boot_failed(error)
        except Exception:
            sys.print_exception(error)
        if display is not None:
            try:
                display.fill(0xF800)
            except Exception:
                pass
        (start_recovery or _recovery)("startup_error")


run()
