"""OpsGate engine: guardrails -> deterministic router -> (hybrid RAG | simulated tools | direct | HITL draft) -> verified, cited answer.
SQLite owns state; approvals are atomic, hash-checked, expiring and idempotent. All infrastructure/ITSM is simulated."""
import hashlib, html, json, re, sqlite3, time, uuid
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, ValidationError
import config as C, guard, kb as KBM, tools as T, llm, telemetry as M

CAT = {'KB-102': 'Network/VPN', 'KB-110': 'Network/VPN', 'KB-204': 'Messaging/Outlook', 'KB-210': 'Messaging/Outlook',
       'KB-301': 'Identity/MFA', 'KB-310': 'Identity/MFA', 'KB-702': 'Identity/MFA', 'KB-401': 'Hardware/Print',
       'KB-501': 'Hardware/Print', 'KB-601': 'NDMC/Portal', 'KB-701': 'General'}
TEAMS = {'Network/VPN': 'Network-Ops', 'Messaging/Outlook': 'Workplace-Support', 'Identity/MFA': 'IAM-L2',
         'Hardware/Print': 'Endpoint-Field-Ops', 'NDMC/Portal': 'NDMC-Portal-Ops', 'General': 'Workplace-Support'}
PEOPLE = {'Network/VPN': 'Rohan Verma (L2 Network Engineer)', 'Identity/MFA': 'Ananya Nair (Senior IAM Specialist)',
          'Messaging/Outlook': 'Vikram Sethi (L2 Messaging Engineer)', 'Hardware/Print': 'Pooja Sharma (L2 Endpoint Specialist)'}
HASHED = ('ticketId', 'category', 'priority', 'impact', 'urgency', 'summary', 'evidence', 'thread', 'actor')

RESOLVED_RE = re.compile(r"^\s*(resolved|fixed|solved|it'?s (working|fixed|resolved)( now)?|that (worked|fixed it)|yes,? ?(it'?s )?(resolved|fixed|working))\b")
EXPLICIT_ESC = re.compile(r"raise (a )?ticket|escalat|cannot resolve|can'?t resolve|lost my (phone|device|token)|speak to (a )?human|talk to (a )?human|not satisfied")
SOFT_FAIL = re.compile(r"\bstill (get|getting|fail|not|can'?t|doesn)|didn'?t work|did not work|none of (that|these)")
TOOLS_RE = re.compile(r"\b(logs?|diagnos\w*|device context|sandbox|grievance|311|water supply|electricity|ndmc|service status|outage|network status)\b|GRV-?\d", re.I)
GREET_RE = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening))\b|who are you|what (issues|can you)\b")
FOLLOW_RE = re.compile(r"\b(it|this|that|again|still|same)\b")

class Event(BaseModel):
    model_config = ConfigDict(extra='forbid')   # strict schema: unknown fields rejected
    kind: Literal['new', 'chat', 'approve', 'reject']
    thread: Optional[str] = Field(None, max_length=64)
    text: Optional[str] = Field(None, max_length=20000)
    draft: Optional[str] = Field(None, max_length=64)
    nonce: Optional[str] = Field(None, max_length=64)

def draft_hash(d): return hashlib.sha256(json.dumps({k: d[k] for k in HASHED}, sort_keys=True).encode()).hexdigest()

def render(text, labels):
    """Escape everything, then turn ONLY known citation labels into chips (no model-generated HTML ever reaches the UI)."""
    out = html.escape(text)
    for lb in labels: out = out.replace(f'[{html.escape(lb)}]', f'<span class="cite-tag">{html.escape(lb)}</span>')
    return out.replace('\n', '<br>')

class Engine:
    def __init__(self, path='state.db', kb=None):
        C.validate()
        self.db = sqlite3.connect(path, timeout=10); self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS sessions (owner TEXT PRIMARY KEY, data TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS audit (ts REAL, actor TEXT, event TEXT, detail TEXT)')
        self.kb = kb or KBM.get_kb(); self._m = []

    def load(self, owner):
        row = self.db.execute('SELECT data FROM sessions WHERE owner=?', (owner,)).fetchone()
        return json.loads(row[0]) if row else {'threads': [], 'tickets': [], 'drafts': {}}

    # ---- helpers -------------------------------------------------------------------------------------------
    def _e(self, metric, *labels, n=1): self._m.append(lambda: (metric.labels(*labels) if labels else metric).inc(n))
    def _audit(self, owner, event, detail=''):
        self.db.execute('INSERT INTO audit VALUES (?,?,?,?)', (time.time(), hashlib.sha256(owner.encode()).hexdigest()[:8], event, guard.redact(detail)[:200]))
    def _msg(self, route, path, text, labels=(), **kw):
        return dict(sender='agent', route=route, path=path, text=render(text, labels), **kw)

    # ---- public API ----------------------------------------------------------------------------------------
    def act(self, owner, event):
        t0 = time.monotonic(); self._m = []; route = None
        try: ev = Event(**event)
        except (ValidationError, TypeError): M.ERRORS.labels('invalid_event').inc(); return self.load(owner), None
        self.db.execute('BEGIN IMMEDIATE')
        try:
            s = self.load(owner); t = next((x for x in s['threads'] if x['id'] == ev.thread), None)
            if ev.kind == 'new':
                t = {'id': uuid.uuid4().hex, 'title': 'New Support Chat', 'group': 'today', 'messages': [], 'steps': [], 'evidence': []}
                s['threads'].insert(0, t)
            elif ev.kind == 'chat' and t and (ev.text or '').strip():
                q = ev.text.strip(); a = self._turn(q, t, s, owner); route = a['route']
                t['messages'] += [{'sender': 'user', 'text': q if route != 'blocked' else '[blocked input]'}, a]
                if t['title'] == 'New Support Chat' and route != 'blocked': t['title'] = q[:28]
                self._e(M.TURNS, route)
            elif ev.kind in ('approve', 'reject') and t: self._decide(ev, t, s, owner)
            self.db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (owner, json.dumps(s))); self.db.commit()
        except Exception:
            self.db.rollback(); M.ERRORS.labels('engine').inc(); raise
        for f in self._m: f()     # metrics only after a committed transaction
        if route: M.LATENCY.labels(route).observe(time.monotonic() - t0)
        return s, (t['id'] if t else None)

    # ---- one chat turn -------------------------------------------------------------------------------------
    def _turn(self, q, t, s, owner):
        now = time.time(); tr = []
        s['rl'] = [x for x in s.get('rl', []) if now - x < 60]
        if len(s['rl']) >= C.RATE_PER_MIN or s.get('tok', 0) >= C.SESSION_TOKENS:
            self._e(M.BLOCKS, 'limit'); return self._msg('blocked', 'Path 1 · Limit', 'Usage limit reached for this session. Please wait a minute or start a new session.', trace=['limit'])
        s['rl'].append(now)
        code = guard.check(q)
        if code:
            self._e(M.BLOCKS, code); self._audit(owner, 'blocked', code)
            return self._msg('blocked', 'Blocked', guard.MESSAGES[code], trace=['guardrail:' + code])
        tr.append('guardrail:ok'); low = q.lower()
        if RESOLVED_RE.search(low) and t.get('last_route') in ('rag', 'tools'):
            if not t.get('resolved'): t['resolved'] = True; self._e(M.RESOLVED, t['last_route'])
            return self._msg('verify', 'Verification', 'Great - I have recorded this as resolved based on your confirmation.', trace=tr + ['route:VERIFY'])
        if EXPLICIT_ESC.search(low) or (SOFT_FAIL.search(low) and t.get('steps')):
            t['last_route'] = 'hitl'; return self._hitl(q, t, s, owner, tr + ['route:HITL'])
        if TOOLS_RE.search(q): t['last_route'] = 'tools'; return self._tools(q, t, s, owner, tr + ['route:TOOLS'])
        if len(q) <= 40 and GREET_RE.search(low):
            return self._msg('direct', 'Path 1 · Direct Chat', 'I am the OpsGate L1 Virtual Agent. I can help with VPN, MFA, Outlook, printers and network issues, check synthetic diagnostics, and escalate to the right team with your approval.', trace=tr + ['route:DIRECT'])
        t['last_route'] = 'rag'; return self._rag(q, t, s, owner, tr + ['route:RAG'])

    def _answer(self, q, t, s, route, ev, envs, tr):
        hist = [m['text'] for m in t['messages'] if m['sender'] == 'user' and m['text'] != '[blocked input]']
        res = llm.synthesize(q, ev, envs, hist, on_retry=lambda: self._e(M.LLM_RETRY))
        if res['fallback']: self._e(M.LLM_FALLBACK, res['fallback']); tr.append('fallback:' + res['fallback'])
        u = res['usage']
        if u:
            s['tok'] = s.get('tok', 0) + u['input'] + u['output']
            self._m.append(lambda: M.usage(route, u['input'], u['output'], u['cached'], u['source']))
        return res

    def _rag(self, q, t, s, owner, tr):
        ev = self.kb.evidence(q, 3); outcome = 'grounded'
        if not ev and FOLLOW_RE.search(q.lower()) and t.get('last_q') and len(q.split()) <= 8:   # bounded replan: one query rewrite
            ev = self.kb.evidence(t['last_q'] + ' ' + q, 3); outcome = 'retried'; tr.append('replan:1')
        else: t['last_q'] = q
        if not ev:
            self._e(M.RETRIEVAL, 'abstained')
            return self._msg('rag', 'Path 2 · Abstain (no KB evidence)', "I couldn't find a documented answer for that, so I won't guess. Please tell me the affected service (VPN, MFA, Outlook, printer, network) and any error message, or ask me to raise a ticket.", outcome='abstained', trace=tr + ['retrieval:0', 'verify:abstain'])
        self._e(M.RETRIEVAL, outcome); seen = set(t['evidence']); ev.sort(key=lambda h: h['chunk_id'] in seen)   # prefer steps not yet tried
        res = self._answer(q, t, s, 'rag', ev, [], tr)
        t['evidence'] += [i for i in res['cited'] if i not in seen]; t['steps'].append('KB ' + ', '.join(KBM.label(h) for h in ev[:2]))
        t['category'] = CAT.get(ev[0]['article_id'], t.get('category', 'General'))
        return self._msg('rag', 'Path 2 · Hybrid RAG', res['text'], [KBM.label(h) for h in ev], outcome='grounded', cites=res['cited'], est_in=res['est_in'], trace=tr + [f'retrieval:{len(ev)}', 'verify:citations_ok'])

    def _tools(self, q, t, s, owner, tr):
        calls, ask = T.plan(q)
        if ask: return self._msg('tools', 'Path 3 · Tools & Sandbox', ask, outcome='clarify', trace=tr + ['clarify'])
        envs = [T.call(n, a, owner) for n, a in calls[:C.MAX_TOOL_CALLS]]
        for e in envs: self._e(M.TOOLS, e['tool'], e['status'])
        sig = next((e['data']['vpn_error_signature'] for e in envs if e['status'] == 'ok' and e['data'] and 'vpn_error_signature' in e['data']), None)
        ev = self.kb.evidence(f'vpn error {sig}' if sig else q, 2)   # diagnostic signature drives the KB lookup
        self._e(M.RETRIEVAL, 'grounded' if ev else 'abstained')
        res = self._answer(q, t, s, 'tools', ev, envs, tr)
        t['evidence'] += [i for e in envs for i in e['evidence_ids']] + res['cited']; t['steps'].append('Diagnostics: ' + ', '.join(e['tool'] for e in envs))
        if ev: t['category'] = CAT.get(ev[0]['article_id'], 'General')
        return self._msg('tools', 'Path 3 · Tools & Sandbox', res['text'], [KBM.label(h) for h in ev], outcome='grounded', cites=res['cited'], est_in=res['est_in'], trace=tr + [f'tools:{len(envs)}', f'retrieval:{len(ev)}', 'verify:citations_ok'])

    # ---- human-in-the-loop ticket draft --------------------------------------------------------------------
    def _hitl(self, q, t, s, owner, tr):
        top = self.kb.search(q, 1); cat = CAT.get(top[0]['article_id']) if top and top[0]['relevance'] >= C.REL_MIN else None
        cat = cat or t.get('category', 'General'); t['category'] = cat
        ex = next((x for x in s['tickets'] if x['category'] == cat and cat != 'General'), None)
        if ex: return self._msg('hitl', 'Path 4 · HITL', f"A mock ticket ({ex['id']}) already covers this category. See Raised Tickets.", outcome='duplicate', trace=tr + ['duplicate'])
        if any(d['thread'] == t['id'] and d['status'] == 'pending' and d['expires'] > time.time() for d in s['drafts'].values()):
            return self._msg('hitl', 'Path 4 · HITL', 'An approval is already pending in this conversation.', outcome='pending', trace=tr + ['pending'])
        urgency = 'high' if re.search(r"lost|cannot (work|log)|can'?t (work|log)|urgent", q.lower()) else 'medium'
        d = {'ticketId': 'INC-' + uuid.uuid4().hex[:10].upper(), 'category': cat, 'impact': 'individual', 'urgency': urgency,
             'priority': T.priority('individual', urgency), 'summary': f'{cat}: unresolved after L1 troubleshooting', 'evidence': list(t['evidence']),
             'stepsAttempted': list(t['steps']) or ['User requested escalation'], 'thread': t['id'], 'actor': hashlib.sha256(owner.encode()).hexdigest()[:8],
             'approved': False, 'status': 'pending', 'expires': time.time() + C.APPROVAL_TTL, 'version': 1}
        d['hash'] = draft_hash(d); s['drafts'][d['ticketId']] = d; self._e(M.DRAFTS); self._audit(owner, 'draft_created', d['ticketId'])
        return self._msg('hitl', 'Path 4 · HITL', 'I could not resolve this at L1. Review the draft below - nothing is created until you approve.', outcome='draft', hitl=dict(d), trace=tr + [f'draft:{d["priority"]}'])

    def _decide(self, ev, t, s, owner):
        d = s['drafts'].get(ev.draft)
        if not (d and d['thread'] == t['id'] and d['status'] == 'pending'): return    # unknown / foreign / already decided -> no-op (idempotent)
        status = 'invalid' if d['hash'] != draft_hash(d) else 'expired' if time.time() > d['expires'] else ev.kind
        d['status'] = status; self._e(M.APPROVALS, status); self._audit(owner, 'decision', f"{d['ticketId']}:{status}")
        if status == 'approve' and not any(x['id'] == d['ticketId'] for x in s['tickets']):
            c = d['category']; s['tickets'].insert(0, {'id': d['ticketId'], 'title': c + ' — Escalated via L1 Agent', 'category': c, 'priority': d['priority'],
                       'status': 'In-Progress', 'team': TEAMS[c], 'assignee': PEOPLE.get(c, 'Suresh Kumar (L2 Support Engineer)'), 'simulated': True})
            self._e(M.TICKETS); self._audit(owner, 'ticket_created', d['ticketId'])
        note = {'reject': 'Approval rejected - no ticket created.', 'expired': 'Approval expired - no ticket created.', 'invalid': 'Draft failed its integrity check - no ticket created.'}
        for m in t['messages']:
            if m.get('hitl', {}).get('ticketId') == d['ticketId']:
                if status == 'approve': m['hitl']['approved'] = True
                else: m.pop('hitl', None); m['text'] += ' ' + note[status]
