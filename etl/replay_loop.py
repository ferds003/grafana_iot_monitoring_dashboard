"""Continuously "replay" the original dataset at its native 1-reading-per-
minute cadence, looping back to the start once the template is exhausted.

Design: sensor_readings_template holds one immutable cycle (seq_no 0..N-1,
confirmed exactly 1 row/minute, no gaps). Each run looks at the live
sensor_readings table's current max(ts)/seq_no and inserts however many
"minutes" have elapsed since then, pulling values from the template at
(last_seq_no + i) % N -- wrapping back to seq_no 0 forever. This makes state
implicit in the data itself (no separate cursor table needed): whatever is
already in sensor_readings IS the cursor.

Meant to be run on a schedule (e.g. every 15 min via GitHub Actions) so the
gap between runs is small; if it hasn't run in a while it will backfill all
missed minutes in one go (capped by --max-insert to bound run time).

Usage:
    python etl/replay_loop.py [--max-insert 2000] [--retention-days 120]
"""
import argparse
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_COLUMNS = [
    "ts", "seq_no", "machine_id", "temperature", "vibration", "humidity",
    "pressure", "energy_consumption", "machine_status", "anomaly_flag",
    "predicted_remaining_life", "failure_type", "downtime_risk",
    "maintenance_required",
]


def get_engine():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        sys.exit("SUPABASE_DB_URL is not set (check your .env file)")
    return create_engine(db_url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-insert", type=int, default=2000,
                         help="Cap on rows inserted in one run (catch-up safety valve)")
    parser.add_argument("--retention-days", type=int, default=120,
                         help="Delete sensor_readings rows older than this many days")
    args = parser.parse_args()

    engine = get_engine()

    with engine.connect() as conn:
        template_size = conn.execute(text("SELECT count(*) FROM sensor_readings_template")).scalar()
        if not template_size:
            sys.exit("sensor_readings_template is empty. Run etl/load.py first.")

        last = conn.execute(
            text("SELECT ts, seq_no FROM sensor_readings ORDER BY ts DESC LIMIT 1")
        ).first()
        if last is None:
            sys.exit("sensor_readings is empty. Run etl/load.py first.")

    last_ts, last_seq = last
    now = pd.Timestamp.now(tz="UTC")
    elapsed_minutes = int((now - last_ts).total_seconds() // 60)

    if elapsed_minutes <= 0:
        print(f"Nothing to do: last row is at {last_ts}, less than 1 minute ago.")
        return

    n_new = min(elapsed_minutes, args.max_insert)
    if n_new < elapsed_minutes:
        print(f"Elapsed {elapsed_minutes} min exceeds --max-insert={args.max_insert}; "
              f"inserting {n_new} now, remainder will catch up on the next run(s).")

    seq_nos = [(last_seq + i) % template_size for i in range(1, n_new + 1)]
    new_ts = [last_ts + pd.Timedelta(minutes=i) for i in range(1, n_new + 1)]

    with engine.connect() as conn:
        template = pd.read_sql(
            text("SELECT * FROM sensor_readings_template WHERE seq_no = ANY(:seqs)"),
            conn,
            params={"seqs": seq_nos},
        )

    template = template.set_index("seq_no").loc[seq_nos].reset_index()
    template["ts"] = new_ts

    with engine.begin() as conn:
        template[DB_COLUMNS].to_sql(
            "sensor_readings", conn, if_exists="append", index=False,
            method="multi", chunksize=5000,
        )
        deleted = conn.execute(
            text("DELETE FROM sensor_readings WHERE ts < :cutoff"),
            {"cutoff": now - pd.Timedelta(days=args.retention_days)},
        ).rowcount

    print(f"Inserted {n_new} rows (seq_no {seq_nos[0]}..{seq_nos[-1]} mod {template_size}), "
          f"new max(ts)={new_ts[-1]}. Pruned {deleted} rows older than {args.retention_days}d.")


if __name__ == "__main__":
    main()
