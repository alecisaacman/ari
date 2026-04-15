"""Compatibility shim for the documentation machine video workflow."""

import sys

from .suits.documentation import video as _impl


sys.modules[__name__] = _impl
