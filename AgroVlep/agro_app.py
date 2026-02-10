import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from sentinelhub import SHConfig, SentinelHubRequest, DataCollection, MimeType, BBox, CRS
import numpy as np
import matplotlib.pyplot as plt
import datetime
import json
import os

# --- 1. ΡΥΘΜΙΣΕΙΣ ΣΕΛΙΔΑΣ ---
st.set_page_config(page_title="AgroVlep", page_icon="🌾", layout="wide")

# --- 2. ΦΟΡΤΩΣΗ ΜΥΣΤΙΚΩΝ ΚΩΔΙΚΩΝ (ΑΣΦΑΛΕΙΑ) ---
# Αντί να τους γράφουμε εδώ, τους τραβάμε από το κρυφό σύστημα του Streamlit
try:
    CLIENT_ID = st.secrets["CLIENT_ID"]
    CLIENT_SECRET = st.secrets["CLIENT_SECRET"]
    
    # Φόρτωση χρηστών από τα secrets
    # Η δομή στα secrets πρέπει να είναι: [users] demo = "1234" κλπ.
    USERS = st.secrets["users"]
except FileNotFoundError:
    st.error("⚠️ ΠΡΟΣΟΧΗ: Δεν βρέθηκαν οι κωδικοί (Secrets). Ρύθμισέ τους στο Streamlit Cloud.")
    st.stop()

# Ρύθμιση SentinelHub
config = SHConfig()
config.sh_client_id = CLIENT_ID
config.sh_client_secret = CLIENT_SECRET

# --- 3. ΒΑΣΗ ΔΕΔΟΜΕΝΩΝ (Τοπική) ---
DB_FILE = 'agro_db.json'

def load_db():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)

# --- 4. LOGIN SYSTEM ---
def check_password():
    if st.session_state.get('logged_in', False): return True
    
    st.markdown("<h1 style='text-align: center;'>🔐 AgroVlep Είσοδος</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Το σύγχρονο εργαλείο του Έλληνα Αγρότη</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        username = st.text_input("Όνομα Χρήστη")
        password = st.text_input("Κωδικός", type="password")
        
        if st.button("Είσοδος", use_container_width=True):
            if username in USERS and USERS[username] == password:
                st.session_state['logged_in'] = True
                st.session_state['user'] = username
                st.rerun()
            else:
                st.error("❌ Λάθος στοιχεία")
    return False

if not check_password(): st.stop()

# --- 5. ΚΥΡΙΩΣ ΕΦΑΡΜΟΓΗ ---
db = load_db()
user = st.session_state['user']
if user not in db: db[user] = []

# -- SIDEBAR --
with st.sidebar:
    st.title(f"👤 {user}")
    st.write("---")
    st.subheader("📂 Τα Χωράφια μου")
    
    if db[user]:
        for idx, field in enumerate(db[user]):
            if st.button(f"📍 {field['name']}", key=f"btn_{idx}"):
                st.session_state['selected_field'] = field
                st.rerun()
    else:
        st.info("Δεν έχεις αποθηκεύσει χωράφια ακόμα.")
        
    st.write("---")
    if st.button("🚪 Έξοδος"):
        st.session_state['logged_in'] = False
        st.rerun()

# -- MAP & ANALYSIS --
st.subheader("🛰️ AgroVlep: Έλεγχος Καλλιέργειας")

start_loc = [40.642, 22.540]
zoom = 14
if 'selected_field' in st.session_state:
    saved = st.session_state['selected_field']
    lats = [c[1] for c in saved['coords']]
    lons = [c[0] for c in saved['coords']]
    start_loc = [sum(lats)/len(lats), sum(lons)/len(lons)]
    zoom = 16
    st.success(f"Επιλέξατε: **{saved['name']}**")

# Χάρτης Google Hybrid (Ο καλύτερος για αγρότες)
m = folium.Map(location=start_loc, zoom_start=zoom)
folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satellite Hybrid').add_to(m)

draw = Draw(export=False, draw_options={"polyline":False,"circle":False,"marker":False,"circlemarker":False,"rectangle":True,"polygon":True})
draw.add_to(m)

# Εμφάνιση αποθηκευμένου χωραφιού
if 'selected_field' in st.session_state:
    folium.Polygon(
        locations=[[c[1], c[0]] for c in st.session_state['selected_field']['coords']],
        color="#ff0000", fill=True, fill_opacity=0.2, popup=st.session_state['selected_field']['name']
    ).add_to(m)

output = st_folium(m, width=1000, height=500)

# -- LOGIC --
if output["all_drawings"]:
    new_drawing = output["all_drawings"][-1]
    coords = new_drawing['geometry']['coordinates'][0]
    
    col1, col2 = st.columns([3, 1])
    with col1: new_name = st.text_input("📝 Όνομα Χωραφιού (π.χ. Βαμβάκι Ποτάμι)")
    with col2:
        st.write("")
        st.write("")
        if st.button("💾 Αποθήκευση"):
            if new_name:
                db[user].append({"name": new_name, "coords": coords, "date": str(datetime.date.today())})
                save_db(db)
                st.success(f"Αποθηκεύτηκε: {new_name}")
                st.rerun()

    # -- SATELLITE ANALYSIS --
    if st.button("🚀 ΑΝΑΛΥΣΗ ΤΩΡΑ (LIVE)"):
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        bbox = BBox(bbox=[min(lons), min(lats), max(lons), max(lats)], crs=CRS.WGS84)
        
        try:
            with st.spinner("Γίνεται σύνδεση με τον δορυφόρο..."):
                # Ζητάμε τελευταίο μήνα
                today = datetime.date.today()
                past = today - datetime.timedelta(days=20)
                
                request = SentinelHubRequest(
                    evalscript="return [B04, B08];",
                    input_data=[SentinelHubRequest.input_data(data_collection=DataCollection.SENTINEL2_L2A, time_interval=(past.isoformat(), today.isoformat()))],
                    responses=[SentinelHubRequest.output_response('default', MimeType.PNG)],
                    bbox=bbox, config=config
                )
                data = request.get_data()[0]
                
                # NDVI Calculation
                red = data[:, :, 0]
                nir = data[:, :, 1]
                ndvi = np.divide((nir - red), (nir + red), where=(nir + red) != 0)
                avg = np.mean(ndvi) * 100
                
                st.divider()
                c1, c2 = st.columns([2, 1])
                
                with c1:
                    fig, ax = plt.subplots(figsize=(10,6))
                    im = ax.imshow(ndvi, cmap='RdYlGn', vmin=0.1, vmax=0.8, interpolation='bicubic') # Bicubic για να μην έχει πίξελ
                    plt.colorbar(im, label='Υγεία Φυτού')
                    ax.axis('off')
                    st.pyplot(fig)
                
                with c2:
                    st.metric("Μέση Υγεία", f"{avg:.1f}%")
                    if avg > 60:
                        st.success("✅ ΚΑΤΑΣΤΑΣΗ: ΑΡΙΣΤΗ")
                        st.write("Το φυτό είναι εύρωστο.")
                    elif avg > 35:
                        st.warning("⚠️ ΚΑΤΑΣΤΑΣΗ: ΜΕΤΡΙΑ")
                        st.write("Ελέγξτε για νερό ή λιπάσματα.")
                    else:
                        st.error("🚨 ΚΑΤΑΣΤΑΣΗ: ΚΑΚΗ")
                        st.write("Πιθανή ασθένεια ή ξηρασία.")

        except Exception as e:
            st.error(f"Δεν βρέθηκε καθαρή εικόνα τις τελευταίες 20 μέρες. (Error: {e})")
