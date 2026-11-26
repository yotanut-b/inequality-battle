import datetime
import json
import logging
import os
import random
import time
import uuid
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st

from addition_board import PLAYER_ANIMALS, game_board_html, game_style_html, hero_html, item_html, pawn_html, walk_duration

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
GEMINI_MODEL = "gemini-4-hydrogen"
Q_DIR = "questions"
MYSTERY_SPOTS = [3, 11, 19, 27, 35, 43, 51, 59]
ROOM_TIMEOUT_SECONDS = 3 * 60
TOPICS = {
    "addition": "การแก้อสมการโดยใช้สมบัติการบวกของการไม่เท่ากัน",
    "multiplication": "การแก้อสมการโดยใช้สมบัติการคูณของการไม่เท่ากัน",
    "linear": "การแก้อสมการเชิงเส้นตัวแปรเดียว",
}

st.set_page_config(page_title=APP_NAME, page_icon="📝", layout="wide")
st.html(game_style_html())


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
    now = time.time()
    return {
        "game_id": uuid.uuid4().hex,
        "created_at": now,
        "last_activity_at": now,
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


def ensure_room_metadata(state):
    changed = False
    now = time.time()
    if "game_id" not in state:
        state["game_id"] = uuid.uuid4().hex
        changed = True
    if "created_at" not in state:
        state["created_at"] = now
        changed = True
    if "last_activity_at" not in state:
        state["last_activity_at"] = now
        changed = True
    return changed


def get_db():
    firestore_db = get_firestore_db()
    if firestore_db:
        snapshot = firestore_db.collection("rooms").document(get_room_id()).get()
        if snapshot.exists:
            state = snapshot.to_dict()
            if ensure_room_metadata(state):
                update_db(state, touch=False)
            return state
        state = get_initial_state()
        update_db(state)
        return state
    if not os.path.exists(get_db_file()):
        state = get_initial_state()
        update_db(state)
        return state
    try:
        with open(get_db_file(), "r", encoding="utf-8") as file:
            state = json.load(file)
        if ensure_room_metadata(state):
            update_db(state, touch=False)
        return state
    except Exception:
        return get_initial_state()


def update_db(state, touch=True):
    if touch:
        state["last_activity_at"] = time.time()
    firestore_db = get_firestore_db()
    if firestore_db:
        firestore_db.collection("rooms").document(get_room_id()).set(state)
        return
    with open(get_db_file(), "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def delete_db():
    firestore_db = get_firestore_db()
    if firestore_db:
        firestore_db.collection("rooms").document(get_room_id()).delete()
        return
    if os.path.exists(get_db_file()):
        os.remove(get_db_file())


def is_room_expired(state):
    return time.time() - state.get("last_activity_at", state.get("created_at", time.time())) >= ROOM_TIMEOUT_SECONDS


def return_to_home(message):
    for key in ["room_id", "player_name", "selected_topic", "my_role", "game_id"]:
        st.session_state.pop(key, None)
    st.session_state.home_notice = message
    st.rerun()


def close_expired_room():
    state = get_db()
    save_room_results(state, "หมดเวลา", show_warning=False)
    delete_db()
    return_to_home("ห้องหมดเวลาแล้ว กรุณาเริ่มเกมใหม่")


def reset_game(topic):
    update_db(get_initial_state(topic))


def save_to_gsheet(data_row, show_warning=True):
    if not gspread:
        if show_warning:
            st.warning("บันทึกผลไม่ได้: ไม่พบแพ็กเกจ gspread")
        return False
    secret_name = None
    if "gcp_service_account" in st.secrets:
        secret_name = "gcp_service_account"
    elif "firebase_service_account" in st.secrets:
        secret_name = "firebase_service_account"
    if not secret_name:
        if show_warning:
            st.warning("บันทึกผลไม่ได้: ยังไม่ได้ตั้งค่า service account ใน Streamlit Secrets")
        return False
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = dict(st.secrets[secret_name])
        credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        service_account = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
        sheet = gspread.authorize(service_account).open("MathGame_Data").sheet1
        sheet.append_row(data_row)
        return True
    except Exception as error:
        if show_warning:
            st.warning(
                "บันทึกลง Google Sheets ไม่สำเร็จ กรุณาตรวจว่าแชร์ชีต MathGame_Data "
                f"ให้ service account เป็น Editor และเปิด Google Sheets API กับ Google Drive API แล้ว: {error}"
            )
        return False


def build_result_row(state, role, status):
    name = state["p1_name"] if role == "Player 1" else state["p2_name"]
    history = state["p1_history"] if role == "Player 1" else state["p2_history"]
    correct = sum(row["ผล"] == "ถูก" for row in history)
    percentage = correct / len(history) * 100 if history else 0
    mistakes = [
        f"{row['โจทย์']} | ตอบ: {row['ตอบ']} | เฉลย: {row['เฉลย']}"
        for row in history
        if row["ผล"] == "ผิด"
    ]
    return [
        datetime.datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S"),
        st.session_state.room_id,
        name,
        role,
        TOPICS[state["topic"]],
        status,
        len(history),
        correct,
        f"{percentage:.2f}%",
        " || ".join(mistakes),
    ]


def claim_room_result_save(state, roles):
    firestore_db = get_firestore_db()
    if not firestore_db:
        return not state.get("results_saving", False)
    room_ref = firestore_db.collection("rooms").document(get_room_id())
    transaction = firestore_db.transaction()

    @firestore.transactional
    def claim(transaction):
        snapshot = room_ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"allowed": False}
        latest_state = snapshot.to_dict()
        if latest_state.get("results_saving", False):
            return {"allowed": False}
        needs_save = any(
            not latest_state.get("p1_saved" if role == "Player 1" else "p2_saved")
            and latest_state["p1_name" if role == "Player 1" else "p2_name"] != role
            for role in roles
        )
        if needs_save:
            transaction.update(room_ref, {"results_saving": True})
        return {
            "allowed": True,
            "p1_saved": latest_state.get("p1_saved", False),
            "p2_saved": latest_state.get("p2_saved", False),
        }

    result = claim(transaction)
    state["p1_saved"] = result.get("p1_saved", state.get("p1_saved", False))
    state["p2_saved"] = result.get("p2_saved", state.get("p2_saved", False))
    return result["allowed"]


def finish_room_result_save(state):
    firestore_db = get_firestore_db()
    if firestore_db:
        firestore_db.collection("rooms").document(get_room_id()).update(
            {
                "p1_saved": state.get("p1_saved", False),
                "p2_saved": state.get("p2_saved", False),
                "results_saving": False,
            }
        )
        return
    state["results_saving"] = False
    update_db(state)


def save_room_results(state, status, roles=None, show_warning=True):
    roles = roles or ["Player 1", "Player 2"]
    if not claim_room_result_save(state, roles):
        return False
    state["results_saving"] = True
    saved_all = True
    for role in roles:
        saved_key = "p1_saved" if role == "Player 1" else "p2_saved"
        name = state["p1_name"] if role == "Player 1" else state["p2_name"]
        if not state.get(saved_key) and name != role:
            state[saved_key] = save_to_gsheet(build_result_row(state, role, status), show_warning)
            saved_all = state[saved_key] and saved_all
    finish_room_result_save(state)
    return saved_all


def get_ai_feedback(answer_record):
    fallback = "ลองตรวจอีกครั้งว่าต้องทำอะไรกับอสมการทั้งสองข้าง และควรกลับเครื่องหมายหรือไม่"
    try:
        api_key = st.secrets.get("GENAI_API_KEY")
        if not isinstance(api_key, str) or not api_key.strip():
            return fallback, "ข้อความสำรอง · ยังไม่ได้ตั้งค่า Gemini"
        prompt = (
            f"โจทย์: {answer_record['โจทย์']}\n"
            f"คำตอบที่เลือก: {answer_record['ตอบ']}\n"
            f"เฉลยที่ตรวจแล้ว: {answer_record['เฉลย']}\n"
            "ให้คำแนะนำภาษาไทย 1 ถึง 2 ประโยคสำหรับนักเรียนมัธยม "
            "ชี้จุดที่ควรตรวจจากโจทย์และคำตอบที่เลือก โดยยึดเฉลยที่ให้มา "
            "ใช้ข้อความธรรมดาและไม่ต้องแจกแจงวิธีทำเต็มข้อ"
        )
        request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            data=json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": "LOW"}},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key.strip()},
            method="POST",
        )
        with urlopen(request, timeout=18) as response:
            data = json.load(response)
        candidates = data.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        feedback = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
        if feedback:
            return feedback, f"คำแนะนำจาก Gemini · {GEMINI_MODEL}"
        logging.warning("Gemini feedback empty: model=%s", GEMINI_MODEL)
        reason = "Gemini ตอบกลับโดยไม่มีข้อความ"
    except HTTPError as error:
        logging.warning("Gemini feedback failed: model=%s HTTP %s", GEMINI_MODEL, error.code)
        reason = {
            400: "Google ปฏิเสธคำขอ ลองตรวจการตั้งค่า API key",
            401: "ยืนยัน API key ไม่สำเร็จ",
            403: "โปรเจกต์ไม่มีสิทธิ์เรียก Gemini",
            404: "โปรเจกต์นี้เรียกโมเดลที่ตั้งไว้ไม่ได้",
            429: "Gemini ถึงขีดจำกัดการเรียกชั่วคราว",
            503: "บริการ Gemini ไม่พร้อมใช้งานชั่วคราว",
        }.get(error.code, "Google ตอบกลับด้วยข้อผิดพลาด")
        reason = f"{reason} (HTTP {error.code})"
        error.close()
    except (TimeoutError, URLError) as error:
        timed_out = isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)
        reason = "รอ Gemini เกินเวลาที่กำหนด" if timed_out else "เชื่อมต่อ Gemini ไม่สำเร็จ"
        logging.warning("Gemini connection failed: model=%s timeout=%s", GEMINI_MODEL, timed_out)
    except Exception as error:
        logging.warning("Gemini feedback failed: model=%s error=%s", GEMINI_MODEL, type(error).__name__)
        reason = "อ่านการตั้งค่าหรือผลตอบกลับจาก Gemini ไม่สำเร็จ"
    return fallback, f"ข้อความสำรอง · {reason} · {GEMINI_MODEL}"


def fresh_walk(state):
    move = state.get("trail_move")
    if not move or (state.get("game_phase") not in ("ROLLED", "ANSWERING") and not state.get("winner")):
        return None
    if time.time() - move["at"] > 10 or st.session_state.get("seen_trail_move") == move["id"]:
        return None
    st.session_state.seen_trail_move = move["id"]
    return move


def claim_seat(state, seat, topic, name):
    key = f"p{seat}_name"
    role = f"Player {seat}"

    def can_join(latest):
        return (
            latest.get("game_id") == state["game_id"]
            and latest.get("topic") in (None, topic)
            and latest.get(key) in (role, name)
            and (not latest.get("winner") or latest.get(key) == name)
            and not is_room_expired(latest)
        )

    db = get_firestore_db()
    if db is None:
        latest = get_db()
        if not can_join(latest):
            return False
        latest.update({"topic": topic, key: name})
        update_db(latest)
        return True

    room = db.collection("rooms").document(get_room_id())

    @firestore.transactional
    def claim(transaction):
        snapshot = room.get(transaction=transaction)
        if not snapshot.exists or not can_join(snapshot.to_dict()):
            return False
        transaction.update(room, {"topic": topic, key: name, "last_activity_at": time.time()})
        return True

    return claim(db.transaction())


def render_formula(text, latex=None):
    if latex:
        st.latex(latex)
    elif text:
        st.write(text)


def render_choice(choice, index):
    with st.container(border=True):
        if choice.get("latex"):
            st.latex(choice["latex"])
        else:
            st.write(choice["value"])
        return st.button(f"เลือกข้อ {index + 1}", key=f"answer_{index}", use_container_width=True)


@st.fragment(run_every=3)
def render_waiting_panel(role):
    latest_state = get_db()
    if (
        latest_state.get("turn") == role
        or latest_state.get("winner")
        or latest_state.get("game_id") != st.session_state.get("game_id")
    ):
        st.rerun()
    if is_room_expired(latest_state):
        close_expired_room()
    waiting_name = latest_state["p1_name" if role == "Player 2" else "p2_name"]
    board_column, waiting_column = st.columns([2, 1])
    board_column.html(game_board_html(latest_state, MYSTERY_SPOTS, fresh_walk(latest_state)))
    with waiting_column, st.container(border=True):
        st.subheader("รอคู่แข่ง")
        st.write(f"{waiting_name} กำลังเล่น")


if "room_id" not in st.session_state:
    st.html(hero_html())
    if "home_notice" in st.session_state:
        st.warning(st.session_state.pop("home_notice"))
    with st.container(border=True, key="battle-lobby"):
        st.subheader("เริ่มเล่น")
        st.caption("ใช้รหัสเดียวกันกับคู่แข่งเพื่อเข้าห้องเดียวกัน")
        topic = st.radio(
            "เนื้อหา",
            options=list(TOPICS),
            format_func=lambda key: TOPICS[key],
            label_visibility="collapsed",
        )
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
    if is_room_expired(state):
        save_room_results(state, "หมดเวลา", show_warning=False)
        delete_db()
        state = get_initial_state()
        update_db(state)
    selected_topic = st.session_state.selected_topic
    st.html(
        f'<header class="battle-room"><h2>ห้อง {escape(st.session_state.room_id)}</h2>'
        f'<p>{escape(TOPICS[selected_topic])}</p></header>'
    )
    if state.get("topic") and state["topic"] != selected_topic:
        st.error(f"ห้องนี้กำลังเล่นเนื้อหา: {TOPICS[state['topic']]}")
        st.stop()
    st.subheader("เลือกตัวละคร")
    col_1, col_2 = st.columns(2)
    for seat, column in enumerate((col_1, col_2), start=1):
        piece = PLAYER_ANIMALS[seat]
        seat_role = f"Player {seat}"
        seat_name = state[f"p{seat}_name"]
        occupied = seat_name != seat_role
        seat_status = f"เข้าห้องแล้ว · {seat_name}" if occupied else "ที่นั่งว่าง"
        with column, st.container(border=True, key=f"battle-seat-{seat}"):
            st.html(
                f'<div class="battle-seat">{pawn_html(seat)}<div><strong>{piece}</strong>'
                f'<small>ผู้เล่น {seat} · {escape(seat_status)}</small></div></div>'
            )
            seat_unavailable = (occupied or state.get("winner")) and seat_name != st.session_state.player_name
            if st.button(
                f"เลือก{piece}", key=f"join-seat-{seat}", use_container_width=True,
                disabled=bool(seat_unavailable),
            ):
                if claim_seat(state, seat, selected_topic, st.session_state.player_name):
                    st.session_state.my_role = seat_role
                    st.session_state.game_id = state["game_id"]
                    st.rerun()
                st.warning("สถานะห้องเปลี่ยนแล้ว กรุณาอัปเดตที่นั่ง")
    if st.button("อัปเดตที่นั่ง"):
        st.rerun()
    st.stop()


state = get_db()
if is_room_expired(state):
    close_expired_room()
if st.session_state.get("game_id") != state.get("game_id"):
    return_to_home("ห้องรอบเดิมถูกปิดแล้ว กรุณาเข้าห้องใหม่")
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

st.html(
    '<header class="battle-room"><h1>Inequality Battle</h1>'
    f'<p>ห้อง {escape(st.session_state.room_id)} · {escape(TOPICS[topic])}</p></header>'
)

if state.get("winner"):
    winner_name = p1_name if state["winner"] == "Player 1" else p2_name
    st.success(f"⛺ {winner_name} ถึงแคมป์แล้ว")
    finish_board, finish_summary = st.columns([2, 1])
    finish_board.html(game_board_html(state, MYSTERY_SPOTS, fresh_walk(state)))
    history_key = "p1_history" if role == "Player 1" else "p2_history"
    saved_key = "p1_saved" if role == "Player 1" else "p2_saved"
    history = state[history_key]
    if not state[saved_key]:
        save_room_results(state, "จบเกม", roles=[role])
    with finish_summary:
        st.subheader("สรุปการเดินทาง")
        answered, correct = st.columns(2)
        answered.metric("ตอบทั้งหมด", len(history))
        correct.metric("ตอบถูก", sum(row["ผล"] == "ถูก" for row in history))
    mistakes = [row for row in history if row["ผล"] == "ผิด"]
    if mistakes:
        st.subheader("ข้อที่ควรกลับไปทบทวน")
        st.dataframe(mistakes, use_container_width=True)
    elif history:
        st.success("คุณตอบถูกทุกข้อ")
    if st.button("เริ่มเกมใหม่"):
        reset_game(topic)
        st.rerun()
    st.stop()

header_main, header_refresh, header_reset, header_timeout = st.columns([3, 1, 1, 1])
with header_main:
    player = 1 if role == "Player 1" else 2
    level_key = f"p{player}_level"
    st.html(
        f'<div class="battle-meta">{pawn_html(player)} <strong>{escape(my_name)}</strong>'
        f'<p>ระดับ {state[level_key]}/{get_max_level(topic)}</p>'
        '<div class="battle-inventory">'
        + item_html("shield", f'โล่ {my_items["shield"]}')
        + item_html("glass", f'แว่นขยาย {my_items["glass"]}')
        + "</div></div>"
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
with header_timeout:
    if st.button("หมดเวลา", help="บันทึกผลของทั้งสองคน ปิดห้อง และกลับหน้าแรก", use_container_width=True):
        if save_room_results(state, "หมดเวลา"):
            delete_db()
            return_to_home("บันทึกผลและปิดห้องแล้ว รหัสห้องนี้พร้อมใช้สำหรับเกมใหม่")
        st.error("ยังปิดห้องไม่ได้ เพราะบันทึกผลไม่สำเร็จ กรุณาตรวจการตั้งค่า Google Sheets")

if state["turn"] != role:
    render_waiting_panel(role)
    st.stop()

phase = state.get("game_phase", "READY")
with st.container(key="battle-question-layout" if phase == "ANSWERING" else "battle-play-layout"):
    board, action = st.columns([2, 1])
move = fresh_walk(state)
board.html(game_board_html(state, MYSTERY_SPOTS, move))

with action, st.container(border=True, key="battle-action"):
    if phase == "READY":
        st.markdown("### ถึงตาคุณแล้ว")
        if st.button("ทอยลูกเต๋า", type="primary", use_container_width=True):
            roll = random.randint(1, 6)
            position_key = "p1_pos" if role == "Player 1" else "p2_pos"
            state["old_pos"] = state[position_key]
            state[position_key] = min(state[position_key] + roll, 63)
            state["trail_move"] = {
                "id": uuid.uuid4().hex, "at": time.time(),
                "player": player, "from": state["old_pos"], "to": state[position_key],
            }
            state["last_roll"] = roll
            state["last_roll_item"] = None
            if state[position_key] in MYSTERY_SPOTS:
                gift = random.choice(["shield", "glass"])
                state[my_items_key][gift] += 1
                state["last_roll_item"] = gift
            if state[position_key] == 63:
                state["winner"] = role
            else:
                state["game_phase"] = "ROLLED"
            update_db(state)
            st.rerun()

    elif phase == "ROLLED":
        roll = state["last_roll"]
        animation = " battle-roll-fresh" if move else ""
        st.html(f'<div class="battle-roll{animation}"><strong aria-hidden="true">{chr(0x2680 + roll - 1)}</strong>'
                f'<span>ทอยได้ <b>{roll}</b> แต้ม</span></div>')
        if state.get("last_roll_item") in ("shield", "glass"):
            gift = state["last_roll_item"]
            gift_label = "โล่ · ป้องกันการถอย 1 ครั้ง" if gift == "shield" else "แว่นขยาย · ตัดตัวเลือกผิด 1 ข้อ"
            reward = item_html(gift, gift_label)
            if move:
                reward = f'<div class="battle-reward-fresh" style="--walk-duration:{walk_duration(move)}ms">{reward}</div>'
            st.html(reward)
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
                    state["shield_used"] = my_items["shield"] > 0
                    if state["shield_used"]:
                        state[my_items_key]["shield"] -= 1
                    else:
                        position_key = "p1_pos" if role == "Player 1" else "p2_pos"
                        state[position_key] = max(0, state["old_pos"] - 3)
                    state["game_phase"] = "FEEDBACK"
                update_db(state)
                st.rerun()

    elif phase == "FEEDBACK":
        st.error("ตอบผิด")
        st.caption(f"ระดับปัจจุบัน {state[level_key]}/{get_max_level(topic)}")
        if state.get("shield_used"):
            st.html(item_html("shield", "ใช้โล่แล้ว · อยู่ช่องเดิม"))
        history = state[f"p{player}_history"]
        if history:
            feedback_key = ("gemini-rest", state["game_id"], role, len(history))
            cached_key, result = st.session_state.get("answer_feedback", (None, None))
            if cached_key != feedback_key:
                with st.spinner("กำลังเตรียมคำแนะนำ"):
                    result = get_ai_feedback(history[-1])
                st.session_state.answer_feedback = (feedback_key, result)
            feedback, source = result
            st.caption(source)
            st.info(feedback)
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
