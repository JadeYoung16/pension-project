"""
Date utilities for ONCAP synthetic data generation.

Covers:
  - Business day arithmetic (Canadian calendar, excluding weekends and simple holidays)
  - Pay period calculations per frequency (BW / SM / MO / WK)
  - Age and service year calculations
  - Random date generation within ranges
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Iterator


# -----------------------------------------------------------------------------
# Canadian statutory holidays (simplified — federal + Ontario common)
# -----------------------------------------------------------------------------

def _ontario_holidays(year: int) -> set[date]:
    """Return a simplified set of Ontario statutory holidays for a year."""
    # Hard-coded fixed-date holidays for simplicity
    fixed = {
        date(year, 1, 1),    # New Year's Day
        date(year, 7, 1),    # Canada Day
        date(year, 12, 25),  # Christmas Day
        date(year, 12, 26),  # Boxing Day
    }
    # Family Day: 3rd Monday of February
    fixed.add(_nth_weekday(year, 2, 0, 3))       # Feb, Monday=0 in iso, but use python's weekday: Mon=0
    # Good Friday: approximated as Easter Sunday - 2 days (simplified: skipping exact Easter calc)
    # For synthetic project, exact holidays don't matter; we skip Good Friday/Easter
    # Victoria Day: Monday before May 25
    fixed.add(_monday_before(date(year, 5, 25)))
    # Civic Holiday: 1st Monday of August
    fixed.add(_nth_weekday(year, 8, 0, 1))
    # Labour Day: 1st Monday of September
    fixed.add(_nth_weekday(year, 9, 0, 1))
    # Thanksgiving: 2nd Monday of October
    fixed.add(_nth_weekday(year, 10, 0, 2))
    return fixed


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """
    Return the nth occurrence of weekday (0=Mon..6=Sun) in a month.
    """
    d = date(year, month, 1)
    # Find first occurrence of weekday
    offset = (weekday - d.weekday()) % 7
    d = d + timedelta(days=offset)
    # Advance by (n-1) weeks
    d = d + timedelta(days=7 * (n - 1))
    return d


def _monday_before(d: date) -> date:
    """Return the Monday on or before date d."""
    offset = d.weekday()  # 0=Mon, so this zeros out on Monday
    return d - timedelta(days=offset)


# -----------------------------------------------------------------------------
# Business day logic
# -----------------------------------------------------------------------------

def is_business_day(d: date) -> bool:
    """
    True if d is a weekday AND not a known Ontario holiday.
    """
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    holidays = _ontario_holidays(d.year)
    return d not in holidays


def add_business_days(d: date, n: int) -> date:
    """
    Add n business days to date d. n can be negative.

    >>> from datetime import date
    >>> add_business_days(date(2024, 1, 8), 5)       # Mon + 5 BD → next Mon
    datetime.date(2024, 1, 15)
    >>> add_business_days(date(2024, 1, 8), 14)      # Mon + 14 BD
    datetime.date(2024, 1, 26)
    """
    if n == 0:
        return d
    direction = 1 if n > 0 else -1
    days_remaining = abs(n)
    current = d
    while days_remaining > 0:
        current = current + timedelta(days=direction)
        if is_business_day(current):
            days_remaining -= 1
    return current


# -----------------------------------------------------------------------------
# Random date generation
# -----------------------------------------------------------------------------

def random_date_between(start: date, end: date, rng: random.Random) -> date:
    """
    Uniform random date in [start, end] inclusive.

    >>> import random
    >>> from datetime import date
    >>> d = random_date_between(date(2020, 1, 1), date(2020, 12, 31), random.Random(42))
    >>> date(2020, 1, 1) <= d <= date(2020, 12, 31)
    True
    """
    if start > end:
        raise ValueError(f"start {start} must be <= end {end}")
    days_span = (end - start).days
    return start + timedelta(days=rng.randint(0, days_span))


def random_business_day_between(
    start: date, end: date, rng: random.Random
) -> date:
    """Random business day in [start, end]."""
    for _ in range(100):
        candidate = random_date_between(start, end, rng)
        if is_business_day(candidate):
            return candidate
    # Fallback: if somehow we got unlucky, step back to a known BD
    current = end
    while not is_business_day(current) and current >= start:
        current = current - timedelta(days=1)
    return current


# -----------------------------------------------------------------------------
# Age / service calculations
# -----------------------------------------------------------------------------

def dob_from_age(target_age: int, as_of: date, rng: random.Random) -> date:
    """
    Generate a DOB that makes the person exactly `target_age` years old on
    `as_of`. Day-of-year is randomized.

    >>> import random
    >>> from datetime import date
    >>> dob = dob_from_age(42, date(2024, 1, 31), random.Random(42))
    >>> 41 <= (date(2024, 1, 31).year - dob.year) <= 42
    True
    """
    # Birth year candidate
    birth_year = as_of.year - target_age
    # Random day of year
    days_in_year = 365
    if birth_year % 4 == 0 and (birth_year % 100 != 0 or birth_year % 400 == 0):
        days_in_year = 366
    day_of_year = rng.randint(1, days_in_year)
    dob = date(birth_year, 1, 1) + timedelta(days=day_of_year - 1)
    # Adjust: if dob is after as_of's month/day in the birth year, person is actually
    # one year younger than target. Subtract a year if that's the case.
    has_had_birthday = (dob.month, dob.day) <= (as_of.month, as_of.day)
    if not has_had_birthday:
        # Handle Feb 29 edge case: when going back 1 year, Feb 29 may not exist
        try:
            dob = date(birth_year - 1, dob.month, dob.day)
        except ValueError:
            # Feb 29 → Feb 28 in non-leap year
            dob = date(birth_year - 1, 2, 28)
    return dob


def age_at(dob: date, as_of: date) -> int:
    """Calculate age in years on a given date."""
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years


def years_between(d1: date, d2: date) -> float:
    """Fractional years between two dates (d2 - d1)."""
    return (d2 - d1).days / 365.25


def add_years(d: date, n: int) -> date:
    """
    Add n years to d. Handles Feb 29 -> Feb 28 on non-leap years.

    >>> from datetime import date
    >>> add_years(date(1992, 7, 15), 65)
    datetime.date(2057, 7, 15)
    """
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        # Feb 29 in non-leap year
        return d.replace(year=d.year + n, day=28)


# -----------------------------------------------------------------------------
# Pay period generation
# -----------------------------------------------------------------------------

def pay_dates_in_range(
    start: date,
    end: date,
    frequency: str,
) -> Iterator[date]:
    """
    Yield pay dates between start and end (inclusive) for a given frequency.

    Anchor logic:
      BW: Fridays every 2 weeks, anchored on first Friday of 2020
      SM: 15th and last day of each month
      MO: Last day of each month
      WK: Fridays every week

    >>> from datetime import date
    >>> list(pay_dates_in_range(date(2024, 1, 1), date(2024, 1, 31), 'SM'))
    [datetime.date(2024, 1, 15), datetime.date(2024, 1, 31)]
    """
    if frequency == "BW":
        # Anchor: first Friday of 2020 (2020-01-03), biweekly thereafter
        anchor = date(2020, 1, 3)
        # Step backward until we find a candidate <= start
        candidate = anchor
        while candidate > start:
            candidate = candidate - timedelta(days=14)
        while candidate < start:
            candidate = candidate + timedelta(days=14)
        while candidate <= end:
            yield candidate
            candidate = candidate + timedelta(days=14)

    elif frequency == "WK":
        # Every Friday
        candidate = start
        while candidate.weekday() != 4:  # Friday=4
            candidate = candidate + timedelta(days=1)
            if candidate > end:
                return
        while candidate <= end:
            yield candidate
            candidate = candidate + timedelta(days=7)

    elif frequency == "SM":
        # 15th and last day of each month
        current = date(start.year, start.month, 1)
        while current <= end:
            fifteenth = current.replace(day=15)
            if start <= fifteenth <= end:
                yield fifteenth
            # Last day of month
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
            last_day = next_month - timedelta(days=1)
            if start <= last_day <= end:
                yield last_day
            current = next_month

    elif frequency == "MO":
        current = date(start.year, start.month, 1)
        while current <= end:
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
            last_day = next_month - timedelta(days=1)
            if start <= last_day <= end:
                yield last_day
            current = next_month

    else:
        raise ValueError(f"Unknown pay frequency: {frequency}")


def pay_period_for_pay_date(
    pay_date: date,
    frequency: str,
) -> tuple[date, date]:
    """
    Given a pay date and frequency, return (period_start, period_end).

    Convention: The pay date is the END of the pay period (or slightly after).
    Pay period = the work time being compensated.

    >>> from datetime import date
    >>> pay_period_for_pay_date(date(2024, 1, 12), 'BW')
    (datetime.date(2023, 12, 30), datetime.date(2024, 1, 12))
    >>> pay_period_for_pay_date(date(2024, 1, 15), 'SM')
    (datetime.date(2024, 1, 1), datetime.date(2024, 1, 15))
    """
    if frequency == "BW":
        return (pay_date - timedelta(days=13), pay_date)
    if frequency == "WK":
        return (pay_date - timedelta(days=6), pay_date)
    if frequency == "SM":
        if pay_date.day == 15:
            return (pay_date.replace(day=1), pay_date)
        # end of month pay date: 16th to end
        return (pay_date.replace(day=16), pay_date)
    if frequency == "MO":
        return (pay_date.replace(day=1), pay_date)
    raise ValueError(f"Unknown pay frequency: {frequency}")
