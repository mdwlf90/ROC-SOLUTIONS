import streamlit as st
import gspread
import re
from datetime import datetime
import google.generativeai as genai
from oauth2client.service_account import ServiceAccountCredentials
import os

# --- 1. DRAW THE UI FIRST ---
st.set_page_config(page_title="Recruiting Portal", page_icon="📝")
st.title("🚀 Job Application Portal")

# --- CONFIGURATION (SECURE) ---
# We use st.secrets so we don't expose keys in public code
GEMINI_KEY = st.secrets["GEMINI_KEY"]
SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]

# Helper to handle the Google Credentials from Secrets
def get_creds():
    # Streamlit secrets converts the TOML entry into a dictionary automatically
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

# --- CONNECT TO GOOGLE ---
@st.cache_resource
def connect_services():
    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash-lite') 
        
        creds = get_creds() 
        client = gspread.authorize(creds)
        sh = client.open_by_key(SPREADSHEET_ID).sheet1
        return model, sh, None
    except Exception as e:
        return None, None, str(e)

# Run the connection
with st.spinner("Connecting to database..."):
    model, sh, error_msg = connect_services()

if error_msg:
    st.error(f"System Offline: {error_msg}")
    st.stop() # Stop the app here if connection failed

st.success("System Online ✅")

# --- 4. CONSTANTS & LISTS ---
EXP_OPTIONS = ["Housekeeping", "Houseman", "Dishwasher", "Prep Cook", "Line cook", "Server", "Pool attendant / Host", "Other"]
SHIFT_OPTIONS = ["AM", "PM", "Flexible", "Overnight"]
LANG_OPTIONS = ["English", "Spanish", "Bilingual"]
TRANS_OPTIONS = ["Own transportation", "Public Transportation"]

QUESTIONS_EN = [
    ("Let's start. What is your **First Name**?", "First Name", None),
    ("Thanks. And what is your **Last Name**?", "Last Name", None),
    ("What is your **Phone Number**?", "Phone", None),
    ("Select your **Previous Experience** (You can pick multiple, e.g., 1, 3):\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(EXP_OPTIONS)]), "Experience", EXP_OPTIONS),
    ("What position do you want to **Apply For**? (Select numbers)\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(EXP_OPTIONS)]), "Applied Position", EXP_OPTIONS),
    ("What **Shift** are you available to work?\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(SHIFT_OPTIONS)]), "Shift", SHIFT_OPTIONS),
    ("What **Language** do you speak?\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(LANG_OPTIONS)]), "Language", LANG_OPTIONS),
    ("What's your **Transportation** method?\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(TRANS_OPTIONS)]), "Transport", TRANS_OPTIONS),
    ("When can you **Start**?", "Start Date", None)
]

QUESTIONS_ES = [
    ("Empecemos. ¿Cuál es tu **Primer Nombre**?", "First Name", None),
    ("Gracias. ¿Y tu **Apellido**?", "Last Name", None),
    ("¿Cuál es tu número de **Teléfono**?", "Phone", None),
    ("Selecciona tu **Experiencia Previa** (Puedes elegir varias, ej. 1, 3):\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(EXP_OPTIONS)]), "Experience", EXP_OPTIONS),
    ("¿A qué posición quieres **Aplicar**? (Selecciona números)\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(EXP_OPTIONS)]), "Applied Position", EXP_OPTIONS),
    ("¿Qué **Turno** puedes trabajar?\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(SHIFT_OPTIONS)]), "Shift", SHIFT_OPTIONS),
    ("¿Qué **Idioma** hablas?\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(LANG_OPTIONS)]), "Language", LANG_OPTIONS),
    ("¿Cuál es tu método de **Transporte**?\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(TRANS_OPTIONS)]), "Transport", TRANS_OPTIONS),
    ("¿Cuándo puedes **Comenzar**?", "Start Date", None)
]

# --- 5. SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! / ¡Hola!\n\nPlease type **English** or **Español** to start."}]
if "step" not in st.session_state:
    st.session_state.step = -1
if "data" not in st.session_state:
    st.session_state.data = []
if "lang" not in st.session_state:
    st.session_state.lang = None

# --- 6. CHAT INTERFACE ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_input := st.chat_input("Type your answer here..."):
    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    response_text = ""
    
    # PHASE A: LANGUAGE SELECTION
    if st.session_state.step == -1:
        txt = user_input.lower()
        if "span" in txt or "espa" in txt:
            st.session_state.lang = 'es'
            st.session_state.step = 0
            response_text = QUESTIONS_ES[0][0]
        elif "eng" in txt or "ingl" in txt:
            st.session_state.lang = 'en'
            st.session_state.step = 0
            response_text = QUESTIONS_EN[0][0]
        else:
            response_text = "Please type **English** or **Español**."
    
    # PHASE B: QUESTIONS
    else:
        lang = st.session_state.lang
        step = st.session_state.step
        q_list = QUESTIONS_ES if lang == 'es' else QUESTIONS_EN
        current_q = q_list[step]
        options_available = current_q[2]
        
        valid_answer = True
        answer_to_save = user_input
        
        # VALIDATOR
        if options_available:
            found_numbers = re.findall(r'\d+', user_input)
            valid_selections = []
            if found_numbers:
                for num in found_numbers:
                    idx = int(num)
                    if 1 <= idx <= len(options_available):
                        valid_selections.append(options_available[idx - 1])
                
                if valid_selections:
                    answer_to_save = ", ".join(list(dict.fromkeys(valid_selections)))
                else:
                    valid_answer = False
            else:
                valid_answer = False
            
            if not valid_answer:
                response_text = "⚠️ Invalid selection. Please type the numbers (e.g., 1, 3)."
        
        if valid_answer:
            st.session_state.data.append(answer_to_save)
            next_step = step + 1
            if next_step < len(q_list):
                st.session_state.step = next_step
                response_text = q_list[next_step][0]
            else:
                try:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row = [timestamp] + st.session_state.data
                    sh.append_row(row)
                    response_text = "✅ Application Received! You can close this window."
                    st.session_state.step = -1
                    st.session_state.data = []
                    st.session_state.lang = None
                except Exception as e:
                    response_text = f"Error saving data: {e}"

    with st.chat_message("assistant"):
        st.markdown(response_text)
    st.session_state.messages.append({"role": "assistant", "content": response_text})
