"""Compatibility shim for the documentation machine recording planner."""

import sys

from .suits.documentation import record as _impl


sys.modules[__name__] = _impl
