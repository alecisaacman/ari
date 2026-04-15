"""Compatibility shim for the ARI networking module database layer."""

import sys

from .modules.networking import db as _impl


sys.modules[__name__] = _impl
