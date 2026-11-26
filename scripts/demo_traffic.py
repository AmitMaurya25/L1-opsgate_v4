"""Drive the REAL engine with the eval queries so the Grafana dashboard shows real (DEMO_MODE) metrics, without the Streamlit UI.
Usage: python -m scripts.demo_traffic   (Ctrl+C to stop). Don't run alongside the Streamlit app: both would bind the metrics port."""
import json, random, sys, tempfile, time, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
import telemetry
from engine import Engine

telemetry.start(); qs = json.loads((ROOT / 'data' / 'eval_queries.json').read_text()); e = Engine(Path(tempfile.mkdtemp()) / 'demo.db')
print(f'Serving metrics on :{telemetry.C.METRICS_PORT}; replaying {len(qs)} queries. Ctrl+C to stop.')
while True:
    q = random.choice(qs); o = uuid.uuid4().hex; _, t = e.act(o, {'kind': 'new'})
    for p in q.get('prior', []): e.act(o, {'kind': 'chat', 'thread': t, 'text': p})
    s, _ = e.act(o, {'kind': 'chat', 'thread': t, 'text': q['query']}); m = s['threads'][0]['messages'][-1]
    if m.get('hitl'): e.act(o, {'kind': random.choice(['approve', 'approve', 'reject']), 'thread': t, 'draft': m['hitl']['ticketId']})
    elif m['route'] in ('rag', 'tools') and random.random() < .6: e.act(o, {'kind': 'chat', 'thread': t, 'text': 'resolved'})
    time.sleep(random.uniform(.5, 2))
