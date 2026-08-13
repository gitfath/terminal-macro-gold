import os
import time
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone
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
    # Suppression du paramètre 'key' qui causait le TypeError
    components.html(f'<audio autoplay style="display:none;"><source src="{sound_url}" type="audio/mp3"></audio>', height=0)

def speak_text(text_to_speak):
    safe_text = text_to_speak.replace("'", "\\'").replace("\n", " ")
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
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

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

    if "nonfarm payrolls" in name or "nfp" in name:
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
# 4. RÉCUPÉRATION FRED API
# ==========================================
@st.cache_data(ttl=600)
def fetch_macro_data():
    FRED_API_KEY = os.getenv("FRED_API_KEY")
    if not FRED_API_KEY:
        st.error("❌ Clé API FRED manquante dans les Secrets Streamlit !")
        return []

    series_map = {
        "DFII10": {"name": "Taux Réels 10Y (TIPS)", "gmt_time": "20:00 GMT"},
        "CPIAUCSL": {"name": "CPI (Consumer Price Index)", "gmt_time": "12:30 GMT"},
        "CPILFESL": {"name": "Core CPI (Inflation)", "gmt_time": "12:30 GMT"},
        "PCEPI": {"name": "PCE Inflation Index", "gmt_time": "12:30 GMT"},
        "PAYEMS": {"name": "Nonfarm Payrolls (NFP)", "gmt_time": "12:30 GMT"},
        "UNRATE": {"name": "Unemployment Rate", "gmt_time": "12:30 GMT"},
        "ICSA": {"name": "Initial Jobless Claims", "gmt_time": "12:30 GMT"},
        "RSAFS": {"name": "Retail Sales", "gmt_time": "12:30 GMT"},
        "PPIACO": {"name": "PPI (Producer Price Index)", "gmt_time": "12:30 GMT"},
        "FEDFUNDS": {"name": "Fed Funds Rate", "gmt_time": "18:00 GMT"},
        "GDP": {"name": "GDP Growth Rate", "gmt_time": "12:30 GMT"}
    }

    events_list = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for series_id, info in series_map.items():
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=2"
        try:
            res = requests.get(url, headers=headers, timeout=15)

            if res.status_code == 200:
                data = res.json().get('observations', [])
                if len(data) >= 2 and data[0]['value'] != "." and data[1]['value'] != ".":
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
        except Exception:
            pass

    return events_list

# ==========================================
# 5. EXECUTION, ENVOI AUTOMATIQUE & INTERFACE
# ==========================================
gmt_time, gmt_date = get_current_gmt_time()

st.title("⚡ Terminal Macro Institutionnel XAU/USD")
st.caption(f"Horloge UTC/GMT : **{gmt_time}** | Date : **{gmt_date}**")

events = fetch_macro_data()

if events:
    total_score = 0.0
    details = []

    for ev in events:
        score, detail = get_raw_score(ev["event"], ev["actual"], ev["estimate"], ev["prev"])
        total_score += score
        if detail:
            details.append(detail)

    final_score = max(min(total_score, 1.0), -1.0)

    # BANNIÈRE DE PRÉDICTION
    st.subheader("💡 Direction & Impulsion Immédiate XAU/USD")
    if final_score >= 0.25:
        bias_text = "🟢 BIAIS BULLISH (HAUSSIER)"
        st.success(f"### {bias_text} | Score Macro : {round(final_score, 2)}")
    elif final_score <= -0.25:
        bias_text = "🔴 BIAIS BEARISH (BAISSIER)"
        st.error(f"### {bias_text} | Score Macro : {round(final_score, 2)}")
    else:
        bias_text = "🟧 BIAIS NEUTRE / CONSOLIDATION"
        st.warning(f"### {bias_text} | Score Macro : {round(final_score, 2)}")

    st.markdown("#### 📜 Synthèse des Moteurs de Décision :")
    for d in details:
        st.markdown(f"- {d}")

    st.divider()

    # --- ENVOI AUTOMATIQUE AU BOT TELEGRAM ---
    # Détection de changement de signal ou premier chargement de la journée
    last_sent_key = f"sent_{round(final_score, 2)}_{gmt_date}"
    if "last_signal_sent" not in st.session_state:
        st.session_state["last_signal_sent"] = None

    if st.session_state["last_signal_sent"] != last_sent_key:
        auto_msg = f"<b>{bias_text}</b>\n<b>Score Macro : {round(final_score, 2)}</b>\n\n"
        auto_msg += "<b>📊 Synthèse des Moteurs :</b>\n" + "\n".join([f"• {d}" for d in details])
        
        if send_telegram_alert(f"Mise à Jour Macro - {gmt_time} GMT", auto_msg):
            st.session_state["last_signal_sent"] = last_sent_key
            play_alert_sound()
            st.toast("📲 Synthèse envoyée automatiquement sur Telegram !", icon="⚡")

    # TABLEAU DES ANNONCES
    st.subheader("📅 Tableau Macro Stratégique (Annonces Importantes)")
    df_events = pd.DataFrame(events)
    st.dataframe(
        df_events[["event", "time_gmt", "date_releve", "actual", "estimate", "prev", "status"]],
        use_container_width=True
    )

    # BOUTON DE REDIFFUSION MANUELLE
    if st.button("🔄 Renvoyer Manuellement sur Telegram"):
        msg = f"<b>{bias_text}</b>\n<b>Score Macro : {round(final_score, 2)}</b>\n\n"
        msg += "<b>📊 Synthèse :</b>\n" + "\n".join([f"• {d}" for d in details])
        if send_telegram_alert(f"FLASH MACRO - {gmt_time} GMT", msg):
            st.success("Alerte réexpédiée avec succès !")
            play_alert_sound()
        else:
            st.error("Échec de l'envoi. Vérifiez les identifiants Telegram.")
