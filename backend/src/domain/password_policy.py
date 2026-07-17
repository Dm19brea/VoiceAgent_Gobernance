"""Password policy for dashboard credentials (first-run setup).

Single source of truth: server-side validation always wins over the
frontend's advisory mirror. Returns EVERY unmet rule so the caller can
surface a complete error list in one round trip, instead of one-at-a-time.
"""

import re

MIN_LENGTH = 12

_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def validate(password: str) -> list[str]:
    """Return the list of unmet policy rules; empty when compliant.

    Possible rule identifiers: ``min_length``, ``uppercase``, ``lowercase``,
    ``digit``, ``special``.
    """
    violations: list[str] = []
    if len(password) < MIN_LENGTH:
        violations.append("min_length")
    if not _UPPERCASE_RE.search(password):
        violations.append("uppercase")
    if not _LOWERCASE_RE.search(password):
        violations.append("lowercase")
    if not _DIGIT_RE.search(password):
        violations.append("digit")
    if not _SPECIAL_RE.search(password):
        violations.append("special")
    return violations
