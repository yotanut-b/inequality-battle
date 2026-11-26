from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path


PLAYER_ANIMALS = {1: "หมาจิ้งจอก", 2: "กระต่าย"}

GAME_STYLE = """
<style>
[data-testid="stAppViewContainer"] {
  --battle-text-size: clamp(1.2rem, 1.1rem + .45vw, 1.45rem);
}
[data-testid="stAppViewContainer"] :is(
  [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
  [data-testid="stWidgetLabel"] p, [role="radiogroup"] p,
  [data-testid="stTextInput"] input
) {
  font-size: var(--battle-text-size);
  line-height: 1.4;
}
[data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] p {
  font-size: clamp(1.05rem, 1rem + .3vw, 1.25rem);
  line-height: 1.35;
}
[data-testid="stAppViewContainer"] [data-testid="stButton"] button {
  min-height: 2.8rem;
  padding: .35rem .5rem;
}
[data-testid="stAppViewContainer"] [data-testid="stButton"] button p {
  font-size: clamp(1.15rem, 1.05rem + .4vw, 1.35rem);
  line-height: 1.2;
  overflow-wrap: anywhere;
}
.battle-hero {
  position: relative; isolation: isolate; overflow: hidden;
  display: grid; align-content: center; min-height: clamp(13rem, 31vw, 24rem);
  padding: clamp(1.35rem, 5vw, 3rem); border-radius: 24px; color: #faf8ff;
  background: radial-gradient(ellipse at 88% 18%, #56784a 0%, transparent 52%),
    linear-gradient(125deg, #142c22, #284f35);
}
.battle-hero > img {
  position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
  object-position: center 52%; z-index: -2;
}
.battle-hero::after {
  content: ""; position: absolute; z-index: -1; inset: 0;
  background: linear-gradient(90deg,#10251deb,#10251d98 40%,#10251d0b 76%);
}
.battle-hero h1 { color: inherit; padding: 0; font-size: clamp(2.45rem, 6vw, 4.35rem); line-height: 1.15; }
.battle-hero p { margin: .45rem 0 0; color: #e3efc9; font-size: clamp(1.35rem, 3.4vw, 1.9rem); }
.battle-meta { margin: .25rem 0; overflow-wrap: anywhere; font-size: var(--battle-text-size); }
.battle-meta strong { font-size: 1.2em; }
.battle-meta p { margin: .2rem 0 0; }
.battle-inventory { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .45rem; }
.battle-chip {
  display: inline-flex; align-items: center; gap: .35rem; padding: .24rem .6rem;
  border-radius: 999px; background: #244938; color: #f4f5e6; font-size: 1.1rem;
}
.battle-icon { position: relative; display: inline-block; width: 1em; height: 1em; flex: none; }
.battle-shield {
  clip-path: polygon(50% 0, 96% 18%, 88% 62%, 50% 100%, 12% 62%, 4% 18%);
  background: linear-gradient(120deg,#c4f8ff 0 30%,#4ca8fb 31% 61%,#2667b7 62%);
}
.battle-glass::before, .battle-glass::after { content: ""; position: absolute; }
.battle-glass::before { inset: 0 .3em .3em 0; border: .14em solid #f9d887; border-radius: 50%; background: #adf5ff; }
.battle-glass::after { width: .5em; height: .16em; top: .73em; left: .5em; transform: rotate(45deg); background: #f9d887; border-radius: 1em; }
.battle-chest {
  height: .69em; border-radius: .16em .16em .1em .1em;
  background: linear-gradient(90deg,transparent 19%,#ffe59d 20% 29%,transparent 30% 70%,#ffe59d 71% 80%,transparent 81%),
    linear-gradient(#c98139 45%,#4d291f 46% 58%,#a6592c 59%);
  border: 1px solid #5f3420; box-shadow: 0 2px #39251c35;
}
.battle-chest::after { content: ""; position: absolute; inset: 39% 40% 20%; border-radius: 2px; background: #ffe59d; }
.battle-chest::before {
  content: ""; position: absolute; inset: -1px -1px 55%; border-radius: .16em .16em .04em .04em;
  border: 1px solid #5f3420; background: linear-gradient(150deg,#efb56b,#a65a2b);
  transform-origin: top left;
}
.battle-room {
  padding: 1.1rem 1.3rem; border-radius: 18px; color: #f9f5e2;
  background: radial-gradient(ellipse at top right,#5a7750,#203a2b 68%);
}
.battle-room h1, .battle-room h2 { color: inherit; margin: 0; padding: 0; overflow-wrap: anywhere; }
.battle-room p { margin: .35rem 0 0; color: #e2ebcf; overflow-wrap: anywhere; font-size: var(--battle-text-size); }
.battle-seat { display: flex; align-items: center; gap: .75rem; margin-bottom: .65rem; font-size: var(--battle-text-size); }
.battle-seat .trail-pawn { font-size: 2.1rem; }
.battle-seat strong, .battle-seat small { display: block; overflow-wrap: anywhere; }
.st-key-battle-lobby, .st-key-battle-action, .st-key-battle-seat-1, .st-key-battle-seat-2 { border-radius: 18px; }
.st-key-battle-action [data-testid="stLatex"] {
  overflow-x: auto;
}
.st-key-battle-action [data-testid="stLatex"] .katex { font-size: 1.33em; }
.battle-roll { display: flex; align-items: center; gap: .75rem; margin: 0 0 .7rem; font-size: var(--battle-text-size); }
.battle-roll strong {
  display: grid; place-items: center; width: 2.6rem; aspect-ratio: 1;
  border-radius: .65rem; background: #e6edcf; color: #27402c; font-size: 1.45rem;
}
.battle-board {
  --accent: #c4df9e; --tile-light: #d8ddae; --tile-dark: #abb78a; --frame: #42633e;
  color: #fcf9e9; background: #1c372a; border: 1px solid #577453;
  border-radius: 20px; overflow: hidden;
}
.battle-board.battle-multiplication { --accent: #f0ca8c; --tile-light: #eeddb7; --tile-dark: #c6af85; --frame: #64533a; }
.battle-board.battle-linear { --accent: #a8ded7; --tile-light: #cce0d2; --tile-dark: #91b3a2; --frame: #345e53; }
.battle-board header { padding: .85rem 1rem; border-bottom: 1px solid #ffffff23; }
.battle-board h2 { margin: 0; padding: 0; color: inherit; font-size: 1.5rem; }
.battle-board .trail-turn { margin: .2rem 0 0; color: var(--accent); overflow-wrap: anywhere; font-size: var(--battle-text-size); }
.battle-board .trail-grid {
  --tile-gap: clamp(3px, .85vw, 9px);
  display: grid; grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: var(--tile-gap); padding: clamp(.45rem, 2vw, 1rem);
  background: repeating-radial-gradient(ellipse at 0 100%, transparent 0 20px,#dbe8b112 21px 22px,transparent 23px 35px),
    radial-gradient(ellipse at 50% 28%, var(--frame), #19382c);
}
.battle-board .trail-tile {
  position: relative; display: grid; place-items: center; aspect-ratio: 1;
  min-width: 0; border-radius: 26% 22% 28% 19%;
  background: linear-gradient(145deg,var(--tile-light),var(--tile-dark)); color: #203122;
  font-size: clamp(.95rem, 2.4vw, 1.25rem); font-variant-numeric: tabular-nums;
  box-shadow: inset 0 2px #ffffff45, inset 0 -3px #26341d40, 0 2px 3px #0d1d1b60;
}
.battle-board .trail-tile:nth-child(3n) { border-radius: 20% 29% 18% 24%; }
.battle-board .trail-right::after, .battle-board .trail-down::before {
  content: ""; position: absolute; background: var(--accent); opacity: .65; border-radius: 1px;
}
.battle-board .trail-right::after { left: 100%; width: var(--tile-gap); height: 2px; }
.battle-board .trail-down::before { top: 100%; height: var(--tile-gap); width: 2px; }
.battle-board .trail-item { background: linear-gradient(145deg,#ffe8ab,#d9a953); color: #422a02; }
.battle-board .trail-end { background: linear-gradient(135deg,#fff4cf,var(--accent)); color: #243624; }
.battle-board .trail-creek {
  background: repeating-linear-gradient(160deg,#ffffff23 0 2px,transparent 3px 9px), #a2cfc5;
}
.battle-board .trail-bridge {
  background: repeating-linear-gradient(0deg,#784b2d55 0 2px,transparent 3px 9px), #e3be8d;
}
.battle-board .trail-icon { display: grid; place-items: center; line-height: 1; }
.battle-board .trail-icon:empty { display: none; }
.battle-board .trail-item .trail-number, .battle-board .trail-end .trail-number, .battle-board .trail-occupied .trail-number {
  position: absolute; inset: 1% auto auto 8%; font-size: .72em; line-height: 1;
}
.battle-board .trail-occupied .trail-icon { position: absolute; right: 6%; top: 7%; font-size: .65em; }
.battle-board .trail-pawns { display: flex; gap: 0; margin-top: 24%; }
.trail-pawn {
  position: relative; display: inline-grid; place-items: center; width: 1.2em; height: 1.2em;
  line-height: 1; vertical-align: middle; flex: none;
}
.trail-pawn img { width: 100%; height: 100%; object-fit: contain; }
.battle-seat .trail-pawn { width: 1.65em; height: 1.65em; }
.battle-board .trail-pawn { font-size: clamp(.72rem, 2.25vw, 1.3rem); }
.trail-moving {
  position: absolute; inset: 0; display: grid; place-items: center; z-index: 2;
  pointer-events: none;
  animation: trail-walk var(--walk-duration) linear both;
}
.trail-arriving { animation: trail-arrive var(--walk-duration) steps(1, end) both; }
.trail-opening .battle-chest {
  transform-origin: bottom; animation: trail-chest .48s ease-out var(--walk-duration) both;
}
.trail-opening .battle-chest::before { animation: trail-lid .48s ease-out var(--walk-duration) both; }
.battle-roll.battle-roll-fresh strong { animation: trail-dice .48s ease-out both; }
.battle-reward-fresh { animation: trail-reward .35s ease-out var(--walk-duration) both; }
@keyframes trail-arrive { from { opacity: 0; } to { opacity: 1; } }
@keyframes trail-chest { 45% { transform: translateY(-.25em) rotate(-16deg) scale(1.24); filter: brightness(1.55); } }
@keyframes trail-lid { to { transform: rotate(-42deg) translateY(-.15em); } }
@keyframes trail-dice { from { transform: rotate(-170deg) scale(.65); } 75% { transform: rotate(14deg) scale(1.12); } }
@keyframes trail-reward { from { opacity: 0; transform: translateY(.4rem); } }
@media (prefers-reduced-motion: reduce) {
  .trail-moving { display: none; }
  .trail-arriving, .trail-opening .battle-chest, .trail-opening .battle-chest::before,
  .battle-roll.battle-roll-fresh strong, .battle-reward-fresh {
    animation: none;
  }
}
@media (max-width: 640px) {
  .st-key-battle-question-layout [data-testid="stHorizontalBlock"] { flex-direction: column-reverse; }
  .st-key-battle-question-layout [data-testid="stColumn"] { width: 100%; }
}
.battle-board .trail-occupied { box-shadow: inset 0 0 0 2px #284c32, inset 0 1px #ffffff40; }
.battle-board footer { padding: .75rem .85rem; font-size: clamp(1.05rem, 1rem + .35vw, 1.3rem); }
.battle-board .trail-players { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .5rem; }
.battle-board .trail-player { overflow-wrap: anywhere; padding: .4rem .5rem; border-radius: 9px; background: #2d5039; }
.battle-board .trail-current { box-shadow: inset 0 -2px var(--accent); }
.battle-board .trail-player small { display: block; color: #e1e9ce; margin-top: .15rem; font-size: .9em; }
.battle-board .trail-legend { margin: .7rem 0 0; color: #e1e9ce; }
@media (max-width: 480px) {
  .battle-board header, .battle-board footer { padding: .6rem; }
  .battle-hero > img { object-position: 65% center; }
  .battle-board .trail-pawn { font-size: .7rem; }
}
</style>
"""


@lru_cache(maxsize=1)
def game_style_html():
    path = Path(__file__).with_name("ChulaCharasNewReg.ttf")
    if not path.is_file():
        return GAME_STYLE
    data = b64encode(path.read_bytes()).decode("ascii")
    return GAME_STYLE + f"""
<style>
@font-face {{
  font-family: "ChulaCharasNew";
  src: url("data:font/ttf;base64,{data}") format("truetype");
  font-style: normal;
  font-weight: 400;
  font-display: swap;
}}
[data-testid="stAppViewContainer"] {{
  --battle-ui-font: "ChulaCharasNew", system-ui, sans-serif;
  font-family: var(--battle-ui-font);
}}
[data-testid="stAppViewContainer"] :is(
  h1, h2, h3, h4, h5, h6, button, input, textarea, label,
  [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
  [data-testid="stMetric"], .battle-hero, .battle-room, .battle-seat,
  .battle-meta, .battle-board, .battle-roll, .battle-chip
) {{
  font-family: var(--battle-ui-font);
}}
</style>
"""


@lru_cache(maxsize=3)
def _image_src(filename):
    path = Path(__file__).with_name(filename)
    return "data:image/webp;base64," + b64encode(path.read_bytes()).decode("ascii") if path.is_file() else ""


def hero_html():
    src = _image_src("forest-trail.webp")
    return (
        '<header class="battle-hero">' + (f'<img src="{src}" alt="">' if src else "")
        + '<h1>Inequality Battle</h1><p>ตะลุยโลกอสมการ</p></header>'
    )


def pawn_html(player, arriving=False):
    animal = "🦊" if player == 1 else "🐰"
    src = _image_src("trail-fox.webp" if player == 1 else "trail-rabbit.webp")
    contents = f'<img src="{src}" alt="">' if src else animal
    arrival = " trail-arriving" if arriving else ""
    return f'<span class="trail-pawn trail-p{player}{arrival}" aria-hidden="true">{contents}</span>'


def item_html(item, label):
    return f'<span class="battle-chip"><i class="battle-icon battle-{item}" aria-hidden="true"></i>{escape(label)}</span>'


def walk_duration(move):
    return 480 + 155 * (move["to"] - move["from"])


def walk_style(move):
    start = move["from"]
    end = move["to"]

    def coordinates(index):
        row, column = divmod(index, 8)
        return row, column if row % 2 == 0 else 7 - column

    row_start, col_start = coordinates(start)
    duration = walk_duration(move)
    frames = ["0% { transform: translate(0,0); }", f"{480 / duration * 100:.3f}% {{ transform: translate(0,0); }}"]
    for step, index in enumerate(range(start + 1, end + 1), start=1):
        row, col = coordinates(index)
        x, y = col - col_start, row - row_start
        progress = min(99.9, (480 + 155 * step) / duration * 100)
        frames.append(
            f"{progress:.3f}% {{ transform: translate(calc({x * 100}% + {x} * var(--tile-gap)),"
            f"calc({y * 100}% + {y} * var(--tile-gap))); }}"
        )
    frames.append("100% { opacity: 0; }")
    return "<style>@keyframes trail-walk { " + " ".join(frames) + " }</style>"


def game_board_html(state, mystery_spots, move=None):
    positions = (state["p1_pos"], state["p2_pos"])
    names = (state["p1_name"], state["p2_name"])
    current_player = 1 if state["turn"] == "Player 1" else 2
    current_name = names[current_player - 1]
    tiles = []

    for row in range(8):
        # Only the display order changes. Room positions still count from 0 to 63.
        indices = range(row * 8, (row + 1) * 8)
        for index in indices if row % 2 == 0 else reversed(indices):
            occupants = [player for player, pos in enumerate(positions, start=1) if pos == index]
            classes = ["trail-tile"]
            if index % 8 != 7:
                classes.append("trail-right")
            if row < 7 and index % 8 == (7 if row % 2 == 0 else 0):
                classes.append("trail-down")
            labels = [f"ช่อง {index + 1}"]
            icon = ""
            if index in (0, 63):
                classes.append("trail-end")
                labels.append("จุดเริ่มต้น" if index == 0 else "เส้นชัย จุดตั้งแคมป์")
                icon = "▶" if index == 0 else "⛺"
            elif index in mystery_spots:
                classes.append("trail-item")
                labels.append("หีบเสบียง")
                icon = '<i class="battle-icon battle-chest"></i>'
                if move and move["to"] == index and state.get("last_roll_item"):
                    classes.append("trail-opening")
            elif row == 3:
                classes.append("trail-bridge")
            elif row in (2, 4):
                classes.append("trail-creek")

            pawns = ""
            if occupants:
                classes.append("trail-occupied")
                labels.extend(f"ผู้เล่น {player} {PLAYER_ANIMALS[player]}" for player in occupants)
                pawns = '<span class="trail-pawns">' + "".join(
                    pawn_html(player, arriving=bool(move and player == move["player"]))
                    for player in occupants
                ) + "</span>"
            if move and index == move["from"]:
                pawns += f'<span class="trail-moving" aria-hidden="true">{pawn_html(move["player"])}</span>'
            tiles.append(
                f'<div class="{" ".join(classes)}" role="img" aria-label="{escape(" · ".join(labels))}">'
                f'<span class="trail-number">{index + 1}</span>'
                f'<span class="trail-icon" aria-hidden="true">{icon}</span>{pawns}</div>'
            )

    topic = state["topic"]
    theme = topic if topic in ("addition", "multiplication", "linear") else "addition"
    players = "".join(
        f'<div class="trail-player{" trail-current" if player == current_player else ""}">{pawn_html(player)} '
        f'{escape(names[player - 1])}<small>ช่อง {positions[player - 1] + 1}'
        f' · ระดับ {state[f"p{player}_level"]} · {PLAYER_ANIMALS[player]}</small></div>'
        for player in (1, 2)
    )
    motion = f' style="--walk-duration:{walk_duration(move)}ms"' if move else ""
    return (
        (walk_style(move) if move else "")
        + f'<section class="battle-board battle-{theme}" aria-label="กระดานเกม"{motion}>'
        + f'<header><h2>กระดานเกม</h2><p class="trail-turn">ตาของ {escape(current_name)}</p></header>'
        + f'<div class="trail-grid">{"".join(tiles)}</div>'
        + f'<footer><div class="trail-players">{players}</div>'
        + '<p class="trail-legend">▶ เริ่ม · สะพานไม้ · <i class="battle-icon battle-chest" aria-hidden="true"></i> หีบเสบียง · ⛺ จุดตั้งแคมป์</p></footer></section>'
    )
