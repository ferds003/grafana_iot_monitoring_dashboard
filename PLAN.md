# Smart Manufacturing IoT Dashboard — Execution Plan

Goal: Build a fully cloud-hosted Grafana dashboard for the Kaggle
"Smart Manufacturing IoT-Cloud Monitoring Dataset" (ziya07), with data stored
online and Grafana running online. No local servers required after setup.

This file is written to be executed by Claude Code. Each phase lists concrete
steps, commands, and acceptance criteria. Human-only steps (account signups,
copying API keys) are marked **[HUMAN]**.

---

## Architecture

```
Kaggle CSV
   │  (one-time download via Kaggle API)
   ▼
Python ETL script (pandas)  ── clean, type-cast, normalize timestamps
   │
   ▼
Cloud Postgres (Supabase free tier)   ← online data store
   │  (Grafana PostgreSQL data source over SSL)
   ▼
Grafana Cloud (free tier)             ← online dashboard
   ▲
   │ (optional) replay_stream.py via GitHub Actions cron
   └── simulates "live" sensor ingestion for a realistic demo
```

Why this stack:
- **Supabase Postgres (free)**: real SQL database, 500 MB storage (plenty for
  this dataset), direct connection string, natively supported by Grafana.
  Alternative: Neon.tech (also free Postgres). InfluxDB Cloud is an option but
  its free tier deletes data after 30 days — Postgres avoids that.
- **Grafana Cloud (free)**: hosted Grafana, no server to maintain, supports the
  PostgreSQL data source out of the box, shareable public dashboard links.
- **GitHub Actions (free)**: optional cron job to replay rows into the DB so
  the dashboard looks live.

---

## Dataset Schema (expected columns)

| Column | Type | Notes |
|---|---|---|
| timestamp | timestamptz | primary time axis |
| machine_id | text | e.g. M_01 … M_50 |
| temperature | double | °C |
| vibration | double | mm/s or g |
| humidity | double | % |
| pressure | double | bar/kPa |
| energy_consumption | double | kWh |
| machine_status | text | Idle / Running / Failure |
| anomaly_flag | int/bool | extreme temp/vibration values |
| predicted_remaining_life | double | hours until maintenance |
| failure_type | text | Overheating, Vibration Issue, Normal, etc. |
| downtime_risk | double | 0–1 probability |
| maintenance_required | int | 0/1 target |

⚠️ Claude Code: after downloading, inspect the actual CSV header with
`head -n 3 data/*.csv` and adjust column names in the ETL + SQL to match
exactly. Do not assume the names above are literal.

---

## Phase 0 — Accounts & Credentials **[HUMAN]**

1. Kaggle account → create API token (`kaggle.json` from Account settings).
2. Supabase account → create a new project (region: Southeast Asia /
   Singapore for low latency from the Philippines). Copy:
   - Host, port (5432 or 6543 pooler), database name, user, password.
   - Use the **session pooler / direct connection string**, not the REST URL.
3. Grafana Cloud account (free) → note your stack URL
   (e.g. `https://<you>.grafana.net`) and create a **service account token**
   with Editor role (for dashboard provisioning via API).
4. (Optional) GitHub repo for the project + repository secrets:
   `SUPABASE_DB_URL`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, `GRAFANA_URL`,
   `GRAFANA_TOKEN`.

Store secrets locally in a `.env` file (git-ignored):

```
SUPABASE_DB_URL=postgresql://user:pass@host:5432/postgres?sslmode=require
GRAFANA_URL=https://<you>.grafana.net
GRAFANA_TOKEN=glsa_xxx
KAGGLE_USERNAME=xxx
KAGGLE_KEY=xxx
```

---

## Phase 1 — Project Scaffold (Claude Code)

```
iot-grafana-dashboard/
├── PLAN.md                  ← this file
├── .env                     ← secrets (git-ignored)
├── .gitignore
├── requirements.txt         ← pandas, sqlalchemy, psycopg2-binary, kaggle, python-dotenv, requests
├── data/                    ← raw CSV (git-ignored)
├── etl/
│   ├── download.py          ← Kaggle API download
│   ├── schema.sql           ← table + indexes
│   ├── load.py               ← clean + bulk load to Supabase
│   └── replay_stream.py     ← optional live-data simulator
├── grafana/
│   ├── datasource.notes.md  ← manual datasource setup notes
│   └── dashboard.json       ← provisioned dashboard definition
└── .github/workflows/replay.yml   ← optional cron streamer
```

Acceptance: `pip install -r requirements.txt` succeeds.

---

## Phase 2 — Download & Inspect Data

`etl/download.py`:
- Use the Kaggle API: `kaggle datasets download -d ziya07/smart-manufacturing-iot-cloud-monitoring-dataset -p data/ --unzip`
- Print shape, dtypes, null counts, min/max timestamp, unique machine_ids,
  value distributions for status/failure_type.

Acceptance: CSV in `data/`, exploration summary printed, schema confirmed.

---

## Phase 3 — Cloud Database Setup

`etl/schema.sql` (adjust column names to actual CSV):

```sql
CREATE TABLE IF NOT EXISTS sensor_readings (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  machine_id TEXT NOT NULL,
  temperature DOUBLE PRECISION,
  vibration DOUBLE PRECISION,
  humidity DOUBLE PRECISION,
  pressure DOUBLE PRECISION,
  energy_consumption DOUBLE PRECISION,
  machine_status TEXT,
  anomaly_flag SMALLINT,
  predicted_remaining_life DOUBLE PRECISION,
  failure_type TEXT,
  downtime_risk DOUBLE PRECISION,
  maintenance_required SMALLINT
);
CREATE INDEX IF NOT EXISTS idx_sr_ts ON sensor_readings (ts);
CREATE INDEX IF NOT EXISTS idx_sr_machine_ts ON sensor_readings (machine_id, ts);
```

`etl/load.py`:
- Read CSV with pandas; parse timestamps to UTC tz-aware.
- **Important**: if the dataset's timestamps are old/synthetic, add a
  `--shift-to-now` flag that offsets all timestamps so the latest row = now.
  This makes Grafana's default "Last 24h / 7d" time pickers actually show data.
- Clean: strip column names to snake_case, coerce numerics, map status
  strings consistently, drop exact duplicates.
- Bulk insert via SQLAlchemy `to_sql(method='multi', chunksize=5000)` or
  `COPY` via psycopg2 for speed.
- Idempotency: `TRUNCATE` + reload, or skip if row count matches.

Acceptance: `SELECT count(*) FROM sensor_readings;` matches CSV row count;
`SELECT max(ts)` is near current time (if shifted).

---

## Phase 4 — Grafana Cloud Setup

1. **[HUMAN]** In Grafana Cloud: Connections → Add data source → PostgreSQL.
   - Host: Supabase host:5432, DB: postgres, user/password, TLS: require.
   - Note: Supabase direct connections are IPv6-first; if Grafana Cloud can't
     connect, use the **Supavisor session pooler** host (port 5432/6543) which
     is IPv4-compatible.
2. Claude Code: build `grafana/dashboard.json` and push it via the HTTP API:
   `POST $GRAFANA_URL/api/dashboards/db` with the service account token.

### Dashboard layout (single dashboard, 4 rows)

**Template variables**: `$machine` (multi-select from
`SELECT DISTINCT machine_id ...`), `$status`.

**Row 1 — Fleet Overview (stat panels)**
- Machines online (count distinct machine_id in range)
- % machines in Failure status (thresholds: green <5%, yellow <15%, red ≥15%)
- Active anomalies (sum of anomaly_flag in range)
- Machines needing maintenance (maintenance_required = 1, latest per machine)

**Row 2 — Sensor Time Series**
- Temperature over time by $machine (time series, threshold line at anomaly level)
- Vibration over time by $machine
- Pressure & humidity (combined or separate)
- Energy consumption (stacked by machine or total)

Example Grafana SQL (time series):
```sql
SELECT ts AS "time", machine_id, temperature
FROM sensor_readings
WHERE $__timeFilter(ts) AND machine_id IN ($machine)
ORDER BY ts;
```
Use `$__timeGroup(ts, $__interval)` with AVG() aggregation for large ranges.

**Row 3 — Health & Prediction**
- Predicted remaining life per machine (bar gauge, ascending — lowest first)
- Downtime risk score heatmap or table (color-coded 0–1)
- Machine status timeline (state timeline panel: Idle/Running/Failure per machine)

**Row 4 — Failure Analytics**
- Failure type breakdown (pie/bar: count by failure_type, excluding Normal)
- Anomaly count over time (bar chart, $__timeGroup by hour/day)
- Maintenance-required table: latest reading per machine where
  maintenance_required = 1, with risk score and remaining life columns

**Alerting (optional but great for portfolio)**: Grafana alert rules —
e.g. downtime_risk > 0.8 or temperature above threshold → email/Discord.

Acceptance: dashboard renders in Grafana Cloud with data in all panels for
the default time range; variables filter correctly.

---

## Phase 5 — Optional: Simulated Live Streaming

`etl/replay_stream.py`:
- Holds back the most recent N% of rows during initial load (or generates
  new rows by sampling per-machine distributions + noise).
- Every run, inserts the next batch with `ts = now()`.

`.github/workflows/replay.yml`:
- `schedule: cron: '*/15 * * * *'` (GitHub Actions minimum ~5 min, often
  delayed; 15 min is reliable).
- Runs the script with `SUPABASE_DB_URL` secret.

Result: dashboard visibly updates over time — much stronger demo than a
static historical dataset.

---

## Phase 6 — Polish & Portfolio

- Public dashboard: Grafana Cloud → Share → Public dashboard link.
- README with architecture diagram, screenshots, link to live dashboard.
- Stretch goals (ties into your CV/data-science direction):
  - Train a maintenance_required classifier (scikit-learn) offline, write
    predictions back to a `predictions` table, add a panel comparing
    predicted vs. actual.
  - Anomaly detection (Isolation Forest) on temperature/vibration and plot
    detected anomalies as Grafana annotations.

---

## Execution Order for Claude Code

1. Scaffold repo (Phase 1) → wait for human `.env` (Phase 0).
2. Phase 2: download + inspect → report actual schema back to user.
3. Phase 3: create table, load data, verify counts.
4. Phase 4: generate dashboard.json, push via API, verify via GET.
5. Phase 5 only if user confirms they want streaming.
6. Phase 6: README + screenshots checklist.

## Gotchas

- Kaggle API needs `~/.kaggle/kaggle.json` with chmod 600, or env vars.
- Supabase free tier pauses projects after ~1 week of inactivity — the
  replay cron conveniently keeps it awake.
- Grafana Cloud free tier: 14-day dashboard-data retention applies to its
  hosted metrics/logs, NOT to your external Postgres — your data is safe.
- Always use `$__timeFilter(ts)` in every panel query or Grafana's time
  picker will do nothing.
- If timestamps aren't shifted to present, set the dashboard's default time
  range to the dataset's actual min–max range instead.
