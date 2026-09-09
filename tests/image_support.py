"""Load the real image package without importing device startup services."""

import importlib
from pathlib import Path
import sys
import types
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("tartlabutils")
package.__path__ = [str(ROOT / "src/lib/tartlabutils")]
with patch.dict(sys.modules, {"tartlabutils": package}):
    images = importlib.import_module("tartlabutils.images")
    qoi = importlib.import_module("tartlabutils.images.qoi")
    ts16 = importlib.import_module("tartlabutils.images.ts16")
    sprites = importlib.import_module("tartlabutils.sprites")
    IMAGE_MODULES = {name: module for name, module in sys.modules.items()
                     if name == "tartlabutils" or
                     name.startswith("tartlabutils.images") or
                     name == "tartlabutils.sprites"}
