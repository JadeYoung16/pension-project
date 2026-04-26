"""
ID generation utilities.

All IDs in ONCAP synthetic data follow deterministic, zero-padded, prefixed
formats so that:
  1. IDs are sortable lexicographically and numerically
  2. IDs are visually distinguishable by type (EMP vs EVT vs TXN)
  3. Generation is reproducible given a seed

ID formats:
  member_id       : 10-digit zero-padded number      e.g. "0000428150"
  employer_id     : "EMP" + 7 digits                 e.g. "EMP0000042"
  event_id        : "EVT" + 17-char alphanumeric     e.g. "EVT01H9G3K8X4Z7N2M1"
  transaction_id  : "TXN" + 13-digit number          e.g. "TXN0000015672834"
  call_id         : "CALL" + YYYYMMDD + 6-digit seq  e.g. "CALL20240115001234"
  attendance_id   : "SEM" + YYYYMM + 7-digit seq     e.g. "SEM2023010000001"
  email_event_id  : "EML" + YYYYMMDD + 6-digit seq   e.g. "EML20240108000015"
"""

from __future__ import annotations

import random
import string
from datetime import date


# -----------------------------------------------------------------------------
# Member / Employer IDs
# -----------------------------------------------------------------------------

def generate_member_id(seq: int) -> str:
    """
    Generate a member ID from a sequence number.

    Args:
        seq: 1-based sequence (1..99_999_999_99)

    Returns:
        10-digit zero-padded string.

    >>> generate_member_id(1)
    '0000000001'
    >>> generate_member_id(428150)
    '0000428150'
    """
    if seq < 1 or seq > 9_999_999_999:
        raise ValueError(f"Member sequence out of range: {seq}")
    return f"{seq:010d}"


def generate_employer_id(seq: int) -> str:
    """
    Generate an employer ID.

    >>> generate_employer_id(1)
    'EMP0000001'
    >>> generate_employer_id(42)
    'EMP0000042'
    """
    if seq < 1 or seq > 9_999_999:
        raise ValueError(f"Employer sequence out of range: {seq}")
    return f"EMP{seq:07d}"


# -----------------------------------------------------------------------------
# Event IDs (ULID-like)
# -----------------------------------------------------------------------------

# Crockford Base32 alphabet (excludes I, L, O, U to avoid ambiguity)
_BASE32_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_event_id(rng: random.Random) -> str:
    """
    Generate an event ID: "EVT" + 17-character Crockford Base32.

    This mimics ULID format without requiring the ulid package. We use a
    seeded random generator to ensure reproducibility.

    Args:
        rng: A seeded random.Random instance

    Returns:
        20-character string. First 3 chars = 'EVT', followed by
        17 Crockford Base32 characters (e.g., 'EVT71HFE865V215DE1CT').
    """
    suffix = "".join(rng.choice(_BASE32_ALPHABET) for _ in range(17))
    return f"EVT{suffix}"


# -----------------------------------------------------------------------------
# Transaction / Call / Email / Seminar IDs
# -----------------------------------------------------------------------------

def generate_transaction_id(seq: int) -> str:
    """
    Generate a transaction ID.

    >>> generate_transaction_id(1)
    'TXN0000000000001'
    >>> generate_transaction_id(15672834)
    'TXN0000015672834'
    """
    return f"TXN{seq:013d}"


def generate_call_id(d: date, seq: int) -> str:
    """
    Generate a call ID: CALL + YYYYMMDD + 6-digit sequence.

    >>> from datetime import date
    >>> generate_call_id(date(2024, 1, 15), 1234)
    'CALL20240115001234'
    """
    return f"CALL{d.strftime('%Y%m%d')}{seq:06d}"


def generate_seminar_attendance_id(year: int, seq: int) -> str:
    """
    Generate a seminar attendance ID: SEM + YYYYMM + 7-digit sequence.

    >>> generate_seminar_attendance_id(2023, 1)
    'SEM2023010000001'
    """
    # Use January as default month for yearly seminar file
    return f"SEM{year}01{seq:07d}"


def generate_email_event_id(d: date, seq: int) -> str:
    """
    Generate an email event ID: EML + YYYYMMDD + 6-digit sequence.

    >>> from datetime import date
    >>> generate_email_event_id(date(2024, 1, 8), 15)
    'EML20240108000015'
    """
    return f"EML{d.strftime('%Y%m%d')}{seq:06d}"


def generate_session_id(rng: random.Random) -> str:
    """
    Generate a portal session ID: 'sess_' + 12 hex chars.

    >>> import random
    >>> generate_session_id(random.Random(42))[:5]
    'sess_'
    """
    hex_chars = "".join(rng.choice(string.hexdigits.lower()[:16]) for _ in range(12))
    return f"sess_{hex_chars}"


def generate_ip_hash(rng: random.Random) -> str:
    """
    Generate a synthetic hashed IP representation.

    Format: 'sha256:' + 16 hex chars (truncated for file size)

    >>> import random
    >>> generate_ip_hash(random.Random(42))[:7]
    'sha256:'
    """
    hex_chars = "".join(rng.choice(string.hexdigits.lower()[:16]) for _ in range(16))
    return f"sha256:{hex_chars}"


# -----------------------------------------------------------------------------
# SIN last 4 (synthetic, for demo masking)
# -----------------------------------------------------------------------------

def generate_sin_last_4(member_id: str) -> str:
    """
    Derive a deterministic "SIN last 4" from a member ID.
    Uses modular arithmetic so the same member_id always produces the same
    synthetic SIN-last-4. This is NOT a real SIN; it's for simulating the
    masked SIN field in extracts.

    >>> a = generate_sin_last_4('0000428150')
    >>> b = generate_sin_last_4('0000428150')
    >>> a == b
    True
    >>> len(a)
    4
    """
    digits_only = "".join(c for c in member_id if c.isdigit())
    value = int(digits_only) if digits_only else 0
    # Simple deterministic mapping: use (value * 7 + 3) mod 10000
    last_4 = (value * 7 + 3) % 10000
    return f"{last_4:04d}"