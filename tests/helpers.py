import json
from engine import Engine

def new(path, owner='a'):
    e = Engine(path); s, t = e.act(owner, {'kind': 'new'}); return e, t

def say(e, t, text, owner='a'):
    s, _ = e.act(owner, {'kind': 'chat', 'thread': t, 'text': text})
    th = next(x for x in s['threads'] if x['id'] == t)
    return s, th['messages'][-1]

def mutate(e, owner, fn):
    s = e.load(owner); fn(s); e.db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (owner, json.dumps(s))); e.db.commit()

def draft(e, t, owner='a'):
    s, m = say(e, t, 'I lost my phone and cannot complete the MFA prompt', owner)
    return m['hitl']['ticketId']
