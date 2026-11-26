# Staff-only monitoring (Grafana + Prometheus)

Audience: **IT team and developers only.** The chat UI has no link to it; Grafana is bound to `127.0.0.1:3000`, anonymous access and sign-up are off, theme is light.

## Run
```powershell
python -m scripts.demo_traffic            # real engine + eval queries -> real DEMO_MODE metrics on :9464 (or run the Streamlit app instead)
cd observability; "GRAFANA_PASSWORD=choose-a-strong-one" | Out-File -Encoding ascii .env
docker compose up -d                      # http://localhost:3000  (admin / your password)
python gen_dashboard.py                   # regenerate performance.json after editing the panel code
```
**Not validated against a live Grafana/Docker in this build** (metrics endpoint and dashboard JSON structure were checked; panels were not rendered).

## Access model
- Create staff users with the **Viewer** role (or configure Entra/OIDC via `GF_AUTH_GENERIC_OAUTH_*`) and expose Grafana only through the corporate VPN/reverse proxy. Developers may get Editor; employees get nothing.
- The metrics port (9464) has no auth: firewall it to the Prometheus host. Metrics are aggregate only (no user/thread IDs, prompts or text).
- In the app, `?staff=<OPSGATE_STAFF_TOKEN>` only reveals the per-message trace and architecture tab; it is a demo gate, replace with SSO roles.

## Interactivity
Variables **Route / Token source / Tool** filter the panels; clicking a bar in *Turns by route* drills into that route (`var-route` URL); *Reset filters* link; shared crosshair; 10 s refresh; table legends with mean/max. Sections: Overview · Quality & safety · Performance & cost · Human approval.

## Metric caveats
Counters reset on restart (not an audit ledger). "Resolution confirmations" = explicit user confirmations ÷ answered turns, not a measured resolution rate. Tokens show `source=estimated` (chars/4) in DEMO_MODE; provider counts and cached tokens appear only for live calls that return them. Latency is local processing time.
