/**
 * app.js — BTC Quant Forecaster Dashboard
 * Handles: live price, chart rendering, backtest visualisation,
 *          gauge animation, regime colouring, auto-refresh.
 */

'use strict';

// ─── Config ───────────────────────────────────────────
const API_BASE      = '';           // same-origin FastAPI
const REFRESH_MS    = 30_000;       // live data refresh interval
const PRICE_REFRESH = 10_000;       // price-only fast refresh
const fmt           = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 });
const fmtFull       = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct        = v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
const fmtVol        = v => (v / 1e3).toFixed(1) + 'K BTC';
const circumference = 2 * Math.PI * 32;   // gauge radius = 32

// ─── State ────────────────────────────────────────────
let priceChart   = null;
let btChart      = null;
let regimeChart  = null;
let prevPrice    = null;
let isFirstLoad  = true;

// ─── DOM helpers ──────────────────────────────────────
const $  = id => document.getElementById(id);
const setText = (id, v) => { const el = $(id); if (el) el.textContent = v; };
const setClass = (id, cls) => { const el = $(id); if (el) { el.className = el.className.replace(/\b(pos|neg|calm|medium|volatile)\b/g, ''); el.classList.add(cls); } };

// ─── Toast ────────────────────────────────────────────
function showToast(msg, duration = 3000) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

// ─── Gauge Updater ────────────────────────────────────
function setGauge(fillId, fraction) {
  const el = $(fillId);
  if (!el) return;
  const clamped = Math.min(Math.max(fraction, 0), 1);
  el.setAttribute('stroke-dasharray', `${clamped * circumference} ${circumference}`);
}

// ─── Flash animation ──────────────────────────────────
function flashValue(id, direction) {
  const el = $(id);
  if (!el) return;
  const cls = direction === 'up' ? 'flash-up' : 'flash-down';
  el.classList.add(cls);
  setTimeout(() => el.classList.remove(cls), 700);
}

// ─── Number counter ───────────────────────────────────
function animateNumber(id, targetStr) {
  const el = $(id);
  if (!el) return;
  el.textContent = targetStr;
}

// ─── Chart: Main Price + CI Band ──────────────────────
function initPriceChart() {
  const ctx = $('priceChart').getContext('2d');
  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Close Price',
          data: [],
          borderColor: '#f7931a',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          order: 1,
        },
        {
          label: 'Upper CI',
          data: [],
          borderColor: 'rgba(167,139,250,0.7)',
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
          tension: 0.3,
          fill: '+1',
          backgroundColor: 'rgba(100,130,255,0.08)',
          order: 2,
        },
        {
          label: 'Lower CI',
          data: [],
          borderColor: 'rgba(0,212,255,0.7)',
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          order: 2,
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 600, easing: 'easeInOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(13,21,38,0.95)',
          borderColor: 'rgba(255,255,255,0.12)',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#e2e8f0',
          padding: 12,
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${fmtFull.format(ctx.parsed.y)}`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#475569', font: { size: 10, family: 'Inter' }, maxTicksLimit: 8, maxRotation: 0 },
          grid:  { color: 'rgba(255,255,255,0.04)' },
        },
        y: {
          position: 'right',
          ticks: { color: '#475569', font: { size: 10, family: 'JetBrains Mono' }, callback: v => '$' + (v/1000).toFixed(1) + 'K' },
          grid:  { color: 'rgba(255,255,255,0.04)' },
        }
      }
    }
  });
}

function updatePriceChart(candles, lower, upper) {
  if (!priceChart) return;

  const labels  = candles.map(c => {
    const d = new Date(c.timestamp);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  });
  const closes  = candles.map(c => c.close);

  // Extend the last candle with forecast band
  const lastLabel  = 'Next';
  const lastClose  = closes[closes.length - 1];

  priceChart.data.labels              = [...labels, lastLabel];
  priceChart.data.datasets[0].data    = [...closes, null];
  priceChart.data.datasets[1].data    = [...Array(closes.length).fill(null), upper];
  priceChart.data.datasets[2].data    = [...Array(closes.length).fill(null), lower];

  // Draw shaded band over last few bars
  // We add the CI band as a fill on the last 2 points
  priceChart.update('active');
}

// ─── Chart: Backtest detail ────────────────────────────
function initBtChart() {
  const ctx = $('btChart').getContext('2d');
  btChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Actual',
          data: [],
          borderColor: '#f7931a',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: false,
          order: 1,
        },
        {
          label: 'Upper CI',
          data: [],
          borderColor: 'rgba(167,139,250,0.6)',
          borderWidth: 1,
          borderDash: [4, 3],
          pointRadius: 0,
          tension: 0.2,
          fill: '+1',
          backgroundColor: 'rgba(0,212,255,0.07)',
          order: 2,
        },
        {
          label: 'Lower CI',
          data: [],
          borderColor: 'rgba(0,212,255,0.6)',
          borderWidth: 1,
          borderDash: [4, 3],
          pointRadius: 0,
          tension: 0.2,
          fill: false,
          order: 2,
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 800 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(13,21,38,0.95)',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleColor: '#64748b',
          bodyColor: '#e2e8f0',
          padding: 10,
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${fmtFull.format(ctx.parsed.y)}`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#334155', font: { size: 9 }, maxTicksLimit: 10, maxRotation: 0 },
          grid:  { color: 'rgba(255,255,255,0.03)' },
        },
        y: {
          position: 'right',
          ticks: { color: '#334155', font: { size: 9, family: 'JetBrains Mono' }, callback: v => '$' + (v/1000).toFixed(0) + 'K' },
          grid:  { color: 'rgba(255,255,255,0.03)' },
        }
      }
    }
  });
}

function updateBtChart(details) {
  if (!btChart || !details || details.length === 0) return;

  const labels = details.map((_, i) => `T-${details.length - i}`);
  btChart.data.labels              = labels;
  btChart.data.datasets[0].data   = details.map(d => d.actual);
  btChart.data.datasets[1].data   = details.map(d => d.upper);
  btChart.data.datasets[2].data   = details.map(d => d.lower);
  btChart.update('active');
}

// ─── Chart: Regime Pie ────────────────────────────────
function initRegimeChart() {
  const ctx = $('regimeChart').getContext('2d');
  regimeChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Calm', 'Medium', 'Volatile'],
      datasets: [{
        data: [1, 1, 1],
        backgroundColor: [
          'rgba(0,212,255,0.8)',
          'rgba(251,191,36,0.8)',
          'rgba(247,147,26,0.8)',
        ],
        borderColor: '#070b14',
        borderWidth: 3,
        hoverOffset: 8,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      animation: { animateRotate: true, duration: 900 },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: '#64748b', font: { size: 10, family: 'Inter' }, padding: 10, boxWidth: 10 }
        },
        tooltip: {
          backgroundColor: 'rgba(13,21,38,0.95)',
          bodyColor: '#e2e8f0',
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} bars`
          }
        }
      }
    }
  });
}

function updateRegimeChart(details) {
  if (!regimeChart || !details) return;
  const counts = { calm: 0, medium: 0, volatile: 0 };
  details.forEach(d => { if (d.regime in counts) counts[d.regime]++; });
  regimeChart.data.datasets[0].data = [counts.calm, counts.medium, counts.volatile];
  regimeChart.update();
}

// ─── Main update ──────────────────────────────────────
async function fetchAndUpdate() {
  try {
    const res  = await fetch(`${API_BASE}/api/forecast`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const p    = data.live_price;
    const fc   = data.forecast;
    const bt   = data.backtest;
    const s24  = data.stats_24h;
    const cands = data.candles || [];

    // ── Header
    const priceStr = fmtFull.format(p);
    const changeStr = fmtPct(s24.price_change_pct);
    animateNumber('headerPrice', priceStr);
    const changeEl = $('headerChange');
    changeEl.textContent = changeStr;
    const dir = s24.price_change_pct >= 0 ? 'pos' : 'neg';
    changeEl.className = `header-change ${dir}`;
    $('lastUpdate').textContent = `Updated ${new Date(data.timestamp).toLocaleTimeString()}`;

    // ── KPI cards
    if (prevPrice !== null) {
      if (p > prevPrice) flashValue('kpiPriceVal', 'up');
      else if (p < prevPrice) flashValue('kpiPriceVal', 'down');
    }
    prevPrice = p;

    setText('kpiPriceVal', fmtFull.format(p));
    setText('kpiPriceSub', `${changeStr} (24h)`);

    setText('kpiLowerVal', fmt.format(fc.lower));
    setText('kpiLowerSub', `${(((fc.lower - p) / p) * 100).toFixed(2)}% vs current`);

    setText('kpiUpperVal', fmt.format(fc.upper));
    setText('kpiUpperSub', `${(((fc.upper - p) / p) * 100).toFixed(2)}% vs current`);

    const width = fc.upper - fc.lower;
    const widthPct = ((width / p) * 100).toFixed(2);
    setText('kpiWidthVal', fmt.format(width));
    setText('kpiWidthSub', `${widthPct}% of price`);

    // ── Model params
    const regimeName = fc.regime;
    setText('paramRegime', regimeName.charAt(0).toUpperCase() + regimeName.slice(1));
    $('paramRegime').className = `param-val regime-val ${regimeName}`;
    setText('paramSigma', (fc.sigma * 100).toFixed(4) + '%');
    setText('paramDf',    fc.df.toFixed(2));
    setText('paramMu',    (fc.mu * 100).toFixed(5) + '%');
    setText('paramCalib', fc.calib.toFixed(4));

    // ── Regime badge
    const rb = $('regimeBadge');
    rb.textContent = regimeName.toUpperCase();
    rb.className = `regime-badge ${regimeName}`;

    // ── Calib badge
    $('calibBadge').textContent = `calib: ${fc.calib.toFixed(3)}`;

    // ── Backtest metrics gauges
    const cov = bt.coverage * 100;
    setText('coverageVal', cov.toFixed(1));
    setGauge('coverageFill', bt.coverage);                       // fill by actual coverage
    $('coverageFill').style.stroke = cov >= 93 && cov <= 97 ? '#34d399' : '#f7931a';

    setText('widthVal', (bt.avg_width / 1000).toFixed(1) + 'K');
    // gauge: lower width is better; fill inversely (relative to 5% of price)
    const widthNorm = Math.min(bt.avg_width / (p * 0.06), 1);
    setGauge('widthFill', 1 - widthNorm);

    setText('winklerVal', (bt.winkler / 1000).toFixed(1) + 'K');
    const winkNorm = Math.min(bt.winkler / (p * 0.12), 1);
    setGauge('winklerFill', 1 - winkNorm);

    setText('btSamples', bt.n_samples.toLocaleString());

    // ── 24h stats
    setText('stat24hHigh',   fmtFull.format(s24.high_24h));
    setText('stat24hLow',    fmtFull.format(s24.low_24h));
    $('stat24hChange').textContent = changeStr;
    $('stat24hChange').className   = `stat-val ${s24.price_change_pct >= 0 ? 'green' : 'red'}`;
    setText('stat24hVol', fmtVol(s24.volume_24h));

    // ── Main price chart
    updatePriceChart(cands, fc.lower, fc.upper);

    if (isFirstLoad) {
      showToast('✅ Forecast loaded — 95% CI active');
      isFirstLoad = false;
    }

  } catch (err) {
    console.error('Forecast fetch error:', err);
    showToast('⚠️ API error — retrying…', 4000);
  }
}

async function fetchBtDetails() {
  try {
    const res  = await fetch(`${API_BASE}/api/backtest_details?limit=100`);
    if (!res.ok) return;
    const data = await res.json();
    updateBtChart(data.details);
    updateRegimeChart(data.details);
  } catch (e) {
    console.error('BT detail fetch error:', e);
  }
}

// ─── Fast price refresh ───────────────────────────────
async function refreshPrice() {
  try {
    const res  = await fetch(`${API_BASE}/api/price`);
    if (!res.ok) return;
    const data = await res.json();
    const p = data.price;

    if (prevPrice !== null) {
      if (p > prevPrice) flashValue('headerPrice', 'up');
      else if (p < prevPrice) flashValue('headerPrice', 'down');
    }
    prevPrice = p;

    setText('headerPrice', fmtFull.format(p));
    const pct = data.price_change_pct;
    $('headerChange').textContent = fmtPct(pct);
    $('headerChange').className = `header-change ${pct >= 0 ? 'pos' : 'neg'}`;
    setText('kpiPriceVal', fmtFull.format(p));
  } catch (_) {}
}

// ─── Boot ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initPriceChart();
  initBtChart();
  initRegimeChart();

  // Initial load
  fetchAndUpdate();
  fetchBtDetails();

  // Periodic refresh
  setInterval(fetchAndUpdate,  REFRESH_MS);
  setInterval(fetchBtDetails,  REFRESH_MS * 2);
  setInterval(refreshPrice,    PRICE_REFRESH);
});
