"""Read-only, schema-validated, SIMULATED tools (fixtures). Envelope: {tool, request_id, status, simulated, data, evidence_ids, error}.
No shell, no network, no real device/ticket/civic-system access. Results are untrusted data and never grant permissions."""
import re, uuid, hashlib
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
import config as C

class _M(BaseModel): model_config = ConfigDict(extra='forbid')
class NoArgs(_M): pass
class Grievance(_M): ref_id: str = Field(pattern=r'^GRV-\d{5,8}$')
class Ward(_M): ward: int = Field(ge=1, le=104)
class Service(_M): service: Literal['vpn', 'outlook', 'mfa', 'print', 'network', 'ndmc_portal']
class Sla(_M):
    impact: Literal['individual', 'team', 'site']; urgency: Literal['low', 'medium', 'high']; vip: bool = False

_PRI = {('site', 'high'): 'P1', ('site', 'medium'): 'P2', ('team', 'high'): 'P2', ('individual', 'high'): 'P2',
        ('team', 'medium'): 'P3', ('site', 'low'): 'P3', ('individual', 'medium'): 'P3'}
_SLA_H = {'P1': 1, 'P2': 4, 'P3': 8, 'P4': 24}

def priority(impact, urgency, vip=False):
    p = _PRI.get((impact, urgency), 'P4')
    return ('P' + str(max(1, int(p[1]) - 1))) if vip and p != 'P1' else p

def _grievance(a, owner):
    n = int(a.ref_id[4:]); st = ['Registered', 'In progress', 'Resolved'][n % 3]
    return {'ref_id': a.ref_id, 'status': st, 'ward': n % 104 + 1, 'sla_days': 7}
def _water(a, owner): return {'ward': a.ward, 'status': 'Scheduled maintenance' if a.ward % 2 else 'Normal supply'}
def _health(a, owner): return {'service': a.service, 'status': 'degraded' if a.service == 'ndmc_portal' else 'operational'}
def _ctx(a, owner): return {'os': 'macOS 14', 'device': 'MacBook-Pro-09', 'vpn_client': 'AnyConnect 5.1', 'user': 'principal:' + hashlib.sha256(owner.encode()).hexdigest()[:6]}
def _net(a, owner): return {'internet': 'reachable', 'dns': 'resolves', 'vpn_gateway': 'vpn.corp.local TLS handshake timeout', 'vpn_error_signature': '809'}
def _logs(a, owner): return {'lines_scanned': 200, 'signatures': ['VPN_ERR_809: IKE negotiation timeout (UDP 500/4500)']}
def _sla(a, owner): p = priority(a.impact, a.urgency, a.vip); return {'priority': p, 'sla_hours': _SLA_H[p]}

REGISTRY = {  # name -> (input model, fn, summary)
    'ndmc_311_grievance_lookup': (Grievance, _grievance, lambda d: f"Grievance {d['ref_id']}: {d['status']} (ward {d['ward']}, SLA {d['sla_days']} days) - synthetic NDMC fixture."),
    'ndmc_water_supply_status': (Ward, _water, lambda d: f"Ward {d['ward']} water supply: {d['status']} - synthetic fixture."),
    'check_service_health': (Service, _health, lambda d: f"Service '{d['service']}' is {d['status']}."),
    'get_user_context': (NoArgs, _ctx, lambda d: f"Device {d['device']} ({d['os']}), VPN client {d['vpn_client']}."),
    'check_network_status': (NoArgs, _net, lambda d: f"Internet {d['internet']}, DNS {d['dns']}; VPN gateway: {d['vpn_gateway']}."),
    'parse_system_logs': (NoArgs, _logs, lambda d: f"Log signature found: {d['signatures'][0]}."),
    'calculate_sla_priority': (Sla, _sla, lambda d: f"Priority {d['priority']} (SLA {d['sla_hours']}h)."),
}

def call(name, args, owner):
    env = {'tool': name, 'request_id': uuid.uuid4().hex[:8], 'status': 'ok', 'simulated': True, 'data': None, 'evidence_ids': [f'TOOL:{name}'], 'error': None}
    if name not in REGISTRY: return {**env, 'status': 'error', 'error': 'unknown_tool'}
    model, fn, _ = REGISTRY[name]
    try: env['data'] = fn(model(**args), owner)
    except ValidationError: return {**env, 'status': 'error', 'error': 'invalid_args'}
    return env

def summarize(env):
    return REGISTRY[env['tool']][2](env['data']) if env['status'] == 'ok' else f"{env['tool']} failed ({env['error']})."

def plan(q):
    """Deterministic tool plan -> (calls, clarification_or_None). Capped at MAX_TOOL_CALLS."""
    low = q.lower(); g = re.search(r'\bGRV-?(\d{5,8})\b', q, re.I)
    if g or 'grievance' in low or '311' in low:
        if g: return [('ndmc_311_grievance_lookup', {'ref_id': 'GRV-' + g.group(1)})], None
        return [], 'Please share your grievance reference (format GRV-123456). Do not share personal identifiers.'
    if 'water' in low:
        w = re.search(r'ward\s*#?(\d{1,3})', low)
        if w: return [('ndmc_water_supply_status', {'ward': int(w.group(1))})], None
        return [], 'Which ward number should I check for water supply?'
    if re.search(r'electricity|ndmc|portal', low): return [('check_service_health', {'service': 'ndmc_portal'})], None
    m = re.search(r'\b(vpn|outlook|mfa|print\w*|network)\b.*\b(status|outage|down|health)\b|\b(status|outage|health)\b.*\b(vpn|outlook|mfa|print\w*|network)\b', low)
    if m:
        svc = next(x for x in (m.group(1), m.group(4)) if x); svc = 'print' if svc.startswith('print') else svc
        return [('check_service_health', {'service': svc})], None
    calls = [('get_user_context', {}), ('check_network_status', {})]
    if re.search(r'\blogs?\b', low): calls.append(('parse_system_logs', {}))
    return calls[:C.MAX_TOOL_CALLS], None
