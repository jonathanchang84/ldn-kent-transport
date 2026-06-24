import streamlit as st
import requests
from supabase import create_client, Client

# --- PAGE CONFIGURATION (Optimized for Mobile Viewports) ---
st.set_page_config(
    page_title="LDN & Kent Commuter",
    page_icon="🚇",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom Minimalist CSS for clean mobile rendering
st.markdown("""
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
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

# --- API CORE DATA FETCHERS ---
@st.cache_data(ttl=60)
def get_tfl_line_statuses(modes="tube,overground,elizabeth-line,dlr"):
    """Fetches real-time London transit line operational statuses."""
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
    """Fetches live Southeastern & Thameslink departures for Kent train stations."""
    url = f"https://huxley2.azurewebsites.net/departures/{crs_code}?rows=5"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

@st.cache_data(ttl=30)
def get_kent_bus_arrivals(stop_id):
    """Fetches live regional Kent bus arrivals using public NaPTAN data gateway feeds."""
    url = f"https://transportapi.com/v3/uk/bus/stop/{stop_id}/live.json"
    params = {
        "app_id": "c62fdfbf",  # Public sandbox prototyping application ID
        "app_key": "9cfcb68c67a3f3b970878516ee70a0e9",
        "group": "no"
    }
    try:
        response = requests.get(url, params=params, timeout=8)
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
st.caption("Unified live dashboard for cross-border commuters.")

menu = st.segmented_control(
    "Navigate", 
    options=["Watchlist", "London Lines", "Kent Live Hubs", "Manage Watchlist"], 
    default="Watchlist",
    label_visibility="collapsed"
)

# Pre-fetch London status configurations globally
raw_line_data = get_tfl_line_statuses()
line_status_map = {line['name']: line['lineStatuses'][0]['statusSeverityDescription'] for line in raw_line_data}

# --- VIEW 1: WATCHLIST ---
if menu == "Watchlist":
    st.subheader("Your Commute Alerts")
    
    # 1. Saved London Lines
    saved_lines = get_saved_routes(USER_ID)
    if saved_lines:
        st.markdown("#### London Lines")
        for line in saved_lines:
            status = line_status_map.get(line, "Good Service")
            if status == "Good Service":
                st.success(f"**{line} Line**: Good Service")
            else:
                st.warning(f"⚠️ **{line} Line**: {status}")

    # 2. Saved Kent Hubs (Trains & Buses)
    saved_locs = get_saved_locations(USER_ID)
    if saved_locs:
        # Filter and display trains
        train_hubs = [l for l in saved_locs if l['transport_mode'] == "National Rail"]
        if train_hubs:
            st.markdown("#### Kent Train Stations")
            for loc in train_hubs:
                with st.container(border=True):
                    st.markdown(f"🚉 **{loc['location_name']} Departures**")
                    board = get_national_rail_board(loc['stop_id'])
                    if board and board.get('trainServices'):
                        for train in board['trainServices'][:3]:
                            std = train.get('std')
                            etd = train.get('etd')
                            dest = train['destination'][0]['locationName']
                            op = train.get('operator', 'Rail')
                            status_text = "On Time" if etd == "On time" else f"Delayed: {etd}"
                            if etd == "Cancelled": status_text = "❌ Cancelled"
                            st.caption(f"**{std}** to {dest} ({op}) — {status_text}")
                    else:
                        st.caption("No upcoming trains or data feed unavailable.")

        # Filter and display buses
        bus_hubs = [l for l in saved_locs if l['transport_mode'] == "Bus"]
        if bus_hubs:
            st.markdown("#### Kent Bus Hubs")
            for loc in bus_hubs:
                with st.container(border=True):
                    st.markdown(f"🚌 **{loc['location_name']} Arrivals**")
                    bus_data = get_kent_bus_arrivals(loc['stop_id'])
                    if bus_data and 'departures' in bus_data:
                        all_buses = []
                        for line_no, lists in bus_data['departures'].items():
                            all_buses.extend(lists)
                        
                        all_buses = sorted(all_buses, key=lambda x: x.get('best_departure_estimate', '23:59'))[:3]
                        if all_buses:
                            for bus in all_buses:
                                eta = bus.get('best_departure_estimate')
                                line = bus.get('line')
                                dest = bus.get('direction', 'Local Route')
                                st.caption(f"**{line}** to {dest} — **{eta}**")
                        else:
                            st.caption("No scheduled departures running currently.")
                    else:
                        st.caption("No live bus tracker connection available.")

    if not saved_lines and not saved_locs:
        st.info("Your watchlist is empty. Head to 'Manage Watchlist' to customize your feeds.")

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

# --- VIEW 3: KENT LIVE HUBS ---
elif menu == "Kent Live Hubs":
    st.subheader("Live Regional Explorer")
    mode_tab = st.radio("Select Hub Category:", ["Trains", "Buses"], horizontal=True, label_visibility="collapsed")
    
    if mode_tab == "Trains":
        kent_trains = {
            "Sevenoaks": "SEV", "Ashford International": "AFK", "Tunbridge Wells": "TBW",
            "Canterbury West": "CBW", "Chatham": "CTM", "Dartford": "DFD", "Maidstone East": "MDE"
        }
        selected_train = st.selectbox("Select Station:", options=list(kent_trains.keys()))
        board = get_national_rail_board(kent_trains[selected_train])
        
        if board and board.get('trainServices'):
            st.markdown(f"### Live departures from {selected_train}")
            for train in board['trainServices']:
                with st.container(border=True):
                    col1, col2 = st.columns([0.3, 0.7])
                    with col1: st.markdown(f"### {train.get('std')}")
                    with col2:
                        dest = train['destination'][0]['locationName']
                        st.markdown(f"**To {dest}**")
                        st.caption(f"Plat {train.get('platform','-')} | {train.get('operator')} | Status: {train.get('etd')}")
        else:
            st.info("No active departures reported at this platform.")

    elif mode_tab == "Buses":
        kent_buses = {
            "Sevenoaks Bus Station (Bay A)": "2400A041320A",
            "Dartford Home Gardens (Stop K)": "2400A001090A",
            "Ashford International Bus Interchange": "2400A052040A"
        }
        selected_bus = st.selectbox("Select Bus Interchange:", options=list(kent_buses.keys()))
        bus_data = get_kent_bus_arrivals(kent_buses[selected_bus])
        
        if bus_data and 'departures' in bus_data:
            st.markdown(f"### Live countdown for {selected_bus}")
            all_buses = []
            for line_no, lists in bus_data['departures'].items():
                all_buses.extend(lists)
            all_buses = sorted(all_buses, key=lambda x: x.get('best_departure_estimate', '23:59'))
            
            for bus in all_buses:
                with st.container(border=True):
                    col1, col2 = st.columns([0.25, 0.75])
                    with col1: st.metric(label="Line", value=bus.get('line'))
                    with col2:
                        st.markdown(f"**To {bus.get('direction', 'Local Route')}**")
                        st.caption(f"Estimated Arrival Time: **{bus.get('best_departure_estimate')}**")
        else:
            st.info("No upcoming real-time bus telemetry available for this stop.")

# --- VIEW 4: MANAGE WATCHLIST ---
elif menu == "Manage Watchlist":
    st.subheader("Edit Watchlist Preferences")
    
    # 1. Manage London Lines
    st.markdown("### London Underground/Overground")
    current_saved_lines = get_saved_routes(USER_ID)
    available_lines = sorted(list(line_status_map.keys()))
    selected_lines = st.multiselect("Select lines to track:", options=available_lines, default=current_saved_lines)
    
    # 2. Manage Kent Trains
    st.markdown("### Kent Rail Hubs")
    kent_train_options = {
        "Sevenoaks (SEV)": "SEV", "Ashford International (AFK)": "AFK", "Tunbridge Wells (TBW)": "TBW",
        "Canterbury West (CBW)": "CBW", "Chatham (CTM)": "CTM", "Dartford (DFD)": "DFD", "Maidstone East (MDE)": "MDE"
    }
    current_saved_locs = get_saved_locations(USER_ID)
    current_train_codes = [l['stop_id'] for l in current_saved_locs if l['transport_mode'] == "National Rail"]
    default_trains = [k for k, v in kent_train_options.items() if v in current_train_codes]
    selected_train_hubs = st.multiselect("Select stations to watch:", options=list(kent_train_options.keys()), default=default_trains)
    
    # 3. Manage Kent Buses
    st.markdown("### Kent Bus Stops")
    kent_bus_options = {
        "Sevenoaks Bus Station (Bay A)": "2400A041320A",
        "Dartford Home Gardens (Stop K)": "2400A001090A",
        "Ashford International Bus Interchange": "2400A052040A"
    }
    current_bus_codes = [l['stop_id'] for l in current_saved_locs if l['transport_mode'] == "Bus"]
    default_buses = [k for k, v in kent_bus_options.items() if v in current_bus_codes]
    selected_bus_hubs = st.multiselect("Select bus stops to watch:", options=list(kent_bus_options.keys()), default=default_buses)
    
    if st.button("Save Dashboard Changes", use_container_width=True):
        # Sync London Lines
        for line in current_saved_lines:
            if line not in selected_lines: remove_saved_route(USER_ID, line)
        for line in selected_lines:
            if line not in current_saved_lines: add_saved_route(USER_ID, line)
            
        # Sync Kent Trains
        chosen_train_codes = [kent_train_options[h] for h in selected_train_hubs]
        for loc in current_saved_locs:
            if loc['transport_mode'] == "National Rail" and loc['stop_id'] not in chosen_train_codes:
                remove_saved_location(USER_ID, loc['stop_id'])
        for h in selected_train_hubs:
            code = kent_train_options[h]
            name = h.split(" (")[0]
            if code not in current_train_codes:
                add_saved_location(USER_ID, name, code, "National Rail")
                
        # Sync Kent Buses
        chosen_bus_codes = [kent_bus_options[h] for h in selected_bus_hubs]
        for loc in current_saved_locs:
            if loc['transport_mode'] == "Bus" and loc['stop_id'] not in chosen_bus_codes:
                remove_saved_location(USER_ID, loc['stop_id'])
        for h in selected_bus_hubs:
            code = kent_bus_options[h]
            if code not in current_bus_codes:
                add_saved_location(USER_ID, h, code, "Bus")
                
        st.success("Watchlist preferences synced securely to Supabase backend database!")
        st.rerun()