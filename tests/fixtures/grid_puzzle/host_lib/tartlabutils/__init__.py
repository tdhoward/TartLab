"""Unix test package shell: load real shared modules without device startup.

grid_puzzle_compat.py redirects __path__ to src/lib/tartlabutils immediately.
This supplies no implementations or device mocks; MicroPython cannot construct
the empty module object used by the CPython tests' image_support helper.
"""
