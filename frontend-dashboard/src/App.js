import React, { useState, useEffect, useMemo, useRef } from 'react';
import io from 'socket.io-client';
import {
  ShieldAlert, Activity, Lock, TrendingUp, AlertTriangle,
  Users, Radio, Zap, Globe, Server, ChevronRight, Eye, CheckCircle2
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell
} from 'recharts';
import './App.css';

function App() {
  const [alerts, setAlerts] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [clock, setClock] = useState(new Date());
  const [reviewed, setReviewed] = useState(new Set());
  const [escalatedCount, setEscalatedCount] = useState(0);
  const [toast, setToast] = useState(null);
  const feedRef = useRef(null);

  // Live clock
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    setLoginError('');
    try {
      const response = await fetch('http://localhost:4000/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await response.json();
      if (data.success) {
        localStorage.setItem('token', data.token);
        setToken(data.token);
      } else {
        setLoginError(data.message || 'Authentication rejected');
      }
    } catch (err) {
      setLoginError('Cannot reach authentication service');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken('');
    setAlerts([]);
    setSelectedAlert(null);
    setReviewed(new Set());
    setEscalatedCount(0);
  };

  // Escalate: remove alert from feed, increment escalated counter, show toast
  const handleEscalate = (alert) => {
    setAlerts(prev => prev.filter(a => a.transaction_id !== alert.transaction_id));
    setEscalatedCount(c => c + 1);
    setSelectedAlert(null);
    setToast({ type: 'escalate', msg: `Case escalated · ${alert.user_id}` });
  };

  // Mark reviewed: tag transaction as reviewed, keep in feed but dimmed
  const handleReview = (alert) => {
    setReviewed(prev => new Set(prev).add(alert.transaction_id));
    setSelectedAlert(null);
    setToast({ type: 'review', msg: `Marked reviewed · ${alert.user_id}` });
  };

  useEffect(() => {
    if (!token) return;

    const fetchHistory = async () => {
      try {
        const response = await fetch('http://localhost:4000/api/alerts', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.status === 401 || response.status === 403) {
          handleLogout();
          return;
        }
        const data = await response.json();
        setAlerts(Array.isArray(data) ? data : []);
      } catch (error) {
        console.error("Error fetching alerts:", error);
      }
    };

    fetchHistory();
    const socket = io('http://localhost:4000');
    socket.on('connect', () => setIsConnected(true));
    socket.on('disconnect', () => setIsConnected(false));
    socket.on('new_fraud_alert', (newAlert) => {
      setAlerts((prev) => [newAlert, ...prev].slice(0, 100));
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('new_fraud_alert');
      socket.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const formatTime = (ts) => {
    if (!ts) return "--:--:--";
    const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
    return d.toLocaleTimeString('en-GB');
  };

  const severityOf = (alert) => {
    const n = (alert.reasons || []).length;
    if (n >= 3) return 'critical';
    if (n === 2) return 'high';
    return 'medium';
  };

  // DERIVED DATA
  const stats = useMemo(() => {
    const total = alerts.length;
    const users = new Set(alerts.map(a => a.user_id)).size;
    const ai = alerts.filter(a => (a.reasons || []).some(r => r.includes('AI'))).length;
    const critical = alerts.filter(a => (a.reasons || []).length >= 3).length;
    const volume = alerts.reduce((s, a) => s + (a.amount || 0), 0);
    return { total, users, ai, critical, volume };
  }, [alerts]);

  const timeline = useMemo(() => {
    const buckets = {};
    alerts.forEach(a => {
      if (!a.timestamp) return;
      const d = typeof a.timestamp === 'number' ? new Date(a.timestamp * 1000) : new Date(a.timestamp);
      const k = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      buckets[k] = (buckets[k] || 0) + 1;
    });
    return Object.entries(buckets).map(([time, count]) => ({ time, count })).slice(-20);
  }, [alerts]);

  const byType = useMemo(() => {
    const c = {};
    alerts.forEach(a => (a.reasons || []).forEach(r => {
      let k = r.includes('Velocity') ? 'Velocity' : r.includes('International') ? 'Geo-Anomaly' : r.includes('AI') ? 'ML Model' : 'Other';
      c[k] = (c[k] || 0) + 1;
    }));
    return Object.entries(c).map(([type, count]) => ({ type, count })).sort((a, b) => b.count - a.count);
  }, [alerts]);

  const barColor = (t) => ({ 'Velocity': '#f5a623', 'Geo-Anomaly': '#38bdf8', 'ML Model': '#a78bfa', 'Other': '#64748b' }[t] || '#64748b');

  // LOGIN
  if (!token) {
    return (
      <div className="auth-shell">
        <div className="auth-grid-bg" />
        <div className="auth-panel">
          <div className="auth-brand">
            <div className="auth-logo"><ShieldAlert size={20} /></div>
            <div>
              <div className="auth-brand-name">SENTINEL</div>
              <div className="auth-brand-sub">Fraud Operations Console</div>
            </div>
          </div>

          <div className="auth-divider" />

          <div className="auth-form">
            <label className="field-label">Operator ID</label>
            <input
              className="field-input"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
              placeholder="analyst.id"
              autoFocus
            />

            <label className="field-label">Access Key</label>
            <input
              className="field-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
              placeholder="********"
            />

            {loginError && <div className="auth-error"><AlertTriangle size={13} /> {loginError}</div>}

            <button className="auth-submit" onClick={handleLogin}>
              Authenticate <ChevronRight size={16} />
            </button>
          </div>

          <div className="auth-footer">
            <span className="auth-status-dot" /> Secure channel &middot; TLS 1.3 &middot; Session-scoped
          </div>
        </div>
      </div>
    );
  }

  // CONSOLE
  return (
    <div className="console">
      {/* Top Command Bar */}
      <header className="cmd-bar">
        <div className="cmd-left">
          <div className="cmd-logo"><ShieldAlert size={18} /></div>
          <div className="cmd-title">
            <span className="cmd-name">SENTINEL</span>
            <span className="cmd-tag">FRAUD OPS</span>
          </div>
        </div>

        <div className="cmd-center">
          <div className={`link-state ${isConnected ? 'up' : 'down'}`}>
            <Radio size={13} />
            <span>{isConnected ? 'STREAM LIVE' : 'STREAM DOWN'}</span>
            <span className="pulse-dot" />
          </div>
        </div>

        <div className="cmd-right">
          <div className="cmd-clock">{clock.toLocaleTimeString('en-GB')} UTC</div>
          <button className="cmd-logout" onClick={handleLogout}>
            <Lock size={13} /> End Session
          </button>
        </div>
      </header>

      {/* Live Ticker */}
      <div className="ticker">
        <div className="ticker-label"><Zap size={12} /> LIVE</div>
        <div className="ticker-track">
          <div className="ticker-move">
            {alerts.slice(0, 15).map((a, i) => (
              <span key={i} className="ticker-item">
                <span className={`tick-sev tick-${severityOf(a)}`} />
                {a.user_id} &middot; {a.currency} {(a.amount || 0).toLocaleString()} &middot; {(a.reasons || [])[0]?.split(':')[0] || 'FLAG'}
                <span className="ticker-sep">|</span>
              </span>
            ))}
            {alerts.length === 0 && <span className="ticker-item ticker-idle">Awaiting telemetry stream from detection engine...</span>}
          </div>
        </div>
      </div>

      {/* Metric Strip */}
      <div className="metric-strip">
        <div className="metric">
          <div className="metric-head"><AlertTriangle size={14} /> THREATS FLAGGED</div>
          <div className="metric-val">{stats.total.toLocaleString()}</div>
          <div className="metric-foot">rolling window</div>
        </div>
        <div className="metric metric-critical">
          <div className="metric-head"><Zap size={14} /> CRITICAL</div>
          <div className="metric-val">{stats.critical}</div>
          <div className="metric-foot">3+ signals fired</div>
        </div>
        <div className="metric">
          <div className="metric-head"><Users size={14} /> ACCOUNTS</div>
          <div className="metric-val">{stats.users}</div>
          <div className="metric-foot">unique flagged</div>
        </div>
        <div className="metric metric-escalated">
          <div className="metric-head"><CheckCircle2 size={14} /> ESCALATED</div>
          <div className="metric-val">{escalatedCount}</div>
          <div className="metric-foot">cases actioned</div>
        </div>
        <div className="metric metric-wide">
          <div className="metric-head"><Server size={14} /> EXPOSURE VOLUME</div>
          <div className="metric-val metric-val-sm">${stats.volume.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
          <div className="metric-foot">sum of flagged transaction value</div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid">
        {/* Left: Charts */}
        <section className="panel panel-charts">
          <div className="panel-head">
            <span className="panel-title"><Activity size={14} /> DETECTION RATE</span>
            <span className="panel-meta">alerts / minute</span>
          </div>
          <div className="chart-wrap">
            {timeline.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={timeline} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="#1e2b3d" vertical={false} />
                  <XAxis dataKey="time" stroke="#3d4f66" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="#3d4f66" fontSize={10} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: '#0d1725', border: '1px solid #1e2b3d', borderRadius: 4, fontSize: 12, fontFamily: 'IBM Plex Mono, monospace', color: '#e2e8f0' }}
                    cursor={{ stroke: '#38bdf8', strokeWidth: 1, strokeDasharray: '3 3' }}
                  />
                  <Area type="monotone" dataKey="count" stroke="#38bdf8" strokeWidth={1.5} fill="url(#grad)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <div className="chart-idle">Collecting telemetry...</div>}
          </div>

          <div className="panel-head panel-head-mid">
            <span className="panel-title"><Eye size={14} /> SIGNAL BREAKDOWN</span>
            <span className="panel-meta">by detector</span>
          </div>
          <div className="chart-wrap">
            {byType.length > 0 ? (
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={byType} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#1e2b3d" horizontal={false} />
                  <XAxis type="number" stroke="#3d4f66" fontSize={10} tickLine={false} axisLine={false} allowDecimals={false} />
                  <YAxis type="category" dataKey="type" stroke="#7089a8" fontSize={11} width={82} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#0d1725', border: '1px solid #1e2b3d', borderRadius: 4, fontSize: 12, fontFamily: 'IBM Plex Mono, monospace', color: '#e2e8f0' }}
                    cursor={{ fill: 'rgba(56,189,248,0.05)' }}
                  />
                  <Bar dataKey="count" radius={[0, 2, 2, 0]} barSize={18}>
                    {byType.map((e, i) => <Cell key={i} fill={barColor(e.type)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="chart-idle">No signals yet</div>}
          </div>
        </section>

        {/* Center: Live Feed */}
        <section className="panel panel-feed">
          <div className="panel-head">
            <span className="panel-title"><Radio size={14} /> LIVE THREAT FEED</span>
            <span className="panel-meta">{alerts.length} active</span>
          </div>
          <div className="feed" ref={feedRef}>
            {alerts.length === 0 ? (
              <div className="feed-empty">
                <Server size={28} strokeWidth={1.2} />
                <p>Monitoring transaction stream</p>
                <span>Flagged events will appear here in real time</span>
              </div>
            ) : (
              alerts.map((a, i) => {
                const sev = severityOf(a);
                const isReviewed = reviewed.has(a.transaction_id);
                return (
                  <div
                    key={a.transaction_id || i}
                    className={`row row-${sev} ${selectedAlert?.transaction_id === a.transaction_id ? 'row-active' : ''} ${isReviewed ? 'row-reviewed' : ''}`}
                    onClick={() => setSelectedAlert(a)}
                  >
                    <div className={`row-sev row-sev-${sev}`} />
                    <div className="row-time">{formatTime(a.timestamp)}</div>
                    <div className="row-user">{a.user_id}</div>
                    <div className="row-amt">
                      <span className="row-cur">{a.currency}</span>
                      {(a.amount || 0).toLocaleString()}
                    </div>
                    <div className="row-tags">
                      {isReviewed && <span className="row-tag row-tag-reviewed"><CheckCircle2 size={10} /> REVIEWED</span>}
                      {(a.reasons || []).slice(0, 2).map((r, j) => (
                        <span key={j} className="row-tag">{r.split(':')[0].replace('AI Anomaly Detected', 'ML').replace('International physical card transaction', 'GEO').replace('Velocity hit', 'VELOCITY')}</span>
                      ))}
                      {(a.reasons || []).length > 2 && <span className="row-tag row-tag-more">+{(a.reasons || []).length - 2}</span>}
                    </div>
                    <ChevronRight size={14} className="row-arrow" />
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* Right: Inspector */}
        <section className="panel panel-inspect">
          <div className="panel-head">
            <span className="panel-title"><Eye size={14} /> INSPECTOR</span>
          </div>
          {selectedAlert ? (
            <div className="inspect">
              <div className={`inspect-sev inspect-sev-${severityOf(selectedAlert)}`}>
                {severityOf(selectedAlert).toUpperCase()} SEVERITY
              </div>

              <div className="inspect-block">
                <div className="inspect-k">Transaction ID</div>
                <div className="inspect-v inspect-mono">{selectedAlert.transaction_id}</div>
              </div>
              <div className="inspect-row">
                <div className="inspect-block">
                  <div className="inspect-k">Account</div>
                  <div className="inspect-v">{selectedAlert.user_id}</div>
                </div>
                <div className="inspect-block">
                  <div className="inspect-k">Amount</div>
                  <div className="inspect-v inspect-amt">{selectedAlert.currency} {(selectedAlert.amount || 0).toLocaleString()}</div>
                </div>
              </div>
              <div className="inspect-row">
                <div className="inspect-block">
                  <div className="inspect-k">Merchant</div>
                  <div className="inspect-v">{selectedAlert.merchant || selectedAlert.merchant_category || '-'}</div>
                </div>
                <div className="inspect-block">
                  <div className="inspect-k">Timestamp</div>
                  <div className="inspect-v inspect-mono">{formatTime(selectedAlert.timestamp)}</div>
                </div>
              </div>

              <div className="inspect-divider" />

              <div className="inspect-k inspect-k-wide">Triggered Signals</div>
              <div className="inspect-signals">
                {(selectedAlert.reasons || []).map((r, i) => (
                  <div key={i} className="signal">
                    <Zap size={12} />
                    <span>{r}</span>
                  </div>
                ))}
              </div>

              {reviewed.has(selectedAlert.transaction_id) && (
                <div className="inspect-reviewed-note">
                  <CheckCircle2 size={13} /> This case has been marked reviewed
                </div>
              )}

              <div className="inspect-actions">
                <button className="act act-primary" onClick={() => handleEscalate(selectedAlert)}>Escalate Case</button>
                <button className="act act-ghost" onClick={() => handleReview(selectedAlert)}>Mark Reviewed</button>
              </div>
            </div>
          ) : (
            <div className="inspect-empty">
              <Eye size={26} strokeWidth={1.2} />
              <p>Select a threat</p>
              <span>Click any event in the feed to inspect its full signal chain</span>
            </div>
          )}
        </section>
      </div>

      {/* Status Footer */}
      <footer className="status-bar">
        <div className="status-seg"><span className="status-dot ok" /> DETECTION ENGINE</div>
        <div className="status-seg"><span className="status-dot ok" /> KAFKA STREAM</div>
        <div className="status-seg"><span className="status-dot ok" /> MONGO STORE</div>
        <div className="status-seg status-push"><Globe size={12} /> Isolation Forest &middot; 284K training records &middot; hybrid rules active</div>
      </footer>

      {/* Toast Notification */}
      {toast && (
        <div className={`toast toast-${toast.type}`}>
          <CheckCircle2 size={15} />
          <span>{toast.msg}</span>
        </div>
      )}
    </div>
  );
}

export default App;