import streamlit as st
import requests
from supabase import create_client, Client

# --- PAGE CONFIGURATION (Optimized for Mobile viewports) ---
st.set_page_config(
    page_title="LDN & Kent Commuter",
    page_icon="🚇",
    layout="centered", # Forces vertical mobile stack layout, ignoring wide monitors
    initial_sidebar_state="collapsed" # Save screen real estate on mobile devices
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

# Simple mock mobile session user context
USER_ID = "jonathan_commuter"

# --- API CORE UTILITIES ---
@st.cache_data(ttl=60) # Cache live status for 60 seconds to optimize mobile battery/data
def get_tfl_line_statuses(modes="tube,overground,elizabeth-line,dlr"):
    """Fetches real-time line statuses from the TfL Unified API."""
    url = f"https://api.tfl.gov.uk/Line/Mode/{modes}/Status?app_key={TFL_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error fetching TfL live data: {e}")
    return []

# --- DATABASE PERSISTENCE UTILITIES ---
def get_saved_routes(user_id):
    res = supabase.table("saved_routes").select("*").eq("user_id", user_id).execute()
    return [row['line_name'] for row in res.data]

def add_saved_route(user_id, line_name):
    supabase.table("saved_routes").insert({"user_id": user_id, "line_name": line_name}).execute()

def remove_saved_route(user_id, line_name):
    supabase.table("saved_routes").delete().eq("user_id", user_id).eq("line_name", line_name).execute()


# --- MOBILE APPLICATION UI LAYOUT ---

st.title("🚇 LDN & Kent Transit")
st.caption("Live operational status and saved routes.")

# Use segmented controls for clean single-finger mobile navigation
menu = st.segmented_control(
    "Navigate", 
    options=["Watchlist", "Live Network Status", "Manage Routes"], 
    default="Watchlist",
    label_visibility="collapsed"
)

# Fetch data once at top of application execution
raw_line_data = get_tfl_line_statuses()

# Map human-readable line statuses
line_status_map = {}
for line in raw_line_data:
    name = line['name']
    status_desc = line['lineStatuses'][0]['statusSeverityDescription']
    line_status_map[name] = status_desc

# --- VIEW 1: WATCHLIST ---
if menu == "Watchlist":
    st.subheader("Your Commute Alerts")
    saved_user_lines = get_saved_routes(USER_ID)
    
    if not saved_user_lines:
        st.info("You don't have any saved routes yet. Go to 'Manage Routes' to tailor your mobile dashboard feeds.")
    else:
        disruption_counter = 0
        for line in saved_user_lines:
            status = line_status_map.get(line, "Unknown Status")
            
            if status == "Good Service":
                st.success(f"**{line} Line**: Good Service")
            else:
                st.warning(f"⚠️ **{line} Line**: {status}")
                disruption_counter += 1
                
        if disruption_counter == 0:
            st.toast("All your routes look clear! 🎉")

# --- VIEW 2: LIVE NETWORK STATUS ---
elif menu == "Live Network Status":
    st.subheader("All System Services")
    
    search_query = st.text_input("🔍 Filter Lines (e.g., Central, Victoria)", "").lower()
    
    for line_name, status in line_status_map.items():
        if search_query and search_query not in line_name.lower():
            continue
            
        with st.container(border=True):
            col1, col2 = st.columns([0.6, 0.4])
            with col1:
                st.markdown(f"**{line_name}**")
            with col2:
                if status == "Good Service":
                    st.caption("✅ Good Service")
                else:
                    st.caption(f"🚨 {status}")

# --- VIEW 3: MANAGE ROUTES ---
elif menu == "Manage Routes":
    st.subheader("Edit Watchlist Preferences")
    
    current_saved = get_saved_routes(USER_ID)
    available_lines = sorted(list(line_status_map.keys()))
    
    selected_lines = st.multiselect(
        "Select routes to track on your home view:",
        options=available_lines,
        default=current_saved
    )
    
    if st.button("Save Changes", use_container_width=True):
        for line in current_saved:
            if line not in selected_lines:
                remove_saved_route(USER_ID, line)
        for line in selected_lines:
            if line not in current_saved:
                add_saved_route(USER_ID, line)
                
        st.success("Watchlist configuration successfully synced to Supabase!")
        st.rerun()