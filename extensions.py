"""
Shared Flask extensions — created here to avoid circular imports.
"""

from typing import TYPE_CHECKING

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)

# Typed re-export of current_app so route files can import it from here and get
# the correct OpenOMSApp type without triggering circular-import errors.
# At runtime this is identical to flask.current_app (the same proxy object).
if TYPE_CHECKING:
    import flask as _flask_mod

    from app import OpenOMSApp as _OpenOMSApp

    current_app: "_OpenOMSApp" = _flask_mod.current_app  # type: ignore[assignment]
else:
    from flask import current_app  # noqa: F401
