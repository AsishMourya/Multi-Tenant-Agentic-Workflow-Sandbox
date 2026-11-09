import React, { useEffect, useState } from 'react';

const templates = {
  'orders-cents': {
    label: 'Order totals',
    mode: 'Python',
    file: 'main.py',
    source: `import json
import sys

orders = json.load(sys.stdin)
totals = {}
for order in orders:
    totals[order['sku']] = totals.get(order['sku'], 0) + order['quantity'] * order['unit_cents']

print(json.dumps({
    'by_sku': dict(sorted(totals.items())),
    'total_cents': sum(totals.values()),
}))`,
    payload: `[
  { "sku": "apple", "quantity": 2, "unit_cents": 125 },
  { "sku": "pear", "quantity": 1, "unit_cents": 80 }
]`,
  },
  inventory: {
    label: 'Inventory check',
    mode: 'LangGraph',
    file: 'agent.py',
    source: `import json
import sys
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from guest_broker_client import lookup

class State(TypedDict, total=False):
    sku: str
    quantity: int
    available: int
    accepted: bool
    explanation: str

def inventory(state: State):
    return {'available': lookup(state['sku'])['available']}

def explain(state: State):
    accepted = state['quantity'] <= state['available']
    return {
        'accepted': accepted,
        'explanation': f"Requested {state['quantity']}; available {state['available']}; accepted {accepted}.",
    }

graph = StateGraph(State)
graph.add_node('inventory', inventory)
graph.add_node('explain', explain)
graph.add_edge(START, 'inventory')
graph.add_edge('inventory', 'explain')
graph.add_edge('explain', END)

result = graph.compile().invoke(json.load(sys.stdin))
print(json.dumps(result))`,
    payload: `{
  "sku": "apple",
  "quantity": 2
}`,
  },
  'daily-revenue': {
    label: 'Daily revenue',
    mode: 'Python',
    file: 'daily_revenue.py',
    source: `import json
import sys

sales = json.load(sys.stdin)['sales']
by_day = {}
for sale in sales:
    by_day[sale['day']] = by_day.get(sale['day'], 0) + sale['amount_cents']

print(json.dumps({
    'by_day': dict(sorted(by_day.items())),
    'total_cents': sum(by_day.values()),
}))`,
    payload: `{
  "sales": [
    { "day": "2026-01-01", "amount_cents": 1250 },
    { "day": "2026-01-01", "amount_cents": 750 },
    { "day": "2026-01-02", "amount_cents": 900 }
  ]
}`,
  },
  'stock-reorder': {
    label: 'Stock reorder',
    mode: 'LangGraph',
    file: 'reorder_agent.py',
    source: `import json
import sys
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from guest_broker_client import lookup

class State(TypedDict, total=False):
    sku: str
    target_quantity: int
    available: int
    reorder_quantity: int
    explanation: str

def inventory(state: State):
    return {'available': lookup(state['sku'])['available']}

def plan(state: State):
    amount = max(0, state['target_quantity'] - state['available'])
    return {
        'reorder_quantity': amount,
        'explanation': f'Reorder {amount} units to reach {state["target_quantity"]}.',
    }

graph = StateGraph(State)
graph.add_node('inventory', inventory)
graph.add_node('plan', plan)
graph.add_edge(START, 'inventory')
graph.add_edge('inventory', 'plan')
graph.add_edge('plan', END)
print(json.dumps(graph.compile().invoke(json.load(sys.stdin))))`,
    payload: `{
  "sku": "apple",
  "target_quantity": 10
}`,
  },
  'inventory-brief': {
    label: 'Inventory brief',
    mode: 'LangGraph',
    file: 'inventory_brief.py',
    source: `import json
import sys
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from guest_broker_client import lookup

class State(TypedDict, total=False):
    sku: str
    quantity: int
    available: int
    accepted: bool
    summary: str

def inventory(state: State):
    return {'available': lookup(state['sku'])['available']}

def brief(state: State):
    accepted = state['quantity'] <= state['available']
    availability = 'sufficient' if accepted else 'short'
    return {'accepted': accepted, 'summary':
        f"{state['sku']}: requested {state['quantity']}; {state['available']} available; {availability}."}

graph = StateGraph(State)
graph.add_node('inventory', inventory)
graph.add_node('brief', brief)
graph.add_edge(START, 'inventory')
graph.add_edge('inventory', 'brief')
graph.add_edge('brief', END)
print(json.dumps(graph.compile().invoke(json.load(sys.stdin))))`,
    payload: `{
  "sku": "pear",
  "quantity": 4
}`,
  },
  'order-explainer': {
    label: 'Order explainer',
    mode: 'LangGraph',
    file: 'order_explainer.py',
    source: `import json
import sys
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from guest_broker_client import lookup

class State(TypedDict, total=False):
    sku: str
    quantity: int
    unit_cents: int
    available: int
    subtotal_cents: int
    accepted: bool
    explanation: str

def inventory(state: State):
    return {'available': lookup(state['sku'])['available']}

def explain(state: State):
    subtotal = state['quantity'] * state['unit_cents']
    accepted = state['quantity'] <= state['available']
    return {'subtotal_cents': subtotal, 'accepted': accepted,
        'explanation': f"{state['quantity']} x {state['unit_cents']} cents = {subtotal} cents; "
                       f"{state['available']} units available."}

graph = StateGraph(State)
graph.add_node('inventory', inventory)
graph.add_node('explain', explain)
graph.add_edge(START, 'inventory')
graph.add_edge('inventory', 'explain')
graph.add_edge('explain', END)
print(json.dumps(graph.compile().invoke(json.load(sys.stdin))))`,
    payload: `{
  "sku": "apple",
  "quantity": 2,
  "unit_cents": 125
}`,
  },
};

function Icon({ name, size = 18 }) {
  const paths = {
    cube: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="m4.3 7.6 7.7 4.3 7.7-4.3M12 12v9" /></>,
    code: <><path d="m8 17-5-5 5-5M16 7l5 5-5 5M14 4l-4 16" /></>,
    workflow: <><rect x="4" y="4" width="6" height="6" rx="1.5" /><rect x="14" y="14" width="6" height="6" rx="1.5" /><path d="M10 7h3a2 2 0 0 1 2 2v5M14 17h-3a2 2 0 0 1-2-2v-5" /></>,
    play: <path d="m8 5 11 7-11 7V5Z" />,
    pause: <><path d="M8 5h3v14H8zM15 5h3v14h-3z" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.6 9a7 7 0 0 1 11.6-2L20 12M4 12l2.8 5a7 7 0 0 0 11.6-2" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    key: <><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9m-4 4 3 3m-6-1 3 3" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    terminal: <><path d="m4 7 5 5-5 5M12 17h8" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6l8-3Z" /><path d="m9 12 2 2 4-4" /></>,
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

async function api(path, token, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function App() {
  const [exercise, setExercise] = useState('orders-cents');
  const [source, setSource] = useState(templates['orders-cents'].source);
  const [payload, setPayload] = useState(templates['orders-cents'].payload);
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [session, setSession] = useState(null);
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [runStartedAt, setRunStartedAt] = useState(null);
  const [runSeconds, setRunSeconds] = useState(0);

  useEffect(() => {
    if (!busy || runStartedAt === null) return undefined;
    const timer = window.setInterval(() => setRunSeconds((Date.now() - runStartedAt) / 1000), 100);
    return () => window.clearInterval(timer);
  }, [busy, runStartedAt]);

  const selectExercise = (value) => {
    if (busy) return;
    setExercise(value);
    setSource(templates[value].source);
    setPayload(templates[value].payload);
    setSession(null);
    setResult(null);
    setMessage('');
  };

  const startCheckpointDemo = async () => {
    if (!token.trim()) {
      setMessage('Add a tenant token to connect this workspace.');
      return;
    }
    setBusy(true);
    try {
      const created = await api('/v1/sessions', token.trim(), {
        method: 'POST', body: JSON.stringify({ exercise: 'inventory' }),
      });
      setSession({ id: created.session, state: 'queued', safePointDemo: true });
      setMessage('');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!token.trim()) {
      setMessage('Add a tenant token to connect this workspace.');
      return;
    }
    setBusy(true);
    setRunStartedAt(Date.now());
    setRunSeconds(0);
    setResult(null);
    setMessage('Preparing isolated session');
    try {
      const input = JSON.parse(payload);
      const created = await api('/v1/sessions', token.trim(), {
        method: 'POST', body: JSON.stringify({ exercise }),
      });
      setSession({ id: created.session, state: 'queued' });
      const endpoint = `/v1/sessions/${encodeURIComponent(created.session)}/${current.mode === 'LangGraph' ? 'agent' : 'python'}`;
      const body = JSON.stringify({ source, payload: input });
      let output;
      try {
        output = await api(endpoint, token.trim(), { method: 'POST', body });
      } catch (error) {
        if (error.status !== 409 || !error.message.includes('queued for execution')) throw error;
        for (let attempt = 0; attempt < 60; attempt += 1) {
          setMessage('Waiting for an available worker');
          await new Promise((resolve) => setTimeout(resolve, 1000));
          const status = await api(`/v1/sessions/${encodeURIComponent(created.session)}`, token.trim());
          setSession({ id: created.session, state: status.state });
          if (status.state === 'running') {
            output = await api(endpoint, token.trim(), { method: 'POST', body });
            break;
          }
          if (status.state !== 'queued') throw new Error(`Session is ${status.state} and cannot run.`);
        }
        if (!output) throw new Error('Still queued. Keep this page open and click Run again later.');
      }
      const status = await api(`/v1/sessions/${encodeURIComponent(created.session)}`, token.trim());
      setSession({ id: created.session, state: status.state });
      setResult(output);
      setMessage('');
    } catch (error) {
      setMessage(error instanceof SyntaxError ? `Input JSON is invalid: ${error.message}` : error.message);
    } finally {
      setBusy(false);
      setRunStartedAt(null);
    }
  };

  const safePoint = async (action) => {
    if (!session) return;
    setBusy(true);
    try {
      const endpoint = `/v1/sessions/${encodeURIComponent(session.id)}/${action}`;
      const body = action === 'pause' ? JSON.stringify({ payload: JSON.parse(payload) }) : '{}';
      const data = await api(endpoint, token.trim(), { method: 'POST', body });
      setResult(data);
      setSession({ ...session, state: action === 'pause' ? 'paused' : 'running', safePointDemo: action === 'pause' });
      setMessage(action === 'pause' ? 'Safe point saved and compute released.' : 'Checkpoint restored with fresh tool access.');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const gradeStatus = result?.grade?.status;
  const deterministicPassed = result?.grade?.deterministic_results?.every((check) => check.passed);
  const current = templates[exercise];

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Sandbox Studio home">
          <span className="brand-mark"><Icon name="cube" size={19} /></span>
          <span className="brand-name">Sandbox Studio</span>
        </a>
        <div className="topbar-center"><span className="runtime-indicator"><i />WSL · Firecracker</span></div>
        <div className="topbar-right"><span className="build-label">LOCAL</span></div>
      </header>

      <div className="app-frame">
        <aside className="sidebar">
          <section className="sidebar-section connection-section">
            <div className="section-label"><label htmlFor="tenant-token">Tenant token</label><span className={`connection-indicator ${token.trim() ? 'connected' : ''}`}><i />{token.trim() ? 'SET' : 'REQUIRED'}</span></div>
            <div className="token-field">
              <Icon name="key" size={15} />
              <input id="tenant-token" aria-label="Tenant token" type={showToken ? 'text' : 'password'} autoComplete="off" placeholder="Paste local token" value={token} onChange={(event) => setToken(event.target.value)} />
              <button type="button" className="icon-button token-toggle" onClick={() => setShowToken(!showToken)} aria-label={showToken ? 'Hide token' : 'Show token'} title={showToken ? 'Hide token' : 'Show token'}>{showToken ? 'Hide' : 'Show'}</button>
            </div>
            <p className="token-note">Not saved in this browser.</p>
          </section>

          <section className="sidebar-section exercise-section">
            <div className="section-label"><span>Exercises</span></div>
            {Object.entries(templates).map(([id, template]) => (
              <button key={id} className={`exercise-option ${exercise === id ? 'selected' : ''}`} onClick={() => selectExercise(id)} disabled={busy} aria-pressed={exercise === id}>
                <span className={`exercise-icon ${template.mode === 'Python' ? 'python-icon' : 'flow-icon'}`}><Icon name={template.mode === 'Python' ? 'code' : 'workflow'} size={17} /></span>
                <span className="exercise-copy"><strong>{template.label}</strong><small>{template.mode}</small></span>
                <span className="option-chevron"><Icon name="chevron" size={14} /></span>
              </button>
            ))}
          </section>

          <section className="sidebar-section session-section">
            <div className="section-label"><span>Session</span></div>
            {session ? (
              <div className="session-card">
                <div className="session-card-head"><span className={`session-status status-${session.state}`}><i />{session.state}</span><button className="icon-button" title="Clear session" aria-label="Clear session" onClick={() => { setSession(null); setResult(null); setMessage(''); }}>×</button></div>
                <div className="session-id">{session.id}</div>
                {session.safePointDemo && <div className="session-controls">{session.state === 'paused' ? <button className="mini-action" onClick={() => safePoint('resume')} disabled={busy}><Icon name="refresh" size={14} />Resume</button> : <button className="mini-action" onClick={() => safePoint('pause')} disabled={busy}><Icon name="pause" size={14} />Save safe point</button>}</div>}
              </div>
            ) : (
              <div className="session-empty"><span className="session-empty-icon"><Icon name="terminal" size={17} /></span><strong>No session</strong></div>
            )}
            {!session && exercise === 'inventory' && <button className="checkpoint-link" onClick={startCheckpointDemo} disabled={busy}>Start checkpoint demo <Icon name="arrow" size={14} /></button>}
          </section>

        </aside>

        <main className="main-content">
          <div className="page-heading">
            <div>
              <h1>{current.label}</h1>
            </div>
            <div className="runtime-chip"><span className="runtime-chip-dot" />{current.mode} · isolated</div>
          </div>

          <div className="workbench">
            <section className="editor-pane" aria-label="Code editor">
              <div className="pane-toolbar">
                <div className="file-tab"><span className="file-type-dot" />{current.file}</div>
              </div>
              <div className="editor-body">
                <div className="line-gutter" aria-hidden="true">{source.split('\n').map((_, index) => <span key={index}>{index + 1}</span>)}</div>
                <textarea className="code-editor" aria-label="Exercise source code" spellCheck="false" value={source} onChange={(event) => setSource(event.target.value)} />
              </div>
              <div className="editor-footer">
                <span className="editor-language"><span className="language-dot" />{current.mode === 'LangGraph' ? 'Python workflow' : 'Python'}</span>
                <span className="editor-footer-right"><Icon name="shield" size={14} />Firecracker</span>
              </div>
            </section>

            <aside className="run-column">
              <section className="input-pane">
                <div className="pane-heading"><h2>Input</h2><span className="format-tag">JSON</span></div>
                <textarea className="input-editor" aria-label="Exercise JSON input" spellCheck="false" value={payload} onChange={(event) => setPayload(event.target.value)} />
                {exercise === 'inventory' && <button className="sample-button" onClick={() => setPayload('{\n  "sku": "apple",\n  "quantity": 8\n}')}>Load insufficient-stock case <Icon name="arrow" size={13} /></button>}
              </section>

              <section className="output-pane">
                <div className="pane-heading output-pane-heading"><h2>Output</h2>{gradeStatus && <span className={`grade-badge ${gradeStatus.toLowerCase()}`}>{gradeStatus.replace('_', ' ')}</span>}</div>
                <div className={`output-body ${result ? 'has-result' : ''}`}>
                  {result ? <div className="result-content">
                    <div className="result-state"><span className="result-check"><Icon name="check" size={15} /></span><span><strong>{gradeStatus || 'Execution complete'}</strong><small>{result.execution?.backend || 'Run completed'}</small></span></div>
                    <pre className="program-output">{JSON.stringify(result.output ?? result, null, 2)}</pre>
                    {result.execution && <div className="timing-summary">
                      {Number.isFinite(Number(result.execution.total_wall_seconds ?? result.execution.wall_seconds)) && <span><strong>{Number(result.execution.total_wall_seconds ?? result.execution.wall_seconds).toFixed(2)}s</strong> end-to-end</span>}
                      {Number.isFinite(Number(result.execution.wall_seconds)) && <span><strong>{Number(result.execution.wall_seconds).toFixed(2)}s</strong> execution</span>}
                    </div>}
                    {gradeStatus && <div className={`grade-summary ${gradeStatus.toLowerCase()}`}><strong>{gradeStatus === 'REVIEW' && deterministicPassed ? 'Checks passed · human review pending' : `Grade: ${gradeStatus.replace('_', ' ')}`}</strong>{gradeStatus === 'REVIEW' && <span>Semantic decision requires review.</span>}</div>}
                    <details className="audit-details"><summary>Execution details</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
                  </div> : <div className="empty-output"><span className="empty-output-icon"><Icon name="terminal" size={19} /></span><strong>{message || (busy ? 'Running' : 'Output appears here')}</strong>{busy && <small>{runSeconds.toFixed(1)}s</small>}</div>}
                </div>
              </section>

              <div className="run-controls">
                <button className="run-button" onClick={run} disabled={busy}>
                  {busy ? <span className="button-spinner" /> : <Icon name="play" size={16} />}
                  {busy ? 'Running' : 'Run'}
                </button>
              </div>
            </aside>
          </div>

          <footer className="statusbar"><div><span className="status-led" /><span>{busy ? (message || 'Running') : session?.state || 'Ready'}</span><span className="status-separator">·</span><span>tenant-scoped</span></div></footer>
        </main>
      </div>
    </div>
  );
}

export default App;
