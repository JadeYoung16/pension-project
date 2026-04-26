# ONCAP Pension Plan — Data Generation Plan

**Document version**: 1.0
**Prepared for**: Week 1 — Synthetic Data Generation
**Status**: Planning document for upstream simulators

> This document specifies what data files will be generated, in what order, and
> with what intentional imperfections ("messiness"). It is the master plan for
> all `upstream_simulators/generators/` code.

---

## 1. Generation Order & Dependency Graph

Files must be generated in a specific order because downstream files reference
upstream IDs. This is the dependency DAG:

```
┌─────────────────────────────────┐
│  EXTERNAL (already downloaded)  │
│  - CRA T3010 Ontario (30,607)   │
│  - UCI Bank Marketing           │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  STAGE 1: Employer Registry     │
│  (400 employers from T3010)     │
└──────────────┬──────────────────┘
               │ employer_id, pay_frequency
               ▼
┌─────────────────────────────────┐
│  STAGE 2: Member Census         │
│  (50,000 members)               │
│  + Member-level leave history   │
└──────────────┬──────────────────┘
               │ member_id, employer_id
               │ salary, status, service
      ┌────────┼────────┬────────┬────────┐
      ▼        ▼        ▼        ▼        ▼
┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│ STAGE 3a ││ STAGE 3b ││ STAGE 3c ││ STAGE 3d ││ STAGE 3e │
│ Trans-   ││ Life     ││ Portal   ││ Call     ││ Email    │
│ actions  ││ Events   ││ Events   ││ Logs     ││ Engage   │
│          ││ (buyback)││          ││          ││          │
└──────────┘└──────────┘└──────────┘└──────────┘└──────────┘

                        Seminar Attendance (annual, independent)
```

**Key dependency rule**: Once a member is assigned `member_id = 0000428150`,
that ID is **immutable** across all files. Same for `employer_id`.

---

## 2. File Inventory

### Summary

| # | File                 | Source System (modeled)         | Format             | Frequency    |
|---|----------------------|----------------------------------|--------------------|--------------|
| 1 | Employer Registry    | Admin system                     | CSV                | On-change    |
| 2 | Member Census        | Admin system                     | Fixed-width `.DAT` | Monthly      |
| 3 | Transactions         | Financial system                 | Pipe-delimited `.TXT` | Per pay cycle |
| 4 | Life Events          | Events module                    | Pipe-delimited `.TXT` | Monthly batched |
| 5 | Portal Events        | Member portal                    | JSONL              | Daily        |
| 6 | Call Logs            | Contact center                   | CSV                | Monthly      |
| 7 | Seminar Attendance   | Event registration               | CSV                | Annual       |
| 8 | Email Engagement     | Email platform                   | CSV                | Monthly      |

See `docs/03_record_layouts.md` for the detailed field-level specification of
each file.

---

## 3. Data Volume Summary

| File                  | Rows / month         | Rows / year            | Approx size        |
|-----------------------|----------------------|------------------------|--------------------|
| Employer Registry     | 400 (snapshot)       | 400                    | ~40 KB             |
| Member Census         | 50,000 (snapshot)    | 50,000 × 12 snapshots  | ~20 MB / snapshot  |
| Transactions          | ~100,000 total/month | ~1.2M                  | ~30 MB / month     |
| Life Events           | ~300                 | ~3,600                 | ~100 KB / month    |
| Portal Events         | ~20,000              | ~240,000               | ~10 MB / month     |
| Call Logs             | ~2,500               | ~30,000                | ~500 KB / month    |
| Seminar Attendance    | —                    | ~4,000                 | ~300 KB / year     |
| Email Engagement      | ~200,000             | ~2.4M                  | ~40 MB / month     |

**Total ongoing data volume**: ~100 MB / month, ~1.2 GB / year.

---

## 4. Initial Historical Data Bootstrap (Week 1 Output)

Before Week 1 ends, we generate historical depth for downstream pipeline demo
and ML modeling:

| File                | Historical depth                 | Rationale |
|---------------------|----------------------------------|-----------|
| Employer Registry   | Single snapshot (2024-01-31)     | Dimension table, rarely changes |
| Member Census       | Current snapshot + one prior month | For diff detection demo |
| Transactions        | 3 months (2023-11, 2023-12, 2024-01) | Demo multi-file ingestion |
| Life Events         | **24 months** (2022-02 to 2024-01) | ML target labels require long history for rare events |
| Portal Events       | 3 months                         | Behavioral feature engineering |
| Call Logs           | 3 months                         | Engagement feature |
| Seminar Attendance  | 2 years (2022, 2023)             | Seminar attendance is a strong buyback predictor |
| Email Engagement    | 3 months                         | Campaign feature |

---

## 5. Messiness Injection Principles

Every file (except Employer Registry — the master) has deliberate imperfections
to simulate real-world admin system extracts. Rates are configurable via
`upstream_simulators/config/messiness_config.yaml`.

### Summary table

| Messiness category                        | Where it appears           | Rate    |
|-------------------------------------------|----------------------------|---------|
| Missing optional values                   | Member Census, Call Logs   | 5–35%   |
| Duplicate records                         | Transactions               | 0.1%    |
| Malformed rows (e.g., bad JSON)           | Portal Events              | 0.01%   |
| Encoding issues (non-ASCII names)         | Member Census              | ~1%     |
| Date format inconsistency                 | Member Census              | 1%      |
| Timezone inconsistency (UTC vs EST)       | Portal Events, Life Events | 10–20%  |
| Reconciliation gaps (header count wrong)  | 1 file out of ~50          | 2%      |
| Rejected / retry transactions             | Transactions               | 0.5%    |
| Rounding drift (3% of earnings vs total)  | Transactions               | 0.2%    |

### Why messiness matters

Real pension admin systems have these imperfections. Pipeline code needs to
handle them gracefully. If synthetic data is too clean, the pipeline is
untested against real-world pain.

### Testing mode

For unit testing, `messiness_config.yaml` supports an `extreme_mode = true`
flag that inflates all rates to 100%, forcing every record through every
error-handling path.

---

## 6. Synthetic Data Seeding (Reproducibility)

All random generation uses a fixed seed scheme:

```python
BASE_SEED = 42
EMPLOYER_SEED    = BASE_SEED + 1  # 43
MEMBER_SEED      = BASE_SEED + 2  # 44
TRANSACTION_SEED = BASE_SEED + 3  # 45
LIFE_EVENT_SEED  = BASE_SEED + 4  # 46
PORTAL_SEED      = BASE_SEED + 5  # 47
CALL_SEED        = BASE_SEED + 6  # 48
SEMINAR_SEED     = BASE_SEED + 7  # 49
EMAIL_SEED       = BASE_SEED + 8  # 50
```

**Commitment**: Running `python upstream_simulators/run_all.py` on any machine
produces byte-identical output.

---

## 7. Generator Code Organization

```
upstream_simulators/
├── README.md                    # "This is mock upstream — not DE scope"
├── config/
│   ├── plan_config.yaml         # Plan parameters from Plan Spec
│   ├── messiness_config.yaml    # Messiness injection rates
│   └── record_layouts/
│       └── member_census_layout.yaml
├── shared/
│   ├── ids.py                   # ID generation (member_id, event_id, …)
│   ├── dates.py                 # Business day, leave date generation
│   ├── faker_pool.py            # Seeded Faker instance
│   ├── messiness.py             # Apply imperfections to values
│   └── writers/
│       ├── fixed_width.py
│       ├── delimited.py
│       └── jsonl.py
├── generators/
│   ├── employer_generator.py    # Stage 1
│   ├── member_generator.py      # Stage 2 (depends on employer)
│   ├── transaction_generator.py # Stage 3a
│   ├── life_event_generator.py  # Stage 3b (buyback core logic)
│   ├── portal_event_generator.py
│   ├── call_log_generator.py
│   ├── seminar_generator.py
│   └── email_engagement_generator.py
└── run_all.py                   # Orchestrator: runs in dependency order
```

---

## 8. Output Location

```
data/synthetic/
├── employer_registry/
│   └── ONCAP001_EMPLOYER_REGISTRY_20240131.csv
├── member_census/
│   ├── ONCAP001_MEMBER_CENSUS_20231231.DAT   ← previous month (diff demo)
│   └── ONCAP001_MEMBER_CENSUS_20240131.DAT   ← current
├── transactions/
│   ├── ONCAP001_TXN_PAYDATE_20231110.TXT
│   ├── ...                                   (multiple files per month)
│   └── ONCAP001_TXN_PAYDATE_20240131.TXT
├── life_events/
│   ├── ONCAP001_LIFE_EVENTS_202202.TXT
│   ├── ...                                   (24 files)
│   └── ONCAP001_LIFE_EVENTS_202401.TXT
├── portal_events/
│   └── ONCAP001_PORTAL_EVENTS_YYYYMMDD.jsonl ← daily files, 90 days
├── call_logs/
│   ├── ONCAP001_CALL_LOG_202311.csv
│   ├── ONCAP001_CALL_LOG_202312.csv
│   └── ONCAP001_CALL_LOG_202401.csv
├── seminar_attendance/
│   ├── ONCAP001_SEMINAR_ATTENDANCE_2022.csv
│   └── ONCAP001_SEMINAR_ATTENDANCE_2023.csv
└── email_engagement/
    ├── ONCAP001_EMAIL_ENGAGEMENT_202311.csv
    ├── ONCAP001_EMAIL_ENGAGEMENT_202312.csv
    └── ONCAP001_EMAIL_ENGAGEMENT_202401.csv
```

**Total files after Week 1 bootstrap**: ~180 files, ~300 MB total.

---

## 9. Post-Generation Validation

After `run_all.py` completes, validation checks:

- ✅ Row counts match spec (50,000 members, 400 employers)
- ✅ All foreign keys resolve (member.employer_id exists in employer registry)
- ✅ Status distribution matches spec (within ±1%)
- ✅ Age distribution matches spec by status
- ✅ Buyback count in life events matches target (~10% of eligible)
- ✅ No orphan `member_id` across files
- ✅ Every file has valid header + trailer (where applicable)

If validation fails, `run_all.py` exits with non-zero status and prints which
check failed.