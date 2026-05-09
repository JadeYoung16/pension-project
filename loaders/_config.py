"""Table loader configurations.

Each entry in TABLES describes how to load one raw_oncap table:
where its CSVs live, what table to load into, and the column order.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TableConfig:
    source_dir: Path
    target_table: str
    columns: tuple[str, ...]


employer_registry = TableConfig(
    source_dir=Path("data/synthetic/employer_registry"),
    target_table="raw_oncap.employer_registry",
    columns=(
        "employer_id", "business_number", "legal_name", "operating_name",
    "sector_category_code", "city", "postal_code", "employer_size_band",
    "employee_count", "enrolled_member_count", "pay_frequency",
    "participation_start_date", "plan_administrator_name",
    "plan_administrator_email", "status",
    "_source_file", "_row_num",
    ),
)


call_log = TableConfig(
    source_dir=Path("data/synthetic/call_logs"),
    target_table="raw_oncap.call_log",
    columns=(
         "call_id", "member_id", "call_timestamp", "duration_seconds",
    "call_reason_category", "call_reason_subcategory", "resolution_code",
    "agent_id", "csat_score", "notes",
    "_source_file", "_row_num",
    ),
)


TABLES: dict[str, TableConfig] = {
    "employer_registry": employer_registry,
    "call_log": call_log,
}