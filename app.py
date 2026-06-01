import datetime
import json
import os
import random
import time

import streamlit as st

try:
    from google import genai
except ImportError:
    genai = None

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    gspread = None
    ServiceAccountCredentials = None

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    firebase_admin = None
    credentials = None
    firestore = None


APP_NAME = "Inequality Battle: ตะลุยโลกอสมการ"
Q_DIR = "questions"
MYSTERY_SPOTS = [3, 11, 19, 27, 35, 43, 51, 59]
TOPICS = {
    "addition": "การแก้อสมการโดยใช้สมบัติการบวกของการไม่เท่ากัน",
    "multiplication": "การแก้อสมการโดยใช้สมบัติการคูณของการไม่เท่ากัน",
    "linear": "การแก้อสมการเชิงเส้นตัวแปรเดียว",
}

st.set_page_config(page_title=APP_NAME, page_icon="📝", layout="wide")


@st.cache_data
def load_questions():
    if not os.path.isdir(Q_DIR):
        st.error(f"ไม่พบโฟลเดอร์ {Q_DIR}")
        return {}
    try:
        topics = {}
        for topic in TOPICS:
            with open(os.path.join(Q_DIR, f"{topic}.json"), "r", encoding="utf-8") as file:
                topics[topic] = json.load(file)
        return {"topics": topics}
    except Exception as error:
        st.error(f"โหลดไฟล์โจทย์ไม่สำเร็จ: {error}")
        return {}


question_db = load_questions()


def get_q_and_choices(topic, level):
    questions = question_db.get("topics", {}).get(topic, {}).get("levels", {}).get(str(level), [])
    if not questions:
        return None, []
    question = random.choice(questions)
    choices = question["choices"].copy()
    random.shuffle(choices)
    return question, choices


def get_max_level(topic):
    levels = question_db.get("topics", {}).get(topic, {}).get("levels", {})
    return max((int(level) for level in levels), default=1)


def get_room_id():
    room_id = st.session_state.get("room_id", "default")
    safe_room_id = "".join(char for char in room_id if char.isalnum() or char in "-_")
    return safe_room_id or "default"


def get_db_file():
    return f"game_state_{get_room_id()}.json"


@st.cache_resource
def get_firestore_db():
    if "firebase_service_account" not in st.secrets:
        return None
    if not firebase_admin:
        st.error("ไม่พบแพ็กเกจ firebase-admin กรุณาติดตั้งจาก requirements.txt")
        return None
    try:
        service_account = dict(st.secrets["firebase_service_account"])
        service_account["private_key"] = service_account["private_key"].replace("\\n", "\n")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(service_account))
        return firestore.client()
    except Exception as error:
        st.error(f"เชื่อมต่อ Firestore ไม่สำเร็จ: {error}")
        return None


def get_initial_state(topic=None):
    return {
        "topic": topic,
        "p1_pos": 0,
        "p2_pos": 0,
        "turn": "Player 1",
        "game_phase": "READY",
        "current_q": None,
        "current_choices": [],
        "p1_level": 1,
        "p2_level": 1,
        "last_roll": 0,
        "old_pos": 0,
        "ai_feedback": "",
        "ai_feedback_source": "",
        "p1_items": {"shield": 0, "glass": 0},
        "p2_items": {"shield": 0, "glass": 0},
        "winner": None,
        "p1_name": "Player 1",
        "p2_name": "Player 2",
        "p1_saved": False,
        "p2_saved": False,
        "p1_history": [],
        "p2_history": [],
        "p1_reset_req": False,
        "p2_reset_req": False,
    }


def get_db():
    firestore_db = get_firestore_db()
    if firestore_db:
        snapshot = firestore_db.collection("rooms").document(get_room_id()).get()
        if snapshot.exists:
            return snapshot.to_dict()
        state = get_initial_state()
        update_db(state)
        return state
    if not os.path.exists(get_db_file()):
        state = get_initial_state()
        update_db(state)
        return state
    try:
        with open(get_db_file(), "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return get_initial_state()


def update_db(state):
    firestore_db = get_firestore_db()
    if firestore_db:
        firestore_db.collection("rooms").document(get_room_id()).set(state)
        return
    with open(get_db_file(), "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def reset_game(topic):
    update_db(get_initial_state(topic))


def save_to_gsheet(data_row):
    if "gcp_service_account" not in st.secrets or not gspread:
        return
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = dict(st.secrets["gcp_service_account"])
        credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        service_account = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
        sheet = gspread.authorize(service_account).open("MathGame_Data").sheet1
        sheet.append_row(data_row)
    except Exception as error:
        st.warning(f"บันทึกลง Google Sheets ไม่สำเร็จ: {error}")


def get_ai_response(question, answer, selected):
    fallback = "ลองพิจารณาว่าต้องทำอะไรกับทั้งสองข้างของอสมการ และตรวจสอบเครื่องหมายอีกครั้ง"
    if not genai or "GENAI_API_KEY" not in st.secrets:
        return fallback, "ข้อความสำรอง: ยังไม่ได้เชื่อมต่อ Gemini"
    try:
        client = genai.Client(api_key=st.secrets["GENAI_API_KEY"])
        prompt = (
            f"โจทย์: {question}\nเฉลย: {answer}\nนักเรียนตอบ: {selected}\n"
            "อธิบายวิธีคิดที่ถูกต้องเป็นภาษาไทยแบบกระชับสำหรับนักเรียนมัธยม "
            "ใช้ไม่เกิน 4 ประโยค และอธิบายให้ตรงกับโจทย์ข้อนี้"
        )
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return response.text, "AI Feedback จาก Gemini"
    except Exception as error:
        return fallback, f"ข้อความสำรอง: Gemini ใช้งานไม่สำเร็จ ({type(error).__name__})"


def render_formula(text, latex=None):
    if text:
        st.write(text)
    if latex:
        st.latex(latex)


def render_choice(choice, index):
    with st.container(border=True):
        if choice.get("latex"):
            st.latex(choice["latex"])
        else:
            st.write(choice["value"])
        return st.button("เลือกคำตอบนี้", key=f"answer_{index}", use_container_width=True)


if "room_id" not in st.session_state:
    st.title(APP_NAME)
    st.subheader("เลือกเนื้อหาก่อนเริ่มเกม")
    topic = st.radio(
        "เนื้อหา",
        options=list(TOPICS),
        format_func=lambda key: TOPICS[key],
        label_visibility="collapsed",
    )
    col_left, col_main, col_right = st.columns([1, 2, 1])
    with col_main:
        room_input = st.text_input("ชื่อห้อง")
        name_input = st.text_input("ชื่อผู้เล่น")
        if st.button("เข้าสู่ห้อง", type="primary", use_container_width=True):
            if room_input.strip() and name_input.strip():
                st.session_state.room_id = room_input.strip()
                st.session_state.player_name = name_input.strip()
                st.session_state.selected_topic = topic
                st.rerun()
            st.error("กรุณากรอกข้อมูลให้ครบ")
    st.stop()


if "my_role" not in st.session_state:
    state = get_db()
    selected_topic = st.session_state.selected_topic
    st.header(f"ห้อง: {st.session_state.room_id}")
    if state.get("topic") and state["topic"] != selected_topic:
        st.error(f"ห้องนี้กำลังเล่นเนื้อหา: {TOPICS[state['topic']]}")
        st.stop()
    st.info(f"เนื้อหา: {TOPICS[selected_topic]}")
    col_1, col_2 = st.columns(2)
    if col_1.button(f"เลือก Player 1 (ปัจจุบัน: {state.get('p1_name', 'ว่าง')})"):
        st.session_state.my_role = "Player 1"
        state["topic"] = selected_topic
        state["p1_name"] = st.session_state.player_name
        update_db(state)
        st.rerun()
    if col_2.button(f"เลือก Player 2 (ปัจจุบัน: {state.get('p2_name', 'ว่าง')})"):
        st.session_state.my_role = "Player 2"
        state["topic"] = selected_topic
        state["p2_name"] = st.session_state.player_name
        update_db(state)
        st.rerun()
    st.stop()


state = get_db()
role = st.session_state.my_role
topic = state["topic"]
other_role = "Player 2" if role == "Player 1" else "Player 1"
p1_name = state.get("p1_name", "Player 1")
p2_name = state.get("p2_name", "Player 2")
my_name = p1_name if role == "Player 1" else p2_name
my_items_key = "p1_items" if role == "Player 1" else "p2_items"
my_items = state[my_items_key]

if state.get("p1_reset_req") and state.get("p2_reset_req"):
    reset_game(topic)
    st.rerun()

st.title(APP_NAME)
st.caption(f"เนื้อหา: {TOPICS[topic]}")

if state.get("winner"):
    st.balloons()
    winner_name = p1_name if state["winner"] == "Player 1" else p2_name
    st.success(f"เกมจบแล้ว ผู้ชนะคือ {winner_name}")
    history_key = "p1_history" if role == "Player 1" else "p2_history"
    saved_key = "p1_saved" if role == "Player 1" else "p2_saved"
    history = state[history_key]
    if not state[saved_key]:
        correct = sum(row["ผล"] == "ถูก" for row in history)
        percentage = correct / len(history) * 100 if history else 0
        mistakes = [
            f"{row['โจทย์']} | ตอบ: {row['ตอบ']} | เฉลย: {row['เฉลย']}"
            for row in history
            if row["ผล"] == "ผิด"
        ]
        save_to_gsheet(
            [
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                st.session_state.room_id,
                my_name,
                role,
                TOPICS[topic],
                len(history),
                correct,
                f"{percentage:.2f}%",
                " || ".join(mistakes),
            ]
        )
        state[saved_key] = True
        update_db(state)
    st.dataframe(history, use_container_width=True)
    if st.button("เริ่มเกมใหม่"):
        reset_game(topic)
        st.rerun()
    st.stop()

header_main, header_refresh, header_reset = st.columns([4, 1, 1])
with header_main:
    st.subheader(f"{my_name} ({role})")
    level_key = "p1_level" if role == "Player 1" else "p2_level"
    st.write(
        f"ระดับ: {state[level_key]}/{get_max_level(topic)} | "
        f"โล่: {my_items['shield']} | แว่นขยาย: {my_items['glass']}"
    )
with header_refresh:
    if st.button("รีเฟรช", use_container_width=True):
        st.rerun()
with header_reset:
    reset_key = "p1_reset_req" if role == "Player 1" else "p2_reset_req"
    if state.get(reset_key):
        st.info("รอคู่แข่ง")
    elif st.button("รีเซ็ต", use_container_width=True):
        state[reset_key] = True
        update_db(state)
        st.rerun()

board, action = st.columns([2, 1])
with board:
    current_name = p1_name if state["turn"] == "Player 1" else p2_name
    st.write(f"ตาของ: **{current_name}**")
    for row in range(8):
        cells = st.columns(8)
        for column in range(8):
            index = row * 8 + column
            p1_here = state["p1_pos"] == index
            p2_here = state["p2_pos"] == index
            label = "🏁" if index == 63 else ("🎁" if index in MYSTERY_SPOTS else str(index + 1))
            if p1_here and p2_here:
                label = "🟣"
            elif p1_here:
                label = "🔴"
            elif p2_here:
                label = "🔵"
            cells[column].button(label, key=f"board_{index}", disabled=True)

with action:
    if state["turn"] != role:
        waiting_name = p1_name if role == "Player 2" else p2_name
        st.warning(f"รอ {waiting_name} เล่น")
        time.sleep(3)
        st.rerun()

    phase = state.get("game_phase", "READY")
    if phase == "READY":
        st.markdown("### ถึงตาคุณแล้ว")
        if st.button("ทอยลูกเต๋า", type="primary", use_container_width=True):
            roll = random.randint(1, 6)
            position_key = "p1_pos" if role == "Player 1" else "p2_pos"
            state["old_pos"] = state[position_key]
            state[position_key] = min(state[position_key] + roll, 63)
            state["last_roll"] = roll
            if state[position_key] in MYSTERY_SPOTS:
                gift = random.choice(["shield", "glass"])
                state[my_items_key][gift] += 1
            if state[position_key] == 63:
                state["winner"] = role
            else:
                state["game_phase"] = "ROLLED"
            update_db(state)
            st.rerun()

    elif phase == "ROLLED":
        st.info(f"ทอยได้: {state['last_roll']}")
        if st.button("เปิดโจทย์", type="primary", use_container_width=True):
            level_key = "p1_level" if role == "Player 1" else "p2_level"
            question, choices = get_q_and_choices(topic, state[level_key])
            if not question:
                st.error("ไม่พบโจทย์สำหรับเนื้อหาและระดับนี้")
            else:
                state["current_q"] = question
                state["current_choices"] = choices
                state["game_phase"] = "ANSWERING"
                update_db(state)
                st.rerun()

    elif phase == "ANSWERING":
        question = state["current_q"]
        st.markdown("### โจทย์")
        render_formula(question.get("text"), question.get("latex"))
        if my_items["glass"] > 0 and len(state["current_choices"]) > 2:
            if st.button(f"ใช้แว่นขยาย ({my_items['glass']})"):
                state[my_items_key]["glass"] -= 1
                wrong_choices = [
                    choice for choice in state["current_choices"] if choice["value"] != question["answer"]
                ]
                state["current_choices"].remove(random.choice(wrong_choices))
                update_db(state)
                st.rerun()
        for index, choice in enumerate(state["current_choices"]):
            if render_choice(choice, index):
                is_correct = choice["value"] == question["answer"]
                history_key = "p1_history" if role == "Player 1" else "p2_history"
                state[history_key].append(
                    {
                        "โจทย์": question["text"],
                        "ตอบ": choice["value"],
                        "เฉลย": question["answer"],
                        "ผล": "ถูก" if is_correct else "ผิด",
                    }
                )
                if is_correct:
                    level_key = "p1_level" if role == "Player 1" else "p2_level"
                    state[level_key] = min(get_max_level(topic), state[level_key] + 1)
                    state["game_phase"] = "CORRECT_FEEDBACK"
                else:
                    level_key = "p1_level" if role == "Player 1" else "p2_level"
                    state[level_key] = max(1, state[level_key] - 1)
                    if my_items["shield"] > 0:
                        state[my_items_key]["shield"] -= 1
                    else:
                        position_key = "p1_pos" if role == "Player 1" else "p2_pos"
                        state[position_key] = max(0, state["old_pos"] - 3)
                    state["ai_feedback"], state["ai_feedback_source"] = get_ai_response(
                        question["text"], question["answer"], choice["value"]
                    )
                    state["game_phase"] = "FEEDBACK"
                update_db(state)
                st.rerun()

    elif phase == "FEEDBACK":
        st.error("ตอบผิด")
        st.caption(state.get("ai_feedback_source", "ข้อความสำรอง"))
        st.info(state["ai_feedback"])
        if st.button("จบตา", type="primary", use_container_width=True):
            state["turn"] = other_role
            state["game_phase"] = "READY"
            update_db(state)
            st.rerun()

    elif phase == "CORRECT_FEEDBACK":
        level_key = "p1_level" if role == "Player 1" else "p2_level"
        st.success("ตอบถูก")
        st.info(f"ระดับปัจจุบัน: {state[level_key]}/{get_max_level(topic)}")
        if st.button("จบตา", type="primary", use_container_width=True):
            state["turn"] = other_role
            state["game_phase"] = "READY"
            update_db(state)
            st.rerun()
