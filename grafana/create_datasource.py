"""Create (or update) the Supabase PostgreSQL data source in Grafana Cloud
via the HTTP API. Requires GRAFANA_URL, GRAFANA_TOKEN, and SUPABASE_DB_URL
in .env, and a service account token with datasources:create/write.

Usage:
    python grafana/create_datasource.py [--name "Supabase Postgres"]
"""
import argparse
import os
import sys
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="Supabase Postgres")
    args = parser.parse_args()

    grafana_url = os.environ.get("GRAFANA_URL", "").rstrip("/")
    token = os.environ.get("GRAFANA_TOKEN")
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not (grafana_url and token and db_url):
        sys.exit("Missing GRAFANA_URL, GRAFANA_TOKEN, or SUPABASE_DB_URL in .env")

    p = urlsplit(db_url)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {
        "name": args.name,
        "type": "postgres",
        "url": f"{p.hostname}:{p.port or 5432}",
        "user": p.username,
        "database": p.path.lstrip("/"),
        "access": "proxy",
        "isDefault": True,
        "jsonData": {
            "database": p.path.lstrip("/"),
            "sslmode": "require",
            "postgresVersion": 1600,
            "timescaledb": False,
        },
        "secureJsonData": {"password": p.password},
    }

    # Check if it already exists; update in place if so (idempotent).
    existing = requests.get(f"{grafana_url}/api/datasources/name/{args.name}", headers=headers)
    if existing.status_code == 200:
        ds_id = existing.json()["id"]
        resp = requests.put(f"{grafana_url}/api/datasources/{ds_id}", headers=headers, json=payload)
    else:
        resp = requests.post(f"{grafana_url}/api/datasources", headers=headers, json=payload)

    if resp.status_code not in (200, 201):
        sys.exit(f"Failed to create/update data source ({resp.status_code}): {resp.text}")

    result = resp.json()
    print(f"Data source '{args.name}' ready. uid={result.get('datasource', result).get('uid', result.get('uid'))}")

    # Verify connectivity via Grafana's health check endpoint.
    ds = requests.get(f"{grafana_url}/api/datasources/name/{args.name}", headers=headers).json()
    health = requests.get(f"{grafana_url}/api/datasources/uid/{ds['uid']}/health", headers=headers)
    print(f"Health check ({health.status_code}): {health.text}")


if __name__ == "__main__":
    main()
