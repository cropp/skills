#!/usr/bin/env python3
"""
Trading Dashboard — local Flask web server.
Dark glassmorphism UI with Plotly charts.
Shows all configured accounts: positions, P&L, equity curve, trade history.

Usage:
  python3 dashboard.py [--port 7432]
"""
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from db import init_db

try:
    from flask import Flask, jsonify, render_template_string
except ImportError:
    print("Flask not installed. Run: pip install flask")
    sys.exit(1)

import alpaca_client as ac
from market_filters import get_recent_news

app = Flask(__name__)

# ── HTML Template ──────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Trading Dashboard</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.27.0/plotly.min.js"></script>
  <style>
    :root {
      --bg:        #080b14;
      --surface:   rgba(255,255,255,0.04);
      --border:    rgba(255,255,255,0.08);
      --green:     #00e676;
      --red:       #ff1744;
      --blue:      #448aff;
      --purple:    #e040fb;
      --yellow:    #ffd740;
      --text:      #e8eaf6;
      --muted:     rgba(232,234,246,0.45);
      --glow-g:    0 0 20px rgba(0,230,118,0.2);
      --glow-r:    0 0 20px rgba(255,23,68,0.2);
      --glow-b:    0 0 20px rgba(68,138,255,0.15);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* Animated background grid */
    body::before {
      content: '';
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(68,138,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(68,138,255,0.03) 1px, transparent 1px);
      background-size: 40px 40px;
      pointer-events: none;
      z-index: 0;
    }

    .wrapper { position: relative; z-index: 1; padding: 24px; max-width: 1600px; margin: 0 auto; }

    /* Header */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 1.3rem;
      font-weight: 700;
      letter-spacing: 0.05em;
    }
    .logo-dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 12px var(--green);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.5; transform: scale(0.8); }
    }
    .header-right { display: flex; align-items: center; gap: 16px; }
    .refresh-btn {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-family: inherit;
      font-size: 0.8rem;
      transition: all 0.2s;
    }
    .refresh-btn:hover { border-color: var(--blue); color: var(--blue); }
    .last-update { color: var(--muted); font-size: 0.75rem; }

    /* Account tabs */
    .tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 24px;
    }
    .tab {
      padding: 8px 20px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--muted);
      cursor: pointer;
      font-family: inherit;
      font-size: 0.85rem;
      transition: all 0.2s;
    }
    .tab.active, .tab:hover {
      border-color: var(--blue);
      color: var(--blue);
      background: rgba(68,138,255,0.08);
      box-shadow: var(--glow-b);
    }
    .tab .badge {
      display: inline-block;
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 0.7rem;
      margin-left: 6px;
    }
    .paper-badge { background: rgba(255,215,64,0.15); color: var(--yellow); }
    .live-badge  { background: rgba(0,230,118,0.15);  color: var(--green); }

    /* Cards grid */
    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      backdrop-filter: blur(10px);
      transition: border-color 0.2s;
    }
    .card:hover { border-color: rgba(255,255,255,0.15); }
    .card-label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px; }
    .card-value { font-size: 1.6rem; font-weight: 700; }
    .card-sub   { font-size: 0.8rem; color: var(--muted); margin-top: 4px; }
    .green  { color: var(--green); }
    .red    { color: var(--red); }
    .blue   { color: var(--blue); }
    .purple { color: var(--purple); }

    /* Charts row */
    .charts-row {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 16px;
      margin-bottom: 28px;
    }
    .chart-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      backdrop-filter: blur(10px);
    }
    .chart-title {
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      margin-bottom: 16px;
    }

    /* Tables */
    .section-title {
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    .table-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      backdrop-filter: blur(10px);
      margin-bottom: 20px;
      overflow-x: auto;
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th {
      text-align: left;
      color: var(--muted);
      font-weight: 500;
      padding: 8px 12px;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255,255,255,0.02); }
    .symbol-cell { font-weight: 700; color: var(--blue); }
    .mono { font-family: 'SF Mono', monospace; }

    /* Pill badges */
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 600;
    }
    .pill-buy   { background: rgba(0,230,118,0.12); color: var(--green); }
    .pill-sell  { background: rgba(255,23,68,0.12);  color: var(--red); }
    .pill-paper { background: rgba(255,215,64,0.12); color: var(--yellow); }
    .pill-live  { background: rgba(0,230,118,0.12);  color: var(--green); }

    .empty-state {
      text-align: center;
      color: var(--muted);
      padding: 40px;
      font-size: 0.85rem;
    }

    /* Loading */
    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 200px;
      color: var(--muted);
    }
    .spinner {
      width: 24px; height: 24px;
      border: 2px solid var(--border);
      border-top-color: var(--blue);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin-right: 12px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* News feed */
    .news-item {
      display: flex;
      gap: 12px;
      padding: 12px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .news-item:last-child { border-bottom: none; }
    .news-sentiment {
      width: 6px;
      min-width: 6px;
      border-radius: 3px;
      align-self: stretch;
    }
    .sent-positive { background: var(--green); }
    .sent-negative { background: var(--red); }
    .sent-neutral  { background: rgba(255,255,255,0.2); }
    .news-content { flex: 1; }
    .news-headline {
      font-size: 0.83rem;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      line-height: 1.4;
      margin-bottom: 3px;
    }
    .news-headline a { color: var(--text); text-decoration: none; }
    .news-headline a:hover { color: var(--blue); }
    .news-meta { font-size: 0.7rem; color: var(--muted); }
    .news-symbols { display: inline-flex; gap: 4px; }
    .news-sym {
      background: rgba(68,138,255,0.12);
      color: var(--blue);
      padding: 0px 5px;
      border-radius: 3px;
      font-size: 0.68rem;
      font-weight: 600;
    }

    /* Analysis log */
    .log-entry {
      padding: 14px;
      border-left: 2px solid var(--blue);
      margin-bottom: 10px;
      background: rgba(255,255,255,0.02);
      border-radius: 0 8px 8px 0;
    }
    .log-entry.param-change { border-left-color: var(--yellow); }
    .log-meta { font-size: 0.72rem; color: var(--muted); margin-bottom: 4px; }
    .log-text { font-size: 0.82rem; line-height: 1.5; }
    .log-change { color: var(--yellow); font-size: 0.78rem; margin-top: 4px; }

    @media (max-width: 900px) {
      .charts-row { grid-template-columns: 1fr; }
      .cards-grid { grid-template-columns: repeat(2, 1fr); }
    }
  </style>
</head>
<body>
<div class="wrapper">
  <header>
    <div class="logo">
      <div class="logo-dot"></div>
      TRADE DESK
    </div>
    <div class="header-right">
      <span class="last-update" id="lastUpdate">Loading...</span>
      <button class="refresh-btn" onclick="loadData()">↻ Refresh</button>
    </div>
  </header>

  <div class="tabs" id="tabs"></div>

  <div id="content">
    <div class="loading"><div class="spinner"></div> Loading account data...</div>
  </div>
</div>

<script>
let allData   = {};
let activeTab = null;

async function loadData() {
  try {
    const r = await fetch('/api/data');
    allData  = await r.json();
    document.getElementById('lastUpdate').textContent =
      'Updated ' + new Date().toLocaleTimeString();
    renderTabs();
    if (activeTab && allData[activeTab]) {
      renderAccount(activeTab);
    } else {
      const first = Object.keys(allData)[0];
      if (first) { activeTab = first; renderAccount(first); }
    }
  } catch(e) {
    document.getElementById('content').innerHTML =
      '<div class="empty-state">Error loading data: ' + e.message + '</div>';
  }
}

function renderTabs() {
  const tabs = document.getElementById('tabs');
  tabs.innerHTML = '';
  for (const [name, data] of Object.entries(allData)) {
    const kind  = data.account?.paper ? 'PAPER' : 'LIVE';
    const badge = data.account?.paper
      ? '<span class="badge paper-badge">PAPER</span>'
      : '<span class="badge live-badge">LIVE</span>';
    const btn = document.createElement('button');
    btn.className = 'tab' + (name === activeTab ? ' active' : '');
    btn.innerHTML = name.toUpperCase() + badge;
    btn.onclick = () => { activeTab = name; renderTabs(); renderAccount(name); };
    tabs.appendChild(btn);
  }
}

function fmt$(n) {
  if (n == null) return '—';
  return '$' + parseFloat(n).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
}
function fmtPct(n) {
  if (n == null) return '—';
  const v = parseFloat(n);
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
}
function colorClass(n) {
  if (n == null) return '';
  return parseFloat(n) >= 0 ? 'green' : 'red';
}

function renderAccount(name) {
  const d = allData[name];
  if (!d) return;
  const a = d.account || {};
  const positions = d.positions || [];
  const trades    = d.trades    || [];
  const history   = d.history   || {};
  const snapshots = d.snapshots || [];
  const logs      = d.analysis_log || [];

  const pnl    = a.pnl_today   || 0;
  const pnlPct = a.pnl_today_pct || 0;
  const gclass = pnl >= 0 ? 'green' : 'red';

  // Latest snapshot metrics
  const snap = snapshots.length ? snapshots[snapshots.length - 1] : {};

  let html = `
  <div class="cards-grid">
    <div class="card">
      <div class="card-label">Portfolio Value</div>
      <div class="card-value blue">${fmt$(a.equity)}</div>
      <div class="card-sub">Cash: ${fmt$(a.cash)}</div>
    </div>
    <div class="card">
      <div class="card-label">Today's P&L</div>
      <div class="card-value ${gclass}">${fmt$(pnl)}</div>
      <div class="card-sub ${gclass}">${fmtPct(pnlPct)}</div>
    </div>
    <div class="card">
      <div class="card-label">Buying Power</div>
      <div class="card-value">${fmt$(a.buying_power)}</div>
      <div class="card-sub">${a.paper ? 'Paper Account' : 'Live Account'}</div>
    </div>
    <div class="card">
      <div class="card-label">Win Rate</div>
      <div class="card-value ${snap.win_rate >= 50 ? 'green' : 'red'}">${snap.win_rate != null ? snap.win_rate.toFixed(1)+'%' : '—'}</div>
      <div class="card-sub">${snap.total_trades || 0} trades</div>
    </div>
    <div class="card">
      <div class="card-label">Sharpe Ratio</div>
      <div class="card-value ${(snap.sharpe_ratio||0) >= 1 ? 'green' : (snap.sharpe_ratio||0) >= 0 ? 'yellow' : 'red'}">${snap.sharpe_ratio != null ? snap.sharpe_ratio.toFixed(2) : '—'}</div>
      <div class="card-sub">30-day annualized</div>
    </div>
    <div class="card">
      <div class="card-label">Max Drawdown</div>
      <div class="card-value red">${snap.max_drawdown != null ? snap.max_drawdown.toFixed(2)+'%' : '—'}</div>
      <div class="card-sub">Peak to trough</div>
    </div>
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <div class="chart-title">Equity Curve</div>
      <div id="chartEquity" style="height:240px"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Daily P&L</div>
      <div id="chartPnl" style="height:240px"></div>
    </div>
  </div>

  <div class="table-card">
    <div class="section-title">Open Positions (${positions.length})</div>
    ${positions.length === 0 ? '<div class="empty-state">No open positions</div>' : `
    <table>
      <thead><tr>
        <th>Symbol</th><th>Shares</th><th>Avg Entry</th><th>Current</th>
        <th>Market Value</th><th>Unrealized P&L</th><th>Change Today</th><th>Buy Date</th>
      </tr></thead>
      <tbody>
        ${positions.map(p => {
          const plc = (p.unrealized_plpc||0) >= 0 ? 'green' : 'red';
          const buyTrade = trades.find(t => t.symbol === p.symbol && t.side === 'buy');
          const buyDate  = buyTrade ? buyTrade.timestamp?.split('T')[0] || buyTrade.timestamp?.split(' ')[0] || '—' : '—';
          return `<tr>
            <td class="symbol-cell">${p.symbol}</td>
            <td class="mono">${parseFloat(p.qty).toFixed(2)}</td>
            <td class="mono">${fmt$(p.avg_entry)}</td>
            <td class="mono">${fmt$(p.current_price)}</td>
            <td class="mono">${fmt$(p.market_value)}</td>
            <td class="mono ${plc}">${fmt$(p.unrealized_pl)} <span style="font-size:0.75em">(${fmtPct(p.unrealized_plpc)})</span></td>
            <td class="mono ${(p.change_today||0)>=0?'green':'red'}">${fmtPct(p.change_today)}</td>
            <td>${buyDate}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`}
  </div>

  <div class="table-card">
    <div class="section-title">Trade History (Last 50)</div>
    ${trades.length === 0 ? '<div class="empty-state">No trades yet</div>' : `
    <table>
      <thead><tr>
        <th>Date</th><th>Symbol</th><th>Side</th><th>Shares</th>
        <th>Price</th><th>Total</th><th>P&L</th><th>Strategy</th>
      </tr></thead>
      <tbody>
        ${trades.slice(0,50).map(t => {
          const total = t.price && t.qty ? t.price * t.qty : null;
          const plc   = t.pnl == null ? '' : t.pnl >= 0 ? 'green' : 'red';
          return `<tr>
            <td>${(t.timestamp||'').substring(0,16)}</td>
            <td class="symbol-cell">${t.symbol}</td>
            <td><span class="pill pill-${t.side}">${t.side.toUpperCase()}</span></td>
            <td class="mono">${parseFloat(t.qty||0).toFixed(2)}</td>
            <td class="mono">${fmt$(t.price)}</td>
            <td class="mono">${fmt$(total)}</td>
            <td class="mono ${plc}">${t.pnl != null ? fmt$(t.pnl) : '—'}</td>
            <td style="color:var(--muted);font-size:0.75em">${t.strategy||'—'}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`}
  </div>

  <div class="table-card">
    <div class="section-title">Recent News & Sentiment</div>
    <div id="newsSection">
      <div class="loading" style="min-height:80px"><div class="spinner"></div> Loading news...</div>
    </div>
  </div>

  <div class="table-card">
    <div class="section-title">Analysis & Self-Update Log</div>
    ${logs.length === 0 ? '<div class="empty-state">No analysis runs yet</div>' :
      logs.slice(0,20).map(l => `
        <div class="log-entry ${l.param_changed ? 'param-change' : ''}">
          <div class="log-meta">${l.run_at} · ${l.strategy_name}</div>
          <div class="log-text">${l.reasoning}</div>
          ${l.param_changed ? `<div class="log-change">⚡ ${l.param_changed}: ${l.old_value} → ${l.new_value} (trigger: ${l.metric_trigger})</div>` : ''}
        </div>`).join('')
    }
  </div>`;

  document.getElementById('content').innerHTML = html;

  // ── News feed ───────────────────────────────────────────────────────────────
  const watchSymbols = positions.map(p => p.symbol);
  if (watchSymbols.length) loadNews(name, watchSymbols);
  else {
    const ns = document.getElementById('newsSection');
    if (ns) ns.innerHTML = '<div class="empty-state">No positions — open some trades to see news</div>';
  }

  // ── Equity chart ────────────────────────────────────────────────────────────
  if (history.timestamps && history.equity) {
    const color = (history.equity[history.equity.length-1] || 0) >= (history.equity[0] || 0)
      ? '#00e676' : '#ff1744';
    Plotly.newPlot('chartEquity', [{
      x: history.timestamps,
      y: history.equity,
      type: 'scatter',
      mode: 'lines',
      line: { color, width: 2 },
      fill: 'tozeroy',
      fillcolor: color.replace(')', ',0.08)').replace('rgb', 'rgba'),
      name: 'Equity',
    }], {
      paper_bgcolor: 'transparent',
      plot_bgcolor:  'transparent',
      margin: { t:10, r:10, b:30, l:60 },
      xaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: 'rgba(232,234,246,0.4)', tickfont:{size:10} },
      yaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: 'rgba(232,234,246,0.4)', tickformat:'$,.0f', tickfont:{size:10} },
      showlegend: false,
    }, { responsive: true, displayModeBar: false });
  }

  // ── Daily P&L bar chart ────────────────────────────────────────────────────
  if (history.timestamps && history.profit_loss) {
    const colors = history.profit_loss.map(v => v >= 0 ? '#00e676' : '#ff1744');
    Plotly.newPlot('chartPnl', [{
      x: history.timestamps,
      y: history.profit_loss,
      type: 'bar',
      marker: { color: colors },
      name: 'Daily P&L',
    }], {
      paper_bgcolor: 'transparent',
      plot_bgcolor:  'transparent',
      margin: { t:10, r:10, b:30, l:60 },
      xaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: 'rgba(232,234,246,0.4)', tickfont:{size:9} },
      yaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: 'rgba(232,234,246,0.4)', tickformat:'$,.0f', tickfont:{size:10} },
      showlegend: false,
    }, { responsive: true, displayModeBar: false });
  }
}

async function loadNews(accountName, symbols) {
  const section = document.getElementById('newsSection');
  if (!section) return;
  try {
    const r = await fetch(`/api/news?account=${accountName}&symbols=${symbols.join(',')}`);
    const news = await r.json();
    const all = Object.entries(news).flatMap(([sym, articles]) =>
      articles.map(a => ({...a, sym}))
    ).sort((a,b) => (b.published_at||'').localeCompare(a.published_at||''));

    if (!all.length) {
      section.innerHTML = '<div class="empty-state">No recent news</div>';
      return;
    }
    section.innerHTML = all.slice(0,20).map(a => `
      <div class="news-item">
        <div class="news-sentiment sent-${a.sentiment}"></div>
        <div class="news-content">
          <div class="news-headline">
            ${a.url ? `<a href="${a.url}" target="_blank">${a.headline}</a>` : a.headline}
          </div>
          <div class="news-meta">
            <span class="news-sym">${a.sym}</span>
            &nbsp;${a.source || ''}&nbsp;·&nbsp;${(a.published_at||'').substring(0,16)}
            &nbsp;·&nbsp;<span style="color:${a.sentiment==='positive'?'var(--green)':a.sentiment==='negative'?'var(--red)':'var(--muted)'}">${a.sentiment}</span>
          </div>
        </div>
      </div>`).join('');
  } catch(e) {
    section.innerHTML = `<div class="empty-state">News unavailable</div>`;
  }
}

// Auto-refresh every 30 seconds
loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>"""


# ── API Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/data")
def api_data():
    result = {}
    accounts = db.get_accounts()

    if not accounts:
        return jsonify({"_error": "No accounts configured. Run setup.py first."})

    for acct in accounts:
        name = acct["name"]
        data = {"account": None, "positions": [], "trades": [], "history": {}, "snapshots": [], "analysis_log": []}

        # Account info (live from Alpaca)
        try:
            data["account"] = ac.get_account_info(name)
        except Exception as e:
            data["account"] = {"name": name, "error": str(e), "paper": bool(acct["paper"])}

        # Positions (live)
        try:
            data["positions"] = ac.get_positions(name)
        except Exception as e:
            data["positions"] = []

        # Portfolio history (live)
        try:
            data["history"] = ac.get_portfolio_history(name, days=30)
        except Exception as e:
            data["history"] = {}

        # Trades from DB
        data["trades"] = db.get_trades(account_name=name, days=90, limit=100)

        # Performance snapshots from DB
        data["snapshots"] = db.get_snapshots(account_name=name, days=90)

        # Analysis log from DB
        data["analysis_log"] = db.get_analysis_log(account_name=name, limit=20)

        result[name] = data

    return jsonify(result)


@app.route("/api/news")
def api_news():
    from flask import request as freq
    account_name = freq.args.get("account", "paper")
    symbols_raw  = freq.args.get("symbols", "")
    symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]
    if not symbols:
        return jsonify({})
    try:
        news = get_recent_news(account_name, symbols, hours=48)
        return jsonify(news)
    except Exception as e:
        return jsonify({"_error": str(e)})


@app.route("/api/accounts")
def api_accounts():
    return jsonify(db.get_accounts())


@app.route("/api/params/<strategy>")
def api_params(strategy):
    return jsonify(db.get_all_params(strategy))


def main():
    parser = argparse.ArgumentParser(description="Trading Dashboard")
    parser.add_argument("--port", default=7432, type=int, help="Port to run on (default: 7432)")
    parser.add_argument("--host", default="127.0.0.1",  help="Host (default: 127.0.0.1)")
    args = parser.parse_args()

    init_db()
    accounts = db.get_accounts()
    if not accounts:
        print("No accounts configured. Run setup.py first.")
        print("Then come back and run dashboard.py\n")

    print(f"\n{'─'*45}")
    print(f"  Trade Desk Dashboard")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Auto-refreshes every 30 seconds")
    print(f"{'─'*45}\n")

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
