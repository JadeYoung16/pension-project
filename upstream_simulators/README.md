# Upstream Simulators — Mock Data Sources

> **⚠️ Scope disclaimer**: This directory simulates **upstream systems** — pension
> admin systems, recordkeepers, payroll platforms, web analytics, call center
> logs, etc. In a real pension organization, these systems are maintained by
> other teams (admin IT, vendor IT, web platform team). A **data engineer's
> scope starts at the landing zone**, not here.
>
> Code in this directory exists **only to create realistic synthetic data** so
> the downstream pipeline has something to process. It should be physically and
> logically isolated from the pipeline:
>
> - Pipeline code must **not `import`** anything from `upstream_simulators/`.
> - The only interface between them is the files written to `data/synthetic/`
>   (and later, the SFTP landing zone).

## What's here
upstream_simulators/
├── README.md                       ← this file
├── config/
│   ├── plan_config.yaml            ← Plan parameters (salary bands, status %, etc.)
│   ├── messiness_config.yaml       ← Imperfection injection rates
│   └── record_layouts/
│       └── member_census_layout.yaml  ← Machine-readable fixed-width layout
├── shared/                         ← Reusable utilities across generators
│   ├── ids.py                      ← ID generation (member, employer, event)
│   ├── dates.py                    ← Date helpers, business day logic
│   ├── faker_pool.py               ← Seeded Faker for reproducibility
│   ├── messiness.py                ← Apply imperfections to records
│   └── writers/                    ← File format writers
│       ├── fixed_width.py
│       ├── delimited.py
│       └── jsonl.py
├── generators/                     ← One module per output file type
│   ├── employer_generator.py
│   ├── member_generator.py
│   ├── transaction_generator.py
│   ├── life_event_generator.py
│   ├── portal_event_generator.py
│   ├── call_log_generator.py
│   ├── seminar_generator.py
│   └── email_engagement_generator.py
└── run_all.py                      ← Orchestrator (runs generators in order)

## How to run

From the repo root:

\`\`\`bash
# Single generator
python -m upstream_simulators.generators.employer_generator

# All generators in order
python -m upstream_simulators.run_all
\`\`\`

All output is written to `data/synthetic/`.

## Reproducibility

All random generation is seeded. Running any generator on any machine produces
byte-identical output for the same config.

## References

See the authoritative specifications in `docs/`:

- `01_plan_design_specification.md` — Plan business rules
- `02_data_generation_plan.md` — File inventory, dependencies, messiness plan
- `03_record_layouts.md` — Field-level file format specs