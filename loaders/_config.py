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
    field_positions: tuple[tuple[int, int], ...] | None = None
    field_types: tuple[str, ...] | None = None
    # Only fixed_width tables set these. csv/pipe leave both None.


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


member_census = TableConfig(
    source_dir=Path("data/synthetic/member_census"),
    target_table="raw_oncap.member_census",
    source_columns=(
        "member_id",
        "sin_last_4",
        "first_name",
        "middle_initial",
        "last_name",
        "dob",
        "sex_code",
        "marital_status_code",
        "language_preference",
        "street_address",
        "city",
        "province",
        "postal_code",
        "phone",
        "email",
        "employer_id",
        "hire_date",
        "enrollment_date",
        "termination_date",
        "status_code",
        "employment_type",
        "annual_salary",
        "salary_band_code",
        "job_category",
        "credited_service_years",
        "eligible_buyback_service",
        "last_buyback_leave_end_date",
        "normal_retirement_date",
        "accrued_annual_pension",
        "beneficiary_on_file",
        "member_since_date",
        "last_statement_date",
        "record_status",
    ),
    field_positions=(
        (4, 13),      # member_id
        (14, 17),     # sin_last_4
        (18, 42),     # first_name
        (43, 43),     # middle_initial
        (44, 73),     # last_name
        (74, 81),     # dob
        (82, 82),     # sex_code
        (83, 83),     # marital_status_code
        (84, 85),     # language_preference
        (86, 125),    # street_address
        (126, 150),   # city
        (151, 152),   # province
        (153, 159),   # postal_code
        (160, 171),   # phone
        (172, 231),   # email
        (232, 241),   # employer_id
        (242, 249),   # hire_date
        (250, 257),   # enrollment_date
        (258, 265),   # termination_date
        (266, 266),   # status_code
        (267, 268),   # employment_type
        (269, 278),   # annual_salary
        (279, 280),   # salary_band_code
        (281, 283),   # job_category
        (284, 288),   # credited_service_years
        (289, 293),   # eligible_buyback_service
        (294, 301),   # last_buyback_leave_end_date
        (302, 309),   # normal_retirement_date
        (310, 319),   # accrued_annual_pension
        (320, 320),   # beneficiary_on_file
        (321, 328),   # member_since_date
        (329, 336),   # last_statement_date
        (400, 400),   # record_status (FILLER 337-399 skipped)
    ),
    field_types=(
        "text",       # member_id (keep paddings like 0000000010)
        "text",       # sin_last_4
        "text",       # first_name
        "text",       # middle_initial
        "text",       # last_name
        "date",       # dob
        "text",       # sex_code
        "text",       # marital_status_code
        "text",       # language_preference
        "text",       # street_address
        "text",       # city
        "text",       # province
        "text",       # postal_code
        "text",       # phone
        "text",       # email
        "text",       # employer_id
        "date",       # hire_date
        "date",       # enrollment_date
        "date",       # termination_date
        "text",       # status_code
        "text",       # employment_type
        "numeric",    # annual_salary
        "text",       # salary_band_code
        "text",       # job_category
        "numeric",    # credited_service_years
        "numeric",    # eligible_buyback_service
        "date",       # last_buyback_leave_end_date
        "date",       # normal_retirement_date
        "numeric",    # accrued_annual_pension
        "text",       # beneficiary_on_file
        "date",       # member_since_date
        "date",       # last_statement_date
        "text",       # record_status
    ),
    format="fixed_width",
    file_glob="*.DAT",
)


TABLES: dict[str, TableConfig] = {
    "employer_registry": employer_registry,
    "call_log": call_log,
    "transaction": transaction,
    "member_census": member_census,
}