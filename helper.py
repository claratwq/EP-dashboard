import folium
import streamlit as st
import altair as alt
from bs4 import BeautifulSoup

# # Helper function to evaluate category based on NEA threshold bands
# def get_category_badge(val, metric_type):
#     try:
#         val = float(val)
#     except (ValueError, TypeError):
#         return ("Unknown", "#64748b")

#     if metric_type == "pm25_1h":
#         if val <= 55:
#             return ("Band 1 (Normal) | Standard building ventilation & ED triage operations.", "#10b981")      # Green
#         elif val <= 150:
#             return ("Band 2 (Elevated) | Monitor ED respiratory admissions; prepare HEPA filters.", "#f59e0b")    # Amber
#         elif val <= 250:
#             return ("Band 3 (High) | Restrict patient transfers outdoors; prep acute respiratory bays.", "#ef4444")        # Red
#         else:
#             return ("Band 4 (Very High) | Activate HVAC Recirculation**; deploy full respiratory surge plan.", "#8b5cf6")   # Purple

#     elif metric_type in ["psi_24h", "sub_index"]:
#         if val <= 50:
#             return ("Good | Baseline operations; standard respiratory bed allocation.", "#10b981")                 # Green
#         elif val <= 100:
#             return ("Moderate | Normal operations; monitor 12h trend for surge trajectory.", "#38bdf8")             # Blue
#         elif val <= 200:
#             return ("Unhealthy | Prep respiratory surge beds; alert ED for lagged asthma/COPD admissions.", "#f59e0b")            # Amber
#         elif val <= 300:
#             return ("Very Unhealthy | Restrict non-essential patient transfers; review elective respiratory cases.", "#ef4444")       # Red
#         else:
#             return ("Hazardous | Activate full bed capacity contingency; transition wards to full internal airflow.", "#8b5cf6")            # Purple

#     elif metric_type == "pm25_24h":
#         if val <= 12:
#             return ("Good | Baseline operations; standard respiratory bed allocation.", "#10b981")
#         elif val <= 35:
#             return ("Moderate | Normal operations; monitor 12h trend for surge trajectory.", "#38bdf8")
#         elif val <= 55:
#             return ("Unhealthy | Prep respiratory surge beds; alert ED for lagged asthma/COPD admissions.", "#f59e0b")
#         elif val <= 150:
#             return ("Very Unhealthy | Restrict non-essential patient transfers; review elective respiratory cases.", "#ef4444")
#         else:
#             return ("Hazardous | Activate full bed capacity contingency; transition wards to full internal airflow.", "#8b5cf6")

#     return ("Normal", "#10b981")

# def get_delta(df_curr, df_past, reg, col):
#         val_now = df_curr.loc[reg, col] if reg in df_curr.index else 0
#         val_prev = df_past.loc[reg, col] if reg in df_past.index else val_now
#         try:
#             return int(val_now - val_prev)
#         except Exception:
#             return 0

def get_severity_color(val, metric_type):
    """
    Evaluates metric severity and returns category label and color code.
    """
    if val is None or val == "N/A" or val == "NA":
        return ("Data Unavailable", "#64748b")
    
    try:
        val = float(val)
    except (ValueError, TypeError):
        return ("Data Unavailable", "#64748b")

    if metric_type == "wbgt":
        if val < 31.0:
            return ("Low Heat Stress", "#10b981")        # Green
        elif val < 33.0:
            return ("Moderate Heat Stress", "#f59e0b")   # Amber
        else:
            return ("High Heat Stress", "#ef4444")       # Red
            
    elif metric_type == "pm25_1h":
        if val <= 55:
            return ("Normal", "#10b981")                 # Green
        elif val <= 150:
            return ("Elevated","#d7de05")                # yellow
        elif val <= 250:
            return ("High", "#dd900a")                   # Amber
        else:
            return ("Very High", "#ef4444")              # Red

    elif metric_type == "psi_24h":
        if val <= 50:
            return ("Good", "#10b981")                   # Green
        elif val <= 100:
            return ("Moderate", "#38bdf8")               # Blue
        elif val <= 200:
            return ("Unhealthy", "#d7de05")              # Yellow
        elif val <= 300:
            return ("Very Unhealthy","#dd900a")         # Amber
        else:
            return ("Hazardous",  "#ef4444")              # Red
            
    return ("Normal", "#10b981")

# # 2. Your Existing Function (No amendments needed)
# def render_custom_card(title, west_val, unit, delta, other_regions_data, metric_type, is_tactical=False):
#     delta_color = "#10b981" if delta <= 0 else "#ef4444"
#     delta_symbol = "↓" if delta <= 0 else "↑"
    
#     cat_name, cat_color = get_category_badge(west_val, metric_type)
#     tactical_class = "kpi-tactical" if is_tactical else ""

#     other_html = "".join([
#         f"<div class='kpi-secondary'><b>{r}</b> — {val} {unit if unit else None}</div>"
#         for r, val in other_regions_data.items() if r != "West"
#     ])

#     card_html = f"""
#     <div class="kpi-card {tactical_class}">
#         <div class="kpi-title" style="font-size: 15px; font-weight: 600; margin-bottom: 8px;">{title}</div>
#         <div style="display: flex; justify-content: space-between; align-items: center;">
#             <div class="kpi-value" style="font-size: 40px; font-weight: 700; line-height: 1;">
#                 {west_val}<span class="kpi-secondary" style="font-size: 15px; font-weight: 400;"> {unit}</span>
#             </div>
#             <div style="font-size: 11px; line-height: 1.3; text-align: left; padding-left: 8px;">
#                 {other_html}
#             </div>
#         </div>
#         <div style="margin-top: 14px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
#             <span style="background-color: {cat_color}22; color: {cat_color}; border: 1px solid {cat_color}; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700;">
#                 ● {cat_name}
#             </span>
#             <span style="background-color: rgba(16, 185, 129, 0.15); color: {delta_color}; padding: 3px 8px; border-radius: 16px; font-size: 11px; font-weight: 600;">
#                 {delta_symbol} {delta:+d} vs 1h ago
#             </span>
#         </div>
#     </div>
#     """
#     return card_html

# # Helper layer generator to attach value labels to the West region trendline
# def create_west_annotation(df_data, metric_col, dy_offset=-10):
#     df_west = df_data[df_data["region"] == "West"]
#     return alt.Chart(df_west).mark_text(
#         align="center",
#         baseline="bottom",
#         dy=dy_offset,
#         color="#f59e0b",
#         fontSize=11,
#         fontWeight="bold"
#     ).encode(
#         x=alt.X("Time:O"),
#         y=alt.Y(f"{metric_col}:Q"),
#         text=alt.Text(f"{metric_col}:Q")
#     )

def get_folium_icon(message):
    msg_upper = str(message).upper()
    if "ACCIDENT" in msg_upper:
        return folium.Icon(color="red", icon="car", prefix="fa")
    elif "FIRE" in msg_upper:
        return folium.Icon(color="orange", icon="fire", prefix="fa")
    elif "PLANT FAILURE" in msg_upper:
        return folium.Icon(color="purple", icon="industry", prefix="fa")
    else:
        return folium.Icon(color="blue", icon="warning", prefix="fa")




def parse_zika_description(description_html: str) -> dict:
    """Parses the HTML table inside the Description key to extract metadata fields."""
    parsed_data = {"locality": "Unknown Area", "case_size": 0}
    if not description_html:
        return parsed_data

    try:
        soup = BeautifulSoup(description_html, "html.parser")
        for tr in soup.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                key = th.get_text(strip=True).upper()
                val = td.get_text(strip=True)

                if key == "LOCALITY" and val:
                    parsed_data["locality"] = val
                elif key == "CASE_SIZE" and val.isdigit():
                    parsed_data["case_size"] = int(val)
    except Exception:
        pass

    return parsed_data