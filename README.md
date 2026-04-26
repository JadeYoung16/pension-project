# Pension Project

OnCap pension data analysis project.

## Structure

- `upstream_simulators/` — synthetic data generators for pension plan members, transactions, life events, engagement signals, etc.
- `downloaders/` — scripts to fetch external/reference datasets (CRA T3010, UCI Bank Marketing).
- `docs/` — project specifications: plan design, data generation plan, record layouts.
- `data/` — raw and generated data (gitignored; regenerated via scripts).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Status

Week 2 — environment & repo setup in progress.
