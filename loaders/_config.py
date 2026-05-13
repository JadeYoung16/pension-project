"""Table loader configurations.

Each entry in TABLES describes how to load one raw_oncap table:
where its source files live, what table to load into, which columns
the source files contain, and which format module knows how to parse them.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TableConfig:
    source_dir: Path
    target_table: str
    source_columns: tuple[str, ...]
    format: str
    file_glob: str


employer_registry = TableConfig(
    source_dir=Path("data/synthetic/employer_registry"),
    target_table="raw_oncap.employer_registry",
    source_columns=(
        "employer_id", "business_number", "legal_name", "operating_name",
        "sector_category_code", "city", "postal_code", "employer_size_band",
        "employee_count", "enrolled_member_count", "pay_frequency",
        "participation_start_date", "plan_administrator_name",
        "plan_administrator_email", "status",
    ),
    format="csv",
    file_glob="*.csv",
)


call_log = TableConfig(
    source_dir=Path("data/synthetic/call_logs"),
    target_table="raw_oncap.call_log",
    source_columns=(
        "call_id", "member_id", "call_timestamp", "duration_seconds",
        "call_reason_category", "call_reason_subcategory", "resolution_code",
        "agent_id", "csat_score", "notes",
    ),
    format="csv",
    file_glob="*.csv",
)


transaction = TableConfig(
    source_dir=Path("data/synthetic/transactions"),
    target_table="raw_oncap.transaction",
    source_columns=(
        "transaction_id", "member_id", "employer_id", "pay_date",
        "pay_period_start", "pay_period_end", "pay_frequency_code",
        "pensionable_earnings", "member_contribution", "employer_contribution",
        "contribution_type", "buyback_reference_id", "transaction_status",
    ),
    format="pipe",
    file_glob="*.TXT",
)


TABLES: dict[str, TableConfig] = {
    "employer_registry": employer_registry,
    "call_log": call_log,
    "transaction": transaction,
}