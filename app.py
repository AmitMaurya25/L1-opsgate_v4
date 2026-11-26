import hmac, os, uuid
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import telemetry
from engine import Engine

st.set_page_config(layout='wide', page_title='OpsGate L1 Virtual Agent')
st.markdown('<style>[data-testid="stHeader"]{display:none}.stApp{background:#f8fafc}.block-container{padding:0;max-width:none}</style>', unsafe_allow_html=True)
telemetry.start()   # staff-only Prometheus endpoint (see docs/OBSERVABILITY.md); employees never see metrics or Grafana
# Staff view (trace line + architecture tab): demo-grade shared token. Replace with SSO/role claims in production.
_tok = os.getenv('OPSGATE_STAFF_TOKEN'); _q = st.query_params.get('staff')
staff = bool(_tok and _q and hmac.compare_digest(_tok, _q))
if 'owner' not in st.session_state: st.session_state.owner = uuid.uuid4().hex   # ephemeral demo identity
engine = Engine(); owner = st.session_state.owner
if 'active' not in st.session_state: _, st.session_state.active = engine.act(owner, {'kind': 'new'})
state = engine.load(owner)
ui = components.declare_component('opsgate', path=str(Path(__file__).parent / 'frontend'))
event = ui(state=state, active=st.session_state.active, staff=staff, key='workspace', default=None)
if event and event.get('nonce') != st.session_state.get('nonce'):
    st.session_state.nonce = event['nonce']; _, active = engine.act(owner, event)
    st.session_state.active = active or st.session_state.active; engine.db.close(); st.rerun()
engine.db.close()
