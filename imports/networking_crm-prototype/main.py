"""Legacy `networking-crm` CLI shim for the ARI networking module."""

import sys

from .modules.networking import cli as _impl


sys.modules[__name__] = _impl
