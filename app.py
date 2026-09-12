import pandas as pd
import streamlit as st
import folium
import altair as alt
from streamlit_folium import st_folium
from backend import get_hospital_past_12h_haze, get_traffic_incidents, get_dengue_geojson
from helper import get_folium_icon, get_category_badge, render_custom_card, create_west_annotation

# 1. Load environment variables
st.set_page_config(page_title="EP dashboard", layout="wide")
st.title("EP dashboard")

# 1. Inject Theme-Aware CSS once at the top of your script or UI section
st.markdown("""
<style>
/* Base KPI Card (Transparent Background) */
[data-testid="stAppViewContainer"] .kpi-card {
    background-color: transparent !important;
    padding: 16px;
    border-radius: 10px;
    transition: all 0.3s ease;
}

/* Light Mode Card Styling */
[data-testid="stAppViewContainer"] .kpi-card {
    color: #0f172a;
    border: 1.5px solid #cbd5e1; /* Default grey border */
}

[data-testid="stAppViewContainer"] .kpi-title, 
[data-testid="stAppViewContainer"] .kpi-value {
    color: #0f172a !important;
}

[data-testid="stAppViewContainer"] .kpi-secondary {
    color: #475569 !important;
}

/* Dark Mode Card Styling */
[data-testid="stAppViewContainer"][data-theme="dark"] .kpi-card,
.stApp[data-theme="dark"] .kpi-card {
    color: #ffffff;
    border: 1.5px solid #334155; /* Neutral dark grey border */
}

[data-testid="stAppViewContainer"][data-theme="dark"] .kpi-title, 
[data-testid="stAppViewContainer"][data-theme="dark"] .kpi-value {
    color: #ffffff !important;
}

[data-testid="stAppViewContainer"][data-theme="dark"] .kpi-secondary {
    color: #94a3b8 !important;
}

/* Tactical Alert Card: Blue Border */
[data-testid="stAppViewContainer"] .kpi-tactical {
    border: 2px solid #0284c7 !important; /* Blue for Light Mode */
}

[data-testid="stAppViewContainer"][data-theme="dark"] .kpi-tactical,
.stApp[data-theme="dark"] .kpi-tactical {
    border: 2px solid #38bdf8 !important; /* Cyan-blue for Dark Mode */
}
</style>
""", unsafe_allow_html=True)


# -------------------------------------------------------------
# Top Section: West Hospital Haze Metrics & 12-Hour Trend
# -------------------------------------------------------------
df_12h = get_hospital_past_12h_haze()

if not df_12h.empty:
    latest_time = df_12h["timestamp"].max()
    df_latest = df_12h[df_12h["timestamp"] == latest_time].set_index("region")

    # Get 1 hour ago time to calculate delta
    timestamps = sorted(df_12h["timestamp"].unique())
    prev_time = timestamps[-2] if len(timestamps) > 1 else latest_time
    df_prev = df_12h[df_12h["timestamp"] == prev_time].set_index("region")

    # Helper function to extract numeric delta safely
    def get_delta(df_curr, df_past, reg, col):
        val_now = df_curr.loc[reg, col] if reg in df_curr.index else 0
        val_prev = df_past.loc[reg, col] if reg in df_past.index else val_now
        try:
            return int(val_now - val_prev)
        except Exception:
            return 0

    psi_delta = get_delta(df_latest, df_prev, "West", "psi_24h")
    pm25_delta = get_delta(df_latest, df_prev, "West", "pm25_24h")
    pm25_1h_delta = get_delta(df_latest, df_prev, "West", "pm25_1h")

    # -------------------------------------------------------------
    # 1. Custom KPI Cards (4 Columns layout including 1-Hour PM2.5)
    # -------------------------------------------------------------
    st.subheader("🏥 West Region Metrics & Regional Benchmarks")
    col1, col2, col3, col4 = st.columns(4)

    
    # Column 1: Real-time Tactical Indicator (1-Hour PM2.5)
    other_pm25_1h = df_latest["pm25_1h"].to_dict() if "pm25_1h" in df_latest.columns else {}
    west_1h_val = df_latest.loc["West", "pm25_1h"] if "West" in df_latest.index else "N/A"
    col1.markdown(
            render_custom_card("⚡ West 1h PM2.5 (Tactical)", west_1h_val, "µg/m³", pm25_1h_delta, other_pm25_1h, metric_type="pm25_1h", is_tactical=True), 
            unsafe_allow_html=True
    )
    
    # Column 2: 24h PM2.5 Concentration
    other_pm25 = df_latest["pm25_24h"].to_dict() if "pm25_24h" in df_latest.columns else {}
    west_pm25_now = df_latest.loc["West", "pm25_24h"] if "West" in df_latest.index else 0
    col2.markdown(
            render_custom_card("West 24h PM2.5", west_pm25_now, "µg/m³", pm25_delta, other_pm25, metric_type="pm25_24h"), 
            unsafe_allow_html=True
    )
    
    # Column 3: 24h PSI Index
    other_psi = df_latest["psi_24h"].to_dict() if "psi_24h" in df_latest.columns else {}
    west_psi_now = df_latest.loc["West", "psi_24h"] if "West" in df_latest.index else 0
    col3.markdown(
            render_custom_card("West 24h PSI", west_psi_now, "", psi_delta, other_psi, metric_type="psi_24h"), 
            unsafe_allow_html=True
    )
    
    # Column 4: PM2.5 Sub-Index
    west_sub = df_latest.loc["West", "pm25_sub_index"] if "West" in df_latest.index else 0
    other_sub = df_latest["pm25_sub_index"].to_dict() if "pm25_sub_index" in df_latest.columns else {}
    col4.markdown(
            render_custom_card("West PM2.5 Sub-Index", west_sub, "", 0, other_sub, metric_type="sub_index"), 
            unsafe_allow_html=True
    )

    with st.expander("ℹ️ View Air Pollution Benchmark Thresholds & Advisories"):
        tab1, tab2, tab3 = st.tabs(["1-Hour PM2.5 Tactical Bands","24h PM2.5 bands","24-Hour PSI Bands",])
        
        with tab1:
            st.markdown("""
                        | Hourly PM2.5 µg/m³ | Band / Descriptor | Tactical Hospital Action |
                        | :--- | :--- | :--- |
                        | **0 – 55** | **Band 1 (Normal)** | Standard building ventilation & ED triage operations. |
                        | **56 – 150** | **Band 2 (Elevated)** | Monitor ED respiratory admissions; prepare HEPA filters. |
                        | **151 – 250** | **Band 3 (High)** | Restrict patient transfers outdoors; prep acute respiratory bays. |
                        | **> 250** | **Band 4 (Very High)** | **Activate HVAC Recirculation**; deploy full respiratory surge plan. |
                        """)
            
        with tab2:
            st.markdown("""
                        | 24h PM2.5 µg/m³ | Category | Strategic Hospital & Ward Action |
                        | :--- | :--- | :--- |
                        | **0 – 12** | 🟢 **Good** | Baseline operations; standard respiratory bed allocation. |
                        | **13 – 35** | 🔵 **Moderate** | Normal operations; monitor 12h trend for surge trajectory. |
                        | **36 – 55** | 🟡 **Unhealthy** | Prep respiratory surge beds; alert ED for lagged asthma/COPD admissions. |
                        | **56 – 150** | 🟠 **Very Unhealthy** | Restrict non-essential patient transfers; review elective respiratory cases. |
                        | **> 150** | 🔴 **Hazardous** | Activate full bed capacity contingency; transition wards to full internal airflow. |
                        """)
        
        with tab3:
            st.markdown("""
                        | 24h PSI Value | Category | Health Advisory |
                        | :--- | :--- | :--- |
                        | **0 – 50** | 🟢 **Good** | Normal activities for all individuals. |
                        | **51 – 100** | 🔵 **Moderate** | Normal activities for most people. |
                        | **101 – 200** | 🟡 **Unhealthy** | Healthy: *Reduce* prolonged outdoor exertion.<br>Vulnerable/Patients: *Minimise* outdoor exertion. |
                        | **201 – 300** | 🟠 **Very Unhealthy** | Healthy: *Avoid* prolonged outdoor exertion.<br>Vulnerable/Patients: *Avoid* outdoor activity. |
                        | **> 300** | 🔴 **Hazardous** | Everyone: *Minimise/Avoid* all outdoor activities. |
                        """)
    
    st.markdown("---")
    
    # -------------------------------------------------------------
    # 2. Separate Altair Trend Charts (West Line Bolded)
    # -------------------------------------------------------------
    st.subheader("📈 12-Hour Regional Haze Trends")
    chart_col1, chart_col2 = st.columns(2)

    df_chart = df_12h.copy()
    df_chart["Time"] = df_chart["timestamp"].dt.strftime("%H:%M")

    # Custom color palette with West highlighted in bold amber/orange and others muted
    region_colors = alt.Scale(
        domain=["West", "North", "South", "East", "Central"],
        range=["#f59e0b", "#64748b", "#94a3b8", "#cbd5e1", "#475569"]
    )

    chart_col1, chart_col2,chart_col3 = st.columns(3)

    df_chart = df_12h.copy()
    df_chart["Time"] = df_chart["timestamp"].dt.strftime("%H:%M")

    region_colors = alt.Scale(
        domain=["West", "North", "South", "East", "Central"],
        range=["#f59e0b", "#64748b", "#94a3b8", "#cbd5e1", "#475569"]
    )



    # Chart 1: 1-Hour PM2.5 Trend (Tactical Spikes)
    with chart_col1:
        st.markdown("##### ⚡ 1-Hour PM2.5 Trend (Tactical Alerts)")
        pm25_1h_lines = alt.Chart(df_chart).mark_line().encode(
            x=alt.X("Time:O", title="Time"),
            y=alt.Y("pm25_1h:Q", title="1h PM2.5 (µg/m³)", scale=alt.Scale(zero=False)),
            color=alt.Color("region:N", scale=region_colors, title="Region"),
            strokeWidth=alt.condition(
                alt.datum.region == "West",
                alt.value(4),   # Bold line for West region
                alt.value(1.5)  # Muted line for other regions
            ),
            tooltip=["Time", "region", "pm25_1h"]
        )
        pm25_1h_text = create_west_annotation(df_chart, "pm25_1h")
        st.altair_chart((pm25_1h_lines + pm25_1h_text).properties(height=320), width='stretch')
        st.caption("⚡ **Expected Impact (2–6h lag):** Triggers an acute ED surge of asthma and COPD exacerbations, requiring immediate action to prepare nebulizer bays and switch facility HVAC units to internal re-circulation.")

    # Chart 2: 24-Hour PM2.5 Trend (Strategic Baseline)
    with chart_col2:
        st.markdown("##### 📊 24-Hour PM2.5 Trend (Strategic Capacity)")
        pm25_24h_lines = alt.Chart(df_chart).mark_line().encode(
            x=alt.X("Time:O", title="Time"),
            y=alt.Y("pm25_24h:Q", title="24h PM2.5 (µg/m³)", scale=alt.Scale(zero=False)),
            color=alt.Color("region:N", scale=region_colors, title="Region"),
            strokeWidth=alt.condition(
                alt.datum.region == "West",
                alt.value(4),   # Bold line for West region
                alt.value(1.5)  # Muted line for other regions
            ),
            tooltip=["Time", "region", "pm25_24h"]
        )
        pm25_24h_text = create_west_annotation(df_chart, "pm25_24h")
        st.altair_chart((pm25_24h_lines + pm25_24h_text).properties(height=320), width='stretch')
        st.caption("📊 **Expected Impact (12–24h lag):** Drives sustained inpatient ward admissions and cardiovascular complications, requiring pre-emptive allocation of general respiratory beds and nursing staff.")
        
    # Chart 3: 24-Hour PSI Trend (Strategic Baseline)
    with chart_col3:
        st.markdown("##### 🌫️ 24-Hour PSI Trend (Strategic Baseline)")
        psi_lines = alt.Chart(df_chart).mark_line().encode(
            x=alt.X("Time:O", title="Time"),
            y=alt.Y("psi_24h:Q", title="24h PSI Value", scale=alt.Scale(zero=False)),
            color=alt.Color("region:N", scale=region_colors, title="Region"),
            strokeWidth=alt.condition(
                alt.datum.region == "West",
                alt.value(4),   # Bold line for West region
                alt.value(1.5)  # Muted line for other regions
            ),
            tooltip=["Time", "region", "psi_24h"]
        )
        psi_text = create_west_annotation(df_chart, "psi_24h")
        st.altair_chart((psi_lines + psi_text).properties(height=320), width='stretch')
        st.caption("🌫️ **Expected Impact (24–48h lag):** Leads to prolonged hospital length-of-stay across general medicine wards, prompting institutional alignment with MOH haze response protocols and potential deferral of non-urgent elective procedures.")
else:
    st.warning("Unable to load 12-hour haze trend data.")

# Map Render Logic
st.subheader("💥 Traffic conditions and 🦟 dengue clusters")
df_incidents = get_traffic_incidents()
geojson_dengue = get_dengue_geojson()

col_map, col_sidebar = st.columns([2, 1])
with col_map: 
    # Initialize base map centered on Western Singapore
    m = folium.Map(
        location=[1.345428, 103.7508],
        zoom_start=13,
        scrollWheelZoom=True,
        dragging=True,
        zoomControl=True
    )


    # Safely check if valid GeoJSON object was returned
    if geojson_dengue and isinstance(geojson_dengue, dict) and "features" in geojson_dengue:
        dengue_group = folium.FeatureGroup(name="🦟 Dengue Clusters", show=True)
        folium.GeoJson(
            geojson_dengue,
            style_function=lambda feature: {
                "fillColor": "#f59e0b",
                "color": "#d97706",
                "weight": 2,
                "fillOpacity": 0.4,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["LOCALITY", "CASE_SIZE"],
                aliases=["Locality:", "Active Cases:"],
                localize=True
            )
        ).add_to(dengue_group)
        dengue_group.add_to(m)
        
        
    # Layer 2: Traffic Incidents Group
    if not df_incidents.empty:
        incident_group = folium.FeatureGroup(name="💥 Traffic Incidents", show=True)
        for _, row in df_incidents.iterrows():
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                popup=folium.Popup(row["Message"], max_width=300),
                tooltip=row["Message"],
                icon=get_folium_icon(row["Message"])
            ).add_to(incident_group)
        incident_group.add_to(m)

    # Add built-in interactive layer control widget to the map canvas (top-right)
    folium.LayerControl(position="topleft", collapsed=False).add_to(m)

    # Render Map in Streamlit
    st_folium(m, width='stretch', height=650)

with col_sidebar:
    st.markdown("### 🚨 Major Traffic Incidents")

    if not df_incidents.empty:
        # Define target incident keywords to keep
        target_keywords = ["ACCIDENT", "FIRE", "PLANT FAILURE"]

        # Filter dataframe for matching messages
        df_filtered = df_incidents[
            df_incidents["Message"].str.upper().str.contains("|".join(target_keywords), na=False)
        ]

        if not df_filtered.empty:
            for _, row in df_filtered.iterrows():
                msg = row["Message"]
                msg_upper = msg.upper()

                # Dynamic tag styling based on incident type
                if "ACCIDENT" in msg_upper:
                    st.error(f"🚗 **Accident**: {msg}")
                elif "FIRE" in msg_upper:
                    st.error(f"🔥 **Vehicle Fire**: {msg}")
                elif "PLANT FAILURE" in msg_upper:
                    st.warning(f"⚙️ **Plant Failure**: {msg}")
        else:
            st.info("No active accidents, fires, or plant failures reported.")
    else:
        st.info("No active traffic incidents reported.")

    st.markdown("---")
    
    st.markdown("### 🦟 Active Dengue Hotspots")
    # Assuming geojson_dengue has been fetched
    if geojson_dengue and "features" in geojson_dengue:
        for feature in geojson_dengue["features"][:10]:  # Limit to top 10 for clean UI
            props = feature.get("properties", {})
            locality = props.get("LOCALITY", "Unknown Area")
            cases = props.get("CASE_SIZE", 0)
            
            st.warning(f"**{locality}**\n\nActive Cases: `{cases}`")
    else:
        st.info("No active dengue clusters loaded.")