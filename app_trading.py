import os
import time
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# ==========================================
# 1. CONFIGURATION INITIALE & HEURE GMT
# ==========================================
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

st.set_page_config(page_title="Terminal Macro Institutionnel XAU/USD", page_icon="⚡", layout="wide")

def get_current_gmt_time():
    """Renvoie l'heure actuelle au format HH:MM en GMT"""
    utc_now = datetime.now(timezone.utc)
    return utc_now.strftime('%H:%M'), utc_now.strftime('%Y-%m-%d')

# ==========================================
# 2. MULTIMÉDIA & TÉLÉGRAM (ALERTES)
# ==========================================
def play_alert_sound(sound_url="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"):
    components.html(f'<audio autoplay style="display:none;"><source src="{sound_url}" type="audio/mp3"></audio>', height=0)

def speak_text(text_to_speak):
    safe_text = text_to_speak.replace("'", "\\'")
    js_code = f"""
        <script>
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                var utterance = new SpeechSynthesisUtterance('{safe_text}');
                utterance.lang = 'fr-FR';
                utterance.rate = 1.1;
                window.speechSynthesis.speak(utterance);
            }}
        </script>
    """
    components.html(js_code, height=0)

def send_telegram_alert(title_msg, message_body):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    message = f"<b>⚡ {title_msg} ⚡</b>\n\n{message_body}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# ==========================================
# 3. MOTEUR D'ANALYSE & SYNERGIES
# ==========================================
def get_raw_score(event_name, actual, forecast, prev):
    fc = forecast if forecast is not None else (prev if prev is not None else actual)
    if actual is None or fc is None:
        return 0.0, ""

    delta = actual - fc
    score = 0.0
    detail = ""
    name = event_name.lower()

    if "nonfarm payrolls" in name:
        if delta < -30: score, detail = 0.40, f"🟢 NFP faible ({actual}) -> Gold ⬆"
        elif delta > 30: score, detail = -0.40, f"🔴 NFP fort ({actual}) -> Gold ⬇"
    elif "unemployment rate" in name:
        if delta >= 0.1: score, detail = 0.35, f"🟢 Chômage en hausse ({actual}%) -> Gold ⬆"
        elif delta <= -0.1: score, detail = -0.35, f"🔴 Chômage en baisse ({actual}%) -> Gold ⬇"
    elif "cpi" in name or "consumer price" in name:
        if delta < -0.1: score, detail = 0.45, f"🟢 CPI en baisse ({actual}) : Désinflation -> Gold ⬆"
        elif delta > 0.1: score, detail = -0.45, f"🔴 CPI en hausse ({actual}) : Inflation -> Gold ⬇"
    elif "retail sales" in name:
        if delta < -0.2: score, detail = 0.30, f"🟢 Ventes au détail faibles ({actual}) -> Gold ⬆"
        elif delta > 0.2: score, detail = -0.30, f"🔴 Ventes au détail fortes ({actual}) -> Gold ⬇"
    else:
        if delta < 0: score, detail = 0.15, f"🟡 {event_name} sous les attentes"
        elif delta > 0: score, detail = -0.15, f"🔴 {event_name} au-dessus des attentes"
        else: score, detail = 0.0, f"⚪ {event_name} conforme"
            
    return score, detail

# ==========================================
# 4. RÉCUPÉRATION FRED API (ROBUSTE & TIMEOUT ÉTENDU)
# ==========================================
@st.cache_data(ttl=600)
def fetch_macro_data():
    FRED_API_KEY = os.getenv("FRED_API_KEY")
    if not FRED_API_KEY:
        st.error("❌ Clé API FRED manquante dans les Secrets Streamlit !")
        return []
    
    series_map = {
        "CPIAUCSL": {"name": "Consumer Price Index (CPI)", "gmt_time": "12:30"},
        "UNRATE": {"name": "Unemployment Rate", "gmt_time": "12:30"},
        "PAYEMS": {"name": "Nonfarm Payrolls", "gmt_time": "12:30"},
        "RRSFS": {"name": "Retail Sales", "gmt_time": "12:30"}
    }
    
    events_list = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for series_id, info in series_map.items():
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=2"
        try:
            # Timeout augmenté à 15 secondes pour éviter les coupures réseau du cloud
            res = requests.get(url, headers=headers, timeout=15)
            
            if res.status_code == 200:
                data = res.json().get('observations', [])
                if len(data) >= 2:
                    actual = float(data[0]['value'])
                    prev = float(data[1]['value'])
                    date_val = data[0]['date']
                    
                    events_list.append({
                        "event": info["name"],
                        "country": "US",
                        "time_gmt": info["gmt_time"],
                        "date_releve": date_val,
                        "actual": actual,
                        "estimate": prev,
                        "prev": prev,
                        "status": "PUBLIÉ"
                    })
            else:
                st.warning(f"⚠️ FRED a répondu avec le code {res.status_code} pour {info['name']}")
        except requests.exceptions.Timeout:
            st.error(f"⏳ Délai dépassé pour l'indicateur {info['name']} (Le serveur FRED met trop de temps à répondre).")
        except Exception as e:
            st.error(f"❌ Erreur réseau sur {info['name']} : {e}")
            
    return events_list

# ==========================================
# 5. INTERFACE UTILISATEUR & LOGIQUE GMT
# ==========================================
current_gmt, current_date = get_current_gmt_time()
st.title(f"⚡ Terminal Macro — XAU/USD (Heure GMT : {current_gmt})")

st.sidebar.header("⚙️ Paramètres")
if st.sidebar.button("🔊 Activer l'Audio"):
    play_alert_sound()
    speak_text("Système initialisé en heure GMT.")
    st.sidebar.success("Prêt !")

events = fetch_macro_data()

if not events:
    st.warning("⏳ En attente des flux macroéconomiques...")
else:
    # Séparation : Annonces du jour / Récentes vs À venir
    st.subheader("📅 1. Agenda des Annonces & Indicateurs Clés (Heure GMT)")
    
    upcoming_events = [ev for ev in events if ev.get('status') == 'AVENIR']
    published_events = [ev for ev in events if ev.get('status') == 'PUBLIÉ']
    
    # Affichage des annonces à venir
    with st.expander("📌 Annonces à venir / Suivi du jour", expanded=True):
        if not upcoming_events:
            st.info("Aucune annonce programmée dans les minutes exactes à venir. Les derniers chiffres officiels de référence sont affichés ci-dessous.")
        for ev in events:
            st.markdown(f"• **{ev['event']}** | Heure prévue : `{ev['time_gmt']} GMT` | Référence précédente : `{ev['prev']}`")

    st.divider()
    st.subheader("🎯 2. Interprétation Post-Publication & Biais Or (XAU/USD)")

    net_score = 0.0
    all_details = []
    event_names = []
    
    for ev in events:
        event_names.append(ev['event'])
        score, detail = get_raw_score(ev['event'], ev['actual'], ev['estimate'], ev['prev'])
        net_score += score
        if detail:
            all_details.append(detail)
            
    if net_score >= 0.25: bias = "HAUSSIER (BULLISH)"
    elif net_score <= -0.25: bias = "BAISSIER (BEARISH)"
    else: bias = "NEUTRE / MIXTE"
        
    confidence = min(abs(net_score) * 100, 100)

    # Automatisation Telegram propre
    if 'last_gmt_alert' not in st.session_state:
        st.session_state['last_gmt_alert'] = None

    alert_key = f"{current_date}_{net_score}"
    if st.session_state['last_gmt_alert'] != alert_key:
        msg_body = f"<b>🕒 Heure GMT :</b> {current_gmt}\n<b>🎯 Biais :</b> {bias} (Force: {round(confidence)}/100)\n\n<b>Analyse :</b>\n" + "\n".join([f"• {d}" for d in all_details])
        send_telegram_alert("SYNTHÈSE MACRO XAU/USD", msg_body)
        play_alert_sound()
        speak_text(f"Nouvelle analyse macro. Biais {bias} sur l'Or.")
        st.session_state['last_gmt_alert'] = alert_key

    st.success(f"### Biais Consolidé : {bias} (Force: {round(confidence)}/100)")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Détails de l'algorithme :**")
        for d in all_details:
            st.write(f"- {d}")
    with col2:
        st.write("**Valeurs Officielles Enregistrées :**")
        for ev in events:
            st.write(f"- {ev['event']} : Actuel `{ev['actual']}` (Précédent `{ev['prev']}`)")
