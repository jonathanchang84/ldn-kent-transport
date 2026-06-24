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
    .leg-block { border-left: 4px solid #1E3A8A; padding-left: 10px; margin-bottom: 10px; }
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
        "app_id": "c62fdfbf",
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

@st.cache_data(ttl=3600)
def search_uk_bus_stops(query_string):
    """Searches the entire UK NaPTAN database for matching bus stops via API."""
    if len(query_string) < 3:
        return []
    url = "https://transportapi.com/v3/uk/places.json"
    params = {
        "app_id": "c62fdfbf",
        "app_key": "9cfcb68c67a3f3b970878516ee70a0e9",
        "query": query_string,
        "type": "bus_stop"
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            return response.json().get('member', [])
    except Exception:
        pass
    return []

@st.cache_data(ttl=60)
def plan_journey(start, end):
    """Plans a multi-modal journey using the TfL Cross-Border Journey API."""
    url = f"https://api.tfl.gov.uk/Journey/JourneyResults/{start}/to/{end}"
    params = {
        "app_key": TFL_KEY,
        "nationalSearch": "true",  # Forces inclusion of Kent National Rail/Buses
        "timeIs": "departing"
    }
    try:
        response = requests.get(url, params=params, timeout=12)
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
    options=["Watchlist", "Route Planner", "London Lines", "Kent Live Hubs", "Manage Watchlist"], 
    default="Watchlist",
    label_visibility="collapsed"
)

# Pre-fetch London status configurations globally
raw_line_data = get_tfl_line_statuses()
line_status_map = {line['name']: line['lineStatuses'][0]['statusSeverityDescription'] for line in raw_line_data}

# --- VIEW 1: WATCHLIST ---
if menu == "Watchlist":
    st.subheader("Your Commute Alerts")
    
    saved_lines = get_saved_routes(USER_ID)
    if saved_lines:
        st.markdown("#### London Lines")
        for line in saved_lines:
            status = line_status_map.get(line, "Good Service")
            if status == "Good Service":
                st.success(f"**{line} Line**: Good Service")
            else:
                st.warning(f"⚠️ **{line} Line**: {status}")

    saved_locs = get_saved_locations(USER_ID)
    if saved_locs:
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

# --- VIEW 2: ROUTE PLANNER ---
elif menu == "Route Planner":
    st.subheader("📍 Cross-Border Route Planner")
    st.caption("Plan options using postcodes, station names, or street addresses.")
    
    col1, col2 = st.columns(2)
    with col1:
        start_point = st.text_input("From (Postcode / Address):", placeholder="e.g., DA1 1DR")
    with col2:
        end_point = st.text_input("To (Postcode / Address):", placeholder="e.g., EC4N 6JD")
        
    if st.button("Find Routes", use_container_width=True):
        if not start_point or not end_point:
            st.error("Please fill in both a starting point and destination.")
        else:
            with st.spinner("Calculating optimal transit legs..."):
                journey_data = plan_journey(start_point, end_point)
                
            if journey_data and 'journeys' in journey_data:
                st.success(f"Found {len(journey_data['journeys'])} viable route options:")
                
                for idx, journey in enumerate(journey_data['journeys'][:3]): # Top 3 itineraries
                    duration = journey.get('duration')
                    start_time = journey.get('startDateTime','').split('T')[-1][:5]
                    arrival_time = journey.get('arrivalDateTime','').split('T')[-1][:5]
                    
                    with st.expander(f"Option {idx+1}: {start_time} ➡️ {arrival_time} ({duration} mins)"):
                        # Check for global route issues/disruptions
                        has_disruptions = False
                        
                        st.markdown("#### 🗺️ Journey Steps")
                        for leg in journey.get('legs', []):
                            instruction = leg.get('instruction', {}).get('summary', 'Travel leg')
                            mode = leg.get('mode', {}).get('name', 'transit')
                            leg_duration = leg.get('duration')
                            
                            # Gather leg anomalies/issues
                            disruptions = leg.get('disruptions', [])
                            
                            st.markdown(f"""
                            <div class="leg-block">
                                <strong>{instruction}</strong> ({mode.title()})<br>
                                <span style="font-size:0.85rem; color:gray;">Duration: {leg_duration} mins</span>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            if disruptions:
                                has_disruptions = True
                                for d in disruptions:
                                    st.error(f"⚠️ **Issue Alert**: {d.get('description')}")
                                    
                        if not has_disruptions:
                            st.caption("✅ No recorded line delays or service disruptions on this option.")
            else:
                st.warning("No routes found. Ensure names or postcodes are typed accurately.")

# --- VIEW 3: LONDON LINES ---
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

# --- VIEW 4: KENT LIVE HUBS ---
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
        st.caption("Search for specific stops in 'Manage Watchlist' to view countdowns here.")
        current_saved_locs = get_saved_locations(USER_ID)
        saved_buses = {l['location_name']: l['stop_id'] for l in current_saved_locs if l['transport_mode'] == "Bus"}
        
        if saved_buses:
            selected_bus = st.selectbox("Select Bus Interchange:", options=list(saved_buses.keys()))
            bus_data = get_kent_bus_arrivals(saved_buses[selected_bus])
            
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
        else:
            st.info("You haven't saved any bus stops yet. Use the 'Manage Watchlist' search to save your local loops.")

# --- VIEW 5: MANAGE WATCHLIST ---
elif menu == "Manage Watchlist":
    st.subheader("Edit Watchlist Preferences")
    
    st.markdown("### 🚇 London Lines")
    current_saved_lines = get_saved_routes(USER_ID)
    available_lines = sorted(list(line_status_map.keys()))
    selected_lines = st.multiselect("Select lines to track:", options=available_lines, default=current_saved_lines)
    
    if st.button("Save London Line Changes", use_container_width=True):
        for line in current_saved_lines:
            if line not in selected_lines: remove_saved_route(USER_ID, line)
        for line in selected_lines:
            if line not in current_saved_lines: add_saved_route(USER_ID, line)
        st.success("London lines updated successfully!")
        st.rerun()

    st.markdown("---")

    st.markdown("### 🔍 Search & Add Kent Hubs")
    search_term = st.text_input("Enter search query (e.g., 'Sevenoaks', 'London Road', 'Dartford'):", value="")
    
    if search_term:
        kent_train_options = {
            "Sevenoaks": "SEV", "Ashford International": "AFK", "Tunbridge Wells": "TBW",
            "Canterbury West": "CBW", "Chatham": "CTM", "Dartford": "DFD", "Maidstone East": "MDE"
        }
        
        matched_trains = {k: v for k, v in kent_train_options.items() if search_term.lower() in k.lower()}
        if matched_trains:
            st.markdown("**Matched Train Stations:**")
            for name, crs in matched_trains.items():
                col1, col2 = st.columns([0.7, 0.3])
                with col1: st.markdown(f"🚉 **{name}** ({crs})")
                with col2:
                    if st.button("Add Station", key=f"add_train_{crs}", use_container_width=True):
                        add_saved_location(USER_ID, name, crs, "National Rail")
                        st.success(f"Added {name} to Watchlist!")
                        st.rerun()

        with st.spinner("Searching nationwide bus stops via API..."):
            found_bus_stops = search_uk_bus_stops(search_term)
            
        if found_bus_stops:
            st.markdown("**Matched Regional Bus Stops:**")
            for stop in found_bus_stops[:8]:
                stop_name = stop.get('name', 'Unknown Stop')
                indicator = stop.get('indicator', '')
                description = f"{stop_name} ({indicator})" if indicator else stop_name
                atco_code = stop.get('atcocode')
                locality = stop.get('locality', 'Kent')
                
                col1, col2 = st.columns([0.7, 0.3])
                with col1: 
                    st.markdown(f"🚌 **{description}**")
                    st.caption(f"Locality: {locality} | Code: {atco_code}")
                with col2:
                    if st.button("Add Bus", key=f"add_bus_{atco_code}", use_container_width=True):
                        add_saved_location(USER_ID, description, atco_code, "Bus")
                        st.success(f"Saved {stop_name} to your Watchlist!")
                        st.rerun()

    st.markdown("---")

    st.markdown("### 🗑️ Current Saved Hubs")
    current_saved_locs = get_saved_locations(USER_ID)
    
    if current_saved_locs:
        for loc in current_saved_locs:
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                icon = "🚉" if loc['transport_mode'] == "National Rail" else "🚌"
                st.markdown(f"{icon} **{loc['location_name']}**")
                st.caption(f"Type: {loc['transport_mode']} | Code: {loc['stop_id']}")
            with col2:
                if st.button("Remove", key=f"del_{loc['stop_id']}", use_container_width=True):
                    remove_saved_location(USER_ID, loc['stop_id'])
                    st.toast(f"Removed {loc['location_name']}")
                    st.rerun()
    else:
        st.caption("You are not tracking any Kent stations or bus loops currently.")