-- Schema for sensor_readings table.
-- Confirmed against the real CSV (smart_manufacturing_data.csv, 100k rows,
-- 50 machines, 1-minute interval readings from 2025-01-01 to 2025-03-11).
-- machine_id is a plain integer (1-50). machine_status arrives as an int
-- code (0/1/2) and is mapped to Idle/Running/Failure text at load time
-- (see etl/load.py STATUS_MAP) to match the dataset's documented categories.

CREATE TABLE IF NOT EXISTS sensor_readings (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  seq_no INTEGER,
  machine_id INTEGER NOT NULL,
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

-- Idempotent migration in case sensor_readings already existed pre-seq_no.
ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS seq_no INTEGER;

CREATE INDEX IF NOT EXISTS idx_sr_ts ON sensor_readings (ts);
CREATE INDEX IF NOT EXISTS idx_sr_machine_ts ON sensor_readings (machine_id, ts);

-- Immutable snapshot of one full loop cycle (confirmed: the source CSV is
-- exactly one reading per minute, seq_no 0..99999, no gaps/duplicates).
-- etl/replay_loop.py walks this table in seq_no order forever, wrapping back
-- to 0 when it runs off the end, to simulate a continuous 1-minute-interval
-- live feed without needing to regenerate synthetic values.
CREATE TABLE IF NOT EXISTS sensor_readings_template (
  seq_no INTEGER PRIMARY KEY,
  machine_id INTEGER NOT NULL,
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
