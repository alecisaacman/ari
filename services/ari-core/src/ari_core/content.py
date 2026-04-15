"""Compatibility shim for the documentation machine content workflow."""

import sys

from .suits.documentation import content as _impl


sys.modules[__name__] = _impl
