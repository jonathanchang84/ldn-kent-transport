import streamlit as st
import requests
from supabase import create_client, Client

# --- PAGE CONFIGURATION (Optimized for Mobile viewports) ---
st.set_page_config(
    page_title="LDN & Kent Commuter",
    page_icon="🚇",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom Minimalist CSS to make text and components match phone UI standards
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    div[data-testid="stNotification"] { padding: 0.5rem; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALIZE CONNECTIONS ---
@st.cache_resource
def init_supabase() -> Client:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()
TFL_KEY = st.secrets["TFL_API_KEY"]
USER_ID = "jonathan_commuter"

# --- API CORE UTILITIES ---
@st.cache_data(ttl=60)
def get_tfl_line_statuses(modes="tube,overground,elizabeth-line,dlr"):
    """Fetches real-time London line statuses."""
    url = f"https://api.tfl.gov.uk/Line/Mode/{modes}/Status?app_key={TFL_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []

@st.cache_data(ttl=30)
def get_national_rail_board(crs_code):
    """Fetches live Southeastern & Thameslink departures for Kent stations using open data rail feeds."""
    url = f"https://huxley2.azurewebsites.net/departures/{crs_code}?rows=5"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

# --- DATABASE PERSISTENCE UTILITIES ---
def get_saved_routes(user_id):
    res = supabase.table("saved_routes").select("*").eq("user_id", user_id).execute()
    return [row['line_name'] for row in res.data]

def add_saved_route(user_id, line_name):
    supabase.table("saved_routes").insert({"user_id": user_id, "line_name": line_name}).execute()

def remove_saved_route(user_id, line_name):
    supabase.table("saved_routes").delete().eq("user_id", user_id).eq("line_name", line_name).execute()

def get_saved_locations(user_id):
    res = supabase.table("saved_locations").select("*").eq("user_id", user_id).execute()
    return res.data

def add_saved_location(user_id, name, stop_id, mode):
    supabase.table("saved_locations").insert({
        "user_id": user_id, "location_name": name, "stop_id": stop_id, "transport_mode": mode
    }).execute()

def remove_saved_location(user_id, stop_id):
    supabase.table("saved_locations").delete().eq("user_id", user_id).eq("stop_id", stop_id).execute()


# --- MOBILE APPLICATION UI LAYOUT ---
st.title("🚇 LDN & Kent Transit")
st.caption("Live operational status and saved hubs.")

menu = st.segmented_control(
    "Navigate", 
    options=["Watchlist", "London Lines", "Kent Rail Boards", "Manage Watchlist"], 
    default="Watchlist",
    label_visibility="collapsed"
)

# Pre-fetch London line data
raw_line_data = get_tfl_line_statuses()
line_status_map = {line['name']: line['lineStatuses'][0]['statusSeverityDescription'] for line in raw_line_data}

# --- VIEW 1: WATCHLIST ---
if menu == "Watchlist":
    st.subheader("Your Commute Alerts")
    
    # Section A: Saved London Lines
    saved_lines = get_saved_routes(USER_ID)
    if saved_lines:
        st.markdown("#### London Lines")
        for line in saved_lines:
            status = line_status_map.get(line, "Good Service")
            if status == "Good Service":
                st.success(f"**{line} Line**: Good Service")
            else:
                st.warning(f"⚠️ **{line} Line**: {status}")

    # Section B: Saved Kent Rail Hubs
    saved_locs = get_saved_locations(USER_ID)
    if saved_locs:
        st.markdown("#### Kent Stations")
        for loc in saved_locs:
            with st.container(border=True):
                st.markdown(f"🚉 **{loc['location_name']} Departures**")
                board = get_national_rail_board(loc['stop_id'])
                if board and board.get('trainServices'):
                    for train in board['trainServices'][:3]:
                        std = train.get('std')
                        etd = train.get('etd')
                        dest = train['destination'][0]['locationName']
                        operator = train.get('operator', 'Rail Service')
                        
                        status_text = "On Time" if etd == "On time" else f"Delayed: {etd}"
                        if etd == "Cancelled":
                            status_text = "❌ Cancelled"
                            
                        st.caption(f"**{std}** to {dest} ({operator}) — {status_text}")
                else:
                    st.caption("No active departures or schedule disruptions found.")

    if not saved_lines and not saved_locs:
        st.info("Your watchlist is empty. Go to 'Manage Watchlist' to tailor your personal mobile dashboard feeds.")

# --- VIEW 2: LONDON LINES ---
elif menu == "London Lines":
    st.subheader("All London Services")
    search_query = st.text_input("🔍 Filter Lines (e.g., Central, Victoria)", "").lower()
    
    for line_name, status in line_status_map.items():
        if search_query and search_query not in line_name.lower():
            continue
            
        with st.container(border=True):
            col1, col2 = st.columns([0.6, 0.4])
            with col1: st.markdown(f"**{line_name}**")
            with col2:
                if status == "Good Service": st.caption("✅ Good Service")
                else: st.caption(f"🚨 {status}")

# --- VIEW 3: KENT RAIL BOARDS ---
elif menu == "Kent Rail Boards":
    st.subheader("Live Kent Stations")
    
    # Preset dict of major Southeastern / Thameslink key transit hubs in Kent
    kent_hubs = {
        "Sevenoaks": "SEV",
        "Ashford International": "AFK",
        "Tunbridge Wells": "TBW",
        "Canterbury West": "CBW",
        "Chatham": "CTM",
        "Dartford": "DFD",
        "Maidstone East": "MDE"
    }
    
    selected_hub = st.selectbox("Select a Kent Station:", options=list(kent_hubs.keys()))
    crs = kent_hubs[selected_hub]
    
    board = get_national_rail_board(crs)
    
    if board and board.get('trainServices'):
        st.markdown(f"### Live departures from {selected_hub}")
        for train in board['trainServices']:
            with st.container(border=True):
                col1, col2 = st.columns([0.3, 0.7])
                with col1:
                    st.markdown(f"### {train.get('std')}")
                with col2:
                    dest = train['destination'][0]['locationName']
                    etd = train.get('etd')
                    plat = train.get('platform', '-')
                    op = train.get('operator')
                    
                    st.markdown(f"**To {dest}**")
                    st.caption(f"Plat {plat} | {op} | Status: {etd}")
    else:
        st.info("No active running train connections tracked currently at this hub.")

# --- VIEW 4: MANAGE WATCHLIST ---
elif menu == "Manage Watchlist":
    st.subheader("Edit Watchlist Preferences")
    
    # 1. Manage London Lines
    st.markdown("### London Underground/Overground")
    current_saved_lines = get_saved_routes(USER_ID)
    available_lines = sorted(list(line_status_map.keys()))
    
    selected_lines = st.multiselect(
        "Select lines to track:", options=available_lines, default=current_saved_lines
    )
    
    # 2. Manage Kent Stations
    st.markdown("### Kent Rail Hubs")
    kent_options = {
        "Sevenoaks (SEV)": "SEV",
        "Ashford International (AFK)": "AFK",
        "Tunbridge Wells (TBW)": "TBW",
        "Canterbury West (CBW)": "CBW",
        "Chatham (CTM)": "CTM",
        "Dartford (DFD)": "DFD",
        "Maidstone East (MDE)": "MDE"
    }
    
    current_saved_locs = get_saved_locations(USER_ID)
    current_loc_codes = [l['stop_id'] for l in current_saved_locs]
    
    # Find matching display defaults
    default_locs = [k for k, v in kent_options.items() if v in current_loc_codes]
    selected_hubs = st.multiselect("Select Kent stations to track:", options=list(kent_options.keys()), default=default_locs)
    
    if st.button("Save Dashboard Changes", use_container_width=True):
        # Sync London Lines
        for line in current_saved_lines:
            if line not in selected_lines: remove_saved_route(USER_ID, line)
        for line in selected_lines:
            if line not in current_saved_lines: add_saved_route(USER_ID, line)
            
        # Sync Kent Stations
        chosen_codes = [kent_options[h] for h in selected_hubs]
        for loc in current_saved_locs:
            if loc['stop_id'] not in chosen_codes:
                remove_saved_location(USER_ID, loc['stop_id'])
        for h in selected_hubs:
            code = kent_options[h]
            name = h.split(" (")[0]
            if code not in current_loc_codes:
                add_saved_location(USER_ID, name, code, "National Rail")
                
        st.success("Watchlist configuration successfully synced to Supabase!")
        st.rerun()