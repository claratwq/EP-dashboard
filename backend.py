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
# Robust WBGT Fetcher
# -------------------------------------------------------------
@st.cache_data(ttl=1800)
def get_wbgt_data(target_date: str = None) -> dict:
    """
    Fetches real-time WBGT records from data.gov.sg and maps station readings
    to regional maximums (North, South, East, West, Central).
    Safely handles 'NA' and missing values.
    """
    url = "https://api-open.data.gov.sg/v2/real-time/api/weather"
    params = {"api": "wbgt"}
    if target_date:
        params["date"] = target_date
    headers = {"x-api-key": DATA_GOV_KEY} if DATA_GOV_KEY else {}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        payload = res.json()
        
        records = payload.get("data", {}).get("records", [])
        if not records:
            return {"timestamp": None, "readings": {}}
        
        latest_record = records[-1]
        timestamp = latest_record.get("datetime")
        readings = latest_record.get("item", {}).get("readings", [])
        
        # Mapping weather station names to 5 core regions
        region_map = {
            "Bukit Timah(West)": "West", "Bukit Timah (West)": "West", "Tuas Terminal Gateway": "West",
            "Old Chua Chu Kang Road": "West", "Jurong West Street 93": "West", "West Coast Road": "West",
            "Choa Chu Kang Stadium": "West", "Jalan Bahar": "West", "Taman Jurong Greens": "West",
            "Bukit Batok Street 22": "West", "Sakra Road": "West",
            "Woodlands Street 13": "North", "Yio Chu Kang Stadium": "North", "Punggol North": "North",
            "Mandai Wildlife Reserve": "North", "Outward Bound Singapore(Pulau ubin)": "North",
            "Sengkang East Avenue": "North",
            "Sentosa Palawan Green": "South", "Stadium Road": "South", "Upper Pickering Street": "South",
            "Marina Barrage": "South", "Stirling Road": "South",
            "Bishan Street": "Central", "Evans Road": "Central", "MacRitchie Reservoir": "Central",
            "Cathay Green": "Central", "Hougang Stadium": "Central",
            "Upper Changi Road North": "East", "Bedok North Street 2": "East", "Pasir Ris Walk": "East",
            "Tampines Walk": "East", "Outward Bound Singapore(East Coast)": "East"
        }
        
        region_wbgt = {}
        for r in readings:
            stn_name = r.get("station", {}).get("name")
            raw_val = r.get("wbgt")
            
            # Safe numeric type conversion for 'NA' strings or None
            try:
                val = float(raw_val) if raw_val is not None and str(raw_val).strip().upper() != "NA" else None
            except (ValueError, TypeError):
                val = None

            reg = region_map.get(stn_name, "Central")
            if val is not None:
                # Retain the peak WBGT reading per region for risk monitoring
                region_wbgt[reg] = max(region_wbgt.get(reg, 0.0), val)
                
        return {
            "timestamp": timestamp,
            "readings": region_wbgt
        }
    except Exception as e:
        print(f"Error fetching WBGT: {e}")
        return {"timestamp": None, "readings": {}}

# -------------------------------------------------------------
# 2. Combined Past 24h Metrics (PSI, PM2.5, WBGT)
# -------------------------------------------------------------

@st.cache_data(ttl=1800)
def get_past_24h_environmental_metrics(hours_limit: int = 24) -> pd.DataFrame:
    """
    Fetches 24-hour PSI and 1-hour PM2.5 metrics across SGT dates,
    merges them by timestamp and region, and filters to exactly 
    the past `hours_limit` window (e.g., 1 PM yesterday to 1 PM today).
    """
    url_psi = "https://api-open.data.gov.sg/v2/real-time/api/psi"
    url_pm25 = "https://api-open.data.gov.sg/v2/real-time/api/pm25"
    headers = {"x-api-key": DATA_GOV_KEY} if DATA_GOV_KEY else {}

    # Define SGT Timezone (UTC+8)
    sgt_tz = timezone(timedelta(hours=8))
    now_sgt = datetime.now(sgt_tz)

    # Calculate exact start and end cutoff bounds (e.g. 1 PM yesterday to 1 PM today)
    end_time = now_sgt.replace(minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(hours=hours_limit)

    # Generate required SGT date strings to query
    dates_to_query = sorted(list(set([
        start_time.strftime("%Y-%m-%d"),
        end_time.strftime("%Y-%m-%d")
    ])))

    regions = ["West", "North", "South", "East", "Central"]

    # 1. Fetch 1-Hour PM2.5 readings from dedicated endpoint
    pm25_1h_lookup = {}
    for date_str in dates_to_query:
        try:
            res = requests.get(url_pm25, headers=headers, params={"date": date_str}, timeout=10)
            res.raise_for_status()
            items = res.json().get("data", {}).get("items", [])
            for item in items:
                ts_str = item.get("timestamp")
                if not ts_str:
                    continue
                dt_obj = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(sgt_tz)
                if start_time <= dt_obj <= end_time:
                    pm25_readings = item.get("readings", {}).get("pm25_one_hourly", {})
                    for reg in regions:
                        pm25_1h_lookup[(dt_obj, reg)] = pm25_readings.get(reg.lower())
        except Exception as e:
            print(f"Error fetching PM2.5 for {date_str}: {e}")

    # 2. Fetch 24-Hour PSI readings and join with PM2.5 lookup
    parsed_records = []
    for date_str in dates_to_query:
        try:
            res = requests.get(url_psi, headers=headers, params={"date": date_str}, timeout=10)
            res.raise_for_status()
            items = res.json().get("data", {}).get("items", [])
            for item in items:
                ts_str = item.get("timestamp")
                if not ts_str:
                    continue
                dt_obj = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(sgt_tz)
                if start_time <= dt_obj <= end_time:
                    psi_readings = item.get("readings", {}).get("psi_twenty_four_hourly", {})
                    for reg in regions:
                        parsed_records.append({
                            "timestamp": dt_obj,
                            "region": reg,
                            "psi_24h": psi_readings.get(reg.lower()),
                            "pm25_1h": pm25_1h_lookup.get((dt_obj, reg))
                        })
        except Exception as e:
            print(f"Error fetching PSI for {date_str}: {e}")

    df = pd.DataFrame(parsed_records)
    if not df.empty:
        df = df.sort_values(by=["timestamp", "region"]).drop_duplicates(subset=["timestamp", "region"]).reset_index(drop=True)

    return df

# -------------------------------------------------------------
# 3. Zika Cluster GeoJSON Fetcher
# -------------------------------------------------------------
@st.cache_data(ttl=86400)
def get_zika_geojson():
    """Fetches Zika clusters GeoJSON from Data.gov.sg"""
    dataset_id = "d_a3c783f11d79ff7feb8856f762ccf2c5"
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
                st.warning("Zika API polling returned no download URL.")
                return None

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                st.warning(f"Zika dataset temporarily rate-limited: {e}")
                return None
            time.sleep(2)
    return None

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
        data_df = pd.DataFrame(data.get("value", []))
        
        return data_df
    except Exception as e:
        st.warning(f"Could not reach LTA API. {e}")
        return pd.DataFrame()
        