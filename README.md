# Smart Manufacturing IoT Dashboard

Fully cloud-hosted Grafana dashboard for the Kaggle "Smart Manufacturing
IoT-Cloud Monitoring Dataset". Data lives in a hosted Postgres (Supabase),
the dashboard runs on Grafana Cloud — nothing to run locally after setup.

See [PLAN.md](PLAN.md) for the full architecture and rationale.

## Setup

1. **Accounts** (see PLAN.md Phase 0): Kaggle, Supabase, Grafana Cloud.
   Copy `.env.example` to `.env` and fill in real values.
2. **Install deps**:
   ```
   pip install -r requirements.txt
   ```
3. **Download & inspect the dataset**:
   ```
   python etl/download.py
   ```
   Review the printed column list/dtypes against `etl/schema.sql` and
   `etl/load.py`'s `COLUMN_MAP` — adjust both if the real CSV header differs.
4. **Load into Supabase Postgres**:
   ```
   python etl/load.py --shift-to-now --truncate
   ```
   `--shift-to-now` offsets all timestamps so the latest row lands at "now",
   which makes Grafana's default relative time ranges (Last 24h/7d) useful.
   Omit it to keep original timestamps (then widen the dashboard's time range
   to match, see `grafana/dashboard.json`'s default `now-5y` to `now`).
5. **Create the Grafana PostgreSQL data source** — manual, one-time — see
   [grafana/datasource.notes.md](grafana/datasource.notes.md).
6. **Push the dashboard**:
   ```
   python grafana/push_dashboard.py
   ```
7. (Optional) **Simulate live data**: add `SUPABASE_DB_URL` as a GitHub
   Actions secret in this repo; `.github/workflows/replay.yml` runs
   `etl/replay_loop.py` every 15 minutes, which replays the original dataset
   at its native 1-reading-per-minute cadence and loops back to the start
   once it reaches the end — so the dashboard always has fresh, realistic
   data with no manual re-loading.

## Repo layout

```
etl/                  Kaggle download, schema, load, live-replay scripts
grafana/               Dashboard JSON + push script + datasource setup notes
.github/workflows/     Optional cron to keep the dashboard "live"
```
