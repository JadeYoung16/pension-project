"""
Seeded Faker instance pool.

All generators get Faker instances from this module to guarantee that:
  1. Seeding is consistent (Faker instance seeded once, deterministic)
  2. Locale is correct for Canadian data (en_CA with French support)
  3. No cross-generator pollution (each generator gets its own instance)
"""

from __future__ import annotations

from faker import Faker


def get_faker(seed: int, locale: str = "en_CA") -> Faker:
    """
    Return a seeded Faker instance.

    Args:
        seed: Seed value for reproducibility
        locale: Faker locale (default 'en_CA' for Canadian data)

    Returns:
        Seeded Faker instance
    """
    fake = Faker(locale)
    fake.seed_instance(seed)
    return fake


def get_multilingual_faker(seed: int) -> Faker:
    """
    Return a multi-locale Faker (English and French Canadian).
    Useful when generating names that may be either English or French.
    """
    fake = Faker(["en_CA", "fr_CA"])
    fake.seed_instance(seed)
    return fake