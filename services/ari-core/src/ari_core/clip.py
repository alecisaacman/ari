"""Compatibility shim for the documentation machine clip workflow."""

import sys

from .suits.documentation import clip as _impl


sys.modules[__name__] = _impl
