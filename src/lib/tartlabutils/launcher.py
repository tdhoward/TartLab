import sys

from .bootstate import mark_boot_healthy
from .miscutils import log
from .state import get_selected_app


_health_timer = None
_HEALTH_TIMER_IDS = (-1, 3)


def _healthy_callback(unused):
    global _health_timer
    try:
        committed = mark_boot_healthy("APP")
        log("HEALTHY mode=APP update_committed=%s" % committed)
    finally:
        if _health_timer is not None:
            try:
                _health_timer.deinit()
            except Exception:
                pass
            _health_timer = None


def _timer_callback(unused):
    try:
        import micropython
        micropython.schedule(_healthy_callback, 0)
    except Exception:
        _healthy_callback(0)


def _arm_health_check():
    global _health_timer
    from machine import Timer
    for timer_id in _HEALTH_TIMER_IDS:
        timer = None
        try:
            timer = Timer(timer_id)
            timer.init(
                period=3000, mode=Timer.ONE_SHOT, callback=_timer_callback)
            _health_timer = timer
            return
        except Exception:
            if timer is not None:
                try:
                    timer.deinit()
                except Exception:
                    pass
    _health_timer = None


def _cancel_health_check():
    global _health_timer
    if _health_timer is not None:
        try:
            _health_timer.deinit()
        finally:
            _health_timer = None


def launch_selected_app():
    filename = get_selected_app()
    module_name = filename[:-3].replace("/", ".")
    _arm_health_check()
    try:
        __import__(module_name)
    except Exception:
        _cancel_health_check()
        raise
    if _health_timer is None:
        _healthy_callback(0)
    return sys.modules.get(module_name)
