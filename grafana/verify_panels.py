"""Sanity-check that the dashboard's panel queries actually return data by
running them through Grafana's /api/ds/query endpoint (exercises the same
$__timeFilter / $__timeGroup macro expansion the real dashboard uses).

Template variables ($machine, $status) are resolved to literal "include all"
values here since ad-hoc query calls don't go through dashboard templating.
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_PATH = Path(__file__).resolve().parent / "dashboard.json"


def main():
    grafana_url = os.environ["GRAFANA_URL"].rstrip("/")
    token = os.environ["GRAFANA_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    ds = requests.get(f"{grafana_url}/api/datasources/name/Supabase Postgres", headers=headers).json()
    ds_uid = ds["uid"]

    dashboard = json.loads(DASHBOARD_PATH.read_text())
    panels = [p for p in dashboard["panels"] if p.get("type") != "row"]

    for panel in panels:
        for target in panel["targets"]:
            raw_sql = target["rawSql"]
            resolved = raw_sql.replace("IN ($machine)", "IN (SELECT DISTINCT machine_id FROM sensor_readings)")
            resolved = resolved.replace("IN ($status)", "IN (SELECT DISTINCT machine_status FROM sensor_readings)")

            query = {
                "queries": [{
                    "refId": target["refId"],
                    "datasource": {"type": "postgres", "uid": ds_uid},
                    "rawSql": resolved,
                    "format": target["format"],
                }],
                "from": "now-5y",
                "to": "now",
            }
            resp = requests.post(f"{grafana_url}/api/ds/query", headers=headers, json=query)
            status = "OK" if resp.status_code == 200 else "FAIL"
            n_rows = None
            if resp.status_code == 200:
                try:
                    frames = resp.json()["results"][target["refId"]]["frames"]
                    n_rows = sum(len(f["data"]["values"][0]) if f["data"]["values"] else 0 for f in frames)
                except Exception as e:
                    status = f"PARSE_ERR ({e})"
            print(f"[{status}] panel={panel['title']!r} refId={target['refId']} rows={n_rows} http={resp.status_code}")
            if resp.status_code != 200:
                print("   ", resp.text[:300])


if __name__ == "__main__":
    main()
