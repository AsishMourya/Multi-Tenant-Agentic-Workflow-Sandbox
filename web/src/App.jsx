import React, { useEffect, useState } from 'react';

const templates = {
  'orders-cents': {
    label: 'Python sandbox',
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
    label: 'Agent workflow',
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
};

function Icon({ name, size = 18 }) {
  const paths = {
    mark: <><path d="M4 5.5 12 2l8 3.5v13L12 22l-8-3.5z" /><path d="m4 5.5 8 4 8-4M12 9.5V22" /></>,
    code: <><path d="m8 17-5-5 5-5M16 7l5 5-5 5M14 4l-4 16" /></>,
    play: <path d="m7 4 13 8-13 8z" />,
    pause: <><path d="M8 5h3v14H8zM15 5h3v14h-3z" /></>,
    rotate: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.6 9a7 7 0 0 1 11.6-2L20 12M4 12l2.8 5a7 7 0 0 0 11.6-2" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    cloud: <><path d="M20 16.2A4.5 4.5 0 0 0 18 7.5 6 6 0 0 0 6.3 9.7 4 4 0 0 0 7 17.5h12" /><path d="m9 13 3-3 3 3" /></>,
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
  const [session, setSession] = useState(null);
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [runStartedAt, setRunStartedAt] = useState(null);
  const [runSeconds, setRunSeconds] = useState(0);

  useEffect(() => {
    if (!busy || runStartedAt === null) return undefined;
    const timer = window.setInterval(
      () => setRunSeconds((Date.now() - runStartedAt) / 1000),
      100,
    );
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
      setMessage('Paste a tenant token first. The token is used for this request only.');
      return;
    }
    setBusy(true);
    try {
      const created = await api('/v1/sessions', token.trim(), {
        method: 'POST',
        body: JSON.stringify({ exercise: 'inventory' }),
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
      setMessage('Paste a tenant token first. The token is used for this request only.');
      return;
    }
    setBusy(true);
    setRunStartedAt(Date.now());
    setRunSeconds(0);
    setResult(null);
    setMessage('Starting…');
    try {
      const input = JSON.parse(payload);
      const created = await api('/v1/sessions', token.trim(), {
        method: 'POST',
        body: JSON.stringify({ exercise }),
      });
      setSession({ id: created.session, state: 'queued' });
      const endpoint = `/v1/sessions/${encodeURIComponent(created.session)}/${exercise === 'inventory' ? 'agent' : 'python'}`;
      const body = JSON.stringify({ source, payload: input });
      let output;
      try {
        output = await api(endpoint, token.trim(), { method: 'POST', body });
      } catch (error) {
        if (error.status !== 409 || !error.message.includes('queued for execution')) throw error;
        for (let attempt = 0; attempt < 60; attempt += 1) {
          setMessage('Waiting for an available worker…');
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
      setSession({ ...session, state: action === 'pause' ? 'paused' : 'running',
        safePointDemo: action === 'pause' });
      setMessage(action === 'pause' ? 'Safe point saved and compute released.' : 'Safe point restored with fresh tool access.');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const gradeStatus = result?.grade?.status;
  const deterministicPassed = result?.grade?.deterministic_results?.every((check) => check.passed);
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Sandbox Studio home"><span className="brand-icon"><Icon name="mark" /></span><span>Sandbox<span className="brand-light"> Studio</span></span></a>
        <div className="topbar-right"><span className="system-label"><span className="live-dot" />WSL</span></div>
      </header>

      <main className="page">
        <div className="studio-layout">
          <aside className="sidebar">
            <section className="panel connection-panel">
              <div className="panel-heading"><h2>Tenant token</h2></div>
              <input id="tenant-token" aria-label="Tenant token" type="password" autoComplete="off" placeholder="Paste token" value={token} onChange={(event) => setToken(event.target.value)} />
            </section>

            <section className="panel exercise-panel">
              <div className="panel-heading"><h2>Exercise</h2></div>
              <button className={`exercise-option ${exercise === 'orders-cents' ? 'selected' : ''}`} onClick={() => selectExercise('orders-cents')} disabled={busy}>
                <span className="option-icon python-icon"><Icon name="code" /></span><span className="option-copy"><strong>Python</strong></span><span className="option-radio" />
              </button>
              <button className={`exercise-option ${exercise === 'inventory' ? 'selected' : ''}`} onClick={() => selectExercise('inventory')} disabled={busy}>
                <span className="option-icon agent-icon"><Icon name="cloud" /></span><span className="option-copy"><strong>Agent</strong></span><span className="option-radio" />
              </button>
            </section>

            {session && <section className="session-card">
              <div className="session-card-top"><span className="session-state">{session.state}</span></div>
              <p>{session.id}</p>
              {session?.safePointDemo && session.state !== 'paused' && <div className="session-actions"><button onClick={() => safePoint('pause')} disabled={busy}><Icon name="pause" size={14} /> Save safe point</button></div>}
              {session?.safePointDemo && session.state === 'paused' && <div className="session-actions"><button onClick={() => safePoint('resume')} disabled={busy}><Icon name="rotate" size={14} /> Resume checkpoint</button></div>}
            </section>}
            {!session && exercise === 'inventory' && <button className="checkpoint-start" onClick={startCheckpointDemo} disabled={busy}>Test pause / resume</button>}
          </aside>

          <section className="workspace">
            <div className="workspace-heading"><h2>{templates[exercise].label}</h2></div>

            <div className="editor-grid">
              <section className="editor-card">
                <div className="editor-toolbar"><div className="file-tab"><span className="file-dot" />{templates[exercise].file}</div></div>
                <textarea className="code-editor" aria-label="Exercise source code" spellCheck="false" value={source} onChange={(event) => setSource(event.target.value)} />
                <div className="editor-footer"><button className="run-button" onClick={run} disabled={busy}><Icon name={busy ? 'rotate' : 'play'} size={16} />{busy ? 'Running…' : 'Run'}</button></div>
              </section>

              <div className="right-column">
                <section className="input-card">
                  <div className="card-title-row"><h3>Input</h3><span className="json-tag">JSON</span></div>
                  <textarea className="input-editor" aria-label="Exercise JSON input" spellCheck="false" value={payload} onChange={(event) => setPayload(event.target.value)} />
                  {exercise === 'inventory' && <button className="sample-link" onClick={() => setPayload('{\n  "sku": "apple",\n  "quantity": 8\n}')}>Try a rejected order <Icon name="arrow" size={13} /></button>}
                </section>

                <section className="result-card">
                  <div className="result-heading"><div><h3>Output</h3></div>{gradeStatus && <span className={`grade-badge ${gradeStatus.toLowerCase()}`}>{gradeStatus}</span>}</div>
                  <div className={`result-body ${result ? '' : 'empty'}`}>
                    {result ? <div className="result-content">
                      <pre className="program-output">{JSON.stringify(result.output ?? result, null, 2)}</pre>
                      {result.execution && <div className="timing-summary">
                        {Number.isFinite(Number(result.execution.total_wall_seconds ?? result.execution.wall_seconds)) && <span><strong>{Number(result.execution.total_wall_seconds ?? result.execution.wall_seconds).toFixed(2)}s</strong> total · VM startup + grading</span>}
                        {Number.isFinite(Number(result.execution.wall_seconds)) && <span><strong>{Number(result.execution.wall_seconds).toFixed(2)}s</strong> for code</span>}
                      </div>}
                      {gradeStatus && <div className="grade-summary">
                        <strong>{gradeStatus === 'REVIEW' && deterministicPassed ? 'Deterministic checks passed; review pending.' : `Grade: ${gradeStatus}`}</strong>
                        {gradeStatus === 'REVIEW' && <span>Semantic judge not configured.</span>}
                      </div>}
                      <details className="audit-details">
                        <summary>Show full audit details</summary>
                        <pre>{JSON.stringify(result, null, 2)}</pre>
                      </details>
                    </div> : <div className="empty-state">{busy ? `${message} ${runSeconds.toFixed(1)}s` : message || 'Run to see output.'}</div>}
                  </div>
                </section>
              </div>
            </div>

          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
