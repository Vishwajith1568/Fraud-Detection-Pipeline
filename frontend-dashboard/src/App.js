import React, { useState, useEffect, useMemo } from 'react';
import io from 'socket.io-client';
import { ShieldAlert, Activity, CreditCard, Clock, Lock, TrendingUp, AlertTriangle, Users } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, PieChart, Pie
} from 'recharts';
import './App.css';

function App() {
  const [alerts, setAlerts] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
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
        setLoginError(data.message || 'Authentication Failed');
      }
    } catch (err) {
      setLoginError('Cannot connect to security backend');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken('');
    setAlerts([]);
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
        console.error("Error fetching historical alerts:", error);
      }
    };

    fetchHistory();

    const socket = io('http://localhost:4000');
    socket.on('connect', () => setIsConnected(true));
    socket.on('disconnect', () => setIsConnected(false));
    socket.on('new_fraud_alert', (newAlert) => {
      setAlerts((prevAlerts) => [newAlert, ...prevAlerts].slice(0, 100));
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
    if (!ts) return "Unknown Time";
    const dateObj = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
    return dateObj.toLocaleTimeString();
  };

  // ── CHART DATA CALCULATIONS ──

  // Alerts grouped by minute for the line chart
  const timelineData = useMemo(() => {
    if (alerts.length === 0) return [];

    const minuteBuckets = {};
    alerts.forEach(alert => {
      if (!alert.timestamp) return;
      const dateObj = typeof alert.timestamp === 'number'
        ? new Date(alert.timestamp * 1000)
        : new Date(alert.timestamp);
      const minuteKey = dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      minuteBuckets[minuteKey] = (minuteBuckets[minuteKey] || 0) + 1;
    });

    return Object.entries(minuteBuckets)
      .map(([time, count]) => ({ time, count }))
      .slice(-15); // last 15 minutes
  }, [alerts]);

  // Alerts grouped by reason type for the bar chart
  const reasonData = useMemo(() => {
    if (alerts.length === 0) return [];

    const reasonCounts = {};
    alerts.forEach(alert => {
      (alert.reasons || []).forEach(reason => {
        // Shorten reason labels for chart readability
        let label = reason;
        if (reason.includes('Velocity')) label = 'Velocity';
        else if (reason.includes('International')) label = 'International';
        else if (reason.includes('AI Anomaly')) label = 'AI Anomaly';
        reasonCounts[label] = (reasonCounts[label] || 0) + 1;
      });
    });

    return Object.entries(reasonCounts)
      .map(([reason, count]) => ({ reason, count }))
      .sort((a, b) => b.count - a.count);
  }, [alerts]);

  // Severity distribution for pie chart
  const severityData = useMemo(() => {
    if (alerts.length === 0) return [];

    let high = 0, medium = 0, low = 0;
    alerts.forEach(alert => {
      const numReasons = (alert.reasons || []).length;
      if (numReasons >= 3) high++;
      else if (numReasons === 2) medium++;
      else low++;
    });

    return [
      { name: 'Critical', value: high, color: '#ef4444' },
      { name: 'Warning', value: medium, color: '#f59e0b' },
      { name: 'Low', value: low, color: '#3b82f6' },
    ].filter(d => d.value > 0);
  }, [alerts]);

  // Summary stats
  const stats = useMemo(() => {
    const totalAlerts = alerts.length;
    const uniqueUsers = new Set(alerts.map(a => a.user_id)).size;

    const aiCount = alerts.filter(a =>
      (a.reasons || []).some(r => r.includes('AI Anomaly'))
    ).length;

    const avgAmount = totalAlerts > 0
      ? (alerts.reduce((sum, a) => sum + (a.amount || 0), 0) / totalAlerts).toFixed(2)
      : '0.00';

    return { totalAlerts, uniqueUsers, aiCount, avgAmount };
  }, [alerts]);

  // Bar chart colors
  const BAR_COLORS = ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6'];

  // Custom tooltip for charts
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          background: '#1e293b', border: '1px solid #334155', borderRadius: '8px',
          padding: '10px 14px', color: '#f8fafc', fontSize: '0.85rem'
        }}>
          <p style={{ margin: 0, fontWeight: 600 }}>{label}</p>
          <p style={{ margin: '4px 0 0', color: '#ef4444' }}>{payload[0].value} alerts</p>
        </div>
      );
    }
    return null;
  };

  // ── LOGIN SCREEN ──
  if (!token) {
    return (
      <div className="login-wrapper" style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', backgroundColor: '#0f172a'
      }}>
        <div style={{
          background: '#1e293b', padding: '40px', borderRadius: '12px', width: '100%', maxWidth: '400px', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.3)'
        }}>
          <div style={{ textAlign: 'center', marginBottom: '30px' }}>
            <Lock size={48} color="#ef4444" style={{ marginBottom: '10px' }} />
            <h2 style={{ color: '#f8fafc', margin: 0, fontSize: '1.5rem' }}>Security Command Login</h2>
            <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: '5px' }}>Authorized Personnel Only</p>
          </div>

          {loginError && (
            <div style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: '#ef4444', padding: '10px', borderRadius: '6px', marginBottom: '20px', fontSize: '0.875rem', textAlign: 'center', border: '1px solid rgba(239,68,68,0.2)' }}>
              {loginError}
            </div>
          )}

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '8px', fontSize: '0.875rem' }}>Operator Username</label>
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} required style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #334155', backgroundColor: '#0f172a', color: '#f8fafc', boxSizing: 'border-box' }} />
          </div>

          <div style={{ marginBottom: '30px' }}>
            <label style={{ display: 'block', color: '#94a3b8', marginBottom: '8px', fontSize: '0.875rem' }}>Security Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #334155', backgroundColor: '#0f172a', color: '#f8fafc', boxSizing: 'border-box' }} />
          </div>

          <button type="button" onClick={handleLogin} style={{ width: '100%', padding: '12px', borderRadius: '6px', border: 'none', backgroundColor: '#ef4444', color: '#f8fafc', fontWeight: 'bold', cursor: 'pointer', fontSize: '1rem' }}>
            Authenticate Session
          </button>
        </div>
      </div>
    );
  }

  // ── DASHBOARD ──
  return (
    <div className="dashboard-container">
      <header className="header">
        <div className="header-title">
          <ShieldAlert size={32} color="#ff4d4f" />
          <h1>Real-Time Fraud Command Center</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div className={`status-badge ${isConnected ? 'connected' : 'disconnected'}`}>
            <Activity size={18} />
            {isConnected ? 'System Online' : 'System Offline'}
          </div>
          <button onClick={handleLogout} style={{ background: 'none', border: '1px solid #475569', color: '#94a3b8', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.875rem' }}>
            Disconnect
          </button>
        </div>
      </header>

      <main className="main-content">

        {/* ── SUMMARY STAT CARDS ── */}
        <div className="stats-row">
          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: 'rgba(239,68,68,0.15)' }}>
              <AlertTriangle size={22} color="#ef4444" />
            </div>
            <div className="stat-content">
              <span className="stat-value">{stats.totalAlerts}</span>
              <span className="stat-label">Total Alerts</span>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: 'rgba(59,130,246,0.15)' }}>
              <Users size={22} color="#3b82f6" />
            </div>
            <div className="stat-content">
              <span className="stat-value">{stats.uniqueUsers}</span>
              <span className="stat-label">Flagged Users</span>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: 'rgba(139,92,246,0.15)' }}>
              <TrendingUp size={22} color="#8b5cf6" />
            </div>
            <div className="stat-content">
              <span className="stat-value">{stats.aiCount}</span>
              <span className="stat-label">AI Detections</span>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: 'rgba(16,185,129,0.15)' }}>
              <CreditCard size={22} color="#10b981" />
            </div>
            <div className="stat-content">
              <span className="stat-value">${stats.avgAmount}</span>
              <span className="stat-label">Avg Flagged Amount</span>
            </div>
          </div>
        </div>

        {/* ── CHARTS ROW ── */}
        <div className="charts-row">

          {/* Line Chart: Alerts Over Time */}
          <div className="chart-panel">
            <h3 className="chart-title">Alerts Over Time</h3>
            {timelineData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={timelineData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} tick={{ fill: '#94a3b8' }} />
                  <YAxis stroke="#94a3b8" fontSize={11} tick={{ fill: '#94a3b8' }} allowDecimals={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Line type="monotone" dataKey="count" stroke="#ef4444" strokeWidth={2} dot={{ fill: '#ef4444', r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="chart-empty">Collecting data...</div>
            )}
          </div>

          {/* Bar Chart: Alerts by Reason */}
          <div className="chart-panel">
            <h3 className="chart-title">Alerts by Detection Type</h3>
            {reasonData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={reasonData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
                  <XAxis type="number" stroke="#94a3b8" fontSize={11} tick={{ fill: '#94a3b8' }} allowDecimals={false} />
                  <YAxis type="category" dataKey="reason" stroke="#94a3b8" fontSize={11} tick={{ fill: '#94a3b8' }} width={100} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={24}>
                    {reasonData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={BAR_COLORS[index % BAR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="chart-empty">Collecting data...</div>
            )}
          </div>

          {/* Pie Chart: Severity Distribution */}
          <div className="chart-panel chart-panel-small">
            <h3 className="chart-title">Severity Breakdown</h3>
            {severityData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={severityData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    dataKey="value"
                    stroke="none"
                  >
                    {severityData.map((entry, index) => (
                      <Cell key={`pie-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f8fafc', fontSize: '0.85rem' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="chart-empty">Collecting data...</div>
            )}
            <div className="pie-legend">
              {severityData.map((d, i) => (
                <div key={i} className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: d.color }}></span>
                  <span>{d.name}: {d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── ALERT CARDS ── */}
        <div className="alert-count">
          <h2>Live Threat Feed ({alerts.length})</h2>
        </div>

        <div className="alert-grid">
          {alerts.length === 0 ? (
            <div className="empty-state">Scan clean. Monitoring incoming Kafka telemetry data...</div>
          ) : (
            alerts.map((alert, index) => (
              <div key={alert.transaction_id || index} className="alert-card slide-in">
                <div className="card-header">
                  <span className="user-id">{alert.user_id || 'UNKNOWN_USER'}</span>
                  <span className="time"><Clock size={14}/> {formatTime(alert.timestamp)}</span>
                </div>
                <div className="card-body">
                  <div className="amount-section">
                    <span className="currency">{alert.currency || 'USD'}</span>
                    <span className="amount">{(alert.amount || 0).toLocaleString()}</span>
                  </div>
                  <div className="merchant-info">
                    <CreditCard size={16} />
                    <span>
                      {(alert.merchant || alert.merchant_category || 'UNKNOWN_MERCHANT')
                        .replace('_', ' ')
                        .toUpperCase()}
                    </span>
                  </div>
                </div>
                <div className="card-footer">
                  {(alert.reasons || []).map((reason, i) => (
                    <span key={i} className="reason-tag">{reason}</span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
}

export default App;