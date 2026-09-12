import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import time

load_dotenv()
DATA_GOV_KEY = os.getenv("DATA_GOV_KEY")
LTA_ACCOUNT_KEY = os.getenv("LTA_ACCOUNT_KEY")

# -------------------------------------------------------------
# 2. Fetch Haze / Air Quality Data (Data.gov.sg)
# -------------------------------------------------------------
@st.cache_data(ttl=1800)
def get_hospital_past_12h_haze():
    psi_url = "https://api-open.data.gov.sg/v2/real-time/api/psi"
    pm25_url = "https://api-open.data.gov.sg/v2/real-time/api/pm25"
    headers = {"x-api-key": DATA_GOV_KEY} if DATA_GOV_KEY else {}

    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(hours=24)

    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    day_before_str = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    # Dictionary to merge 1-hour PM2.5 readings by (timestamp, region)
    pm25_1h_dict = {}

    # Fetch 1-Hour PM2.5 readings
    for date_str in [day_before_str,yesterday_str, today_str]:
        try:
            res = requests.get(pm25_url, headers=headers, params={"date": date_str}, timeout=10)
            res.raise_for_status()
            items = res.json().get("data", {}).get("items", [])
            for item in items:
                ts_str = item.get("timestamp")
                if not ts_str:
                    continue
                dt_obj = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if cutoff_time <= dt_obj <= now:
                    readings_1h = item.get("readings", {}).get("pm25_one_hourly", {})
                    for reg, val in readings_1h.items():
                        pm25_1h_dict[(dt_obj, reg.lower())] = val
        except Exception as e:
            print(f"Error fetching PM2.5 1h for {date_str}: {e}")

    # Fetch 24-Hour PSI and PM2.5 readings
    parsed_records = []
    for date_str in [day_before_str, yesterday_str, today_str]:
        try:
            res = requests.get(psi_url, headers=headers, params={"date": date_str}, timeout=10)
            res.raise_for_status()
            items = res.json().get("data", {}).get("items", [])
            for item in items:
                ts_str = item.get("timestamp")
                if not ts_str:
                    continue
                dt_obj = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if cutoff_time <= dt_obj <= now:
                    readings = item.get("readings", {})
                    psi_24h = readings.get("psi_twenty_four_hourly", {})
                    pm25_24h = readings.get("pm25_twenty_four_hourly", {})
                    pm25_sub = readings.get("pm25_sub_index", {})

                    for region in ["west", "north", "south", "east", "central"]:
                        parsed_records.append({
                            "timestamp": dt_obj,
                            "region": region.capitalize(),
                            "psi_24h": psi_24h.get(region),
                            "pm25_24h": pm25_24h.get(region),
                            "pm25_sub_index": pm25_sub.get(region),
                            "pm25_1h": pm25_1h_dict.get((dt_obj, region), "N/A")
                        })
        except Exception as e:
            print(f"Error fetching PSI for {date_str}: {e}")

    df = pd.DataFrame(parsed_records)
    if not df.empty:
        df = df.sort_values(by=["timestamp", "region"]).drop_duplicates(subset=["timestamp", "region"]).reset_index(drop=True)

    return df
# -------------------------------------------------------------
# 3. Fetch Live Traffic Incidents (LTA DataMall)
# -------------------------------------------------------------
@st.cache_data(ttl=120)
def get_traffic_incidents():
    # Use HTTPS and the updated LTA domain
    url = "https://datamall2.mytransport.sg/ltaodataservice/TrafficIncidents"
    headers = {
        "AccountKey": LTA_ACCOUNT_KEY,
        "accept": "application/json"
    }
    
    if not LTA_ACCOUNT_KEY:
        # Fallback mock data if key is missing from .env
        return pd.DataFrame([
            {"Latitude": 1.3343, "Longitude": 103.8563, "Message": "(Mock) Accident on PIE near Bedok Exit"},
            {"Latitude": 1.3521, "Longitude": 103.6811, "Message": "(Mock) Breakdown on AYE near Benoi Rd Exit"}
        ])
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        return pd.DataFrame(data.get("value", []))
    except Exception as e:
        st.warning(f"Could not reach LTA API. Loading mock traffic data. Details: {e}")
        return pd.DataFrame([
            {"Latitude": 1.3343, "Longitude": 103.8563, "Message": "Accident on PIE towards Changi near Bedok Exit"},
            {"Latitude": 1.3521, "Longitude": 103.6811, "Message": "Breakdown on AYE towards Tuas near Benoi Rd Exit"}
        ])
        

# -------------------------------------------------------------
# 4. Fetch Dengue hotspots
# -------------------------------------------------------------
    
@st.cache_data(ttl=86400)  # Cache for 24 hours (Dengue data updates infrequently)
def get_dengue_geojson():
    dataset_id = "d_dbfabf16158d1b0e1c420627c0819168"
    poll_url = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
    headers = {"x-api-key": DATA_GOV_KEY} if DATA_GOV_KEY else {}

    max_retries = 3
    for attempt in range(max_retries):
        try:
            poll_res = requests.get(poll_url, headers=headers, timeout=10)
            
            # Handle 429 specifically with backoff
            if poll_res.status_code == 429:
                time.sleep(2 * (attempt + 1))  # Wait 2s, then 4s before retrying
                continue
                
            poll_res.raise_for_status()
            res_data = poll_res.json().get("data")
            
            if res_data and "url" in res_data:
                download_url = res_data["url"]
                geojson_res = requests.get(download_url, timeout=15)
                geojson_res.raise_for_status()
                return geojson_res.json()
            else:
                st.warning("Dengue API polling returned no download URL.")
                return None

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                st.warning(f"Dengue dataset temporarily rate-limited: {e}")
                return None
            time.sleep(2)
            
    return None