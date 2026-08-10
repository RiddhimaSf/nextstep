from dotenv import load_dotenv
load_dotenv()

import os
import uuid
import streamlit as st
import anthropic
import googlemaps
from datetime import datetime
import math
import urllib.parse

from agent.scope_check import is_in_nyc_scope, scope_check_message
from agent.escalation import is_crisis
from agent.runtime import AgentRuntime, persist_trace
from agent.rag_tool import search_kb_tool, GROUNDING_PROMPT
from tools.slack_client import post_escalation_to_slack

USE_RAG = True

st.set_page_config(page_title="NextStep", page_icon="👣", layout="centered")

# ── API Keys ──────────────────────────────────────────────────────────────────

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_KEY", "")

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #FDF6F0; color: #2C1810; }
#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
.block-container { max-width: 480px !important; padding: 24px 20px !important; margin: 0 auto; }
.nextstep-logo { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.nextstep-logo-text { font-size: 28px; font-weight: 700; color: #2C1810; letter-spacing: -0.5px; }
.nextstep-logo-text span { color: #C17B5A; }
.nextstep-tagline { font-size: 15px; color: #6B4C3B; line-height: 1.5; margin-bottom: 24px; }
.ns-divider { height: 2px; background: linear-gradient(to right, #C17B5A, #E8A87C, transparent); border: none; margin: 20px 0; }
.ns-section-title { font-size: 22px; font-weight: 700; color: #2C1810; line-height: 1.3; margin-bottom: 8px; }
.ns-section-subtitle { font-size: 15px; color: #6B4C3B; line-height: 1.6; margin-bottom: 20px; }
.ns-card { background: #FFFFFF; border-radius: 16px; padding: 18px 20px; margin-bottom: 12px; box-shadow: 0 2px 12px rgba(193, 123, 90, 0.1); border-left: 4px solid #C17B5A; }
.ns-card-title { font-size: 16px; font-weight: 600; color: #2C1810; margin-bottom: 6px; }
.ns-card-body { font-size: 14px; color: #6B4C3B; line-height: 1.6; }
.ns-card-body a { color: #C17B5A; text-decoration: none; font-weight: 500; }
.ns-alert-red { background: #FFF0EE; border-left: 4px solid #D94F3D; border-radius: 16px; padding: 18px 20px; margin-bottom: 12px; }
.ns-alert-green { background: #F0F7F4; border-left: 4px solid #7B9E87; border-radius: 16px; padding: 18px 20px; margin-bottom: 12px; }
.ns-alert-amber { background: #FFF9EE; border-left: 4px solid #E8C547; border-radius: 16px; padding: 18px 20px; margin-bottom: 12px; }
.stButton > button { background: #C17B5A !important; color: white !important; border: none !important; border-radius: 12px !important; padding: 14px 24px !important; font-size: 16px !important; font-weight: 600 !important; font-family: 'Inter', sans-serif !important; width: 100% !important; min-height: 52px !important; cursor: pointer !important; transition: background 0.2s !important; margin-bottom: 8px !important; }
.stButton > button:hover { background: #A66345 !important; }
[data-testid="baseButton-secondary"] > button { background: #F5EDE8 !important; color: #C17B5A !important; }
.stRadio > div { gap: 8px !important; }
.stRadio > div > label { background: #FFFFFF; border: 1.5px solid #E8D5CC; border-radius: 12px; padding: 14px 16px !important; font-size: 15px !important; color: #2C1810 !important; cursor: pointer; transition: border-color 0.2s; width: 100%; display: block; }
.stRadio > div > label:hover { border-color: #C17B5A; }
.stSelectbox > div > div { background: #FFFFFF; border: 1.5px solid #E8D5CC; border-radius: 12px; font-size: 15px; }
.stTextInput > div > div > input { background: #FFFFFF; border: 1.5px solid #E8D5CC; border-radius: 12px; padding: 14px 16px; font-size: 15px; font-family: 'Inter', sans-serif; }
.stTextInput > div > div > input:focus { border-color: #C17B5A; box-shadow: 0 0 0 3px rgba(193, 123, 90, 0.15); }
.stTextArea > div > div > textarea { background: #FFFFFF; border: 1.5px solid #E8D5CC; border-radius: 12px; padding: 14px 16px; font-size: 15px; font-family: 'Inter', sans-serif; }
.stMetric { background: #FFFFFF; border-radius: 12px; padding: 12px; box-shadow: 0 2px 8px rgba(193, 123, 90, 0.08); text-align: center; }
.ns-footer { background: #F5EDE8; border-radius: 16px; padding: 16px 20px; margin-top: 24px; text-align: center; }
.ns-footer-hotline { font-size: 17px; font-weight: 700; color: #C17B5A; margin-bottom: 4px; }
.ns-footer-sub { font-size: 13px; color: #6B4C3B; }
.ns-disclaimer { font-size: 11px; color: #9B7B6B; text-align: center; margin-top: 16px; line-height: 1.5; }
.ns-progress { display: flex; gap: 6px; margin-bottom: 24px; }
.ns-progress-dot { height: 4px; border-radius: 2px; flex: 1; background: #E8D5CC; }
.ns-progress-dot.active { background: #C17B5A; }
.ns-hospital-card { background: #FFFFFF; border-radius: 16px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 12px rgba(193, 123, 90, 0.1); }
.ns-hospital-name { font-size: 17px; font-weight: 700; color: #2C1810; margin-bottom: 6px; }
.ns-hospital-detail { font-size: 14px; color: #6B4C3B; margin-bottom: 4px; }
.ns-directions-btn { display: inline-block; background: #C17B5A; color: white !important; text-decoration: none !important; padding: 10px 16px; border-radius: 10px; font-size: 14px; font-weight: 600; margin-top: 10px; }
.ns-back { font-size: 14px; color: #C17B5A; cursor: pointer; margin-bottom: 16px; display: inline-block; }
.ns-quick-exit { position: fixed; top: 12px; right: 12px; z-index: 9999; background: #D94F3D; color: white !important; text-decoration: none !important; padding: 10px 16px; border-radius: 10px; font-size: 14px; font-weight: 700; font-family: 'Inter', sans-serif; box-shadow: 0 2px 8px rgba(217, 79, 61, 0.3); }
.ns-quick-exit:hover { background: #B83A2A; }
</style>
""", unsafe_allow_html=True)

# ── Hospital Data ─────────────────────────────────────────────────────────────

HOSPITALS = [
    {"name": "Bellevue Hospital Center", "address": "462 First Avenue, New York, NY 10016", "phone": "(212) 562-4132", "borough": "Manhattan", "lat": 40.7388717, "lng": -73.9752894},
    {"name": "Harlem Hospital Center", "address": "506 Lenox Avenue, New York, NY 10037", "phone": "(212) 939-1000", "borough": "Manhattan", "lat": 40.8141451, "lng": -73.9404473},
    {"name": "Metropolitan Hospital Center", "address": "1901 First Avenue, New York, NY 10029", "phone": "(212) 423-8993", "borough": "Manhattan", "lat": 40.7852328, "lng": -73.9450290},
    {"name": "Mount Sinai Hospital", "address": "One Gustave L Levy Place, New York, NY 10029", "phone": "(212) 241-7005", "borough": "Manhattan", "lat": 40.7888899, "lng": -73.9540398},
    {"name": "Mount Sinai Morningside", "address": "1111 Amsterdam Avenue, New York, NY 10025", "phone": "(212) 523-4295", "borough": "Manhattan", "lat": 40.8054067, "lng": -73.9613307},
    {"name": "NewYork-Presbyterian Columbia", "address": "622 West 168th Street, New York, NY 10032", "phone": "(212) 305-2500", "borough": "Manhattan", "lat": 40.8413257, "lng": -73.9407077},
    {"name": "NewYork-Presbyterian Weill Cornell", "address": "525 East 68th Street, New York, NY 10021", "phone": "(212) 746-5454", "borough": "Manhattan", "lat": 40.7648658, "lng": -73.9539836},
    {"name": "Northwell Greenwich Village Hospital", "address": "30 Seventh Avenue, New York, NY 10011", "phone": "(516) 465-8018", "borough": "Manhattan", "lat": 40.7378021, "lng": -74.0009090},
    {"name": "Kings County Hospital Center", "address": "451 Clarkson Avenue, Brooklyn, NY 11203", "phone": "(718) 245-3901", "borough": "Brooklyn", "lat": 40.6568816, "lng": -73.9447075},
    {"name": "NewYork-Presbyterian Brooklyn Methodist", "address": "506 Sixth Street, Brooklyn, NY 11215", "phone": "(718) 780-3101", "borough": "Brooklyn", "lat": 40.6678820, "lng": -73.9791462},
    {"name": "NYU Langone Hospital Brooklyn", "address": "150 55th Street, Brooklyn, NY 11220", "phone": "(718) 630-7300", "borough": "Brooklyn", "lat": 40.6468695, "lng": -74.0211488},
    {"name": "South Brooklyn Health", "address": "2601 Ocean Parkway, Brooklyn, NY 11235", "phone": "(718) 616-3000", "borough": "Brooklyn", "lat": 40.5855850, "lng": -73.9648285},
    {"name": "Woodhull Medical Center", "address": "760 Broadway, Brooklyn, NY 11206", "phone": "(718) 963-8101", "borough": "Brooklyn", "lat": 40.6996243, "lng": -73.9430489},
    {"name": "Elmhurst Hospital Center", "address": "79-01 Broadway, Elmhurst, NY 11373", "phone": "(718) 334-4000", "borough": "Queens", "lat": 40.7450814, "lng": -73.8857797},
    {"name": "NewYork-Presbyterian Queens", "address": "56-45 Main Street, Flushing, NY 11355", "phone": "(718) 670-2000", "borough": "Queens", "lat": 40.7468043, "lng": -73.8249338},
    {"name": "Queens Hospital Center", "address": "82-68 164th Street, Jamaica, NY 11432", "phone": "(718) 883-2350", "borough": "Queens", "lat": 40.7181228, "lng": -73.8047780},
    {"name": "Jacobi Medical Center", "address": "1400 Pelham Parkway, Bronx, NY 10461", "phone": "(718) 918-5000", "borough": "Bronx", "lat": 40.8554628, "lng": -73.8458118},
    {"name": "Lincoln Medical Center", "address": "234 East 149th Street, Bronx, NY 10451", "phone": "(718) 579-5700", "borough": "Bronx", "lat": 40.8168282, "lng": -73.9235492},
    {"name": "North Central Bronx Hospital", "address": "3424 Kossuth Avenue, Bronx, NY 10467", "phone": "(718) 519-3500", "borough": "Bronx", "lat": 40.8804138, "lng": -73.8810488},
    {"name": "Richmond University Medical Center", "address": "355 Bard Avenue, Staten Island, NY 10310", "phone": "(718) 818-1234", "borough": "Staten Island", "lat": 40.6356031, "lng": -74.1055743},
]

SAFE_PLACES = {
    "Manhattan": [
        {"name": "NYC Family Justice Center – Manhattan (Safe Horizon advocates on-site)", "address": "80 Centre St, Manhattan", "phone": "212-602-2800", "type": "Family Justice Center", "hours": "Mon–Fri 9am–5pm"},
        {"name": "Bellevue Hospital ER", "address": "462 First Avenue, Manhattan", "phone": "(212) 562-4132", "type": "Hospital", "hours": "24/7"},
        {"name": "NYPD 17th Precinct", "address": "167 E 51st St, Manhattan", "phone": "212-826-3211", "type": "Police", "hours": "24/7"},
    ],
    "Brooklyn": [
        {"name": "NYC Family Justice Center – Brooklyn (Safe Horizon advocates on-site)", "address": "350 Jay St, 14th Floor, Brooklyn", "phone": "718-250-5113", "type": "Family Justice Center", "hours": "Mon–Fri 9am–5pm"},
        {"name": "Kings County Hospital ER", "address": "451 Clarkson Ave, Brooklyn", "phone": "(718) 245-3901", "type": "Hospital", "hours": "24/7"},
        {"name": "NYPD 84th Precinct", "address": "301 Gold St, Brooklyn", "phone": "718-875-6811", "type": "Police", "hours": "24/7"},
    ],
    "Queens": [
        {"name": "NYC Family Justice Center – Queens (Safe Horizon advocates on-site)", "address": "126-02 82nd Ave, Kew Gardens, Queens", "phone": "718-575-4545", "type": "Family Justice Center", "hours": "Mon–Fri 9am–5pm"},
        {"name": "Elmhurst Hospital ER", "address": "79-01 Broadway, Queens", "phone": "(718) 334-4000", "type": "Hospital", "hours": "24/7"},
        {"name": "NYPD 109th Precinct", "address": "37-05 Union St, Queens", "phone": "718-321-2250", "type": "Police", "hours": "24/7"},
    ],
    "Bronx": [
        {"name": "NYC Family Justice Center – Bronx (Safe Horizon advocates on-site)", "address": "198 E 161st St, 2nd Floor, Bronx", "phone": "718-508-1220", "type": "Family Justice Center", "hours": "Mon–Fri 9am–5pm"},
        {"name": "Lincoln Medical Center ER", "address": "234 East 149th Street, Bronx", "phone": "(718) 579-5700", "type": "Hospital", "hours": "24/7"},
        {"name": "NYPD 40th Precinct", "address": "257 Alexander Ave, Bronx", "phone": "718-402-2270", "type": "Police", "hours": "24/7"},
    ],
    "Staten Island": [
        {"name": "NYC Family Justice Center – Staten Island (Safe Horizon advocates on-site)", "address": "126 Stuyvesant Pl, Staten Island", "phone": "718-697-4300", "type": "Family Justice Center", "hours": "Mon–Fri 9am–5pm"},
        {"name": "Richmond University Medical Center ER", "address": "355 Bard Avenue, Staten Island", "phone": "(718) 818-1234", "type": "Hospital", "hours": "24/7"},
        {"name": "NYPD 120th Precinct", "address": "78 Richmond Terrace, Staten Island", "phone": "718-876-8500", "type": "Police", "hours": "24/7"},
    ],
}

# ── Helpers ───────────────────────────────────────────────────────────────────
# is_crisis() is imported from agent.escalation — exactly one source of
# truth for crisis detection, no local duplicate list (Day 5 fix).

def show_crisis_resources():
    card("You don't have to face this alone — please reach out right now",
         "If you are in immediate danger, call <b>911</b>.", "red")
    card("📞 988 Suicide &amp; Crisis Lifeline",
         "Call or text <b>988</b>, anytime. Free, confidential, 24/7. You can talk to someone right now.", "red")
    card("📞 Safe Horizon 24/7 Hotline: 1-800-621-4673",
         "Trained advocates are available any time, day or night.", "default")
    card("📞 RAINN: 1-800-656-4673",
         "Free, confidential support, 24/7.", "default")

def haversine(lat1, lng1, lat2, lng2):
    R = 3958.8
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def get_travel_times(user_lat, user_lng, hospital):
    try:
        gmaps = googlemaps.Client(key=GOOGLE_MAPS_KEY)
        origin = f"{user_lat},{user_lng}"
        destination = f"{hospital['lat']},{hospital['lng']}"
        walking = gmaps.directions(origin, destination, mode="walking")
        driving = gmaps.directions(origin, destination, mode="driving")
        transit = gmaps.directions(origin, destination, mode="transit", departure_time=datetime.now())
        walk_time = walking[0]['legs'][0]['duration']['text'] if walking else "N/A"
        drive_time = driving[0]['legs'][0]['duration']['text'] if driving else "N/A"
        transit_time = transit[0]['legs'][0]['duration']['text'] if transit else "N/A"
        return walk_time, drive_time, transit_time
    except:
        return "N/A", "N/A", "N/A"

def get_directions_url(user_lat, user_lng, hospital):
    return f"https://www.google.com/maps/dir/{user_lat},{user_lng}/{hospital['lat']},{hospital['lng']}"

def card(title, body, style="default"):
    css_class = "ns-card"
    if style == "red":
        css_class = "ns-alert-red"
    elif style == "green":
        css_class = "ns-alert-green"
    elif style == "amber":
        css_class = "ns-alert-amber"
    st.markdown(f"""
    <div class='{css_class}'>
        <div class='ns-card-title'>{title}</div>
        <div class='ns-card-body'>{body}</div>
    </div>
    """, unsafe_allow_html=True)

def progress(step_num, total=7):
    dots = ""
    for i in range(1, total + 1):
        active = "active" if i <= step_num else ""
        dots += f"<div class='ns-progress-dot {active}'></div>"
    st.markdown(f"<div class='ns-progress'>{dots}</div>", unsafe_allow_html=True)

def logo():
    st.markdown("""
    <div class='nextstep-logo'>
        <span style='font-size:32px'>👣</span>
        <span class='nextstep-logo-text'>Next<span>Step</span></span>
    </div>
    <div class='nextstep-tagline'>You don't have to figure this out alone.<br>Just follow along — one step at a time.</div>
    <div class='ns-divider'></div>
    """, unsafe_allow_html=True)

def quick_exit():
    st.markdown(
        "<a href='https://www.google.com' target='_top' class='ns-quick-exit'>✕ Quick exit</a>",
        unsafe_allow_html=True
    )

def footer():
    st.markdown("""
    <div class='ns-footer'>
        <div class='ns-footer-hotline'>RAINN: 1-800-656-4673</div>
        <div class='ns-footer-sub'>Free, confidential, 24/7 support</div>
    </div>
    <div class='ns-disclaimer'>
        NextStep is an independent resource and is not affiliated with RAINN, Safe Horizon,
        NYC 988, or any other organisation listed. All organisations are referenced for
        informational purposes only. This tool does not constitute legal, medical, or
        professional advice. If you are in immediate danger please call 911.
    </div>
    """, unsafe_allow_html=True)

def back_button(go_to_step):
    if st.button("← Back", key=f"back_{go_to_step}"):
        st.session_state.step = go_to_step
        st.rerun()

# ── Session state ─────────────────────────────────────────────────────────────

if "step" not in st.session_state:
    st.session_state.step = 1
if "borough" not in st.session_state:
    st.session_state.borough = None
if "user_lat" not in st.session_state:
    st.session_state.user_lat = None
if "user_lng" not in st.session_state:
    st.session_state.user_lng = None

# ── RENDER ────────────────────────────────────────────────────────────────────

quick_exit()
logo()

# ── SCREEN 1 — Location ───────────────────────────────────────────────────────

if st.session_state.step == 1:
    st.markdown("<div class='ns-section-title'>Where are you right now?</div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-subtitle'>This helps us find the closest certified hospital near you. You can type your neighbourhood, street, or zip code.</div>", unsafe_allow_html=True)

    location_input = st.text_input("", placeholder="e.g. Upper West Side, 10025, or Astoria Queens", label_visibility="collapsed")

    if location_input:
        try:
            gmaps = googlemaps.Client(key=GOOGLE_MAPS_KEY)
            geocode_result = gmaps.geocode(location_input + ", New York City")
            if geocode_result:
                if not is_in_nyc_scope(geocode_result[0]):
                    card("Outside NYC", scope_check_message(), "amber")
                else:
                    loc = geocode_result[0]['geometry']['location']
                    formatted = geocode_result[0]['formatted_address']
                    st.session_state.user_lat = loc['lat']
                    st.session_state.user_lng = loc['lng']
                    st.session_state.borough = "detected"
                    card("📍 Location found", formatted, "green")
                    if st.button("Continue"):
                        st.session_state.step = 2
                        st.rerun()
            else:
                card("Could not find that location", "Try a different neighbourhood or use the borough option below.", "amber")
        except Exception:
            pass

    st.markdown("<div style='margin-top:16px;font-size:14px;color:#6B4C3B;'>Or select your borough:</div>", unsafe_allow_html=True)
    borough = st.selectbox("", ["Select...", "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"], label_visibility="collapsed")
    if borough != "Select..." and not location_input:
        if st.button("Continue with borough"):
            st.session_state.borough = borough
            st.session_state.step = 2
            st.rerun()

# ── SCREEN 2 — Safety check ───────────────────────────────────────────────────

elif st.session_state.step == 2:
    progress(2)
    st.markdown("<div class='ns-section-title'>Are you in a safe place right now?</div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-subtitle'>Your safety is the most important thing in this moment.</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, I am safe"):
            st.session_state.step = 4
            st.rerun()
    with col2:
        if st.button("No / Not sure"):
            st.session_state.step = 3
            st.rerun()

    back_button(1)

# ── SCREEN 3 — Not safe ───────────────────────────────────────────────────────

elif st.session_state.step == 3:
    progress(3)
    card("If you are in immediate danger", "Call 911 now", "red")
    st.markdown("<div class='ns-section-title'>What's making you feel unsafe?</div>", unsafe_allow_html=True)

    situation = st.radio("", [
        "Select...",
        "The person who did this is still here or nearby",
        "I'm inside but scared to go out alone",
        "I'm outside and don't feel safe",
        "I'm not sure"
    ], label_visibility="collapsed")

    if situation == "The person who did this is still here or nearby":
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        card("Call 911 right now", "Tell them your location. They will stay on the phone with you until help arrives.", "red")
        card("While you wait", "Lock yourself in a room if you can. Get to a window where others can see you. Stay on the line with 911.", "default")
        card("📞 NYC Safe Horizon: 1-800-621-4673", "They can stay on the phone with you while you wait for help. Free and confidential.", "default")

    elif situation == "I'm inside but scared to go out alone":
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        card("You don't have to go anywhere right now", "If it isn't safe to leave, you can get help exactly where you are. Trained people can help you figure out how to stay safe, or leave safely when you're ready — for free. Some people call them advocates.", "green")
        card("If you can't speak out loud safely — text or chat", "Text <b>844-997-2121</b> (24/7, no call needed).<br>Safe Horizon: call or chat at <b>1-800-621-4673</b> (24/7).", "default")
        card("To talk with an advocate in person, when you're ready", "<b>Daytime (Mon–Fri, 8am–8pm):</b> Safe Horizon has an advocate in every NYPD police station. You do not need to file a police report to talk to them.<br><br><b>Nights &amp; weekends:</b> The Crime Victims Treatment Center has advocates at their hospitals overnight and on weekends.", "default")
        card("If you are in immediate danger, call 911", "You can say: \"I need help, I don't feel safe.\"", "red")

    elif situation == "I'm outside and don't feel safe":
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        card("Go into the nearest open place", "Any pharmacy, deli, or subway station with staff. Just get inside somewhere with other people.", "amber")

        user_lat = st.session_state.user_lat
        user_lng = st.session_state.user_lng

        if user_lat and user_lng:
            try:
                gmaps = googlemaps.Client(key=GOOGLE_MAPS_KEY)
                pharmacy = gmaps.places_nearby(location=(user_lat, user_lng), radius=500, open_now=True, type="pharmacy")
                police = gmaps.places_nearby(location=(user_lat, user_lng), radius=1000, open_now=True, type="police")

                all_places = []
                for place in pharmacy.get('results', [])[:2]:
                    loc = place['geometry']['location']
                    dist = haversine(user_lat, user_lng, loc['lat'], loc['lng'])
                    all_places.append({"name": place['name'], "address": place.get('vicinity', ''), "type": "Pharmacy", "lat": loc['lat'], "lng": loc['lng'], "dist": dist})
                for place in police.get('results', [])[:1]:
                    loc = place['geometry']['location']
                    dist = haversine(user_lat, user_lng, loc['lat'], loc['lng'])
                    all_places.append({"name": place['name'], "address": place.get('vicinity', ''), "type": "Police Precinct", "lat": loc['lat'], "lng": loc['lng'], "dist": dist})

                all_places = sorted(all_places, key=lambda x: x['dist'])

                for place in all_places[:3]:
                    dist_text = f"{place['dist']:.1f} miles away"
                    directions_url = get_directions_url(user_lat, user_lng, place)
                    st.markdown(f"""
                    <div class='ns-hospital-card'>
                        <div class='ns-hospital-name'>{place['name']}</div>
                        <div class='ns-hospital-detail'>📍 {place['address']}</div>
                        <div class='ns-hospital-detail'>{dist_text}</div>
                        <a href='{directions_url}' target='_blank' class='ns-directions-btn'>Get walking directions</a>
                    </div>
                    """, unsafe_allow_html=True)
            except:
                card("Nearest safe places", "Go into any open pharmacy, deli, or subway station you can see nearby.", "default")
        else:
            borough = st.session_state.borough
            if borough and borough in SAFE_PLACES:
                for place in SAFE_PLACES[borough]:
                    st.markdown(f"""
                    <div class='ns-hospital-card'>
                        <div class='ns-hospital-name'>{place['name']}</div>
                        <div class='ns-hospital-detail'>📍 {place['address']}</div>
                        <div class='ns-hospital-detail'>📞 {place['phone']}</div>
                        <div class='ns-hospital-detail'>🕒 {place['hours']}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                card("Nearest safe places", "Go into any open pharmacy, deli, or subway station you can see nearby.", "default")

        card("Once you are inside", "Tell a staff member you need help. Ask them to call 911 or stay with you while you call. You do not have to explain everything.", "default")
        card("📞 Safe Horizon: 1-800-621-4673", "They can stay on the phone with you.", "default")

    elif situation == "I'm not sure":
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        card("That's okay", "You are safe enough to keep reading. Take a breath. You are here and that matters. When you are ready, keep going and we will guide you through your next steps.", "green")
        card("📞 RAINN: 1-800-656-4673", "If you want to talk to someone right now. Free, confidential, 24/7.", "default")

    if situation != "Select...":
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        if st.button("I am now safe — continue"):
            st.session_state.step = 4
            st.rerun()

    back_button(2)

# ── SCREEN 4 — Perpetrator nearby ────────────────────────────────────────────

elif st.session_state.step == 4:
    progress(4)
    card("What you experienced was not your fault", "Nothing you did or did not do caused this. You are believed.", "green")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-title'>Is the person who did this still nearby?</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, nearby"):
            st.session_state.step = "call_police"
            st.rerun()
    with col2:
        if st.button("No, they are gone"):
            st.session_state.step = 5
            st.rerun()

    back_button(2)

# ── SCREEN 4b — Call police ───────────────────────────────────────────────────

elif st.session_state.step == "call_police":
    progress(4)
    card("Call 911 now", "Tell them your location. You do not need to have all the details ready.", "red")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-subtitle'>You can say: <i>\"I need help. I was sexually assaulted and the person may still be nearby.\"</i></div>", unsafe_allow_html=True)
    card("You still have the right to medical care", "After you call 911 you will be taken to a hospital where a specialist nurse will care for you. The forensic exam is completely free.", "green")
    card("📞 RAINN: 1-800-656-4673", "Free, confidential, 24/7.", "default")

    if st.button("Continue"):
        st.session_state.step = 5
        st.rerun()

    back_button(4)

# ── SCREEN 5 — Hospital guidance ─────────────────────────────────────────────

elif st.session_state.step == 5:
    progress(5)
    st.markdown("<div class='ns-section-title'>Going to the hospital is your best next step</div>", unsafe_allow_html=True)

    card("What a SANE nurse can do for you", "Treat any injuries. Offer emergency contraception if you want it. Test and treat for STIs. Collect forensic evidence. You are in control of every step — you can stop at any time, and you do not have to involve the police.", "default")
    card("Before you go", "Try not to shower, change clothes, or comb your hair. If you already did these things, please still go. Your care matters more than evidence.", "amber")
    card("The exam is completely free", "You will not receive a bill. No insurance needed. Evidence can be collected up to 5 days after the assault.", "green")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-title'>Nearest certified SAFE hospitals</div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-subtitle'>Verified by New York State Department of Health. Trained specialist nurses available 24/7.</div>", unsafe_allow_html=True)

    user_lat = st.session_state.user_lat
    user_lng = st.session_state.user_lng
    borough = st.session_state.borough

    if user_lat and user_lng:
        nearest = sorted(HOSPITALS, key=lambda h: haversine(user_lat, user_lng, h["lat"], h["lng"]))[:3]
    elif borough and borough != "detected":
        nearest = [h for h in HOSPITALS if h["borough"] == borough][:3]
    else:
        nearest = HOSPITALS[:3]

    for h in nearest:
        if user_lat and user_lng:
            with st.spinner(""):
                walk_time, drive_time, transit_time = get_travel_times(user_lat, user_lng, h)
            directions_url = get_directions_url(user_lat, user_lng, h)
            st.markdown(f"""
            <div class='ns-hospital-card'>
                <div class='ns-hospital-name'>🏥 {h['name']}</div>
                <div class='ns-hospital-detail'>📍 {h['address']}</div>
                <div class='ns-hospital-detail'>📞 {h['phone']}</div>
                <div style='display:flex;gap:12px;margin-top:12px;'>
                    <div style='flex:1;background:#FDF6F0;border-radius:8px;padding:8px;text-align:center'>
                        <div style='font-size:11px;color:#6B4C3B'>Walking</div>
                        <div style='font-size:14px;font-weight:600;color:#2C1810'>{walk_time}</div>
                    </div>
                    <div style='flex:1;background:#FDF6F0;border-radius:8px;padding:8px;text-align:center'>
                        <div style='font-size:11px;color:#6B4C3B'>Driving</div>
                        <div style='font-size:14px;font-weight:600;color:#2C1810'>{drive_time}</div>
                    </div>
                    <div style='flex:1;background:#FDF6F0;border-radius:8px;padding:8px;text-align:center'>
                        <div style='font-size:11px;color:#6B4C3B'>Transit</div>
                        <div style='font-size:14px;font-weight:600;color:#2C1810'>{transit_time}</div>
                    </div>
                </div>
                <a href='{directions_url}' target='_blank' class='ns-directions-btn' style='display:block;text-align:center;margin-top:12px;'>Open in Google Maps</a>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='ns-hospital-card'>
                <div class='ns-hospital-name'>🏥 {h['name']}</div>
                <div class='ns-hospital-detail'>📍 {h['address']}</div>
                <div class='ns-hospital-detail'>📞 {h['phone']}</div>
            </div>
            """, unsafe_allow_html=True)

    card("When you arrive", "Say: 'I need to speak with a SANE nurse.' You can bring someone you trust. You do not have to go alone.", "default")

    if st.button("Continue"):
        st.session_state.step = 6
        st.rerun()

    back_button(4)

# ── SCREEN 6 — What to expect ────────────────────────────────────────────────

elif st.session_state.step == 6:
    progress(6)
    st.markdown("<div class='ns-section-title'>What to expect at the hospital</div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-subtitle'>Knowing what's coming can make it feel less overwhelming.</div>", unsafe_allow_html=True)

    card("When you arrive", "You will usually be taken to a private room. A SANE nurse typically explains each step before doing anything, and you can have a support person with you the whole time.", "default")
    card("It usually takes a few hours", "A full exam often takes around 3 to 4 hours — sometimes less, sometimes more. It can help to know that going in, so the length doesn't catch you off guard. You can take breaks.", "amber")
    card("Bring a change of clothes if you can", "The clothes worn during the assault are usually collected as evidence. If you have a spare set, bring them — and if you can't, the hospital can usually provide something.", "default")
    card("Questions you may be asked", "Your general health and medications. What happened, when, and where. You may also be asked about recent consensual sex — only to correctly identify DNA evidence, never to judge you. You can answer as much or as little as you want.", "default")
    card("What the exam may involve", "A physical check for injuries. Photographs, if you consent. DNA swabs. STI testing and prevention. Emergency contraception if you want it. If you think you may have been drugged, a toxicology test (blood or urine) can be done.", "default")
    card("You are in control", "You can decline any part of the exam at any time. Nothing happens without your permission.", "green")
    card("About your evidence kit", "If you choose not to report right now, your kit is stored securely for 20 years under New York law. You can decide to report at any point during that time, and the evidence will still be there.", "default")

    if st.button("Continue"):
        st.session_state.step = 7
        st.rerun()

    back_button(5)

# ── SCREEN 7 — Support ────────────────────────────────────────────────────────

elif st.session_state.step == 7:
    progress(7)
    st.markdown("<div class='ns-section-title'>What do you need help with right now?</div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-subtitle'>Select what feels most important and we will show you exactly what is available.</div>", unsafe_allow_html=True)

    need = st.radio("", [
        "Select...",
        "I need to talk to someone right now",
        "I want to understand my legal options",
        "I need counselling or mental health support",
        "I want to know about financial assistance"
    ], label_visibility="collapsed")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if need == "I need to talk to someone right now":
        card("RAINN: 1-800-656-4673", "Call, chat at <a href='https://rainn.org/get-help' target='_blank'>rainn.org/get-help</a>, or text HOPE to 64673. Trained sexual assault advocates available 24/7. Free and confidential.")
        card("NYC Safe Horizon: 1-800-621-4673", "Free, confidential, 24/7 support in New York City. <a href='https://www.safehorizon.org' target='_blank'>safehorizon.org</a>")
        card("NYC 988", "Call or text <b>988</b> anytime for free mental health support. Available 24/7. <a href='https://nyc988.cityofnewyork.us' target='_blank'>nyc988.cityofnewyork.us</a>")

    elif need == "I want to understand my legal options":
        card("Reporting is your choice", "You do not have to go to the police. It is your choice whether to report — you can still get medical care and have evidence collected without involving law enforcement. There is no deadline to decide.")
        card("Your evidence gives you time", "If a forensic exam was done and you chose not to report, your evidence kit is stored for 20 years under New York law. You can decide to report at any point during that time, and the evidence will still be available.")
        card("If you do want to report", "You can report to the NYPD Special Victims Division at <b>646-610-7273</b>, or call the NYS Police Sexual Assault Hotline at <b>1-844-845-7269</b>. You have the right to have an advocate with you for any of this.")
        card("Protection order", "A protection order legally requires the person to stay away from you. You can apply even without reporting to the police. Safe Horizon can help for free. Call 1-800-621-4673 or visit <a href='https://www.safehorizon.org/get-help/legal-advocacy' target='_blank'>safehorizon.org</a>")
        card("Your right to an advocate", "At every stage of any legal process you have the right to a trained advocate with you. This is free. Call Safe Horizon at 1-800-621-4673 to request one.")

    elif need == "I need counselling or mental health support":
        card("Safe Horizon counselling", "Free individual and group counselling for survivors in New York City. No insurance needed. Call 1-800-621-4673 or visit <a href='https://www.safehorizon.org/get-help/counseling-support-groups' target='_blank'>safehorizon.org</a>")
        card("RAINN local support finder", "Find trauma-informed therapists and support groups near you. <a href='https://centers.rainn.org' target='_blank'>centers.rainn.org</a>")
        card("NYC 988", "Call or text <b>988</b> anytime for free mental health support. Available 24/7. <a href='https://nyc988.cityofnewyork.us' target='_blank'>nyc988.cityofnewyork.us</a>")

    elif need == "I want to know about financial assistance":
        card("The forensic exam is completely free", "Under federal law you cannot be billed for the forensic exam. If you receive a bill, do not pay it — contact Safe Horizon at 1-800-621-4673 and they can help resolve it.", "green")
        card("You may be able to get money back for what this cost you", "New York's Office of Victim Services (OVS) can reimburse crime-related costs like medical bills, counselling, and lost wages. As of a recent change (December 2025), you may not need a police report — a form signed by a medical or mental health provider (the Crime Verification Form) can be used instead for most types of compensation. Start a claim at <a href='https://ovs.ny.gov/victim-compensation' target='_blank'>ovs.ny.gov</a> or call 1-800-247-8035.")
        card("These organisations will do the paperwork for you", "Filing can be complicated — these groups have specialists who handle it so you don't have to:<br><br><b>Crime Victims Treatment Center</b> — will file your OVS claim for you and work to get you the maximum. Call <b>212-523-4728</b>.<br><br><b>Sanctuary for Families</b> — help with compensation alongside legal support. <a href='https://www.sanctuaryforfamilies.org' target='_blank'>sanctuaryforfamilies.org</a>")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-title'>Do you have a question?</div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-subtitle'>Type anything you are unsure about and we will help you find the answer.</div>", unsafe_allow_html=True)

    question = st.text_area("", placeholder="What's on your mind?", label_visibility="collapsed")

    # ── Day 6 real integration ──────────────────────────────────────────
    # RAG path now genuinely runs through AgentRuntime.run() with search_kb
    # registered as a real tool — real orchestration, not two functions
    # called directly. Crisis path deliberately stays deterministic (no
    # LLM call — Day 1 principle) but now gets a real request_id and a
    # real persisted, replayable trace via persist_trace().

    if st.button("Get answer") and question:
        if is_crisis(question):
            request_id = str(uuid.uuid4())
            try:
                slack_result = post_escalation_to_slack(user_id="nextstep_session", reason=question, dry_run=False)
                escalation_ok = slack_result.ok
            except Exception:
                escalation_ok = False

            persist_trace(
                request_id,
                question,
                {
                    "answer": "crisis_resources_shown",
                    "trace": [{"event": "deterministic_crisis_escalation", "slack_ok": escalation_ok}],
                    "request_id": request_id,
                },
            )

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            show_crisis_resources()

        elif USE_RAG:
            qa_agent = AgentRuntime(
                model="claude-sonnet-4-6",
                tools={"search_kb": search_kb_tool},
                system=(
                    "You are a compassionate trauma-informed guide helping a sexual "
                    "assault survivor in New York City.\n\n"
                    "Important principles:\n"
                    "- Lead with belief and validation\n"
                    "- Never pressure them to report to police; reporting is entirely their choice\n"
                    "- Keep language warm, plain, and clear\n"
                    "- Never judge any decision they make\n"
                    "- Answer warmly and concisely. Be human. Be kind.\n\n"
                    + GROUNDING_PROMPT
                ),
                max_turns=4,
                allow_side_effects=False,
            )
            with st.spinner(""):
                result = qa_agent.run(question)

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            card("", result.get("answer", "I wasn't able to complete that — please try again."))

        else:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

            system_prompt = (
                "You are a compassionate trauma-informed guide helping a sexual assault survivor in New York City.\n\n"
                "Important principles:\n"
                "- Lead with belief and validation\n"
                "- Never pressure them to report to police; reporting is entirely their choice\n"
                "- Keep language warm, plain, and clear\n"
                "- Never judge any decision they make\n"
                "- If they ask about costs: the forensic exam is free, no bill will come\n"
                "- You provide information and options only — you are not a substitute for a doctor, "
                "lawyer, or counsellor, and you do not give medical or legal advice\n"
                "- Always close by pointing them to a real person: RAINN at 1-800-656-4673 or "
                "Safe Horizon at 1-800-621-4673\n\n"
                "Answer warmly and concisely. Be human. Be kind."
            )

            with st.spinner(""):
                message = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": question}]
                )
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            card("", message.content[0].text)

    back_button(6)

# ── Footer ────────────────────────────────────────────────────────────────────

footer()