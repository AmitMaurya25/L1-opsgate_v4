"""Central, env-driven configuration. Secrets only from environment / .env (never committed)."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # optional
    pass

def _i(k, d): return int(os.getenv(k, d))
def _f(k, d): return float(os.getenv(k, d))

DEMO_MODE = os.getenv('DEMO_MODE', 'true').lower() != 'false'   # true = deterministic extractive answers, no model call
MODEL = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
MAX_INPUT_CHARS = _i('MAX_INPUT_CHARS', 1500)
MAX_TOOL_CALLS = _i('MAX_TOOL_CALLS', 5)
APPROVAL_TTL = _i('APPROVAL_TTL_SECONDS', 900)
RATE_PER_MIN = _i('RATE_PER_MIN', 12)             # cost control: turns per owner per minute
SESSION_TOKENS = _i('SESSION_TOKEN_BUDGET', 60000)  # cost control: tokens per session
REL_MIN = _f('REL_MIN', 0.35)                     # relevance gate (idf-weighted query-term coverage), calibrated in docs/EVAL_REPORT.md
LLM_ATTEMPTS = _i('LLM_ATTEMPTS', 3)
BACKOFF_BASE = _f('BACKOFF_BASE', 0.4)
METRICS_ADDR = os.getenv('METRICS_ADDR', '0.0.0.0')  # restrict by firewall; staff-only
METRICS_PORT = _i('METRICS_PORT', 9464)

def validate():
    if not DEMO_MODE and not os.getenv('OPENAI_API_KEY'):
        raise RuntimeError('DEMO_MODE=false requires OPENAI_API_KEY in the environment or .env')
