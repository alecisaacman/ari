"""Compatibility shim for the documentation machine storyboard workflow."""

import sys

from .suits.documentation import storyboard as _impl


sys.modules[__name__] = _impl
