"""Compatibility shim for the documentation machine demo workflow."""

import sys

from .suits.documentation import demo as _impl


sys.modules[__name__] = _impl
