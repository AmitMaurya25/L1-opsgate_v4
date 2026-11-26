"""Generates grafana/dashboards/performance.json (light theme, interactive variables, drill-down links). Run: python observability/gen_dashboard.py"""
import json
from pathlib import Path
DS = {'type': 'prometheus', 'uid': 'opsgate-prom'}; R = '$__range'; N = [0]
RT, SRC, TL = 'route=~"$route"', 'source=~"$source"', 'tool=~"$tool"'

def panel(kind, title, exprs, x, y, w, h, legend='{{route}}', desc='', unit=None, options=None, extra=None, instant=None):
    N[0] += 1; inst = kind in ('stat', 'piechart', 'bargauge', 'table', 'gauge') if instant is None else instant
    legends = legend if isinstance(legend, list) else [legend] * len(exprs)
    p = {'id': N[0], 'type': kind, 'title': title, 'description': desc, 'datasource': DS, 'gridPos': {'x': x, 'y': y, 'w': w, 'h': h},
         'targets': [{'refId': chr(65 + i), 'datasource': DS, 'expr': e, 'legendFormat': legends[i], 'instant': inst, 'range': not inst} for i, e in enumerate(exprs)],
         'fieldConfig': {'defaults': {'unit': unit} if unit else {}, 'overrides': []}, 'options': options or {}}
    p.update(extra or {}); return p

def row(title, y):
    N[0] += 1; return {'id': N[0], 'type': 'row', 'title': title, 'collapsed': False, 'gridPos': {'x': 0, 'y': y, 'w': 24, 'h': 1}, 'panels': []}

def pct_stat(title, num, den, x, y, desc, w=4):
    return panel('stat', title, [f'100*({num})/clamp_min({den},1)'], x, y, w, 4, legend='', unit='percent', desc=desc,
                 options={'colorMode': 'background', 'graphMode': 'none', 'reduceOptions': {'calcs': ['lastNotNull']}})

def stat(title, expr, x, y, desc='', w=4, unit=None, legend=''):
    return panel('stat', title, [expr], x, y, w, 4, legend=legend, desc=desc, unit=unit, options={'graphMode': 'area', 'colorMode': 'value', 'reduceOptions': {'calcs': ['lastNotNull']}})

inc = lambda m, sel='': f'sum(increase({m}_total{{{sel}}}[{R}]))'
drill = [{'title': 'Drill into this route', 'url': '/d/opsgate-perf?var-route=${__field.labels.route}&${__url_time_range}', 'targetBlank': False}]
ts_opts = {'legend': {'displayMode': 'table', 'placement': 'bottom', 'calcs': ['mean', 'max']}, 'tooltip': {'mode': 'multi', 'sort': 'desc'}}
stack = {'fieldConfig': {'defaults': {'custom': {'fillOpacity': 25, 'stacking': {'mode': 'normal'}, 'lineWidth': 1}}, 'overrides': []}}

P = [row('Overview - click a route in the bar chart to drill down; use the variables above to filter', 0),
 stat('Handled turns', inc('opsgate_turns', RT), 0, 1, 'All chat turns, including blocked ones.'),
 pct_stat('Resolution confirmations', inc('opsgate_resolved', RT), inc('opsgate_turns', 'route=~"rag|tools"'), 4, 1, 'Explicit user "resolved" confirmations / answered (RAG+tools) turns. Not a measured L1 resolution rate.'),
 pct_stat('Escalation rate', inc('opsgate_turns', 'route="hitl"'), inc('opsgate_turns'), 8, 1, 'HITL turns / all turns.'),
 pct_stat('Abstain rate', inc('opsgate_retrieval', 'outcome="abstained"'), inc('opsgate_retrieval'), 12, 1, 'Retrieval found no adequate evidence -> agent declined to guess.'),
 stat('Guardrail blocks', inc('opsgate_guardrail_blocks'), 16, 1, 'Injection, secrets, unsafe, oversize, rate-limit blocks.'),
 stat('Engine errors', inc('opsgate_errors', ''), 20, 1, 'Failed engine events (all types).'),
 panel('bargauge', 'Turns by route (click to drill down)', [f'sum by(route)(increase(opsgate_turns_total{{{RT}}}[{R}]))'], 0, 5, 8, 7,
       extra={'fieldConfig': {'defaults': {'links': drill}, 'overrides': []}}, options={'displayMode': 'gradient', 'orientation': 'horizontal'}),
 panel('piechart', 'Route mix', [f'sum by(route)(increase(opsgate_turns_total{{{RT}}}[{R}]))'], 8, 5, 6, 7, options={'pieType': 'donut', 'legend': {'displayMode': 'table', 'placement': 'right', 'values': ['percent']}}),
 panel('timeseries', 'Turn throughput / min', [f'sum by(route)(rate(opsgate_turns_total{{{RT}}}[$__rate_interval]))*60'], 14, 5, 10, 7, options=ts_opts, extra=stack),
 row('Quality & safety', 12),
 panel('bargauge', 'Guardrail blocks by reason', [f'sum by(reason)(increase(opsgate_guardrail_blocks_total[{R}]))'], 0, 13, 6, 7, legend='{{reason}}', options={'displayMode': 'basic', 'orientation': 'horizontal'}),
 panel('timeseries', 'Retrieval outcomes', ['sum by(outcome)(increase(opsgate_retrieval_total[$__rate_interval]))'], 6, 13, 9, 7, legend='{{outcome}}', options=ts_opts, extra=stack,
       desc='grounded = cited evidence; retried = one query rewrite; abstained = no adequate evidence.'),
 panel('table', 'Simulated tool calls (filter with $tool)', [f'sum by(tool,status)(increase(opsgate_tool_calls_total{{{TL}}}[{R}]))'], 15, 13, 9, 7, legend='{{tool}} / {{status}}',
       extra={'transformations': [{'id': 'seriesToRows', 'options': {}}]}),
 row('Performance & cost', 20),
 panel('timeseries', 'Latency p50 / p95 (local, per route)', [f'histogram_quantile(0.5,sum by(le,route)(rate(opsgate_latency_seconds_bucket{{{RT}}}[$__rate_interval])))', f'histogram_quantile(0.95,sum by(le,route)(rate(opsgate_latency_seconds_bucket{{{RT}}}[$__rate_interval])))'],
       0, 21, 12, 8, legend=['p50 {{route}}', 'p95 {{route}}'], unit='s', options=ts_opts),
 panel('timeseries', 'Tokens / min (provider vs estimated - see $source)', [f'sum by(kind,source)(rate(opsgate_tokens_total{{{RT},{SRC}}}[$__rate_interval]))*60'], 12, 21, 12, 8, legend='{{kind}} ({{source}})', options=ts_opts,
       desc='source=estimated is chars/4 in DEMO_MODE. cached is shown only when the provider returns it.'),
 stat('Avg input tokens / answered turn', f'sum(increase(opsgate_tokens_total{{kind="input",{SRC}}}[{R}]))/clamp_min({inc("opsgate_turns", "route=~\"rag|tools\"")},1)', 0, 29, w=6, desc='Mixes sources if both selected.'),
 stat('Cached tokens (provider only)', f'sum(increase(opsgate_tokens_total{{kind="cached",source="provider"}}[{R}]))', 6, 29, w=6),
 panel('timeseries', 'Model retries & deterministic fallbacks', ['sum(increase(opsgate_llm_retries_total[$__rate_interval]))', 'sum by(reason)(increase(opsgate_llm_fallbacks_total[$__rate_interval]))'], 12, 29, 12, 4,
       legend=['retries (429/5xx)', 'fallback: {{reason}}'], options=ts_opts),
 row('Human approval & tickets (global)', 33),
 panel('bargauge', 'Approval funnel', [inc('opsgate_drafts'), f'sum by(decision)(increase(opsgate_approvals_total[{R}]))', inc('opsgate_tickets')], 0, 34, 12, 7,
       legend=['drafts proposed', 'decision: {{decision}}', 'tickets created'], options={'displayMode': 'basic', 'orientation': 'horizontal'}, desc='approve/reject/expired/invalid. Tickets are MOCK; no real ITSM.'),
 panel('timeseries', 'Errors by type', ['sum by(type)(increase(opsgate_errors_total[$__rate_interval]))'], 12, 34, 12, 7, legend='{{type}}', options=ts_opts)]

def var(name, query, label, multi=True):
    return {'name': name, 'label': label, 'type': 'query', 'datasource': DS, 'query': {'query': query, 'refId': 'v'}, 'refresh': 2, 'multi': multi, 'includeAll': True, 'allValue': '.*', 'current': {'text': 'All', 'value': '$__all'}}

dash = {'uid': 'opsgate-perf', 'title': 'OpsGate | Agent Performance (staff only)', 'tags': ['opsgate', 'staff-only'], 'timezone': 'browser', 'refresh': '10s', 'schemaVersion': 39, 'editable': False,
        'graphTooltip': 1, 'time': {'from': 'now-1h', 'to': 'now'}, 'panels': P,
        'templating': {'list': [var('route', 'label_values(opsgate_turns_total,route)', 'Route'),
                                {'name': 'source', 'label': 'Token source', 'type': 'custom', 'query': 'estimated,provider', 'multi': True, 'includeAll': True, 'allValue': '.*', 'current': {'text': 'All', 'value': '$__all'}, 'options': []},
                                var('tool', 'label_values(opsgate_tool_calls_total,tool)', 'Tool')]},
        'links': [{'title': 'Reset filters', 'type': 'link', 'url': '/d/opsgate-perf', 'icon': 'dashboard'}],
        'description': 'Internal observability for IT team and developers. Aggregate metrics only - no user IDs, thread IDs or prompts. Prometheus counters reset on restart.'}
out = Path(__file__).parent / 'grafana' / 'dashboards' / 'performance.json'; out.write_text(json.dumps(dash, indent=1)); print('panels:', len(P), '->', out)
