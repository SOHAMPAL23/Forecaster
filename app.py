import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import time

from model.data_fetcher import fetch_klines_sync, klines_to_arrays
from model.forecaster import BTCForecaster

st.set_page_config(
    page_title="BTC Quant Forecaster",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Institutional CSS
st.markdown("""
<style>
    /* Dark institutional background */
    .stApp {
        background-color: #030509;
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    
    /* Hide top header and footer for clean look */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Clean metrics */
    [data-testid="stMetricValue"] {
        color: #eab308 !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 28px !important;
    }
    [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-size: 12px !important;
    }
    [data-testid="stMetricDelta"] {
        font-family: 'JetBrains Mono', monospace;
    }
    
    /* Container styling */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }
    
    /* Stylized titles */
    h1, h2, h3 {
        color: #f8fafc !important;
        font-weight: 600 !important;
    }
    
    /* Horizontal rule */
    hr {
        border-color: rgba(255, 255, 255, 0.05) !important;
        margin-top: 1rem;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------
# Data Fetchers
# -----------------------------------------
@st.cache_data(ttl=60)
def get_historical_data():
    """Fetch 900 hours of 1h candlestick data."""
    return fetch_klines_sync(limit=900)

def get_live_data():
    """Fetch exact live ticker using requests to bypass asyncio complications."""
    base = "https://api.binance.com"
    try:
        p_res = requests.get(f"{base}/api/v3/ticker/price?symbol=BTCUSDT", timeout=5).json()
        s_res = requests.get(f"{base}/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=5).json()
        return float(p_res["price"]), {
            "price_change_pct": float(s_res["priceChangePercent"]),
            "high_24h": float(s_res["highPrice"]),
            "low_24h": float(s_res["lowPrice"]),
            "volume_24h": float(s_res["volume"])
        }
    except Exception as e:
        st.error(f"Failed to fetch live data: {e}")
        return 0.0, {"price_change_pct": 0, "high_24h": 0, "low_24h": 0, "volume_24h": 0}

@st.cache_resource
def get_forecaster():
    """Persist the forecaster object to maintain PI controller state across runs."""
    return BTCForecaster()


# Main Application

def main():
    st.title("⚡ BTC Quant Forecaster")
    # st.markdown("<span style='color:#64748b; font-family:monospace;'>Institutional Grade 1-Hour Price Range Engine • 95% CI • Jump-Diffusion Monte Carlo</span>", unsafe_allow_html=True)
    st.markdown("---")
    
    # Refresh button
    col_a, col_b = st.columns([0.85, 0.15])
    with col_b:
        if st.button("↻ Force Refresh Data", use_container_width=True):
            get_historical_data.clear()
            st.rerun()

    # Fetch Data
    with st.spinner("Fetching market data and running quantitative models..."):
        klines = get_historical_data()
        live_price, stats = get_live_data()
        
        opens, highs, lows, closes = klines_to_arrays(klines)
        forecaster = get_forecaster()
        
        # Run Backtest & Live Forecast
        bt_metrics = forecaster.backtest(closes, highs, lows, n_test=120, warmup=100)
        forecast = forecaster.predict(closes, highs, lows)

    # -----------------------------------------
    # Key Performance Indicators (KPIs)
    # -----------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Live Price", f"${live_price:,.2f}", f"{stats['price_change_pct']:+.2f}%")
    with c2:
        st.metric("Forecast Lower (95% CI)", f"${forecast.lower:,.0f}", f"{((forecast.lower - live_price) / live_price) * 100:+.2f}%")
    with c3:
        st.metric("Forecast Upper (95% CI)", f"${forecast.upper:,.0f}", f"{((forecast.upper - live_price) / live_price) * 100:+.2f}%")
    with c4:
        st.metric("Interval Width", f"${forecast.upper - forecast.lower:,.0f}")

    st.markdown("---")
    

    # Main Dashboard Area

    col1, col2 = st.columns([2.5, 1])
    
    with col1:
        st.subheader("Price Action & 95% Confidence Band")
        
        # Prepare DataFrame for Plotly
        df_candles = pd.DataFrame(klines[-50:])
        df_candles['timestamp'] = pd.to_datetime(df_candles['timestamp'])
        
        # Create Plotly figure
        fig = go.Figure()
        
        # Close Price Line
        fig.add_trace(go.Scatter(
            x=df_candles['timestamp'], y=df_candles['close'],
            mode='lines', name='Close Price',
            line=dict(color='#eab308', width=2, shape='linear'),
            hovertemplate='Price: $%{y:,.0f}<extra></extra>'
        ))
        
        # Add next forecasted point time
        last_time = df_candles['timestamp'].iloc[-1]
        next_time = last_time + pd.Timedelta(hours=1)
        last_price = df_candles['close'].iloc[-1]
        
        # Upper CI
        fig.add_trace(go.Scatter(
            x=[last_time, next_time],
            y=[last_price, forecast.upper],
            mode='lines', name='Upper CI',
            line=dict(color='rgba(139, 92, 246, 0.8)', width=2, dash='dash')
        ))
        
        # Lower CI (with fill)
        fig.add_trace(go.Scatter(
            x=[last_time, next_time],
            y=[last_price, forecast.lower],
            mode='lines', name='Lower CI',
            line=dict(color='rgba(6, 182, 212, 0.8)', width=2, dash='dash'),
            fill='tonexty', fillcolor='rgba(139, 92, 246, 0.15)'
        ))
        
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0),
            height=400,
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.03)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.03)', side='right', tickprefix='$'),
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        st.subheader("Walk-Forward Backtest (Last 120 Bars)")
        bt_df = pd.DataFrame(bt_metrics.details)
        
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(y=bt_df['actual'], mode='lines', name='Actual', line=dict(color='#eab308', width=1.5, shape='linear')))
        fig2.add_trace(go.Scatter(y=bt_df['upper'], mode='lines', name='Upper CI', line=dict(color='rgba(139, 92, 246, 0.5)', width=1, dash='dot')))
        fig2.add_trace(go.Scatter(y=bt_df['lower'], mode='lines', name='Lower CI', line=dict(color='rgba(6, 182, 212, 0.5)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(6, 182, 212, 0.08)'))
        
        fig2.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0),
            height=250,
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.02)', title="Bars Ago", autorange="reversed"),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.02)', side='right', tickprefix='$'),
            showlegend=False
        )
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    # Side Panel
    with col2:
        st.subheader("Model Parameters")
        
        reg_color = "red" if forecast.regime == "volatile" else "orange" if forecast.regime == "medium" else "green"
        st.markdown(f"**Regime:** <span style='color:{reg_color}; font-weight:bold;'>{forecast.regime.upper()}</span>", unsafe_allow_html=True)
        st.markdown(f"**Volatility (σ):** `{forecast.sigma * 100:.4f}%`")
        st.markdown(f"**Student-t ν (df):** `{forecast.df:.2f}`")
        st.markdown(f"**Drift (μ):** `{forecast.mu_est * 100:.5f}%`")
        st.markdown(f"**PI Calib Factor:** `{forecast.calib:.4f}`")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("Backtest Metrics")
        
        cov = bt_metrics.coverage * 100
        cov_color = "#10b981" if 93 <= cov <= 97 else "#eab308"
        
        st.markdown(f"**Target Coverage:** `95.0%`")
        st.markdown(f"**Actual Coverage:** <span style='color:{cov_color}; font-family:monospace; font-weight:bold;'>{cov:.1f}%</span>", unsafe_allow_html=True)
        st.markdown(f"**Avg Interval Width:** `${bt_metrics.avg_width:,.0f}`")
        st.markdown(f"**Winkler Score:** `${bt_metrics.winkler:,.0f}`")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("24h Statistics")
        st.markdown(f"**High:** `${stats['high_24h']:,.0f}`")
        st.markdown(f"**Low:** `${stats['low_24h']:,.0f}`")
        st.markdown(f"**Volume:** `{stats['volume_24h']:,.0f} BTC`")

if __name__ == "__main__":
    main()
