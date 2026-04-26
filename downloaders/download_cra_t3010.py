"""
Download CRA T3010 2023 Registered Charity Information Return data.

Source: Open Government Portal (open.canada.ca)
Dataset: 2023 List of Charities
Dataset ID: 05b3abd0-e70f-4b3b-a9c5-acc436bd15b6
License: Open Government Licence - Canada

Downloads 4 CSV files + 2 PDF data dictionaries needed for the pension project.
Also generates an Ontario-filtered identification file for downstream use.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

# Resolve output directory relative to this script's location
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw_external" / "cra_t3010_2023"

# Files to download. Key = local filename, Value = source URL.
DOWNLOADS = {
    # Core identification file — charity names, BN, addresses, category codes
    "ident_2023_update.csv":
        "https://open.canada.ca/data/dataset/05b3abd0-e70f-4b3b-a9c5-acc436bd15b6/"
        "resource/31a52caf-fa79-4ab3-bded-1ccc7b61c17f/download/ident_2023_update.csv",

    # Financial section A/B/C — basic revenue, expenses, employee count
    "financial_section_a_b_and_c_2023.csv":
        "https://open.canada.ca/data/dataset/05b3abd0-e70f-4b3b-a9c5-acc436bd15b6/"
        "resource/4cf7d8fa-221a-4934-a423-82dbeac7462b/download/"
        "financial_section_a_b_and_c_2023.csv",

    # Financial section D + Schedule 6 — detailed financials
    "financial_d_and_schedule_6_2023_updated.csv":
        "https://open.canada.ca/data/dataset/05b3abd0-e70f-4b3b-a9c5-acc436bd15b6/"
        "resource/0b9b4b01-5cb6-4981-b007-ae88f48cc799/download/"
        "financial_d_and_schedule_6_2023_updated.csv",

    # Schedule 3 — employee compensation distribution
    "schedule_3_compensation_2023.csv":
        "https://open.canada.ca/data/dataset/05b3abd0-e70f-4b3b-a9c5-acc436bd15b6/"
        "resource/aff519a3-a71e-4934-b052-dd29419be224/download/"
        "schedule_3_compensation_2023.csv",

    # Data dictionary (English) — field definitions
    "open-data-data-dictionary-v2.0_eng.pdf":
        "https://open.canada.ca/data/dataset/05b3abd0-e70f-4b3b-a9c5-acc436bd15b6/"
        "resource/19375510-2919-480c-8f8c-e8721d285b72/download/"
        "open-data-data-dictionary-v2.0_eng.pdf",

    # Codes list (English) — category / designation / province code mappings
    "codes_en.pdf":
        "https://open.canada.ca/data/dataset/05b3abd0-e70f-4b3b-a9c5-acc436bd15b6/"
        "resource/2a7e1d1f-83e8-4ad9-b57b-7506837fcbe5/download/codes_en.pdf",
}

# HTTP timeout in seconds for each request
TIMEOUT = 120

# Chunk size for streaming downloads (1 MB)
CHUNK_SIZE = 1024 * 1024


# ----------------------------------------------------------------------------
# Download logic
# ----------------------------------------------------------------------------

def download_file(url: str, dest: Path) -> int:
    """
    Stream a file from `url` to `dest`. Returns the number of bytes written.
    Overwrites existing files.
    """
    print(f"  Downloading from: {urlparse(url).path.split('/')[-1]}")
    with requests.get(url, stream=True, timeout=TIMEOUT) as response:
        response.raise_for_status()
        bytes_written = 0
        with dest.open("wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    bytes_written += len(chunk)
        return bytes_written


def format_bytes(n: int) -> str:
    """Human-readable file size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main() -> int:
    print("=" * 70)
    print("CRA T3010 2023 Data Download")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    # Step 1: download all files
    results = []
    for filename, url in DOWNLOADS.items():
        dest = OUTPUT_DIR / filename
        print(f"[{len(results) + 1}/{len(DOWNLOADS)}] {filename}")
        try:
            size = download_file(url, dest)
            results.append((filename, size, None))
            print(f"  OK ({format_bytes(size)})")
        except requests.HTTPError as e:
            results.append((filename, 0, str(e)))
            print(f"  FAILED: {e}")
        except requests.RequestException as e:
            results.append((filename, 0, str(e)))
            print(f"  FAILED: {e}")
        print()

    # Step 2: filter identification file to Ontario only
    ident_path = OUTPUT_DIR / "ident_2023_update.csv"
    ontario_path = OUTPUT_DIR / "ident_2023_ontario.csv"

    if ident_path.exists():
        print("Filtering identification file to Ontario charities...")
        # Read with explicit dtype to avoid mixed-type warnings.
        # BOM-aware encoding — the CSV starts with a UTF-8 BOM.
        df = pd.read_csv(ident_path, dtype=str, encoding="utf-8-sig")
        total = len(df)
        df_on = df[df["Province"] == "ON"].copy()
        df_on.to_csv(ontario_path, index=False, encoding="utf-8")
        print(f"  Total charities (all provinces): {total:,}")
        print(f"  Ontario charities:               {len(df_on):,}")
        print(f"  Saved to:                        {ontario_path.name}")
        print()

    # Step 3: print summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    for filename, size, error in results:
        status = f"OK ({format_bytes(size)})" if error is None else f"FAILED: {error}"
        print(f"  {filename:<55} {status}")

    failures = sum(1 for _, _, err in results if err is not None)
    if failures:
        print(f"\n{failures} file(s) failed to download.")
        return 1
    print("\nAll files downloaded successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
