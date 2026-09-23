"""Destructive interpreter diagnostic: caller MUST hard-reset afterward.

Invoke on a clean LVGL interpreter, without a display or task handler. Never
force-clear native state: record whether a caught callback exception poisons it.
"""

import json
import time
import lvgl as lv

if not lv.is_initialized():
    lv.init()
_exception_probe = {'before': lv._nesting.value, 'caught': False}
if _exception_probe['before'] != 0:
    raise RuntimeError('Callback probe requires a clean hard restart')


def _exception_callback(timer):
    raise ValueError('intentional-lvgl-callback-probe')


_exception_timer = lv.timer_create(_exception_callback, 1, None)
lv.tick_inc(10)
try:
    lv.timer_handler()
except ValueError as error:
    if str(error) != 'intentional-lvgl-callback-probe':
        raise
    _exception_probe['caught'] = True
_exception_probe['after'] = lv._nesting.value
print(json.dumps(_exception_probe))
