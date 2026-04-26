"""
Messiness injection utilities.

Simulates real-world imperfections in pension admin system extracts:
  - Missing optional values (email, phone)
  - Encoding issues (non-ASCII names)
  - Format drift (different date formats)
  - Trailing whitespace
  - Timezone inconsistency
  - Malformed records

All functions take a random.Random instance and a probability, returning either
the "clean" value or the "messy" value based on the roll.
"""

from __future__ import annotations

import random
from datetime import date, datetime


# -----------------------------------------------------------------------------
# Missing value injection
# -----------------------------------------------------------------------------

def maybe_null(value, rng: random.Random, probability: float):
    """
    Return None with given probability, else return value unchanged.

    Args:
        value: The original value
        rng: Seeded random.Random
        probability: Float in [0.0, 1.0] — chance of returning None

    >>> import random
    >>> r = random.Random(42)
    >>> maybe_null("hello", r, 0.0)
    'hello'
    >>> maybe_null("hello", r, 1.0) is None
    True
    """
    if probability <= 0:
        return value
    if probability >= 1:
        return None
    return None if rng.random() < probability else value


# -----------------------------------------------------------------------------
# Encoding messiness
# -----------------------------------------------------------------------------

# French Canadian common accented substitutions
_ASCII_TO_ACCENTED = {
    "e": "é",
    "a": "à",
    "o": "ô",
    "c": "ç",
    "u": "û",
}


def maybe_add_accents(name: str, rng: random.Random, probability: float) -> str:
    """
    Occasionally substitute ASCII letters in a name with accented characters,
    simulating French-Canadian names or data entry issues with diacritics.

    >>> import random
    >>> r = random.Random(42)
    >>> result = maybe_add_accents("Francois", r, 1.0)
    >>> result != "Francois"
    True
    """
    if rng.random() >= probability:
        return name
    # Pick one letter position to accent
    candidates = [(i, c) for i, c in enumerate(name.lower()) if c in _ASCII_TO_ACCENTED]
    if not candidates:
        return name
    pos, char = rng.choice(candidates)
    # Keep original case
    new_char = _ASCII_TO_ACCENTED[char]
    if name[pos].isupper():
        new_char = new_char.upper()
    return name[:pos] + new_char + name[pos + 1:]


# -----------------------------------------------------------------------------
# Whitespace messiness
# -----------------------------------------------------------------------------

def maybe_add_trailing_whitespace(
    text: str, rng: random.Random, probability: float
) -> str:
    """
    Occasionally add 1-3 trailing spaces to a string value.

    >>> import random
    >>> r = random.Random(42)
    >>> result = maybe_add_trailing_whitespace("ABC", r, 1.0)
    >>> result.endswith(" ")
    True
    """
    if rng.random() >= probability:
        return text
    n_spaces = rng.randint(1, 3)
    return text + " " * n_spaces


# -----------------------------------------------------------------------------
# Date format drift
# -----------------------------------------------------------------------------

def maybe_date_format_drift(
    d: date,
    rng: random.Random,
    probability: float,
    default_format: str = "%Y%m%d",
) -> str:
    """
    Occasionally render a date in a non-standard format, simulating legacy
    system migration artifacts where some records use DD/MM/YYYY.

    >>> import random
    >>> from datetime import date
    >>> r = random.Random(42)
    >>> maybe_date_format_drift(date(2024, 1, 15), r, 0.0)
    '20240115'
    """
    if rng.random() >= probability:
        return d.strftime(default_format)
    # Drift to DD/MM/YYYY
    return d.strftime("%d/%m/%Y")


# -----------------------------------------------------------------------------
# Timezone messiness
# -----------------------------------------------------------------------------

def format_timestamp_with_timezone_drift(
    dt: datetime,
    rng: random.Random,
    utc_probability: float,
) -> str:
    """
    Format a datetime as ISO-8601. With given probability, render in UTC
    instead of local (EST) time. Simulates feeds coming from different systems
    with inconsistent timezone conventions.

    Args:
        dt: A naive datetime representing local Eastern time
        rng: Random source
        utc_probability: Probability of rendering in UTC

    Returns:
        ISO-8601 timestamp string

    >>> import random
    >>> from datetime import datetime
    >>> format_timestamp_with_timezone_drift(
    ...     datetime(2024, 1, 15, 14, 23, 47), random.Random(42), 0.0
    ... )
    '2024-01-15T14:23:47-05:00'
    """
    if rng.random() < utc_probability:
        # Convert EST to UTC by adding 5 hours (ignoring DST for simplicity)
        from datetime import timedelta
        utc_dt = dt + timedelta(hours=5)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "-05:00"


# -----------------------------------------------------------------------------
# Garbage text injection
# -----------------------------------------------------------------------------

_GARBAGE_NOTES = [
    "asdf",
    "n/a",
    "see attached",
    "????",
    "called back 3x",
    "needs followup",
    "CUSTOMER UPSET",
    ".",
    "-",
]


def maybe_garbage_notes(
    clean_note: str, rng: random.Random, probability: float
) -> str:
    """
    With given probability, replace clean note with a nonsense/garbage note.
    Simulates real call center / admin notes which are often unhelpful.
    """
    if rng.random() < probability:
        return rng.choice(_GARBAGE_NOTES)
    return clean_note


# -----------------------------------------------------------------------------
# Weighted rolling utility
# -----------------------------------------------------------------------------

def roll(probability: float, rng: random.Random) -> bool:
    """
    Shorthand: return True with given probability.

    >>> import random
    >>> roll(0.0, random.Random(42))
    False
    >>> roll(1.0, random.Random(42))
    True
    """
    return rng.random() < probability