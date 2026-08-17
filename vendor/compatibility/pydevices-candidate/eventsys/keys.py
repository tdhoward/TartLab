# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy ``eventsys.keys.Keys`` facade over current module-level key codes."""

import keys as _keys


class Keys:
    keyname = staticmethod(_keys.keyname)
    key = staticmethod(_keys.key)
    modname = staticmethod(_keys.modname)
    mod = staticmethod(_keys.mod)


for _name in dir(_keys):
    if _name.startswith("K_") or _name.startswith("KMOD_"):
        setattr(Keys, _name, getattr(_keys, _name))

del _name
