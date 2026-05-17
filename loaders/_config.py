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
    sum_columns: tuple[str, ...] = ()
    # Only pipe tables with T-trailer sums set this (e.g. transaction).
    encoding: str = "utf-8"
    # File encoding. Defaults to utf-8 for ONCAP-generated synthetic files.
    # CRA T3010 files use utf-8-sig (BOM-prefixed); set explicitly per-table.
    # Currently consumed only by csv_format; other format modules accept but
    # ignore the parameter for interface symmetry.
    source_header: tuple[str, ...] | None = None
    # Optional source-file header strings, position-aligned with source_columns.
    # Set this when the source file's column names aren't valid snake_case SQL
    # identifiers (e.g. CRA T3010 has "Legal Name" / "BN" / "Sub Category").
    # source_columns then holds the DDL identifiers and csv_format validates
    # the file header against source_header. Leave None for OnCap tables whose
    # generators already emit snake_case headers.


employer_registry = TableConfig(
    source_dir=Path("data/synthetic/employer_registry"),
    target_table="raw_oncap.employer_registry",
    source_columns=(
        "employer_id", "business_number", "legal_name", "operating_name",
        "sector_category_code", "city", "postal_code", "employer_size_band",
        "employee_count", "enrolled_member_count", "pay_frequency",
        "participation_start_date", "plan_administrator_name",
        "plan_administrator_email", "status",
        # Acquisition funnel (Week 4)
        "acquisition_channel", "prospect_source", "first_contact_date",
    ),
    format="csv",
    file_glob="ONCAP001_EMPLOYER_REGISTRY_*.csv",
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
    sum_columns=("member_contribution", "employer_contribution"),
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


life_event = TableConfig(
    source_dir=Path("data/synthetic/life_events"),
    target_table="raw_oncap.life_event",
    source_columns=(
        "event_id",
        "member_id",
        "employer_id",
        "event_type_code",
        "event_date",
        "event_timestamp",
        "buyback_category_code",
        "buyback_service_years",
        "leave_end_date",
        "months_since_eligibility",
        "is_within_window",
        "is_open_option",
        "member_cost",
        "employer_cost",
        "total_cost",
        "payment_method",
        "installment_months",
        "event_status",
        "channel_code",
        "notes",
    ),
    format="pipe",
    file_glob="*.TXT",
)

seminar_attendance = TableConfig(
    source_dir=Path("data/synthetic/seminar_attendance"),
    target_table="raw_oncap.seminar_attendance",
    source_columns=(
        "attendance_id",
        "member_id",
        "seminar_date",
        "seminar_location",
        "seminar_topic",
        "attendance_format",
        "registration_date",
        "attended_flag",
    ),
    format="csv",
    file_glob="*.csv",
)


email_engagement = TableConfig(
    source_dir=Path("data/synthetic/email_engagement"),
    target_table="raw_oncap.email_engagement",
    source_columns=(
        "event_id",
        "member_id",
        "campaign_id",
        "campaign_name",
        "event_type",
        "event_timestamp",
        "link_url_clicked",
    ),
    format="csv",
    file_glob="*.csv",
)

portal_event = TableConfig(
    source_dir=Path("data/synthetic/portal_events"),
    target_table="raw_oncap.portal_event",
    source_columns=(
        "event_id",
        "member_id",
        "event_timestamp",
        "event_type",
        "session_id",
        "ip_hash",
        "user_agent",
        "page_path",
        "referrer",
        "event_properties",
    ),
    format="jsonl",
    file_glob="*.jsonl",
)


# -----------------------------------------------------------------------------
# raw_external — third-party reference data (CRA T3010)
# -----------------------------------------------------------------------------
# source_columns hold the snake_case DDL identifiers; source_header holds the
# literal header strings as they appear in the CSV file. csv_format validates
# against source_header but yields rows in source_columns order (they're the
# same physical order — just different label conventions).
#
# schedule_3 has numeric column names ("300", "370", ...) which ARE kept as-is
# in both DDL and source — there's no business-friendly snake_case equivalent
# at this layer. Queries against raw_external.t3010_schedule3 will need to
# quote these (e.g. SELECT "300" FROM ...); business-friendly renames happen
# in stg_external (Week 5).
#
# Both files use utf-8-sig (UTF-8 with BOM); set encoding explicitly.

t3010_ident = TableConfig(
    source_dir=Path("data/raw_external/cra_t3010_2023"),
    target_table="raw_external.t3010_ident",
    source_columns=(
        "bn",
        "category",
        "sub_category",
        "designation",
        "legal_name",
        "account_name",
        "address_line_1",
        "address_line_2",
        "city",
        "province",
        "postal_code",
        "country",
    ),
    source_header=(
        "BN",
        "Category",
        "Sub Category",
        "Designation",
        "Legal Name",
        "Account Name",
        "Address Line 1",
        "Address Line 2",
        "City",
        "Province",
        "Postal Code",
        "Country",
    ),
    format="csv",
    file_glob="ident_2023_update.csv",
    encoding="utf-8-sig",
)


t3010_schedule3 = TableConfig(
    source_dir=Path("data/raw_external/cra_t3010_2023"),
    target_table="raw_external.t3010_schedule3",
    source_columns=(
        "bn",
        "fpe",
        "form_id",
        "300", "305", "310", "315", "320", "325",
        "330", "335", "340", "345",
        "370", "380", "390",
    ),
    source_header=(
        "BN",
        "FPE",
        "Form ID",
        "300", "305", "310", "315", "320", "325",
        "330", "335", "340", "345",
        "370", "380", "390",
    ),
    format="csv",
    file_glob="schedule_3_compensation_2023.csv",
    encoding="utf-8-sig",
)


TABLES: dict[str, TableConfig] = {
    "employer_registry": employer_registry,
    "call_log": call_log,
    "transaction": transaction,
    "member_census": member_census,
    "portal_event": portal_event,
    "life_event": life_event,
    "seminar_attendance": seminar_attendance,
    "email_engagement": email_engagement,
    # raw_external (Week 4)
    "t3010_ident": t3010_ident,
    "t3010_schedule3": t3010_schedule3,
}