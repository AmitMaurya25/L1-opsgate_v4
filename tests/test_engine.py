import json, threading
import config as C, llm, tools as T
from kb import get_kb
from tests.helpers import new, say, draft

def test_approval_idempotent_and_isolated(tmp_path):
    e, t = new(tmp_path / 'db'); d = draft(e, t); assert not e.load('a')['tickets']
    s, _ = e.act('a', {'kind': 'approve', 'thread': t, 'draft': d}); assert len(s['tickets']) == 1
    s, _ = e.act('a', {'kind': 'approve', 'thread': t, 'draft': d}); assert len(s['tickets']) == 1
    assert not e.load('b')['tickets']

def test_concurrent_approvals_create_one_ticket(tmp_path):
    e, t = new(tmp_path / 'db'); d = draft(e, t); from engine import Engine
    def go():
        Engine(tmp_path / 'db').act('a', {'kind': 'approve', 'thread': t, 'draft': d})
    th = [threading.Thread(target=go) for _ in range(4)]; [x.start() for x in th]; [x.join() for x in th]
    assert len(e.load('a')['tickets']) == 1

def test_approval_survives_restart(tmp_path):
    e, t = new(tmp_path / 'db'); d = draft(e, t); from engine import Engine
    s, _ = Engine(tmp_path / 'db').act('a', {'kind': 'approve', 'thread': t, 'draft': d}); assert len(s['tickets']) == 1

def test_unknown_asks_clarification(tmp_path):
    e, t = new(tmp_path / 'db'); _, m = say(e, t, 'banana'); assert m['outcome'] == 'abstained'

def test_greeting_skips_retrieval_and_tools(tmp_path):
    e, t = new(tmp_path / 'db'); _, m = say(e, t, 'hello'); assert m['route'] == 'direct' and 'cites' not in m

def test_vpn_multipath_tools_then_rag_then_verify(tmp_path):
    e, t = new(tmp_path / 'db'); _, m = say(e, t, 'Check my device context and recent VPN error log')
    assert m['route'] == 'tools' and 'KB-102-2.1' in m['cites'] and 'no real device' in m['text'].lower()
    s, m2 = say(e, t, 'resolved'); assert m2['route'] == 'verify'

def test_failed_steps_not_repeated_and_escalation_after_failure(tmp_path):
    e, t = new(tmp_path / 'db'); _, a = say(e, t, "My VPN won't connect on macOS"); _, b = say(e, t, "My VPN won't connect on macOS")
    assert a['cites'] != b['cites'] or len(a['cites']) == 1
    _, c = say(e, t, 'I tried those steps and still get Error 809'); assert c['route'] == 'hitl' and c['hitl']['category'] == 'Network/VPN'

def test_retrieval_irrelevant_cannot_pass_on_rrf_alone():
    assert get_kb().evidence('purple elephants dancing') == []
    assert all(h['rrf'] > 0 for h in get_kb().search('vpn error 809'))   # RRF ranks; the relevance gate decides

def test_citations_resolve_to_kb(tmp_path):
    e, t = new(tmp_path / 'db'); _, m = say(e, t, 'Outlook is not syncing my email'); assert set(m['cites']) <= get_kb().ids

def test_tools_validate_args_and_cap():
    assert T.call('ndmc_water_supply_status', {'ward': 999}, 'a')['error'] == 'invalid_args'
    assert T.call('rm_rf', {}, 'a')['error'] == 'unknown_tool'
    assert T.call('get_user_context', {'x': 1}, 'a')['error'] == 'invalid_args'
    assert len(T.plan('diagnose my network show logs')[0]) <= C.MAX_TOOL_CALLS
    assert all(T.call(n, a, 'a')['simulated'] for n, a in T.plan('check my device logs')[0])

def test_priority_matrix_deterministic():
    assert T.priority('individual', 'high') == 'P2' and T.priority('site', 'high') == 'P1' and T.priority('individual', 'low') == 'P4'

def test_retry_recovers_then_exhausts():
    C.BACKOFF_BASE = 0; n = {'c': 0}
    def flaky():
        n['c'] += 1
        if n['c'] < 3: raise llm.SimulatedRateLimit()
        return 'ok'
    assert llm.call_with_retry(flaky) == 'ok' and n['c'] == 3
    def dead(): raise llm.SimulatedRateLimit()
    try: llm.call_with_retry(dead); assert False
    except llm.LLMUnavailable: pass

def test_live_mode_invalid_citation_falls_back(monkeypatch):
    ev = get_kb().evidence('VPN error 809', 2); monkeypatch.setattr(C, 'DEMO_MODE', False)
    monkeypatch.setattr(llm, '_live', lambda m: ({'answer': 'made up', 'cited': ['FAKE-9.9']}, {'input': 10, 'output': 5, 'cached': None, 'source': 'provider'}))
    r = llm.synthesize('VPN error 809', ev, []); assert r['fallback'] == 'invalid_citation' and set(r['cited']) <= {h['chunk_id'] for h in ev}

def test_live_mode_valid_answer_uses_provider_usage(monkeypatch):
    ev = get_kb().evidence('VPN error 809', 1); cid = ev[0]['chunk_id']; monkeypatch.setattr(C, 'DEMO_MODE', False)
    monkeypatch.setattr(llm, '_live', lambda m: ({'answer': 'ok', 'cited': [cid]}, {'input': 100, 'output': 20, 'cached': None, 'source': 'provider'}))
    r = llm.synthesize('VPN error 809', ev, []); assert r['fallback'] is None and r['usage']['source'] == 'provider' and r['usage']['cached'] is None

def test_html_never_reaches_ui(tmp_path):
    e, t = new(tmp_path / 'db'); _, m = say(e, t, '<img src=x onerror=alert(1)> printer offline'); assert '<img' not in json.dumps(m['text'])
