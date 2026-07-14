"""Clean the downloaded CSV and bulk-load it into the Supabase Postgres
sensor_readings table.

Usage:
    python etl/load.py [--shift-to-now] [--truncate]

NOTE: COLUMN_MAP below maps raw CSV headers -> our sensor_readings columns.
Adjust it once the real CSV header is known (see etl/download.py output).
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Raw CSV column name -> target DB column name.
# Update after inspecting the real header from etl/download.py.
COLUMN_MAP = {
    "timestamp": "ts",
    "machine_id": "machine_id",
    "temperature": "temperature",
    "vibration": "vibration",
    "humidity": "humidity",
    "pressure": "pressure",
    "energy_consumption": "energy_consumption",
    "machine_status": "machine_status",
    "anomaly_flag": "anomaly_flag",
    "predicted_remaining_life": "predicted_remaining_life",
    "failure_type": "failure_type",
    "downtime_risk": "downtime_risk",
    "maintenance_required": "maintenance_required",
}

DB_COLUMNS = [
    "ts", "machine_id", "temperature", "vibration", "humidity", "pressure",
    "energy_consumption", "machine_status", "anomaly_flag",
    "predicted_remaining_life", "failure_type", "downtime_risk",
    "maintenance_required",
]

TEMPLATE_COLUMNS = [
    "seq_no", "machine_id", "temperature", "vibration", "humidity", "pressure",
    "energy_consumption", "machine_status", "anomaly_flag",
    "predicted_remaining_life", "failure_type", "downtime_risk",
    "maintenance_required",
]

# Source data encodes machine_status as an int (0/1/2). Map to the dataset's
# documented categories (Idle, Running, Failure) so dashboard panels can
# filter/display human-readable status text.
STATUS_MAP = {0: "Idle", 1: "Running", 2: "Failure"}


def to_snake_case(name: str) -> str:
    name = name.strip().replace(" ", "_").replace("-", "_")
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    name = re.sub(r"_+", "_", name)
    return name


def get_engine():
    import os

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        sys.exit("SUPABASE_DB_URL is not set (check your .env file)")
    return create_engine(db_url)


def ensure_schema(engine):
    ddl = SCHEMA_PATH.read_text()
    with engine.begin() as conn:
        for statement in ddl.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))


def load_csv() -> pd.DataFrame:
    csvs = list(DATA_DIR.glob("*.csv"))
    if not csvs:
        sys.exit(f"No CSV found in {DATA_DIR}. Run etl/download.py first.")
    df = pd.read_csv(csvs[0])
    df.columns = [to_snake_case(c) for c in df.columns]
    return df


def clean(df: pd.DataFrame, shift_to_now: bool) -> pd.DataFrame:
    # Map to target column names where we have a mapping; keep unmapped
    # columns as-is in case the schema needs extending.
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    missing = [c for c in DB_COLUMNS if c not in df.columns]
    if missing:
        print(f"WARNING: columns missing from source data, will insert NULL: {missing}")
        for c in missing:
            df[c] = None

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    df = df.dropna(subset=["ts", "machine_id"])
    df = df.drop_duplicates()
    df = df.sort_values("ts").reset_index(drop=True)
    df["seq_no"] = df.index

    if df["machine_status"].dtype != object:
        df["machine_status"] = df["machine_status"].map(STATUS_MAP)

    if shift_to_now:
        latest = df["ts"].max()
        offset = pd.Timestamp.now(tz="UTC") - latest
        df["ts"] = df["ts"] + offset
        print(f"Shifted timestamps by {offset} so max(ts) ~= now()")

    return df[["seq_no"] + DB_COLUMNS]


def bulk_insert(engine, df: pd.DataFrame, truncate: bool):
    with engine.begin() as conn:
        if truncate:
            conn.execute(text("TRUNCATE TABLE sensor_readings RESTART IDENTITY"))
    df.to_sql(
        "sensor_readings",
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=5000,
    )


def load_template(engine, df: pd.DataFrame):
    """(Re)populate the immutable one-cycle template that replay_loop.py
    walks through forever. Always a full truncate + reload since it must
    stay in lockstep with sensor_readings' seq_no numbering."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE sensor_readings_template"))
    df[TEMPLATE_COLUMNS].to_sql(
        "sensor_readings_template",
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=5000,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shift-to-now", action="store_true",
                         help="Offset all timestamps so the latest row = now()")
    parser.add_argument("--truncate", action="store_true",
                         help="Truncate the table before loading (idempotent reload)")
    args = parser.parse_args()

    engine = get_engine()
    ensure_schema(engine)

    df = load_csv()
    print(f"Loaded {len(df)} rows from CSV")

    df = clean(df, shift_to_now=args.shift_to_now)
    print(f"After cleaning: {len(df)} rows")

    bulk_insert(engine, df, truncate=args.truncate)
    load_template(engine, df)
    print(f"Refreshed sensor_readings_template with {len(df)} rows (seq_no 0..{len(df) - 1})")

    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM sensor_readings")).scalar()
        max_ts = conn.execute(text("SELECT max(ts) FROM sensor_readings")).scalar()
    print(f"sensor_readings row count: {count}")
    print(f"sensor_readings max(ts): {max_ts}")


if __name__ == "__main__":
    main()
