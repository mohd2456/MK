"""Shell command safety utilities for the server management layer."""

import re
import shlex

_SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9/][a-zA-Z0-9._\-/@ ]*$')


def validate_name(value: str, label: str = "name") -> str:
    """Validate a name contains only safe characters.

    Returns the value if valid, raises ValueError if not.
    """
    if not value or not _SAFE_NAME_RE.match(value):
        raise ValueError(f"Invalid {label}: {value!r} contains unsafe characters")
    return value


def safe_quote(value: str) -> str:
    """Shell-quote a value for safe interpolation."""
    return shlex.quote(value)
