"""Generate a public-safe variant of dashboard.json.

Grafana's public/shared dashboards do not support template variables at all
(the whole dashboard is rejected, or renders with no data, if any variable is
present). This dashboard uses $machine and $status in nearly every panel
query, so the interactive dashboard.json can't be shared publicly as-is.

This script strips the `machine_id IN ($machine)` / `machine_status IN
($status)` filter clauses (falling back to "all machines / all statuses",
same as the interactive dashboard's default) and removes the templating
section entirely, writing the result to dashboard_public.json. Push that
file (not dashboard.json) with push_dashboard.py when creating the public
share.

Usage:
    python grafana/build_public_dashboard.py
"""
import json
from pathlib import Path

SRC = Path(__file__).resolve().parent / "dashboard.json"
DST = Path(__file__).resolve().parent / "dashboard_public.json"


def main():
    dashboard = json.loads(SRC.read_text())

    dashboard["uid"] = "smart-mfg-iot-public"
    dashboard["title"] = "Smart Manufacturing IoT Monitoring (Public)"
    dashboard["templating"] = {"list": []}

    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            sql = target.get("rawSql")
            if not sql:
                continue
            sql = sql.replace(" AND machine_id IN ($machine)", "")
            sql = sql.replace(" AND machine_status IN ($status)", "")
            target["rawSql"] = sql

    DST.write_text(json.dumps(dashboard, indent=2))
    print(f"Wrote {DST}")
    print("Next: python grafana/push_dashboard.py grafana/dashboard_public.json")


if __name__ == "__main__":
    main()
