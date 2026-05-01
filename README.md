# ₿ BTC Quant Forecaster

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi)
![NumPy](https://img.shields.io/badge/NumPy-1.24%2B-013243?style=for-the-badge&logo=numpy)
![Vanilla JS](https://img.shields.io/badge/Vanilla_JS-ES6-F7DF1E?style=for-the-badge&logo=javascript)

A high-precision, quantitative Bitcoin price range forecasting system built for professional risk modeling. It produces a **well-calibrated 95% confidence interval** for the next 1-hour BTCUSDT price using probabilistic modeling and Monte Carlo simulations.


## 🚀 Key Features & Quantitative Edge

### 🔬 Advanced Quantitative Core
- **Dynamic Volatility (EWMA)**: Uses Exponentially Weighted Moving Averages (Fast 12, Slow 26) combined with ATR (Average True Range) to capture volatility clustering, regime shifts, and sudden market shocks.
- **Student-t Distribution**: Bitcoin exhibits extreme "fat tails". We dynamically estimate the degrees of freedom ($\nu$) based on the excess kurtosis of recent rolling log returns, avoiding Gaussian assumptions.
- **Adaptive Calibration**: An online learning mechanism (gradient step) that adjusts the interval width in real-time to maintain an empirical walk-forward coverage of exactly 95%.
- **Regime Switching**: Automatically classifies market conditions into *Calm*, *Medium*, or *Volatile* regimes using EWMA speed differentials and ATR, adjusting the risk scaling parameters instantly.
- **Monte Carlo Simulation**: Runs 10,000+ vectorized simulations per bar. Blends Student-t Geometric Brownian Motion (GBM) with historical Bootstrap Resampling to handle extreme tail risks effectively.

### 📊 Real-Time Dashboard
- **Live Price Feed**: Sub-second real-time BTCUSDT price fetching via the Binance REST API.
- **Probabilistic Forecasts**: Shaded 95% confidence bands projected for the next 1-hour period.
- **Live Backtest Metrics**: Displays Empirical Coverage (Target 95%), Average Interval Width, and Winkler Score (penalty-adjusted accuracy).
- **Interactive Charts**: Powered by Chart.js for smooth, responsive visualization of price action, regimes, and model performance.

## 🛠️ Technology Stack & Architecture
- **Backend Core**: FastAPI (Python), providing asynchronous API endpoints.
- **Data Engine**: NumPy, SciPy, Pandas for heavy vectorized quantitative calculations.
- **Frontend UI**: Vanilla JavaScript (ES6), HTML5, and CSS3 styled with a Premium Dark Theme, Chart.js for visualizations.
- **Data Source**: Binance Public REST API (Klines/Candlesticks and Ticker streams).

## 📡 API Endpoints

The FastAPI backend exposes the following robust endpoints:

- `GET /api/forecast`: Returns the current forecast parameters (lower/upper bounds, drift, volatility, DF, regime, calibration factor), live price, and backtest metrics.
- `GET /api/price`: Fetches the live BTCUSDT price and 24-hour volume statistics.
- `GET /api/candles?limit=50`: Returns the most recent 1-hour candlestick data.
- `GET /api/backtest_details?limit=100`: Returns granular walk-forward backtest samples for visual plotting.
- `GET /api/health`: Standard health check ping.

## 📥 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/btc-quant-forecaster.git
   cd btc-quant-forecaster
   ```

2. **Create a virtual environment (recommended)**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python main.py
   ```

5. **Open in browser**:
   Navigate to `http://localhost:8000` to view the real-time forecasting dashboard.

## 📈 Model Performance & Validation
The system is rigorously designed to act as a reliable trading risk model using strict walk-forward (leak-free) validations:
- **Reliability**: Targets exactly ~95% empirical coverage via real-time online EMA scaling.
- **Efficiency**: Minimizes interval width without sacrificing coverage, mathematically optimized via the **Winkler Score**.
- **Adaptability**: Reacts instantaneously to volatility spikes and "flash" moves by re-weighting fast vs. slow EWMA speeds on the fly.

## 📂 Project Structure
```text
├── main.py               # FastAPI server & route handlers
├── requirements.txt      # Project dependencies (FastAPI, NumPy, Pandas, SciPy, Uvicorn)
├── README.md             # Project documentation
├── model/
│   ├── forecaster.py     # Quantitative engine (MC, Student-t, EWMA, Calibration)
│   ├── data_fetcher.py   # Binance API asynchronous integration
│   └── __init__.py
└── frontend/
    ├── index.html        # Dashboard UI
    └── static/
        ├── style.css     # Premium dark mode styling & animations
        └── app.js        # Real-time charting, DOM updates & API logic
```
