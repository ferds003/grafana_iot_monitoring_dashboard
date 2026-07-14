# Grafana Cloud — PostgreSQL data source setup (manual, one-time)

1. Log into your Grafana Cloud stack: `https://<you>.grafana.net`
2. Left nav → Connections → Data sources → Add data source → PostgreSQL
3. Fill in:
   - Host: `<supabase-host>:5432` (or `:6543` for the Supavisor pooler)
   - Database: `postgres`
   - User: from Supabase project settings
   - Password: from Supabase project settings
   - TLS/SSL Mode: `require`
   - Version: 15 (or match your Supabase Postgres version)
4. Click "Save & test" — should show "Database Connection OK".

## If the connection fails
- Supabase's **direct** connection is IPv6-first. Grafana Cloud's outbound
  network is IPv4. Use the **Supavisor session pooler** hostname instead
  (found in Supabase → Project Settings → Database → Connection pooling).
  It looks like `aws-0-<region>.pooler.supabase.com` on port `5432` or `6543`.
- Make sure `sslmode=require` (or `verify-full`) is set.

## Getting a service account token (for API-based dashboard provisioning)
1. Grafana Cloud → Administration → Service accounts → Add service account
   (role: Editor).
2. Add a token, copy it into `.env` as `GRAFANA_TOKEN`.
3. `GRAFANA_URL` = your stack URL, e.g. `https://<you>.grafana.net`.

Once both `GRAFANA_URL` and `GRAFANA_TOKEN` are set, dashboards can be pushed
programmatically with a script like:

```
curl -X POST "$GRAFANA_URL/api/dashboards/db" \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d @grafana/dashboard.payload.json
```

(`dashboard.payload.json` wraps `dashboard.json` in `{"dashboard": ..., "overwrite": true}` —
see `grafana/push_dashboard.py`.)
