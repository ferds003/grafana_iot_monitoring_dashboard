"""Generate a public-safe variant of the *live* interactive dashboard.

Fetches the current dashboard straight from Grafana Cloud (rather than the
local dashboard.json, which drifts out of sync as soon as panels are edited
live in the Grafana UI -- which they routinely are) and writes a public-safe
variant to dashboard_public.json.

Grafana's public/shared dashboards do not support template variables at all
(the whole dashboard is rejected, or renders with no data, if any variable is
present). This dashboard uses $machine and $status in nearly every panel
query, so the interactive dashboard can't be shared publicly as-is.

Rather than string-matching a specific " AND machine_id IN ($machine)" clause
(fragile -- breaks the moment a query is rewritten), every literal $machine /
$status token is replaced with a subquery selecting every possible value.
IN (SELECT DISTINCT machine_id FROM sensor_readings) is semantically "no
filter", same as the interactive dashboard's default "All" selection, and it
survives arbitrary rephrasing of the surrounding SQL.

Usage:
    python grafana/build_public_dashboard.py
"""
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DST = Path(__file__).resolve().parent / "dashboard_public.json"

SOURCE_UID = "smart-mfg-iot"
PUBLIC_UID = "smart-mfg-iot-public"


def fetch_live_dashboard(grafana_url: str, token: str, uid: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{grafana_url}/api/dashboards/uid/{uid}", headers=headers)
    if resp.status_code != 200:
        sys.exit(f"Could not fetch dashboard uid={uid} ({resp.status_code}): {resp.text}")
    return resp.json()["dashboard"]


def strip_vars(sql: str) -> str:
    sql = re.sub(r"\$machine\b", "(SELECT DISTINCT machine_id FROM sensor_readings)", sql)
    sql = re.sub(r"\$status\b", "(SELECT DISTINCT machine_status FROM sensor_readings)", sql)
    return sql


def main():
    grafana_url = os.environ.get("GRAFANA_URL", "").rstrip("/")
    token = os.environ.get("GRAFANA_TOKEN")
    if not (grafana_url and token):
        sys.exit("Missing GRAFANA_URL or GRAFANA_TOKEN in .env")

    dashboard = fetch_live_dashboard(grafana_url, token, SOURCE_UID)
    live_version = dashboard.get("version")

    dashboard.pop("id", None)
    dashboard["uid"] = PUBLIC_UID
    dashboard["title"] = "Smart Manufacturing IoT Monitoring (Public)"
    dashboard["templating"] = {"list": []}

    rewritten = 0
    for panel in dashboard.get("panels", []):
        for target in panel.get("targets", []):
            sql = target.get("rawSql")
            if not sql:
                continue
            new_sql = strip_vars(sql)
            if new_sql != sql:
                rewritten += 1
            target["rawSql"] = new_sql

    DST.write_text(json.dumps(dashboard, indent=2))
    print(f"Pulled live dashboard uid={SOURCE_UID} (version {live_version})")
    print(f"Rewrote {rewritten} panel quer{'y' if rewritten == 1 else 'ies'} to drop $machine/$status")
    print(f"Wrote {DST}")
    print("Next: python grafana/push_dashboard.py grafana/dashboard_public.json")


if __name__ == "__main__":
    main()
