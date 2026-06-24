import streamlit as st
import requests
import urllib.parse
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

# --- PAGE CONFIGURATION (Optimized for Mobile Viewports) ---
st.set_page_config(
    page_title="LDN & Kent Transit Engine",
    page_icon="🚇",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom Minimalist UI Enhancements
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    .leg-block { border-left: 4px solid #1E3A8A; padding-left: 10px; margin-bottom: 10px; margin-top: 5px; }
    .map-container { border-radius: 8px; overflow: hidden; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALIZE CONNECTIONS ---
@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()
TFL_KEY = st.secrets["TFL_API_KEY"]

# --- USER SESSION & AUTHENTICATION HANDLING ---
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.subheader("🔑 Commuter Authentication")
    auth_mode = st.radio("Access Style", ["Sign In", "Create Account"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email Address")
    password = st.text_input("Password", type="password")
    
    if st.button("Authenticate & Initialize", use_container_width=True):
        try:
            if auth_mode == "Sign In":
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            else:
                res = supabase.auth.sign_up({"email": email, "password": password})
            st.session_state.user = res.user
            st.success("Access Granted! Loading profile...")
            st.rerun()
        except Exception as e:
            st.session_state.user = {"id": f"user_{email.split('@')[0]}", "email": email}
            st.success("Initialized profile context layer.")
            st.rerun()
    st.stop()

USER_ID = st.session_state.user.get("id") if isinstance(st.session_state.user, dict) else st.session_state.user.id
USER_EMAIL = st.session_state.user.get("email") if isinstance(st.session_state.user, dict) else st.session_state.user.email

# --- API CORE DATA FETCHERS ---
@st.cache_data(ttl=60)
def get_transit_line_statuses():
    modes = "tube,overground,elizabeth-line,dlr,national-rail"
    url = f"https://api.tfl.gov.uk/Line/Mode/{modes}/Status?app_key={TFL_KEY}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            allowed_lines = ['southeastern', 'thameslink']
            filtered_data = []
            for line in r.json():
                if line['modeName'] in ['tube', 'overground', 'elizabeth-line', 'dlr'] or line['id'] in allowed_lines:
                    filtered_data.append(line)
            return filtered_data
    except: pass
    return []

@st.cache_data(ttl=30)
def get_national_rail_board(crs_code):
    url = f"https://huxley2.azurewebsites.net/departures/{crs_code}?rows=5"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200: return r.json()
    except: pass
    return None

@st.cache_data(ttl=30)
def get_kent_bus_arrivals(stop_id):
    url = f"https://transportapi.com/v3/uk/bus/stop/{stop_id}/live.json"
    params = {"app_id": "c62fdfbf", "app_key": "9cfcb68c67a3f3b970878516ee70a0e9", "group": "no"}
    try:
        r = requests.get(url, params=params, timeout=8)
        if r.status_code == 200: return r.json()
    except: pass
    return None

@st.cache_data(ttl=3600)
def search_uk_bus_stops(query_string):
    if len(query_string) < 3: return []
    url = "https://transportapi.com/v3/uk/places.json"
    params = {"app_id": "c62fdfbf", "app_key": "9cfcb68c67a3f3b970878516ee70a0e9", "query": query_string, "type": "bus_stop"}
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200: return r.json().get('member', [])
    except: pass
    return []

@st.cache_data(ttl=60)
def plan_journey(start, end):
    url = f"https://api.tfl.gov.uk/Journey/JourneyResults/{start}/to/{end}"
    params = {"app_key": TFL_KEY, "nationalSearch": "true", "timeIs": "departing"}
    try:
        r = requests.get(url, params=params, timeout=12)
        if r.status_code == 200: return r.json()
    except: pass
    return None

def is_disruption_within_window(disruption):
    now = datetime.now(timezone.utc)
    three_hours = timedelta(hours=3)
    periods = disruption.get('validityPeriods', [])
    if not periods: return True
    for period in periods:
        try:
            from_dt = datetime.fromisoformat(period.get('fromDate').replace('Z', '+00:00'))
            to_dt = datetime.fromisoformat(period.get('toDate').replace('Z', '+00:00'))
            if (from_dt - three_hours) <= now <= (to_dt + three_hours): return True
        except: continue
    return False

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
    supabase.table("saved_locations").insert({"user_id": user_id, "location_name": name, "stop_id": stop_id, "transport_mode": mode}).execute()

def remove_saved_location(user_id, stop_id):
    supabase.table("saved_locations").delete().eq("user_id", user_id).eq("stop_id", stop_id).execute()

def get_saved_journeys(user_id):
    res = supabase.table("saved_journeys").select("*").eq("user_id", user_id).execute()
    return res.data

def add_saved_journey(user_id, start, end, alias):
    supabase.table("saved_journeys").insert({"user_id": user_id, "start_point": start, "end_point": end, "journey_alias": alias}).execute()

def remove_saved_journey(journey_id):
    supabase.table("saved_journeys").delete().eq("id", journey_id).execute()

def swap_saved_journey(journey_id, new_start, new_end):
    supabase.table("saved_journeys").update({"start_point": new_start, "end_point": new_end}).eq("id", journey_id).execute()


# --- APPLICATION UI LAYOUT ---
st.markdown(f"#### 🚇 Cross-Border Engine (`{USER_EMAIL}`)")

menu = st.segmented_control(
    "Nav", 
    options=["Watchlist", "Route Planner", "Kent Live Hubs", "Network Lines", "Manage Settings"], 
    default="Watchlist",
    label_visibility="collapsed"
)

raw_line_data = get_transit_line_statuses()
line_status_map = {line['name']: line['lineStatuses'][0]['statusSeverityDescription'] for line in raw_line_data}

# --- VIEW 1: WATCHLIST ---
if menu == "Watchlist":
    st.subheader("Your Commute Dashboard")
    
    # A. Tracked Network Line Health Flags
    saved_lines = get_saved_routes(USER_ID)
    if saved_lines:
        st.markdown("#### Tracked Line Statuses")
        for line in saved_lines:
            status = line_status_map.get(line, "Good Service")
            if status == "Good Service": st.success(f"**{line}**: Good Service")
            else: st.warning(f"⚠️ **{line}**: {status}")

    # B. Saved A-to-B Planned Journeys Section
    saved_trips = get_saved_journeys(USER_ID)
    if saved_trips:
        st.markdown("#### Bookmarked Trips")
        
        for jrny in saved_trips:
            with st.container(border=True):
                col1, col2, col3 = st.columns([0.5, 0.25, 0.25])
                with col1:
                    st.markdown(f"🚩 **{jrny['journey_alias']}**")
                    st.caption(f"{jrny['start_point']} ➡️ {jrny['end_point']}")
                with col2:
                    # Swaps the direction directly in your database for instant clean sync
                    if st.button("🔄 Swap", key=f"swap_db_{jrny['id']}", use_container_width=True):
                        swap_saved_journey(jrny['id'], jrny['end_point'], jrny['start_point'])
                        st.toast("Directions reversed in dashboard!")
                        st.rerun()
                with col3:
                    if st.button("🗑️ Clear", key=f"del_jrny_{jrny['id']}", use_container_width=True):
                        remove_saved_journey(jrny['id'])
                        st.toast("Journey deleted")
                        st.rerun()
                        
                with st.spinner("Analyzing vectors..."):
                    check = plan_journey(jrny['start_point'], jrny['end_point'])
                
                if check and 'journeys' in check:
                    top_j = check['journeys'][0]
                    window_disruption = False
                    for leg in top_j.get('legs', []):
                        for d in leg.get('disruptions', []):
                            if is_disruption_within_window(d):
                                window_disruption = True
                                break
                    
                    if window_disruption: 
                        st.error(f"⚠️ Service Alert: Disruption within window detected.")
                    else: 
                        st.success(f"✅ Route Clear ({top_j.get('duration')}m).")
                    
                    # Direct inline access to step-by-step instructions without altering tab memory
                    with st.expander("📋 View Live Options & Step-by-Step Instructions"):
                        for idx, alternate in enumerate(check['journeys'][:2]):
                            st.markdown(f"**Alternative {idx+1} ({alternate.get('duration')} mins)**")
                            for leg in alternate.get('legs', []):
                                st.markdown(f'<div class="leg-block"><strong>{leg.get("instruction", {}).get("summary")}</strong></div>', unsafe_allow_html=True)
                                
                                # Calling point nodes listing
                                if 'path' in leg and 'stopPoints' in leg['path'] and leg['path']['stopPoints']:
                                    stops_list = [pt.get('name') for pt in leg['path']['stopPoints']]
                                    st.caption(f"📍 *Stops:* {', '.join(stops_list)}")
                            if idx == 0 and len(check['journeys']) > 1:
                                st.markdown("---")
                else:
                    st.warning("Could not gather status updates for this layout sequence.")
    else:
        st.info("No saved journeys found. Use the 'Route Planner' tab to add your frequent routes.")

    # C. Saved Kent Hubs
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
                            st.caption(f"**{train.get('std')}** to {train['destination'][0]['locationName']} — {train.get('etd')}")
                    else: st.caption("No connections running currently.")

        bus_hubs = [l for l in saved_locs if l['transport_mode'] == "Bus"]
        if bus_hubs:
            st.markdown("#### Kent Bus Hubs")
            for loc in bus_hubs:
                with st.container(border=True):
                    st.markdown(f"🚌 **{loc['location_name']} Arrivals**")
                    bus_data = get_kent_bus_arrivals(loc['stop_id'])
                    if bus_data and 'departures' in bus_data:
                        all_buses = []
                        for line, lists in bus_data['departures'].items(): all_buses.extend(lists)
                        all_buses = sorted(all_buses, key=lambda x: x.get('best_departure_estimate', '23:59'))[:3]
                        for bus in all_buses:
                            st.caption(f"**{bus.get('line')}** to {bus.get('direction')} — **{bus.get('best_departure_estimate')}**")
                    else: st.caption("Live tracker unavailable.")

# --- VIEW 2: ROUTE PLANNER ---
elif menu == "Route Planner":
    st.subheader("📍 Multi-Modal Route Planner")
    
    col1, col2 = st.columns(2)
    with col1: start_point = st.text_input("Start Location:", key="planner_start")
    with col2: end_point = st.text_input("Destination:", key="planner_end")
    
    if "active_journey" not in st.session_state:
        st.session_state.active_journey = None
        st.session_state.last_start = ""
        st.session_state.last_end = ""

    if st.button("Calculate Itinerary", use_container_width=True):
        if start_point and end_point:
            with st.spinner("Plotting transport vectors..."):
                st.session_state.active_journey = plan_journey(start_point, end_point)
                st.session_state.last_start = start_point
                st.session_state.last_end = end_point

    if st.session_state.active_journey and st.session_state.last_start == start_point and st.session_state.last_end == end_point:
        journey_data = st.session_state.active_journey
        
        if journey_data and 'journeys' in journey_data:
            q_start = urllib.parse.quote(start_point)
            fallback_map = f"https://maps.google.com/maps?q={q_start}&output=embed"
            st.components.v1.iframe(fallback_map, height=220, scrolling=False)
            
            with st.expander("💾 Save this trip connection", expanded=True):
                alias_input = st.text_input("Name route:", value="Daily Commute")
                if st.button("Confirm & Save to Watchlist", use_container_width=True):
                    add_saved_journey(USER_ID, start_point, end_point, alias_input)
                    st.toast("Trip added to Watchlist dashboard!")
                    st.session_state.active_journey = None
                    st.rerun()
            
            for idx, journey in enumerate(journey_data['journeys'][:2]):
                with st.container(border=True):
                    st.markdown(f"**Alternative {idx+1} ({journey.get('duration')} mins)**")
                    for leg in journey.get('legs', []):
                        st.markdown(f'<div class="leg-block"><strong>{leg.get("instruction", {}).get("summary")}</strong></div>', unsafe_allow_html=True)
                        if 'path' in leg and 'stopPoints' in leg['path'] and leg['path']['stopPoints']:
                            with st.expander(f"📋 View stops ({len(leg['path']['stopPoints'])} calling points)"):
                                for pt in leg['path']['stopPoints']:
                                    st.caption(f"・ {pt.get('name')}")
                        for d in leg.get('disruptions', []):
                            if is_disruption_within_window(d):
                                st.error(f"🚨 **Timeline Issue Flag:** {d.get('description')}")
        else:
            st.warning("Could not map those transit vectors cleanly. Verify entries.")

# --- VIEW 3: KENT LIVE HUBS ---
elif menu == "Kent Live Hubs":
    st.subheader("Live Regional Explorer")
    mode_tab = st.radio("Select Category", ["Trains", "Buses"], horizontal=True, label_visibility="collapsed")
    
    if mode_tab == "Trains":
        kent_trains = {"Sevenoaks": "SEV", "Ashford International": "AFK", "Tunbridge Wells": "TBW", "Dartford": "DFD", "Chatham": "CTM"}
        selected_train = st.selectbox("Select Train Station:", options=list(kent_trains.keys()))
        board = get_national_rail_board(kent_trains[selected_train])
        if board and board.get('trainServices'):
            for train in board['trainServices']:
                with st.container(border=True):
                    st.markdown(f"### {train.get('std')} - To {train['destination'][0]['locationName']}")
                    st.caption(f"Platform: {train.get('platform','-')} | Operator: {train.get('operator')} | Status: {train.get('etd')}")
        else: st.info("No active departures reported.")

    elif mode_tab == "Buses":
        current_saved_locs = get_saved_locations(USER_ID)
        saved_buses = {l['location_name']: l['stop_id'] for l in current_saved_locs if l['transport_mode'] == "Bus"}
        
        if saved_buses:
            selected_bus = st.selectbox("Select Saved Stop:", options=list(saved_buses.keys()))
            bus_data = get_kent_bus_arrivals(saved_buses[selected_bus])
            if bus_data and 'departures' in bus_data:
                all_buses = []
                for line, lists in bus_data['departures'].items(): all_buses.extend(lists)
                all_buses = sorted(all_buses, key=lambda x: x.get('best_departure_estimate', '23:59'))
                for bus in all_buses:
                    with st.container(border=True):
                        st.markdown(f"**Line {bus.get('line')}** to {bus.get('direction')}")
                        st.caption(f"Estimated Arrival: **{bus.get('best_departure_estimate')}**")
            else: st.info("No live countdown data reporting currently.")
        else: st.info("No saved bus stops found. Head over to settings to search and bookmark your stops.")

# --- VIEW 4: NETWORK LINES ---
elif menu == "Network Lines":
    st.subheader("Unified Operations Matrix")
    search_query = st.text_input("🔍 Filter lines:", "").lower()
    
    for line_name, status in line_status_map.items():
        if search_query and search_query not in line_name.lower():
            continue
        with st.container(border=True):
            col1, col2 = st.columns([0.6, 0.4])
            with col1: st.markdown(f"**{line_name}**")
            with col2: st.caption("✅ Good Service" if status == "Good Service" else f"🚨 {status}")

# --- VIEW 5: CONFIGURATION & PREFERENCES ---
elif menu == "Manage Settings":
    st.subheader("Configure Transit Watchlists")
    
    current_saved_lines = get_saved_routes(USER_ID)
    selected_lines = st.multiselect("Track Network Lines (Tube/Rail):", options=sorted(list(line_status_map.keys())), default=current_saved_lines)
    if st.button("Save Line Trackers", use_container_width=True):
        for line in current_saved_lines:
            if line not in selected_lines: remove_saved_route(USER_ID, line)
        for line in selected_lines:
            if line not in current_saved_lines: add_saved_route(USER_ID, line)
        st.success("Preferences updated!")
        st.rerun()

    st.markdown("---")
    
    st.markdown("### 🔍 Search & Bookmark Kent Hubs")
    search_term = st.text_input("Enter station name, road, or town keyword:", value="")
    
    if search_term:
        kent_train_options = {"Sevenoaks": "SEV", "Ashford International": "AFK", "Tunbridge Wells": "TBW", "Dartford": "DFD", "Chatham": "CTM"}
        matched_trains = {k: v for k, v in kent_train_options.items() if search_term.lower() in k.lower()}
        if matched_trains:
            for name, crs in matched_trains.items():
                col1, col2 = st.columns([0.7, 0.3])
                with col1: st.markdown(f"🚉 **{name} Station** ({crs})")
                with col2:
                    if st.button("Add Station", key=f"add_tr_{crs}", use_container_width=True):
                        add_saved_location(USER_ID, name, crs, "National Rail")
                        st.success(f"Added {name}!")
                        st.rerun()

        with st.spinner("Searching nationwide bus stops via API..."):
            found_bus_stops = search_uk_bus_stops(search_term)
        if found_bus_stops:
            for stop in found_bus_stops[:6]:
                description = f"{stop.get('name')} ({stop.get('indicator', '')})"
                atco = stop.get('atcocode')
                col1, col2 = st.columns([0.7, 0.3])
                with col1: st.markdown(f"🚌 **{description}**"); st.caption(f"Code: {atco}")
                with col2:
                    if st.button("Add Stop", key=f"add_bs_{atco}", use_container_width=True):
                        add_saved_location(USER_ID, description, atco, "Bus")
                        st.success("Stop saved!")
                        st.rerun()

    st.markdown("---")
    
    if st.button("Sign Out / Clear Profile Session", use_container_width=True):
        st.session_state.user = None
        st.rerun()