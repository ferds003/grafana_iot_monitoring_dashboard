"""Push a dashboard JSON file to Grafana Cloud via the HTTP API.

Requires GRAFANA_URL and GRAFANA_TOKEN in .env, and a PostgreSQL data source
already created in Grafana Cloud (see datasource.notes.md). By default looks
up the data source named "Supabase Postgres" — override with
GRAFANA_DATASOURCE_NAME if you named it differently.

Usage:
    python grafana/push_dashboard.py [path/to/dashboard.json]
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "dashboard.json"


def get_env(name: str, required: bool = True, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"Missing required env var: {name}")
    return value


def main():
    grafana_url = get_env("GRAFANA_URL").rstrip("/")
    token = get_env("GRAFANA_TOKEN")
    ds_name = get_env("GRAFANA_DATASOURCE_NAME", required=False, default="Supabase Postgres")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = requests.get(f"{grafana_url}/api/datasources/name/{ds_name}", headers=headers)
    if resp.status_code != 200:
        sys.exit(
            f"Could not find data source named '{ds_name}' ({resp.status_code}: {resp.text}). "
            "Create it first — see grafana/datasource.notes.md."
        )
    ds_uid = resp.json()["uid"]
    print(f"Found data source '{ds_name}' -> uid={ds_uid}")

    dashboard = json.loads(DASHBOARD_PATH.read_text())
    dashboard.pop("id", None)

    payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "inputs": [
            {"name": "DS_POSTGRES", "type": "datasource", "pluginId": "postgres", "value": ds_uid}
        ],
    }

    resp = requests.post(f"{grafana_url}/api/dashboards/import", headers=headers, json=payload)
    if resp.status_code not in (200, 412):
        sys.exit(f"Dashboard import failed ({resp.status_code}): {resp.text}")

    result = resp.json()
    print(json.dumps(result, indent=2))
    slug = result.get("importedUrl") or result.get("url")
    if slug:
        print(f"\nDashboard URL: {grafana_url}{slug}")


if __name__ == "__main__":
    main()
