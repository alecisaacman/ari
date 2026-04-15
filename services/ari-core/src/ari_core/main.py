"""Canonical ARI CLI shim."""

import sys

from .modules.networking import cli as _impl


sys.modules[__name__] = _impl
