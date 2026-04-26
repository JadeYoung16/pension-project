# ONCAP Pension Plan — Record Layout Specifications

**Document version**: 1.0
**Prepared for**: Week 1 — Generator implementations + downstream pipeline parsers
**Status**: Authoritative file format spec

> This document is the contract between synthetic data generators (upstream
> simulators) and downstream ingestion pipelines. It mimics real pension admin
> system "File Specification" / "Record Layout" documents that data vendors
> provide to their consumers.

---

## File 1: Employer Registry

### File identification

| Property            | Value                                             |
|---------------------|---------------------------------------------------|
| File type           | Employer master snapshot                          |
| Filename pattern    | `ONCAP001_EMPLOYER_REGISTRY_YYYYMMDD.csv`         |
| Character encoding  | UTF-8                                             |
| Line terminator     | LF (`\n`)                                         |
| Delimiter           | Comma                                             |
| Quoting             | Fields containing commas or quotes: double-quoted |
| First line          | Header row with column names                      |

### Columns

| # | Column                    | Type    | Req | Description                                       |
|---|---------------------------|---------|-----|---------------------------------------------------|
| 1 | `employer_id`             | string  | Y   | `EMP` + 7-digit zero-padded (e.g., `EMP0000001`) |
| 2 | `business_number`         | string  | Y   | CRA Business Number from T3010                    |
| 3 | `legal_name`              | string  | Y   | From T3010 `Legal Name`                           |
| 4 | `operating_name`          | string  | Y   | From T3010 `Account Name`                         |
| 5 | `sector_category_code`    | string  | Y   | T3010 category code (numeric, 3 digits)           |
| 6 | `city`                    | string  | Y   | Ontario city                                      |
| 7 | `postal_code`             | string  | Y   | Format `K1A0B1` (no space)                        |
| 8 | `employer_size_band`      | string  | Y   | `LARGE` / `MEDIUM` / `SMALL` / `MICRO`            |
| 9 | `employee_count`          | integer | Y   | Total employees (from T3010 or inferred)          |
| 10 | `enrolled_member_count`  | integer | Y   | Members enrolled in ONCAP from this employer      |
| 11 | `pay_frequency`          | string  | Y   | `BW` / `SM` / `MO` / `WK`                         |
| 12 | `participation_start_date` | date   | Y   | ISO `YYYY-MM-DD`, when joined ONCAP               |
| 13 | `plan_administrator_name` | string | Y   | HR contact name                                   |
| 14 | `plan_administrator_email` | string | Y  | HR contact email                                  |
| 15 | `status`                 | string  | Y   | `ACTIVE` / `WITHDRAWN`                            |

### Example

```
employer_id,business_number,legal_name,operating_name,sector_category_code,city,postal_code,employer_size_band,employee_count,enrolled_member_count,pay_frequency,participation_start_date,plan_administrator_name,plan_administrator_email,status
EMP0000001,123456789RR0001,"Ontario Community Services Network","ONCS Network",120,Toronto,M5V3A8,LARGE,850,520,BW,2019-04-15,Sarah Thompson,sarah.thompson@oncs.ca,ACTIVE
```

---

## File 2: Member Census

### File identification

| Property            | Value                                                |
|---------------------|------------------------------------------------------|
| File type           | Monthly member census snapshot                       |
| Filename pattern    | `ONCAP001_MEMBER_CENSUS_YYYYMMDD.DAT`                |
| Character encoding  | ISO-8859-1 (Latin-1, supports French characters)     |
| Line terminator     | CRLF (`\r\n`) — simulates mainframe origin           |
| Record length       | **400 characters** (fixed)                           |
| Total records       | 50,000 data + 1 header + 1 trailer = 50,002 lines    |

### Record structure overview

| Code  | Record type      | Count per file |
|-------|------------------|----------------|
| `HDR` | Header (first)   | 1              |
| `001` | Member detail    | 50,000         |
| `TRL` | Trailer (last)   | 1              |

### Header Record (positions 1-400)

| From | To  | Len | Field             | Type | Description                   | Example                              |
|------|-----|-----|-------------------|------|-------------------------------|--------------------------------------|
| 1    | 3   | 3   | RECORD_TYPE       | char | Always `HDR`                  | `HDR`                                |
| 4    | 12  | 9   | PLAN_CODE         | char | Plan ID, space-padded         | `ONCAP001 `                          |
| 13   | 20  | 8   | AS_OF_DATE        | char | YYYYMMDD                      | `20240131`                           |
| 21   | 27  | 7   | RECORD_COUNT      | num  | Data records, zero-padded     | `0050000`                            |
| 28   | 41  | 14  | CREATE_TIMESTAMP  | char | YYYYMMDDHHMMSS                | `20240205023015`                     |
| 42   | 44  | 3   | LAYOUT_VERSION    | char | Spec version                  | `003`                                |
| 45   | 74  | 30  | SYSTEM_ID         | char | Source system identifier      | `ONCAP_ADMIN_SYSTEM_V10       `      |
| 75   | 400 | 326 | FILLER            | char | Spaces                        | `                            …`      |

### Member Detail Record (positions 1-400)

| From | To  | Len | Field                         | Type | Req | Description                                       |
|------|-----|-----|-------------------------------|------|-----|---------------------------------------------------|
| 1    | 3   | 3   | RECORD_TYPE                   | char | Y   | Always `001`                                      |
| 4    | 13  | 10  | MEMBER_ID                     | num  | Y   | Zero-padded unique ID                             |
| 14   | 17  | 4   | SIN_LAST_4                    | num  | N   | Last 4 digits of synthetic SIN                    |
| 18   | 42  | 25  | FIRST_NAME                    | char | Y   | Left-aligned, space-padded                        |
| 43   | 43  | 1   | MIDDLE_INITIAL                | char | N   | Single letter or space                            |
| 44   | 73  | 30  | LAST_NAME                     | char | Y   | Left-aligned, space-padded                        |
| 74   | 81  | 8   | DOB                           | date | Y   | YYYYMMDD                                          |
| 82   | 82  | 1   | SEX_CODE                      | char | Y   | `1` = Male, `2` = Female, `9` = Unknown           |
| 83   | 83  | 1   | MARITAL_STATUS_CODE           | char | Y   | `S`/`M`/`D`/`W`/`U`                               |
| 84   | 85  | 2   | LANGUAGE_PREFERENCE           | char | Y   | `EN` / `FR`                                       |
| 86   | 125 | 40  | STREET_ADDRESS                | char | Y   | Left-aligned                                      |
| 126  | 150 | 25  | CITY                          | char | Y   | Left-aligned                                      |
| 151  | 152 | 2   | PROVINCE                      | char | Y   | Always `ON`                                       |
| 153  | 159 | 7   | POSTAL_CODE                   | char | Y   | Format `K1A0B1` (no space)                        |
| 160  | 171 | 12  | PHONE                         | char | N   | 10-digit string or spaces                         |
| 172  | 231 | 60  | EMAIL                         | char | N   | Left-aligned lowercase, or spaces                 |
| 232  | 241 | 10  | EMPLOYER_ID                   | char | Y   | FK to employer registry                           |
| 242  | 249 | 8   | HIRE_DATE                     | date | Y   | YYYYMMDD                                          |
| 250  | 257 | 8   | ENROLLMENT_DATE               | date | Y   | YYYYMMDD                                          |
| 258  | 265 | 8   | TERMINATION_DATE              | date | N   | YYYYMMDD or 8 spaces                              |
| 266  | 266 | 1   | STATUS_CODE                   | char | Y   | `A`/`D`/`R`/`T`/`S`                               |
| 267  | 268 | 2   | EMPLOYMENT_TYPE               | char | Y   | `FT` / `PT`                                       |
| 269  | 278 | 10  | ANNUAL_SALARY                 | num  | Y   | Implicit 2 decimals: `0005512345` = $55,123.45    |
| 279  | 280 | 2   | SALARY_BAND_CODE              | char | Y   | `EN`/`MD`/`SR`/`EX`                               |
| 281  | 283 | 3   | JOB_CATEGORY                  | char | Y   | `SVC`/`ADM`/`MGR`/`EXE`/`PRF`                     |
| 284  | 288 | 5   | CREDITED_SERVICE_YEARS        | num  | Y   | Implicit 2 decimals: `00725` = 7.25 years         |
| 289  | 293 | 5   | ELIGIBLE_BUYBACK_SERVICE      | num  | N   | Same format, or 5 spaces                          |
| 294  | 301 | 8   | LAST_BUYBACK_LEAVE_END_DATE   | date | N   | YYYYMMDD or 8 spaces                              |
| 302  | 309 | 8   | NORMAL_RETIREMENT_DATE        | date | Y   | YYYYMMDD (= DOB + 65 years)                       |
| 310  | 319 | 10  | ACCRUED_ANNUAL_PENSION        | num  | Y   | Implicit 2 decimals                               |
| 320  | 320 | 1   | BENEFICIARY_ON_FILE           | char | Y   | `Y` / `N`                                         |
| 321  | 328 | 8   | MEMBER_SINCE_DATE             | date | Y   | YYYYMMDD                                          |
| 329  | 336 | 8   | LAST_STATEMENT_DATE           | date | N   | YYYYMMDD or 8 spaces                              |
| 337  | 399 | 63  | FILLER                        | char | -   | Spaces                                            |
| 400  | 400 | 1   | RECORD_STATUS                 | char | Y   | `A` = active record, `P` = purged                 |

### Trailer Record (positions 1-400)

| From | To  | Len | Field                  | Description                                        |
|------|-----|-----|------------------------|----------------------------------------------------|
| 1    | 3   | 3   | RECORD_TYPE            | `TRL`                                              |
| 4    | 11  | 8   | AS_OF_DATE             | YYYYMMDD (matches header)                          |
| 12   | 18  | 7   | TOTAL_RECORD_COUNT     | Zero-padded                                        |
| 19   | 25  | 7   | ACTIVE_COUNT           | Count of status = `A`                              |
| 26   | 32  | 7   | DEFERRED_COUNT         | Count of status = `D`                              |
| 33   | 39  | 7   | RETIRED_COUNT          | Count of status = `R`                              |
| 40   | 46  | 7   | TERMINATED_COUNT       | Count of status = `T`                              |
| 47   | 53  | 7   | SURVIVOR_COUNT         | Count of status = `S`                              |
| 54   | 67  | 14  | SUM_ANNUAL_SALARY      | Sum of salaries, implicit 2 decimals               |
| 68   | 81  | 14  | SUM_ACCRUED_PENSION    | Sum of pensions, implicit 2 decimals               |
| 82   | 113 | 32  | CHECKSUM               | SHA256 hex (first 32 chars) of concat member_ids   |
| 114  | 400 | 287 | FILLER                 | Spaces                                             |

### Business rules encoded in generation

1. `MEMBER_ID` is 10 digits zero-padded, sequential `0000000001`–`0000050000`
2. `SIN_LAST_4` = `hash(member_id) mod 10000`, 4-digit string
3. `DOB` generated to match age distribution per `STATUS_CODE`
4. `HIRE_DATE` ≤ `ENROLLMENT_DATE` (waiting period typically 0–90 days)
5. `ENROLLMENT_DATE` ≥ `2014-01-01` (plan effective date)
6. `CREDITED_SERVICE_YEARS` capped at 10 (plan age)
7. `ELIGIBLE_BUYBACK_SERVICE` > 0 only for ~30% of active members
8. `STATUS_CODE` distribution: A=55%, D=20%, R=15%, T=8%, S=2%
9. `TERMINATION_DATE` populated if status ∈ {D, R, T, S}
10. `NORMAL_RETIREMENT_DATE` always = DOB + 65 years

### Messiness injection

| Messiness type                    | Rate                          | Notes                          |
|-----------------------------------|-------------------------------|--------------------------------|
| `EMAIL` missing                   | 15% overall, 35% for 60+      | Older demographic              |
| `MIDDLE_INITIAL` missing          | 60%                           | Most people don't have one     |
| `MARITAL_STATUS_CODE` = `U`       | 3%                            | Unknown                        |
| `SEX_CODE` = `9`                  | 2%                            | Legacy data gap                |
| `PHONE` missing                   | 8%                            |                                |
| Trailing whitespace inconsistency | 5% of rows                    | Parser must strip              |
| Non-ASCII in name                 | ~1%                           | e.g., `Müller`, `François`     |

---

## File 3: Transactions

### File identification

| Property          | Value                                           |
|-------------------|-------------------------------------------------|
| File type         | Per pay-cycle contribution transactions         |
| Filename pattern  | `ONCAP001_TXN_PAYDATE_YYYYMMDD.TXT`             |
| Encoding          | UTF-8                                           |
| Line terminator   | LF (`\n`)                                       |
| Delimiter         | Pipe `|`                                        |
| Structure         | Header line + data lines + trailer line         |

### Header line

```
H|ONCAP001|TXN|<PAY_DATE>|<RECORD_COUNT>|<CREATE_TIMESTAMP>
```

Example:

```
H|ONCAP001|TXN|2024-01-12|17250|20240112T230015Z
```

### Data columns (one line per transaction)

| # | Column                  | Type         | Req | Description                              |
|---|-------------------------|--------------|-----|------------------------------------------|
| 1 | `transaction_id`        | string(16)   | Y   | Unique transaction ID                    |
| 2 | `member_id`             | string       | Y   | 10-digit zero-padded                     |
| 3 | `employer_id`           | string       | Y   | `EMP` + 7 digits                         |
| 4 | `pay_date`              | date         | Y   | ISO `YYYY-MM-DD`                         |
| 5 | `pay_period_start`      | date         | N   | ISO `YYYY-MM-DD`                         |
| 6 | `pay_period_end`        | date         | Y   | ISO `YYYY-MM-DD`                         |
| 7 | `pay_frequency_code`    | char(2)      | Y   | `BW`/`SM`/`MO`/`WK`                      |
| 8 | `pensionable_earnings`  | decimal(10,2)| Y   | Dollar amount                            |
| 9 | `member_contribution`   | decimal(10,2)| Y   | = earnings × 3%                          |
| 10 | `employer_contribution`| decimal(10,2)| Y   | = earnings × 3%                          |
| 11 | `contribution_type`    | char(3)      | Y   | `REG` = regular, `BBK` = buyback install |
| 12 | `buyback_reference_id` | string       | N   | FK to life event (null for REG)          |
| 13 | `transaction_status`   | char(2)      | Y   | `OK` / `RJ` (rejected)                   |

### Trailer line

```
T|ONCAP001|<RECORD_COUNT>|<SUM_MEMBER_CONTRIB>|<SUM_EMPLOYER_CONTRIB>
```

Example:

```
T|ONCAP001|17250|1316428.50|1316428.50
```

### Messiness

| Messiness                             | Rate                           |
|---------------------------------------|--------------------------------|
| `transaction_status` = `RJ`           | 0.5%                           |
| Missing `pay_period_start`            | 2%                             |
| Rounding drift (penny off)            | 0.2%                           |
| Duplicate `transaction_id`            | 1 per month / file group       |

---

## File 4: Life Events (includes Buyback chain)

### File identification

| Property          | Value                                       |
|-------------------|---------------------------------------------|
| File type         | Monthly life events batch                   |
| Filename pattern  | `ONCAP001_LIFE_EVENTS_YYYYMM.TXT`           |
| Encoding          | UTF-8                                       |
| Line terminator   | LF (`\n`)                                   |
| Delimiter         | Pipe `|`                                    |
| First line        | Column names                                |

### Column header

```
event_id|member_id|employer_id|event_type_code|event_date|event_timestamp|buyback_category_code|buyback_service_years|leave_end_date|months_since_eligibility|is_within_window|is_open_option|member_cost|employer_cost|total_cost|payment_method|installment_months|event_status|channel_code|notes
```

### Columns

| # | Column                    | Type          | Req | Description                                       |
|---|---------------------------|---------------|-----|---------------------------------------------------|
| 1 | `event_id`                | string        | Y   | `EVT` + 17-char ULID-like identifier              |
| 2 | `member_id`               | string        | Y   | 10-digit zero-padded                              |
| 3 | `employer_id`             | string        | Y   | `EMP` + 7 digits                                  |
| 4 | `event_type_code`         | enum          | Y   | See event types table below                       |
| 5 | `event_date`              | date          | Y   | ISO `YYYY-MM-DD`                                  |
| 6 | `event_timestamp`         | datetime      | Y   | ISO-8601 with TZ                                  |
| 7 | `buyback_category_code`   | enum          | N   | `ML`/`LOA`/`PST`/`PEP`/`PTT` (null if non-buyback)|
| 8 | `buyback_service_years`   | decimal(5,2)  | N   | Service being purchased                           |
| 9 | `leave_end_date`          | date          | N   | ISO, when eligibility clock started               |
| 10 | `months_since_eligibility`| integer      | N   | Months from leave_end to event_date               |
| 11 | `is_within_window`       | char(1)       | N   | `Y` / `N`                                         |
| 12 | `is_open_option`         | char(1)       | N   | `Y` / `N` (= NOT is_within_window)                |
| 13 | `member_cost`            | decimal(12,2) | N   | Member's share in CAD                             |
| 14 | `employer_cost`          | decimal(12,2) | N   | 0 if open option                                  |
| 15 | `total_cost`             | decimal(12,2) | N   | = member_cost + employer_cost                     |
| 16 | `payment_method`         | enum          | N   | `LUMP_SUM` / `INSTALLMENT`                        |
| 17 | `installment_months`     | integer       | N   | 12/24/36/60/123 or null                           |
| 18 | `event_status`           | enum          | Y   | SUBMITTED/QUOTED/APPROVED/REJECTED/COMPLETED/CANCELLED |
| 19 | `channel_code`           | enum          | Y   | `PORTAL`/`MAIL`/`ADVISOR`/`PHONE`/`SYSTEM`        |
| 20 | `notes`                  | string(200)   | N   | Free text                                         |

### Event types

| Code                   | Description                        | Generation rule                           |
|------------------------|------------------------------------|-------------------------------------------|
| `BBK_APP`              | Buyback application submitted      | Member-initiated; starts the chain        |
| `BBK_QUOTE`            | Quote issued by ONCAP              | +5 business days after APP                |
| `BBK_APPROVED`         | Application approved               | +14 business days after APP (5% rejected) |
| `BBK_COMPLETE`         | Payment complete                   | Immediate (LUMP) or after final install   |
| `BBK_CANCELLED`        | Member cancelled                   | 3% of chains exit here                    |
| `BBK_INSTALLMENT_PAY`  | Single installment payment         | Generated monthly during install period   |
| `BENE_UPD`             | Beneficiary update                 | Independent, ~40 / month                  |
| `MARITAL`              | Marital status change              | Independent, ~15 / month                  |
| `ADDR_CHG`             | Address change                     | Independent, ~100 / month                 |

### Status transitions (buyback event chain)

```
Normal chain (85% of cases):
  BBK_APP (SUBMITTED)
    → BBK_QUOTE (QUOTED, +5 BD)
    → BBK_APPROVED (APPROVED, +14 BD)
    → BBK_COMPLETE (COMPLETED)
       └─ If LUMP_SUM: 1 row, event_date = APPROVED date
       └─ If INSTALLMENT: N rows of BBK_INSTALLMENT_PAY over months

Rejected chain (5% of cases):
  BBK_APP → BBK_QUOTE → BBK_APPROVED (REJECTED, reason in notes)

Cancelled chain (3% of cases):
  BBK_APP → BBK_CANCELLED (member changes mind after quote)

Abandoned chain (7% of cases):
  BBK_APP → BBK_QUOTE → (silence, no completion)
```

### Buyback cost calculation

**Within 24-month window** (`is_within_window = Y`):

```
member_cost   = buyback_service_years × salary_at_leave × 0.03
employer_cost = buyback_service_years × salary_at_leave × 0.03
total_cost    = member_cost + employer_cost
```

**Open option** (`is_within_window = N`):

```
base_cost     = buyback_service_years × current_salary × 0.06
premium       = uniform(0.40, 0.60)
member_cost   = base_cost × (1 + premium)
employer_cost = 0.00
total_cost    = member_cost
```

### Buyback propensity model (probability member submits)

```
base_prob = 0.05
if age_band in [45-60]:             base_prob += 0.30
if salary_band in ['SR','EX']:      base_prob += 0.25
if attended_seminar:                base_prob += 0.40
if portal_login_count > 5:          base_prob += 0.20
if sex == 'F':                      base_prob += 0.05
final_prob = min(base_prob, 0.95)
```

### Example rows

Buyback event chain:

```
EVT01H9G3K8X4Z7N2M1|0000428150|EMP0000042|BBK_APP|2024-01-08|2024-01-08T10:15:32-05:00|ML|0.75|2023-06-30|6|Y|N|1231.50|1231.50|2463.00|LUMP_SUM||SUBMITTED|PORTAL|
EVT01H9G8P2K4Z7N2M2|0000428150|EMP0000042|BBK_QUOTE|2024-01-15|2024-01-15T14:30:00-05:00|ML|0.75|2023-06-30|6|Y|N|1231.50|1231.50|2463.00|LUMP_SUM||QUOTED|SYSTEM|
EVT01H9HG5N8Q7K2M1|0000428150|EMP0000042|BBK_APPROVED|2024-01-24|2024-01-24T09:00:00-05:00|ML|0.75|2023-06-30|6|Y|N|1231.50|1231.50|2463.00|LUMP_SUM||APPROVED|SYSTEM|
EVT01H9HK2M8Q7K4N1|0000428150|EMP0000042|BBK_COMPLETE|2024-01-25|2024-01-25T11:45:12-05:00|ML|0.75|2023-06-30|6|Y|N|1231.50|1231.50|2463.00|LUMP_SUM||COMPLETED|SYSTEM|
```

Non-buyback event:

```
EVT01H9M4P8X7Z3N1K5|0000125789|EMP0000123|BENE_UPD|2024-01-10|2024-01-10T16:22:05-05:00|||||||||||COMPLETED|PORTAL|Beneficiary updated to spouse
```

---

## File 5: Portal Events (JSONL)

### File identification

| Property          | Value                                           |
|-------------------|-------------------------------------------------|
| File type         | Daily portal event log                          |
| Filename pattern  | `ONCAP001_PORTAL_EVENTS_YYYYMMDD.jsonl`         |
| Encoding          | UTF-8                                           |
| Line terminator   | LF (`\n`)                                       |
| Structure         | One JSON object per line, no wrapping array     |

### JSON schema (per line)

```json
{
  "event_id": "evt_01H9G3K8X4Z7N2M1",
  "member_id": "0000428150",
  "event_timestamp": "2024-01-15T14:23:47-05:00",
  "event_type": "portal_login",
  "session_id": "sess_8d4f3b92c1a7",
  "ip_hash": "sha256:a4f9...",
  "user_agent": "Mozilla/5.0 (Macintosh...)",
  "page_path": "/dashboard",
  "referrer": null,
  "event_properties": {
    "auth_method": "password"
  }
}
```

### Event types

- `portal_login`, `portal_logout`
- `statement_view`
- `pension_calculator_use` (event_properties: `calc_result`, `calc_inputs`)
- `buyback_info_page_view`
- `buyback_quote_request` ⭐ (buyback leading indicator)
- `beneficiary_page_view`
- `document_download` (event_properties: `document_type`)

### Messiness

| Messiness                      | Rate                     |
|--------------------------------|--------------------------|
| Missing `user_agent`           | 3%                       |
| `ip_hash` null (mobile app)    | 5%                       |
| Malformed JSON                 | 1 per 10,000 rows        |
| Event timestamp in UTC         | 20%                      |

---

## File 6: Call Logs (CSV)

### File identification

| Property          | Value                                        |
|-------------------|----------------------------------------------|
| Filename pattern  | `ONCAP001_CALL_LOG_YYYYMM.csv`               |
| Encoding          | UTF-8                                        |
| Delimiter         | Comma                                        |
| Line terminator   | LF                                           |
| Quoting           | Fields with comma/quote: double-quoted       |

### Columns

```
call_id,member_id,call_timestamp,duration_seconds,call_reason_category,call_reason_subcategory,resolution_code,agent_id,csat_score,notes
```

**Categories**: `GENERAL` / `BUYBACK` / `RETIREMENT` / `STATEMENT` / `BENEFICIARY` / `COMPLAINT`

**Resolution codes**: `RESOLVED` / `ESCALATED` / `CALLBACK` / `UNRESOLVED`

### Example

```
CALL20240115001234,0000428150,2024-01-15T10:15:00-05:00,423,BUYBACK,COST_INQUIRY,RESOLVED,AGT0042,4,"Explained maternity leave buyback cost and installment options"
```

### Messiness

- 30% null `csat_score` (member didn't respond to survey)
- 5% garbled notes

---

## File 7: Seminar Attendance (CSV)

### File identification

| Property          | Value                                           |
|-------------------|-------------------------------------------------|
| Filename pattern  | `ONCAP001_SEMINAR_ATTENDANCE_YYYY.csv`          |
| Encoding          | UTF-8                                           |
| Delimiter         | Comma                                           |

### Columns

```
attendance_id,member_id,seminar_date,seminar_location,seminar_topic,attendance_format,registration_date,attended_flag
```

**Topics**: `PRE_RETIREMENT` / `BUYBACK_101` / `INVESTMENT` / `GENERAL`

**Formats**: `IN_PERSON` / `VIRTUAL`

### Example

```
SEM2023010000001,0000428150,2023-10-15,Toronto,PRE_RETIREMENT,IN_PERSON,2023-09-20,Y
```

### Messiness

- 10% no-show rate (`attended_flag = N`)

---

## File 8: Email Engagement (CSV)

### File identification

| Property          | Value                                           |
|-------------------|-------------------------------------------------|
| Filename pattern  | `ONCAP001_EMAIL_ENGAGEMENT_YYYYMM.csv`          |
| Encoding          | UTF-8                                           |
| Delimiter         | Comma                                           |

### Columns

```
event_id,member_id,campaign_id,campaign_name,event_type,event_timestamp,link_url_clicked
```

**Event types**: `SENT` / `DELIVERED` / `OPENED` / `CLICKED` / `BOUNCED` / `UNSUBSCRIBED`

### Example

```
EML20240108000015,0000428150,CAMP_Q1_2024_BBK_REM,"Q1 2024 Buyback Reminder",OPENED,2024-01-08T08:22:13-05:00,
EML20240108000016,0000428150,CAMP_Q1_2024_BBK_REM,"Q1 2024 Buyback Reminder",CLICKED,2024-01-08T08:22:47-05:00,https://oncap.example.org/buyback-info
```

### Messiness

- 8% bounce rate
- 0.5% unsubscribe rate