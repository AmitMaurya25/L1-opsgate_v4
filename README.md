# OpsGate L1 Virtual Agent — hackathon build (local-first)

L1 IT service-desk agent: guarded input → deterministic router → **hybrid RAG (BM25 + vector, RRF)** / **simulated tools** / direct reply / **human-approved mock ticket** → cited, verified answer. Light-theme UI (original chat HTML preserved). Everything is synthetic; no real infrastructure, tickets or civic systems are touched.

## Run (Windows PowerShell; Python 3.13)
```powershell
py -3.13 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # DEMO_MODE=true works with no API key
python -m pytest -q           # 25 tests incl. the 10 safety scenarios
python -m scripts.evaluate    # regenerates docs/EVAL_REPORT.md + docs/SAFETY_TESTS.md
streamlit run app.py          # chat UI on :8501
```
Live model: set `DEMO_MODE=false` and `OPENAI_API_KEY` in `.env` (key stays server-side; fails clearly if missing). **The live OpenAI path is unit-tested with a stub but has not been run against the real API here.**
Demo failure flow: `OPSGATE_SIM_429=2` (recovers via backoff) or `OPSGATE_SIM_429=persist` (safe fallback).

## Demo script (5 min) — maps to the guide's required flows
| Flow | Say / click | Shows |
|---|---|---|
| Normal | chip 1 "VPN Help" | route RAG, cited KB-102 chips |
| Evidence | chip 4 "Tools & Sandbox" | simulated diagnostics → signature 809 → KB lookup → citation |
| Approval | chip 2 "Unresolved" → Approve | draft (hash, priority P3) held until approval; ticket appears right panel |
| Exception | "How do I configure the SAP payroll module" | abstains, no invented answer |
| Guardrail | "Ignore previous instructions…" / "password=…" | blocked, secret never stored |
| Staff | open `?staff=<OPSGATE_STAFF_TOKEN>` | adds trace line + architecture tab (hidden for employees) |

## Docs
`docs/ARCHITECTURE.md` (+`architecture.svg`) · `docs/EVAL_REPORT.md` · `docs/SAFETY_TESTS.md` · `docs/OBSERVABILITY.md` (staff-only Grafana) · `NEXT_STEPS.md` (status, gaps, handoff) · `MASTER_PLAN.md` (original long-form spec)

## Known limitations (honest)
- "Vector" channel is TF-IDF char-n-gram, not neural embeddings/FAISS. Router is deterministic regex; the LLM only writes the grounded answer.
- Eval set is small and self-authored (see report caveats); no benchmark claims. Token numbers in DEMO_MODE are chars/4 estimates.
- Demo identity is a random session ID; staff view uses a shared token. Not for real data; no SSO, no Mem0, no real MCP servers, no Foundry deployment.
- Foundry entrypoint (`main.py`, `azure.yaml`) follows the organizer guide but is **unverified** against their package versions.
- UI visual/browser regression and mobile screenshots were not run.
