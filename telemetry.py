"""Bounded aggregate metrics for the staff-only Grafana dashboard. No user/thread IDs, prompts or text exported.
Degrades to no-ops if prometheus_client is not installed."""
from threading import Lock
import config as C
try:
    from prometheus_client import Counter, Histogram, start_http_server
except ImportError:  # pragma: no cover
    class _N:
        def labels(self, *a, **k): return self
        def inc(self, *a, **k): pass
        def observe(self, *a, **k): pass
    Counter = lambda *a, **k: _N()
    Histogram = lambda *a, **k: _N()
    def start_http_server(*a, **k): pass

ROUTES = ('direct', 'rag', 'tools', 'hitl', 'verify', 'blocked')
TURNS = Counter('opsgate_turns', 'Completed agent turns', ['route'])
RESOLVED = Counter('opsgate_resolved', 'Confirmed resolved threads (explicit user confirmation)', ['route'])
TOKENS = Counter('opsgate_tokens', 'Token usage (source=provider|estimated)', ['route', 'kind', 'source'])
APPROVALS = Counter('opsgate_approvals', 'Committed approval decisions', ['decision'])
DRAFTS = Counter('opsgate_drafts', 'Ticket drafts proposed for approval')
TICKETS = Counter('opsgate_tickets', 'Committed mock tickets created')
LATENCY = Histogram('opsgate_latency_seconds', 'Turn latency', ['route'])
ERRORS = Counter('opsgate_errors', 'Failed engine events', ['type'])
BLOCKS = Counter('opsgate_guardrail_blocks', 'Guardrail / limit blocks', ['reason'])
RETRIEVAL = Counter('opsgate_retrieval', 'Retrieval outcomes', ['outcome'])
TOOLS = Counter('opsgate_tool_calls', 'Simulated tool calls', ['tool', 'status'])
LLM_RETRY = Counter('opsgate_llm_retries', 'Model-call retries (429/5xx/timeouts)')
LLM_FALLBACK = Counter('opsgate_llm_fallbacks', 'Answers served by deterministic fallback', ['reason'])

_lock = Lock(); _started = False

def start():
    global _started
    with _lock:
        if not _started:
            start_http_server(C.METRICS_PORT, addr=C.METRICS_ADDR); _started = True

def usage(route, input_tokens, output_tokens, cached_tokens=None, source='provider'):
    if route not in ROUTES or source not in ('provider', 'estimated'): raise ValueError('invalid labels')
    for kind, n in (('input', input_tokens), ('output', output_tokens), ('cached', cached_tokens)):
        if n is not None:
            if n < 0: raise ValueError('negative tokens')
            TOKENS.labels(route, kind, source).inc(n)
