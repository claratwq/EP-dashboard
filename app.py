from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import textwrap

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from backend import (
    get_dengue_geojson,
    get_past_24h_environmental_metrics,
    get_traffic_incidents,
    get_wbgt_data,
    get_zika_geojson,
)
from helper import get_folium_icon, get_severity_color, parse_zika_description

st.set_page_config(
    page_title="Environmental Situation Dashboard", layout="wide"
)
st.markdown(f"""<b>Environmental Situation Dashboard</b>""",
                    unsafe_allow_html=True)
# -------------------------------------------------------------
# 1. Parallel Data Acquisition (Sub-second loading)
# -------------------------------------------------------------
with ThreadPoolExecutor() as executor:
    future_env = executor.submit(
        get_past_24h_environmental_metrics, hours_limit=24
    )
    future_wbgt = executor.submit(get_wbgt_data)
    future_incidents = executor.submit(get_traffic_incidents)
    future_dengue = executor.submit(get_dengue_geojson)
    future_zika = executor.submit(get_zika_geojson)

    df_env = future_env.result()
    wbgt_data = future_wbgt.result()
    df_incidents = future_incidents.result()
    geojson_dengue = future_dengue.result()
    geojson_zika = future_zika.result()

wbgt_dict = wbgt_data.get("readings", {})
df_accidents = (
    df_incidents[
        df_incidents["Type"].isin(["Accident", "Fire", "Plant Failure"])
    ]
    if not df_incidents.empty and "Type" in df_incidents.columns
    else pd.DataFrame()
)

current_as_of = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M SGT")
st.caption(f"🕒 **Data Correct as of:** `{current_as_of}`")

# -------------------------------------------------------------
# 2. Build Map Canvas (Dynamic Instance for DOM stability)
# -------------------------------------------------------------
m = folium.Map(location=[1.3521, 103.8198], zoom_start=11, tiles= False)
folium.TileLayer(tiles="OpenStreetMap", control=False).add_to(m)
whitewash_css = """
<style>
.leaflet-tile-pane {
    filter: opacity(0.8) grayscale(20%) brightness(125%) contrast(80%) !important;
}
.leaflet-marker-pane, .leaflet-control-layers {
    filter: none !important;
}
</style>
"""
m.get_root().html.add_child(folium.Element(whitewash_css))

regions_coord = {
    "North": [1.4700, 103.8200],
    "South": [1.2200, 103.8200],
    "East": [1.3570, 104.0800],
    "West": [1.3570, 103.5800],
    "Central": [1.3570, 103.8200],
}

latest_env = (
    df_env[df_env["timestamp"] == df_env["timestamp"].max()].set_index("region")
    if not df_env.empty
    else pd.DataFrame()
)

env_overlay_group = folium.FeatureGroup(
    name="🌐 Regional 1h PM2.5 / 24h PSI / WBGT", show=True
)

for reg, coords in regions_coord.items():
    pm25_val = latest_env.loc[reg, "pm25_1h"] if reg in latest_env.index else "N/A"
    psi_val = latest_env.loc[reg, "psi_24h"] if reg in latest_env.index else "N/A"
    wbgt_val = wbgt_dict.get(reg, "N/A")

    _, pm25_color = get_severity_color(pm25_val, "pm25_1h")
    _, psi_color = get_severity_color(psi_val, "psi_24h")
    _, wbgt_color = get_severity_color(wbgt_val, "wbgt")

    folium.Marker(
        location=coords,
        tooltip=f"{reg}: PM2.5({pm25_val}) | PSI({psi_val}) | WBGT({wbgt_val}°C)",
        icon=folium.DivIcon(
            icon_size=(160, 95),
            icon_anchor=(80, 47),
            html=f"""
            <div style="display: flex; flex-direction: column; gap: 3px; background-color: rgba(15, 23, 42, 0.92); border: 1.5px solid #38bdf8; border-radius: 8px; padding: 6px 10px; color: white; font-family: sans-serif; font-size: 12px; line-height: 1.25; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);">
                <div style="font-weight: 700; color: #ffffff; margin-bottom: 2px; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 2px;">📍 {reg} Region</div>
                <div style="color: {pm25_color};">1h PM2.5: <b>{pm25_val} µg/m³</b></div>
                <div style="color: {psi_color};">24h PSI: <b>{psi_val}</b></div>
                <div style="color: {wbgt_color};">WBGT: <b>{f'{wbgt_val:.1f}°C' if isinstance(wbgt_val, float) else wbgt_val}</b></div>
            </div>
            """,
        ),
    ).add_to(env_overlay_group)

env_overlay_group.add_to(m)

if geojson_dengue and isinstance(geojson_dengue, dict) and "features" in geojson_dengue:
    dengue_group = folium.FeatureGroup(name="🟡 Dengue Clusters", show=True)
    folium.GeoJson(
        geojson_dengue,
        style_function=lambda f: {"fillColor": "#f59e0b", "color": "#d97706", "weight": 2, "fillOpacity": 0.4},
        tooltip=folium.GeoJsonTooltip(
            fields=["LOCALITY", "CASE_SIZE"] if "LOCALITY" in geojson_dengue["features"][0].get("properties", {}) else ["Name", "Description"],
            aliases=["Locality:", "Case Info:"]
        )
    ).add_to(dengue_group)
    dengue_group.add_to(m)

if geojson_zika and isinstance(geojson_zika, dict) and "features" in geojson_zika:
    zika_group = folium.FeatureGroup(name="🟣 Zika Clusters", show=True)
    folium.GeoJson(
        geojson_zika,
        style_function=lambda f: {"fillColor": "#a855f7", "color": "#7e22ce", "weight": 2, "fillOpacity": 0.5},
        tooltip=folium.GeoJsonTooltip(
            fields=["LOCALITY"] if "LOCALITY" in geojson_zika["features"][0].get("properties", {}) else ["Name"],
            aliases=["Locality:"]
        )
    ).add_to(zika_group)
    zika_group.add_to(m)

if not df_accidents.empty:
    inc_label = '<i class="fa fa-car" style="color:red; margin-right:5px;"></i> Road Traffic Accidents'
    inc_group = folium.FeatureGroup(name=inc_label, show=True)
    for _, row in df_accidents.iterrows():
        folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=folium.Popup(row["Message"], max_width=300),
            tooltip=row["Message"],
            icon=get_folium_icon(row["Message"])
        ).add_to(inc_group)
    inc_group.add_to(m)

folium.LayerControl(position="topleft", collapsed=False).add_to(m)

layer_control_css = """
<style>
.leaflet-control-layers { font-size: 12px !important; line-height: 1.2 !important; padding: 4px 8px !important; }
.leaflet-control-layers-overlays label { margin-bottom: 1px !important; display: flex !important; align-items: center !important; }
.leaflet-control-layers-selector { margin-right: 2px !important; }
</style>
"""
m.get_root().html.add_child(folium.Element(layer_control_css))

# -------------------------------------------------------------
# 3. Streamlit Layout
# -------------------------------------------------------------
col_map, col_panel = st.columns([5, 3])
with col_map:
    # Fixed key + empty returned_objects guarantees map persistence
    st_folium(
        m, 
        width="stretch", 
        height=640, 
        key="env_dashboard_map", 
        returned_objects=[]
    )

    col_dengue, col_zika_accidents = st.columns(2)

    with col_dengue:
        st.markdown("🟡 Active Dengue Clusters")
        dengue_feats = geojson_dengue.get("features", []) if geojson_dengue else []
        if dengue_feats:
            for f in dengue_feats[:10]:
                props = f.get("properties", {})
                loc = props.get("LOCALITY", props.get("Name", "Unknown Area"))
                cases = props.get("CASE_SIZE", "N/A")
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 3px 5px; margin-bottom: 2px; border-radius: 6px; background-color: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3);">
                        <span style="font-weight: 600; font-size: 12px;">📍 {loc}</span>
                        <span style="font-size: 12px; font-weight: 700; color: #f59e0b;">{cases} Case(s)</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No active Dengue hotspots found.")

    with col_zika_accidents:
        st.markdown("🟣 Active Zika Clusters")
        zika_feats = geojson_zika.get("features", []) if geojson_zika else []
        if zika_feats:
            for f in zika_feats[:10]:
                props = f.get("properties", {})
                locality = props.get("LOCALITY")
                case_size = props.get("CASE_SIZE")
                if not locality or case_size is None:
                    parsed_meta = parse_zika_description(props.get("Description", ""))
                    locality = locality or parsed_meta["locality"]
                    case_size = case_size if case_size is not None else parsed_meta["case_size"]
                locality = locality or props.get("Name", "Unknown Area")
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 3px 5px; margin-bottom: 2px; border-radius: 6px; background-color: rgba(139, 92, 246, 0.1); border: 1px solid rgba(139, 92, 246, 0.3);">
                        <span style="font-weight: 600; font-size: 12px;">📍 {locality}</span>
                        <span style="font-size: 12px; font-weight: 700; color: #8b5cf6;">{case_size} Case(s)</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No active Zika hotspots found.")

        st.markdown("🔴 Road Traffic Accidents")
        if df_incidents is not None and not df_incidents.empty:
            target_keywords = ["ACCIDENT", "FIRE", "PLANT FAILURE"]
            df_filtered = df_incidents[
                df_incidents["Message"].str.upper().str.contains("|".join(target_keywords), na=False)
            ]
            if not df_filtered.empty:
                for _, row in df_filtered.iterrows():
                    msg = row.get("Message", "Unknown Incident")
                    msg_upper = msg.upper()
                    if "ACCIDENT" in msg_upper:
                        icon, label, bg_color, border_color, text_color = "🚗", "Accident", "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.3)", "#ef4444"
                    elif "FIRE" in msg_upper:
                        icon, label, bg_color, border_color, text_color = "🔥", "Vehicle Fire", "rgba(249, 115, 22, 0.1)", "rgba(249, 115, 22, 0.3)", "#f97316"
                    elif "PLANT FAILURE" in msg_upper:
                        icon, label, bg_color, border_color, text_color = "⚙️", "Plant Failure", "rgba(234, 179, 8, 0.1)", "rgba(234, 179, 8, 0.3)", "#eab308"
                    else:
                        icon, label, bg_color, border_color, text_color = "🚨", "Incident", "rgba(100, 116, 139, 0.1)", "rgba(100, 116, 139, 0.3)", "#64748b"

                    st.markdown(
                        f"""
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 3px 5px; margin-bottom: 2px; border-radius: 6px; background-color: {bg_color}; border: 1px solid {border_color};">
                            <span style="font-weight: 600; font-size: 12px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 75%;" title="{msg}">
                                {icon} {msg}
                            </span>
                            <span style="font-size: 12px; font-weight: 700; color: {text_color}; white-space: nowrap;">{label}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No active Accidents, Fires, or Plant Failures reported.")
        else:
            st.info("No traffic accident data available.")

with col_panel:
    with st.expander("Haze and WBGT Threshold Guides", expanded=True):
        html_content = textwrap.dedent(""" <div style="font-size: 12px; line-height: 1.2;">
            
<div style="font-weight: bold; font-size: 14px;  margin-bottom: 4px;">1-hr PM2.5 (Immediate Outdoor Guide)</div>

<table style="width: 100%; text-align: left; border-collapse: collapse; margin-bottom: 6px; font-size: 12px;">
    <tr style="border-bottom: 1px solid #334155;">
        <th style="padding: 2px;">Band</th>
        <th style="padding: 2px;">PM2.5 (µg/m3)</th>
        <th style="padding: 2px;">General Public</th>
        <th style="padding: 2px;">Vulnerable*</th>
    </tr>
    <tr>
        <td style="padding: 2px; color: #10b981; font-weight: bold;">Normal</td>
        <td style="padding: 2px; color: #10b981; font-weight: bold;">0 - 55</td>
        <td style="padding: 2px;">Normal</td>
        <td style="padding: 2px;">Normal</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #d7de05; font-weight: bold;">Elevated</td>
        <td style="padding: 2px; color: #d7de05; font-weight: bold;">56 - 150</td>
        <td style="padding: 2px;">Reduce strenuous</td>
        <td style="padding: 2px;">Avoid strenuous</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #dd900a; font-weight: bold;">High</td>
        <td style="padding: 2px;color: #dd900a; font-weight: bold;">151 - 250</td>
        <td style="padding: 2px;">Avoid strenuous</td>
        <td style="padding: 2px;">Avoid all</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #ef4444; font-weight: bold;">Very High</td>
        <td style="padding: 2px;color: #ef4444; font-weight: bold;">>= 251</td>
        <td style="padding: 2px;">Minimise all</td>
        <td style="padding: 2px;">Avoid all</td>
    </tr>
</table>

<div style="font-size: 12px;  margin-bottom: 8px;">
    *Vulnerable: Elderly, pregnant women, children, chronic lung/heart disease. Applies to next 1 hr.
</div>

<hr style="border: 0; border-top: 1px solid #334155; margin: 6px 0;">

<div style="font-weight: bold; font-size: 14px;  margin-bottom: 4px;"> 24-hr PSI Forecast (Next Day Outdoor Activity Planning)</div>

<table style="width: 100%; text-align: left; border-collapse: collapse; margin-bottom: 6px; font-size: 12px;">
    <tr style="border-bottom: 1px solid #334155;">
        <th style="padding: 2px;">Band</th>
        <th style="padding: 2px;">24h PSI</th>
        <th style="padding: 2px;">Healthy Persons</th>
        <th style="padding: 2px;">Vulnerable / Chronic</th>
    </tr>
    <tr>
        <td style="padding: 2px; color: #10b981; font-weight: bold;">Good</td>
        <td style="padding: 2px; color: #10b981;font-weight: bold;">0 - 50</td>
        <td style="padding: 2px;">Normal</td>
        <td style="padding: 2px;">Normal</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #38bdf8; font-weight: bold;">Moderate</td>
        <td style="padding: 2px; color: #38bdf8; font-weight: bold;">51 - 100 </td>
        <td style="padding: 2px;">Normal</td>
        <td style="padding: 2px;">Normal</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #d7de05; font-weight: bold;">Unhealthy</td>
        <td style="padding: 2px; color: #d7de05; font-weight: bold;">101 - 200</td>
        <td style="padding: 2px;">Reduce prolonged/strenuous</td>
        <td style="padding: 2px;">Minimise/Avoid prolonged/strenuous</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #dd900a; font-weight: bold;">Very Unhealthy</td>
        <td style="padding: 2px; color: #dd900a; font-weight: bold;">201 - 300</td>
        <td style="padding: 2px;">Avoid prolonged/strenuous</td>
        <td style="padding: 2px;">Minimise/Avoid all</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #ef4444; font-weight: bold;">Hazardous</td>
        <td style="padding: 2px; color: #ef4444; font-weight: bold;">> 300</td>
        <td style="padding: 2px;">Minimise all</td>
        <td style="padding: 2px;">Avoid all</td>
    </tr>
</table>

<div style="font-size: 12px; margin-bottom: 8px;">
            *Vulnerable: Elderly, pregnant women, children
            *Chronic: chronic lung/heart disease. 
</div>

<hr style="border: 0; border-top: 1px solid #334155; margin: 6px 0;">

<div style="font-weight: bold; font-size: 14px;  margin-bottom: 4px;">🌡️ WBGT Heat Stress Guidelines (Prolonged Outdoor Activities)</div>
<table style="width: 100%; text-align: left; border-collapse: collapse; margin-bottom: 6px; font-size: 12px;">
    <tr style="border-bottom: 1px solid #334155;">
        <th style="padding: 2px;">Level</th>
        <th style="padding: 2px;">WBGT (°C)</th>
        <th style="padding: 2px;">Activity Guidance</th>
        <th style="padding: 2px;">Required Action</th>
        <th style="padding: 2px;">Attire Recommendations</th>
    </tr>
    <tr>
        <td style="padding: 2px; color: #10b981; font-weight: bold;">Low</td>
        <td style="padding: 2px; color: #10b981; font-weight: bold;">&lt; 31.0</td>
        <td style="padding: 2px;">Continue normal activities</td>
        <td style="padding: 2px;">Hydrate normally</td>
        <td style="padding: 2px;">Wear normal attire</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #f59e0b; font-weight: bold;">Moderate</td>
        <td style="padding: 2px; color: #f59e0b; font-weight: bold;">31.0 – 32.9</td>
        <td style="padding: 2px;">Reduce outdoor work; take regular rest breaks</td>
        <td style="padding: 2px;">Drink more fluids; monitor for heat symptoms</td>
        <td style="padding: 2px;">Avoid multi-layers; use hat/umbrella</td>
    </tr>
    <tr>
        <td style="padding: 2px; color: #ef4444; font-weight: bold;">High</td>
        <td style="padding: 2px; color: #ef4444; font-weight: bold;">≥ 33.0</td>
        <td style="padding: 2px;">Minimise outdoor work; longer/more frequent breaks</td>
        <td style="padding: 2px;">Cool actively (sponging/water); monitor symptoms</td>
        <td style="padding: 2px;">Lightweight, light-coloured, thin absorbent material</td>
    </tr>
</table>
<div style="font-size: 12px; margin-bottom: 8px;">
    *Rest breaks should be taken indoors or under shade. Active cooling applies during high heat stress breaks.
</div>
        """)
        st.markdown(html_content, unsafe_allow_html=True)

    with st.expander("Haze Trends", expanded=True):
        time_window = st.slider(
            "Time Range (Hours):",
            min_value=2,
            max_value=24,
            value=24,
            step=1,
            key="shared_haze_time_window",
        )
        if not df_env.empty:
            cutoff_time = df_env["timestamp"].max() - pd.Timedelta(hours=time_window)
            df_chart = (
                df_env[df_env["timestamp"] >= cutoff_time]
                .sort_values(by="timestamp")
                .reset_index(drop=True)
            )
            st.markdown('1h PM2.5 Trend')
            pm25_chart = (
                alt.Chart(df_chart)
                .mark_line()
                .encode(
                    x=alt.X("timestamp:T", title="Date & Time"),
                    y=alt.Y("pm25_1h:Q", title="1h PM2.5 (µg/m³)"),
                    color=alt.Color("region:N", legend=None),
                )
                .properties(height=250)
            )
            st.altair_chart(pm25_chart, width="stretch")
            st.markdown('24h Average PSI Trend')
            psi_chart = (
                alt.Chart(df_chart)
                .mark_line()
                .encode(
                    x=alt.X("timestamp:T", title="Date & Time"),
                    y=alt.Y("psi_24h:Q", title="24h PSI Index"),
                    color=alt.Color("region:N", legend=alt.Legend(orient="bottom")),
                )
                .properties(height=250)
            )
            st.altair_chart(psi_chart, width="stretch")