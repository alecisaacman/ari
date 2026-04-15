"""Compatibility shim for ARI path configuration."""

import sys

from .core import paths as _impl


sys.modules[__name__] = _impl
