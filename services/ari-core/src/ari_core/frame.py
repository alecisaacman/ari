"""Compatibility shim for the documentation machine frame workflow."""

import sys

from .suits.documentation import frame as _impl


sys.modules[__name__] = _impl
