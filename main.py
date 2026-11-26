"""Foundry-template entrypoint (local run: `azd ai agent run`, port 8088). Wraps the OpsGate engine as ONE tool of a Foundry agent.
UNVERIFIED against the organizer's tested package versions - see NEXT_STEPS.md. The Streamlit app (app.py) is the demo UI; both share engine.py."""
import os, uuid
from dotenv import load_dotenv
load_dotenv()
from engine import Engine
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_foundry_hosting import ResponsesHostServer

key = os.getenv('OPENAI_API_KEY')
if not key: raise RuntimeError('Set OPENAI_API_KEY in .env')
_engine = Engine(os.getenv('OPSGATE_DB', 'foundry_state.db')); _owner = uuid.uuid4().hex; _thread = {}

def opsgate_triage(message: str) -> str:
    """Answer an L1 IT support question using the OpsGate guarded pipeline (cited KB, simulated tools, approval-gated tickets)."""
    if 'id' not in _thread: _, _thread['id'] = _engine.act(_owner, {'kind': 'new'})
    s, _ = _engine.act(_owner, {'kind': 'chat', 'thread': _thread['id'], 'text': message})
    m = next(t for t in s['threads'] if t['id'] == _thread['id'])['messages'][-1]
    return m['text'].replace('<br>', '\n') + ('\n[Ticket draft pending human approval in the OpsGate UI]' if m.get('hitl') else '')

agent = Agent(client=OpenAIChatClient(model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), api_key=key),
              instructions='You are the OpsGate L1 IT support agent. Always call opsgate_triage for the user question and relay its answer and citations faithfully.',
              tools=[opsgate_triage])
if __name__ == '__main__': ResponsesHostServer(agent).run()
