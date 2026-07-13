"""Shell command safety utilities for the server management layer."""

import re
import shlex

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9/][a-zA-Z0-9._\-/@]*$")

# systemd OnCalendar expressions use only these characters (digits, letters for
# weekday names/keywords, and the separators * - : , / . ~ and spaces). The
# allowlist crucially forbids newlines, so a value interpolated into a systemd
# unit file cannot inject additional directives (e.g. a rogue [Service] block).
_SAFE_CALENDAR_RE = re.compile(r"^[A-Za-z0-9 *,:/.~-]{1,128}$")


def validate_name(value: str, label: str = "name") -> str:
    """Validate a name contains only safe characters.

    Returns the value if valid, raises ValueError if not.
    """
    if not value or not _SAFE_NAME_RE.match(value):
        raise ValueError(f"Invalid {label}: {value!r} contains unsafe characters")
    return value


def validate_calendar(value: str, label: str = "calendar expression") -> str:
    """Validate a systemd OnCalendar / cron-style expression.

    Restricts to the characters systemd OnCalendar expressions use and forbids
    newlines, so the value can be safely written into a systemd unit file
    without risking unit-directive injection.

    Returns the value if valid, raises ValueError if not.
    """
    if not value or not _SAFE_CALENDAR_RE.match(value):
        raise ValueError(f"Invalid {label}: {value!r} contains unsafe characters")
    return value


def safe_quote(value: str) -> str:
    """Shell-quote a value for safe interpolation."""
    return shlex.quote(value)
