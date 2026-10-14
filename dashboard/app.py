import pandas as pd
# pyrefly: ignore [missing-import]
import streamlit as st
# pyrefly: ignore [missing-import]
import plotly.express as px


# Configure the Streamlit page
st.set_page_config(
    page_title="Bengaluru Air Quality Dashboard",
    page_icon="🌍",
    layout="wide"
)


# Gold layer data
DATA_FILE = "data/gold/aqi_data.csv"
POLLUTION_FILE = "data/cleaned/pollution.csv"
ENRICHED_FILE = "data/cleaned/enriched_air_quality.csv"


@st.cache_data
def load_data():
    # Load final AQI data
    return pd.read_csv(DATA_FILE)


@st.cache_data
def load_pollution():
    try:
        return pd.read_csv(POLLUTION_FILE)
    except Exception:
        return pd.DataFrame()


@st.cache_data
def load_enriched():
    try:
        return pd.read_csv(ENRICHED_FILE)
    except Exception:
        return pd.DataFrame()


# Load data
df = load_data()

# Convert timestamp to datetime
df["timestamp"] = pd.to_datetime(df["timestamp"])


# Dashboard title
st.title("Bengaluru Air Quality Dashboard")
st.write(
    "Air quality and AQI analysis using OpenAQ and Open-Meteo data."
)


# Sidebar filters
st.sidebar.header("Filters")

# Station filter
stations = sorted(
    df["station_id"].dropna().unique()
)

selected_station = st.sidebar.selectbox(
    "Select Station",
    ["All"] + list(stations)
)

if selected_station != "All":
    df = df[
        df["station_id"] == selected_station
    ]


# KPI section
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Average AQI",
        round(df["aqi"].mean(), 2)
    )

with col2:
    st.metric(
        "Maximum AQI",
        int(df["aqi"].max())
    )

with col3:
    st.metric(
        "Records",
        len(df)
    )

with col4:
    st.metric(
        "Stations",
        df["station_id"].nunique()
    )


# AQI trend
st.subheader("AQI Trend")

aqi_trend = (
    df.groupby("timestamp", as_index=False)
    ["aqi"]
    .mean()
)

fig = px.line(
    aqi_trend,
    x="timestamp",
    y="aqi",
    title="Average AQI Over Time"
)

st.plotly_chart(
    fig,
    use_container_width=True
)


# AQI category distribution
st.subheader("AQI Category Distribution")

category_data = (
    df["aqi_category"]
    .value_counts()
    .reset_index()
)

category_data.columns = [
    "category",
    "count"
]

fig = px.bar(
    category_data,
    x="category",
    y="count",
    title="AQI Categories"
)

st.plotly_chart(
    fig,
    use_container_width=True
)


# AQI by station
st.subheader("AQI by Station")

station_data = (
    df.groupby("station_id", as_index=False)
    ["aqi"]
    .mean()
)

fig = px.bar(
    station_data,
    x="station_id",
    y="aqi",
    title="Average AQI by Station"
)

st.plotly_chart(
    fig,
    use_container_width=True
)


# AQI distribution
st.subheader("AQI Distribution")

fig = px.histogram(
    df,
    x="aqi",
    nbins=30,
    title="Distribution of AQI Values"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

# Pollutant contribution analysis (requires cleaned pollution data)
st.subheader("Pollutant Contribution Analysis")
pollution_df = load_pollution()
if not pollution_df.empty:
    pollutant_data = (
        pollution_df.groupby("pollutant", as_index=False)["value"]
        .mean()
        .sort_values("value", ascending=False)
    )
    fig = px.bar(
        pollutant_data,
        x="pollutant",
        y="value",
        title="Average Pollutant Concentration",
        color="pollutant"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Hourly and monthly patterns
    if "timestamp" in pollution_df.columns:
        pollution_df["timestamp"] = pd.to_datetime(pollution_df["timestamp"], errors="coerce", utc=True)
        pollution_df["hour"] = pollution_df["timestamp"].dt.hour
        pollution_df["month"] = pollution_df["timestamp"].dt.month
        col_a, col_b = st.columns(2)
        with col_a:
            hourly = pollution_df.groupby("hour", as_index=False)["value"].mean()
            fig = px.line(hourly, x="hour", y="value", title="Hourly Pollutant Pattern")
            st.plotly_chart(fig, use_container_width=True)
        with col_b:
            monthly = pollution_df.groupby("month", as_index=False)["value"].mean()
            fig = px.bar(monthly, x="month", y="value", title="Monthly Pollutant Pattern")
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Pollution data not available for pollutant analysis.")

# Weather impact on AQI (requires enriched data)
st.subheader("Weather Impact on AQI")
enriched_df = load_enriched()
if not enriched_df.empty and "temperature" in enriched_df.columns:
    # Merge enriched weather with AQI for weather vs AQI
    enriched_df["timestamp"] = pd.to_datetime(enriched_df["timestamp"], errors="coerce", utc=True)
    df_weather = df.copy()
    df_weather["timestamp"] = pd.to_datetime(df_weather["timestamp"], errors="coerce", utc=True)
    # Round to hour for join preview
    enriched_sample = enriched_df.dropna(subset=["temperature", "humidity"]).head(1000)
    if not enriched_sample.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(
                enriched_sample,
                x="temperature",
                y="value",
                color="pollutant",
                title="Temperature vs Pollutant Value",
                opacity=0.6
            )
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.scatter(
                enriched_sample,
                x="humidity",
                y="value",
                color="pollutant",
                title="Humidity vs Pollutant Value",
                opacity=0.6
            )
            st.plotly_chart(fig, use_container_width=True)

        # Wind speed vs AQI-like value
        fig = px.scatter(
            enriched_sample,
            x="wind_speed",
            y="value",
            color="pollutant",
            title="Wind Speed vs Pollutant Value"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No enriched weather-pollution overlap found — weather data period (recent) differs from pollution historic period (2016-2018). This is a known limitation documented in docs/architecture.md.")
else:
    st.info("Enriched weather data not available.")

# City / station comparison
st.subheader("City / Station Comparison")
if df["station_id"].nunique() > 1:
    station_comparison = df.groupby("station_id", as_index=False).agg(
        avg_aqi=("aqi", "mean"),
        max_aqi=("aqi", "max"),
        count=("aqi", "count")
    )
    fig = px.bar(station_comparison, x="station_id", y="avg_aqi", color="station_id", title="Station Comparison — Average AQI")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(station_comparison, use_container_width=True)
else:
    st.info("Single station in filtered view — select 'All' to compare.")

# Raw data preview
st.subheader("Data Preview")

st.dataframe(
    df.head(100),
    use_container_width=True
)


# Part 2 — 24h-ahead AQI prediction (same schema as FastAPI POST /predict).
# Prefers the live FastAPI endpoint; falls back to local joblib artifacts.
st.subheader("AQI Prediction — 24h ahead (Part 2)")
st.caption(
    "Historical charts above show observed AQI. Predictions below are "
    "model forecasts for approximately 24h after the given observation "
    "(UTC, per grid cell). Location uses a generalised ~11km grid cell "
    "(lat_gen/lon_gen), never exact coordinates."
)
try:
    _pred = None
    _via = None
    _versions = {}
    with st.form("aqi_predict_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            p_lat = st.number_input("Grid lat_gen", min_value=-90.0, max_value=90.0, value=13.0, step=0.1)
            p_lon = st.number_input("Grid lon_gen", min_value=-180.0, max_value=180.0, value=77.5, step=0.1)
            p_aqi = st.number_input("Current AQI", min_value=0.0, max_value=1000.0, value=float(round(df["aqi"].mean(), 1)))
            p_lag1 = st.number_input("AQI lag 1", min_value=0.0, max_value=1000.0, value=float(round(df["aqi"].mean(), 1)))
            p_lag2 = st.number_input("AQI lag 2", min_value=0.0, max_value=1000.0, value=float(round(df["aqi"].mean(), 1)))
        with c2:
            p_lag3 = st.number_input("AQI lag 3", min_value=0.0, max_value=1000.0, value=float(round(df["aqi"].mean(), 1)))
            p_lag24 = st.number_input("AQI lag 24h", min_value=0.0, max_value=1000.0, value=float(round(df["aqi"].mean(), 1)))
            p_rm3 = st.number_input("Rolling mean 3", value=float(round(df["aqi"].mean(), 1)))
            p_rs3 = st.number_input("Rolling std 3", min_value=0.0, value=5.0)
            p_rm7 = st.number_input("Rolling mean 7", value=float(round(df["aqi"].mean(), 1)))
        with c3:
            p_rx7 = st.number_input("Rolling max 7", value=float(round(df["aqi"].max(), 1)))
            p_diff = st.number_input("AQI diff 1", value=0.0)
            p_hour = st.number_input("Hour (0-23 UTC)", min_value=0, max_value=23, value=10)
            p_dow = st.number_input("Day of week (0-6)", min_value=0, max_value=6, value=1)
            p_month = st.number_input("Month (1-12)", min_value=1, max_value=12, value=3)
        submitted = st.form_submit_button("Predict AQI +24h")

    if submitted:
        _payload = {
            "lat_gen": p_lat, "lon_gen": p_lon, "aqi": p_aqi,
            "aqi_lag1": p_lag1, "aqi_lag2": p_lag2, "aqi_lag3": p_lag3,
            "aqi_lag24": p_lag24,
            "aqi_roll_mean_3": p_rm3, "aqi_roll_std_3": p_rs3,
            "aqi_roll_mean_7": p_rm7, "aqi_roll_max_7": p_rx7,
            "aqi_diff_1": p_diff, "hour": p_hour,
            "dayofweek": p_dow, "month": p_month,
        }
        try:  # prefer FastAPI when it is running
            import requests as _requests
            _r = _requests.post("http://localhost:8000/predict", json=_payload, timeout=10)
            _r.raise_for_status()
            _pred = _r.json()
            _via = "FastAPI POST /predict"
            _versions = {"reg": _pred.get("model_regressor"), "clf": _pred.get("model_classifier")}
        except Exception:
            import joblib as _joblib
            import numpy as _np
            _payload["hour_sin"] = float(_np.sin(2.0 * _np.pi * p_hour / 24.0))
            _payload["hour_cos"] = float(_np.cos(2.0 * _np.pi * p_hour / 24.0))
            _payload["dayofweek_sin"] = float(_np.sin(2.0 * _np.pi * p_dow / 7.0))
            _payload["dayofweek_cos"] = float(_np.cos(2.0 * _np.pi * p_dow / 7.0))
            _cols = ["lat_gen", "lon_gen", "aqi", "aqi_lag1", "aqi_lag2", "aqi_lag3",
                     "aqi_lag24", "aqi_roll_mean_3", "aqi_roll_std_3", "aqi_roll_mean_7",
                     "aqi_roll_max_7", "aqi_diff_1", "hour", "dayofweek", "month",
                     "hour_sin", "hour_cos", "dayofweek_sin", "dayofweek_cos"]
            _row = pd.DataFrame([[_payload[c] for c in _cols]], columns=_cols)
            _reg = _joblib.load("models/best_regressor.joblib")
            _clf = _joblib.load("models/best_classifier.joblib")
            _pred = {"predicted_aqi": float(_reg.predict(_row)[0]),
                     "predicted_category": str(_clf.predict(_row)[0]),
                     "horizon": "+24h"}
            _via = "local joblib fallback (FastAPI unavailable)"
    if submitted and _pred is not None:
        st.success(f"Predicted AQI (+24h): {_pred['predicted_aqi']:.1f} — category: {_pred['predicted_category']} (via {_via})")
        st.caption("Same schema as training (T+24h ±2h UTC). Start API: `uvicorn api.main:app --port 8000` or `docker run -p 8000:8000 aqi-api`.")
        st.info("Model context: Trained on 3,032 hourly samples across 7 stations (August through October 2026) with 24h lag and cyclical calendar features. Real-time daily sync enabled.", icon="ℹ️")
except FileNotFoundError:
    st.info("Prediction models not trained yet — run `python3 src/models/train.py`.")
except Exception as exc:
    st.warning(f"Prediction unavailable: {exc}")