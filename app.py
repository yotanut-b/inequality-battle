import datetime
import json
import logging
import os
import random
import time
import uuid
from base64 import b64encode
from html import escape
from pathlib import Path
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st

from addition_board import PLAYER_ANIMALS, game_board_html, game_style_html, item_html, pawn_html, walk_duration

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


APP_NAME = "Inequality Battle"
APP_SUBTITLE = "บอร์ดเกมตะลุยโลกอสมการแบบปรับเหมาะ"
GEMINI_MODEL = "gemini-4-hydrogen"
GEMINI_BACKUP_MODEL = "gemini-3.5-flash-lite"
Q_DIR = "questions"
MYSTERY_SPOTS = [3, 11, 19, 27, 35, 43, 51, 59]
ROOM_TIMEOUT_SECONDS = 3 * 60
TOPICS = {
    "addition": "การแก้อสมการโดยใช้สมบัติการบวกของการไม่เท่ากัน",
    "multiplication": "การแก้อสมการโดยใช้สมบัติการคูณของการไม่เท่ากัน",
    "linear": "การแก้อสมการเชิงเส้นตัวแปรเดียว",
}

st.set_page_config(page_title=f"{APP_NAME}: {APP_SUBTITLE}", page_icon="📝", layout="wide")
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


@st.cache_resource
def room_file_lock():
    return RLock()


def get_db(create=True):
    firestore_db = get_firestore_db()
    if firestore_db:
        room = firestore_db.collection("rooms").document(get_room_id())
        snapshot = room.get()
        if snapshot.exists:
            state = snapshot.to_dict()
            if ensure_room_metadata(state):
                update_db(state, touch=False)
            return state
        if not create:
            return None
        @firestore.transactional
        def open_room(transaction):
            current = room.get(transaction=transaction)
            if current.exists:
                return current.to_dict()
            state = get_initial_state()
            transaction.set(room, state)
            return state

        return open_room(firestore_db.transaction())
    with room_file_lock():
        if not os.path.exists(get_db_file()):
            if not create:
                return None
            state = get_initial_state()
            update_db(state)
            return state
        try:
            with open(get_db_file(), "r", encoding="utf-8") as file:
                state = json.load(file)
        except (OSError, ValueError):
            if not create:
                raise
            return get_initial_state()
        if ensure_room_metadata(state):
            update_db(state, touch=False)
        return state


def update_db(state, touch=True):
    if touch:
        state["last_activity_at"] = time.time()
    firestore_db = get_firestore_db()
    expected_id = st.session_state.get("game_id")
    if firestore_db:
        room = firestore_db.collection("rooms").document(get_room_id())
        if expected_id is None:
            room.set(state)
            return

        @firestore.transactional
        def write_player_state(transaction):
            snapshot = room.get(transaction=transaction)
            if not snapshot.exists or snapshot.to_dict().get("game_id") != expected_id:
                return False
            transaction.set(room, state)
            return True

        if not write_player_state(firestore_db.transaction()):
            st.rerun()
        return
    with room_file_lock():
        if expected_id is not None:
            path = Path(get_db_file())
            if not path.exists() or json.loads(path.read_text(encoding="utf-8")).get("game_id") != expected_id:
                st.rerun()
        with open(get_db_file(), "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)


def is_room_expired(state):
    return time.time() - state.get("last_activity_at", state.get("created_at", time.time())) >= ROOM_TIMEOUT_SECONDS


def return_to_home(message=None):
    for key in ["room_id", "player_name", "selected_topic", "my_role", "game_id"]:
        st.session_state.pop(key, None)
    if message:
        st.session_state.home_notice = message
    st.rerun()


def summary_file(game_id):
    return Path(f"game_state_summary_{uuid.UUID(game_id).hex}.json")


def read_room_summary(game_id):
    db = get_firestore_db()
    if db:
        snapshot = db.collection("room_summaries").document(game_id).get()
        return snapshot.to_dict() if snapshot.exists else None
    with room_file_lock():
        path = summary_file(game_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def close_room_with_summary(game_id, expired_only=False):
    def prepare(state):
        if state["game_id"] != game_id or (expired_only and not is_room_expired(state)):
            return None
        if state.get("results_saving"):
            return None
        summary = {key: state[key] for key in (
            "topic", "winner", "p1_name", "p2_name", "p1_history", "p2_history", "p1_saved", "p2_saved",
        )}
        summary["closed_at"] = time.time()
        return summary

    db = get_firestore_db()
    if db:
        room = db.collection("rooms").document(get_room_id())
        archive = db.collection("room_summaries").document(game_id)

        @firestore.transactional
        def close(transaction):
            snapshot = room.get(transaction=transaction)
            summary = prepare(snapshot.to_dict()) if snapshot.exists else None
            if summary is not None:
                transaction.set(archive, summary)
                transaction.delete(room)
            return summary

        summary = close(db.transaction())
    else:
        with room_file_lock():
            current = get_db(create=False)
            summary = prepare(current) if current else None
            if summary is not None:
                summary_file(game_id).write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
                Path(get_db_file()).unlink()

    if summary is None:
        return None
    status = "จบเกม" if summary["winner"] else "หมดเวลา"
    for player in (1, 2):
        role = f"Player {player}"
        saved_key = f"p{player}_saved"
        if summary["topic"] and not summary[saved_key] and summary[f"p{player}_name"] != role:
            summary[saved_key] = save_to_gsheet(build_result_row(summary, role, status), show_warning=False)
    saved = {key: summary[key] for key in ("p1_saved", "p2_saved")}
    if db:
        archive.update(saved)
    else:
        with room_file_lock():
            summary_file(game_id).write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return summary


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
        if latest_state.get("game_id") != state.get("game_id") or latest_state.get("results_saving", False):
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


def request_gemini_feedback(model, api_key, prompt, timeout):
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"thinkingConfig": {"thinkingLevel": "LOW"}},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    candidates = data.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    return "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()


def get_ai_feedback(answer_record):
    fallback = "ลองตรวจอีกครั้งว่าต้องทำอะไรกับอสมการทั้งสองข้าง และควรกลับเครื่องหมายหรือไม่"
    model = GEMINI_MODEL
    try:
        api_key = st.secrets.get("GENAI_API_KEY")
        if not isinstance(api_key, str) or not api_key.strip():
            return fallback, "ข้อความสำรอง · ยังไม่ได้ตั้งค่า Gemini"
        prompt = (
            f"โจทย์: {answer_record['โจทย์']}\nเฉลย: {answer_record['เฉลย']}\nนักเรียนตอบ: {answer_record['ตอบ']}\n"
            "อธิบายวิธีคิดที่ถูกต้องเป็นภาษาไทยแบบกระชับสำหรับนักเรียนมัธยม "
            "ใช้ไม่เกิน 4 ประโยค และอธิบายให้ตรงกับโจทย์ข้อนี้"
        )
        api_key = api_key.strip()
        try:
            feedback = request_gemini_feedback(model, api_key, prompt, timeout=18)
        except HTTPError as error:
            if error.code != 503:
                raise
            error.close()
            logging.warning("Gemini feedback unavailable: model=%s HTTP 503; trying %s", model, GEMINI_BACKUP_MODEL)
            model = GEMINI_BACKUP_MODEL
            time.sleep(random.uniform(0.8, 1.2))
            feedback = request_gemini_feedback(model, api_key, prompt, timeout=10)
        if feedback:
            return feedback, f"คำแนะนำจาก Gemini · {model}"
        logging.warning("Gemini feedback empty: model=%s", model)
        reason = "Gemini ตอบกลับโดยไม่มีข้อความ"
    except HTTPError as error:
        logging.warning("Gemini feedback failed: model=%s HTTP %s", model, error.code)
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
        logging.warning("Gemini connection failed: model=%s timeout=%s", model, timed_out)
    except Exception as error:
        logging.warning("Gemini feedback failed: model=%s error=%s", model, type(error).__name__)
        reason = "อ่านการตั้งค่าหรือผลตอบกลับจาก Gemini ไม่สำเร็จ"
    return fallback, f"ข้อความสำรอง · {reason} · {model}"


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


@st.cache_data
def home_hero_html():
    cover = Path(__file__).with_name("forest-trail.webp")
    image = ""
    if cover.is_file():
        data = b64encode(cover.read_bytes()).decode("ascii")
        image = f'<img src="data:image/webp;base64,{data}" alt="">'
    return (
        f'<header class="battle-hero">{image}'
        f'<h1>{escape(APP_NAME)}:</h1><p>{escape(APP_SUBTITLE)}</p></header>'
    )


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


SUMMARY_STYLE = """
<style>
.battle-finale {
  display: grid; grid-template-columns: minmax(0,1fr) auto; align-items: center; gap: 1rem;
  padding: clamp(1.15rem, 4vw, 2.5rem); border-radius: 1.5rem;
  color: #fff8e5; background: radial-gradient(ellipse at 85% 20%, #8d7545, transparent 56%), #214738;
  box-shadow: inset 0 0 0 1px #fbe6a244;
}
.battle-finale--timeout { background: radial-gradient(ellipse at 90% 0%, #4d6655, transparent 70%), #334b45; }
.battle-finale h1 {
  color: inherit; padding: 0; margin: .2rem 0; font-size: clamp(2.05rem, 5vw, 3.55rem);
  overflow-wrap: anywhere; line-height: 1.15;
}
.battle-finale p { margin: .3rem 0 0; color: #fff0cd; font-size: clamp(1.15rem, 3vw, 1.5rem); }
.battle-finale strong { color: #ffe0a0; font-size: 1.25rem; }
.battle-finale .trail-pawn { font-size: clamp(3.3rem, 10vw, 7rem); filter: drop-shadow(0 .4rem .55rem #101e1880); }
.battle-finale--win .trail-pawn { animation: camp-arrival .5s ease-out both; }
@keyframes camp-arrival { from { transform: translateY(.6rem) scale(.82); } }
@media (prefers-reduced-motion: reduce) { .battle-finale--win .trail-pawn { animation: none; } }
.battle-summary-scores {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem;
}
.battle-summary-stat, .battle-review {
  background: #f7f5e9; color: #24392e; border: 1px solid #d8ddc4; border-radius: 1rem;
  padding: .7rem .85rem; overflow-wrap: anywhere;
}
.battle-summary-stat strong { display: block; font-size: clamp(1.75rem, 5vw, 2.35rem); line-height: 1.1; }
.battle-summary-stat span { display: block; margin-top: .25rem; font-size: 1.15rem; }
.battle-summary-correct { background: #e6f0dd; }
.battle-summary-wrong { background: #fbe9df; }
.battle-review summary { font-size: 1.2rem; cursor: pointer; }
.battle-review dl { margin: .7rem 0 0; }
.battle-review dt { font-weight: 700; }
.battle-review dd { margin: 0 0 .45rem; white-space: pre-wrap; }
@media (max-width: 560px) {
  .battle-summary-scores { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .battle-finale { gap: .5rem; }
}
</style>
"""


def render_round_summary(summary, role):
    player = 1 if role == "Player 1" else 2
    name = summary[f"p{player}_name"]
    winner_role = summary.get("winner")
    if winner_role:
        winner = 1 if winner_role == "Player 1" else 2
        winner_name = summary[f"p{winner}_name"]
        heading = f"{winner_name} ถึงแคมป์ก่อน!"
        label = "คุณชนะรอบนี้" if winner_role == role else "จบการเดินทาง"
        detail = f"ผู้ชนะ · {PLAYER_ANIMALS[winner]}"
        variant = "win"
        character = pawn_html(winner)
    else:
        heading, label, detail = "หมดเวลาเล่น", "จบการเดินทาง", "สรุปผลจากข้อที่ตอบก่อนหมดเวลา"
        variant = "timeout"
        character = pawn_html(player)

    st.html(
        SUMMARY_STYLE + f'<header class="battle-finale battle-finale--{variant}">'
        f'<div><strong>{escape(label)}</strong><h1>{escape(heading)}</h1>'
        f'<p>{escape(detail)}</p></div>{character}</header>'
    )
    st.subheader(f"ผลการเล่นของ {name}")
    st.caption(f"ห้อง {st.session_state.room_id}")
    history = summary[f"p{player}_history"]
    total = len(history)
    correct = sum(row["ผล"] == "ถูก" for row in history)
    wrong = sum(row["ผล"] == "ผิด" for row in history)
    stats = (
        ("ตอบทั้งหมด", total, ""),
        ("ตอบถูก", correct, " battle-summary-correct"),
        ("ตอบผิด", wrong, " battle-summary-wrong"),
        ("ความถูกต้อง", f"{correct / total:.0%}" if total else "–", ""),
    )
    tiles = "".join(
        f'<div class="battle-summary-stat{style}"><strong>{value}</strong><span>{label}</span></div>'
        for label, value, style in stats
    )
    st.html(f'<section class="battle-summary-scores" aria-label="คะแนนของคุณ">{tiles}</section>')
    render_mistakes(history)


def render_mistakes(history):
    mistakes = [row for row in history if row["ผล"] == "ผิด"]
    if mistakes:
        st.subheader(f"ข้อที่ควรทบทวน ({len(mistakes)})")
        for index, row in enumerate(mistakes, start=1):
            opened = " open" if index == 1 else ""
            st.html(
                f'<details class="battle-review"{opened}>'
                f'<summary>{index}. {escape(str(row["โจทย์"]))}</summary>'
                f'<dl><dt>คำตอบที่เลือก</dt><dd>{escape(str(row["ตอบ"]))}</dd>'
                f'<dt>เฉลย</dt><dd>{escape(str(row["เฉลย"]))}</dd></dl></details>'
            )
    elif history:
        st.success("คุณตอบถูกทุกข้อ")
    else:
        st.info("รอบนี้ยังไม่ได้ตอบโจทย์")


def render_closed_summary(summary, role):
    render_round_summary(summary, role)
    if st.button("กลับหน้าแรก", type="primary"):
        return_to_home()
    st.stop()


@st.fragment(run_every=3)
def monitor_active_room(game_id):
    latest = get_db(create=False)
    if not latest or latest["game_id"] != game_id or is_room_expired(latest):
        st.rerun()


@st.fragment(run_every=3)
def render_waiting_panel(role):
    latest_state = get_db(create=False)
    if (
        not latest_state
        or latest_state.get("turn") == role
        or latest_state.get("winner")
        or latest_state.get("game_id") != st.session_state.get("game_id")
        or is_room_expired(latest_state)
    ):
        st.rerun()
    waiting_name = latest_state["p1_name" if role == "Player 2" else "p2_name"]
    board_column, waiting_column = st.columns([2, 1])
    board_column.html(game_board_html(latest_state, MYSTERY_SPOTS, fresh_walk(latest_state)))
    with waiting_column, st.container(border=True):
        st.subheader("รอคู่แข่ง")
        st.write(f"{waiting_name} กำลังเล่น")


if "room_id" not in st.session_state:
    st.html(home_hero_html())
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
        close_room_with_summary(state["game_id"], expired_only=True)
        state = get_db()
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


role = st.session_state.my_role
game_id = st.session_state.game_id
state = get_db(create=False)
if not state or game_id != state.get("game_id"):
    summary = read_room_summary(game_id)
    if summary is not None:
        render_closed_summary(summary, role)
    return_to_home("ห้องรอบเดิมถูกปิดแล้ว กรุณาเข้าห้องใหม่")
if not state.get("winner") and is_room_expired(state):
    summary = close_room_with_summary(game_id, expired_only=True)
    if summary is not None:
        render_closed_summary(summary, role)
    latest = get_db(create=False)
    if not latest or latest["game_id"] != game_id or not is_room_expired(latest):
        st.rerun()
    st.info("ห้องหมดเวลาแล้ว กำลังรอบันทึกผล")
    if st.button("ตรวจผลอีกครั้ง"):
        st.rerun()
    st.stop()
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

if state.get("winner"):
    render_round_summary(state, role)
    saved_key = "p1_saved" if role == "Player 1" else "p2_saved"
    if not state[saved_key]:
        save_room_results(state, "จบเกม", roles=[role])
    with st.expander("ดูกระดานเมื่อจบเกม"):
        st.html(game_board_html(state, MYSTERY_SPOTS))
    if st.button("กลับหน้าแรก", type="primary"):
        close_room_with_summary(game_id)
        return_to_home()
    st.stop()

st.html(
    f'<header class="battle-room"><h1>{APP_NAME}:</h1>'
    f'<p>{APP_SUBTITLE}</p>'
    f'<p>ห้อง {escape(st.session_state.room_id)} · {escape(TOPICS[topic])}</p></header>'
)

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
    if st.button("หมดเวลา", help="ปิดห้องและแสดงสรุปผลของผู้เล่นทั้งสองคน", use_container_width=True):
        close_room_with_summary(game_id)
        st.rerun()

if state["turn"] != role:
    render_waiting_panel(role)
    st.stop()

monitor_active_room(game_id)
phase = state.get("game_phase", "READY")
if phase == "ROLLED":
    question, choices = get_q_and_choices(topic, state[level_key])
    if not question:
        st.error("ไม่พบโจทย์สำหรับเนื้อหาและระดับนี้")
        st.stop()
    state.update(current_q=question, current_choices=choices, game_phase="ANSWERING")
    update_db(state)
    st.rerun()

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
            destination = min(state[position_key] + roll, 63)
            if destination != 63:
                question, choices = get_q_and_choices(topic, state[level_key])
                if not question:
                    st.error("ไม่พบโจทย์สำหรับเนื้อหาและระดับนี้")
                    st.stop()
            state["old_pos"] = state[position_key]
            state[position_key] = destination
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
                state.update(current_q=question, current_choices=choices, game_phase="ANSWERING")
            update_db(state)
            st.rerun()

    elif phase == "ANSWERING":
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
            feedback_key = ("gemini-rest-backup", state["game_id"], role, len(history))
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
