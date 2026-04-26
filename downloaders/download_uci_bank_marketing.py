"""
Download UCI Bank Marketing dataset.

Source: UCI Machine Learning Repository
Dataset: Bank Marketing (Moro et al., 2014)
URL: https://archive.ics.uci.edu/dataset/222/bank+marketing
License: CC BY 4.0

Downloads the zipped archive, extracts the full dataset (bank-additional-full.csv)
and the data dictionary (bank-additional-names.txt). Discards smaller/older
variants we don't need.

Role in project:
- Benchmark dataset for buyback propensity modelling methodology
- Reference for campaign contact feature engineering (campaign, pdays, previous,
  poutcome) — direct analogs exist in pension outreach campaigns
"""

import io
import sys
import zipfile
from pathlib import Path

import requests

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw_external" / "uci_bank_marketing"

# UCI's "bank-additional" archive (the newer, richer version of the dataset).
# This is the canonical URL from the UCI ML Repository.
SOURCE_URL = "https://archive.ics.uci.edu/static/public/222/bank+marketing.zip"

# Files we want to keep from the nested archives. Everything else is discarded.
KEEP_FILES = {
    "bank-additional-full.csv",    # 41,188 rows - main dataset
    "bank-additional-names.txt",   # Data dictionary
}

TIMEOUT = 120


# ----------------------------------------------------------------------------
# Download logic
# ----------------------------------------------------------------------------

def format_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def extract_nested_zip(outer_zip: zipfile.ZipFile, output_dir: Path) -> list[tuple[str, int]]:
    """
    UCI's archive is a zip containing another zip (bank-additional.zip).
    Walk the structure, extract only files we care about, return summary.
    """
    extracted = []
    for name in outer_zip.namelist():
        # Look for the inner bank-additional.zip
        if name.endswith("bank-additional.zip"):
            print(f"  Found inner archive: {name}")
            with outer_zip.open(name) as inner_file:
                inner_bytes = inner_file.read()
            with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner_zip:
                for inner_name in inner_zip.namelist():
                    basename = Path(inner_name).name
                    if basename in KEEP_FILES:
                        dest = output_dir / basename
                        with inner_zip.open(inner_name) as src, dest.open("wb") as dst:
                            data = src.read()
                            dst.write(data)
                        extracted.append((basename, len(data)))
    return extracted


def main() -> int:
    print("=" * 70)
    print("UCI Bank Marketing Dataset Download")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Source URL:       {SOURCE_URL}")
    print()

    # Step 1: download the outer zip to memory
    print("Downloading archive...")
    try:
        response = requests.get(SOURCE_URL, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"FAILED: {e}")
        return 1

    archive_bytes = response.content
    print(f"  Downloaded {format_bytes(len(archive_bytes))}")
    print()

    # Step 2: unzip and extract only the files we need
    print("Extracting...")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as outer_zip:
            extracted = extract_nested_zip(outer_zip, OUTPUT_DIR)
    except zipfile.BadZipFile as e:
        print(f"FAILED to parse zip: {e}")
        return 1

    if not extracted:
        print("  WARNING: No files matched. Archive structure may have changed.")
        print("  Outer archive contents:")
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as outer_zip:
            for name in outer_zip.namelist():
                print(f"    {name}")
        return 1

    print()

    # Step 3: summary + quick sanity check on the CSV
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    for filename, size in extracted:
        print(f"  {filename:<40} {format_bytes(size)}")

    csv_path = OUTPUT_DIR / "bank-additional-full.csv"
    if csv_path.exists():
        # UCI file uses ';' as delimiter — common gotcha
        with csv_path.open("r", encoding="utf-8") as f:
            header = f.readline()
            row_count = sum(1 for _ in f)
        print(f"\n  Rows in bank-additional-full.csv: {row_count:,}")
        print(f"  Delimiter: ';' (not ',')")
        print(f"  Columns:   {len(header.split(';'))}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())