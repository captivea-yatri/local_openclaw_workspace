"""RPC error classification."""
from __future__ import annotations

_ACCESS_MARKERS = (
    "access error",
    "access denied",
    "access rights",
    "not allowed to access",
    "not allowed to create",
    "odoo.exceptions.accesserror",
    "doesn't have",
    "does not have",
    "top-secret",
    "create access",
    "write access",
    "read access",
    "rpc call on",
    "is not allowed",
)


def is_access_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _ACCESS_MARKERS)


class RpcError(RuntimeError):
    """Odoo RPC failure."""
