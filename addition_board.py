from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path


PLAYER_ANIMALS = {1: "หมาจิ้งจอก", 2: "กระต่าย"}

GAME_STYLE = """
<style>
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
.battle-hero h1 { color: inherit; padding: 0; font-size: clamp(1.8rem, 5vw, 3.5rem); line-height: 1.15; }
.battle-hero p { margin: .45rem 0 0; color: #e3efc9; font-size: clamp(1rem, 3vw, 1.45rem); }
.battle-meta { margin: .25rem 0; overflow-wrap: anywhere; }
.battle-meta strong { font-size: 1.1rem; }
.battle-meta p { margin: .2rem 0 0; }
.battle-inventory { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .45rem; }
.battle-chip {
  display: inline-flex; align-items: center; gap: .35rem; padding: .24rem .6rem;
  border-radius: 999px; background: #244938; color: #f4f5e6; font-size: .82rem;
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
.battle-room {
  padding: 1.1rem 1.3rem; border-radius: 18px; color: #f9f5e2;
  background: radial-gradient(ellipse at top right,#5a7750,#203a2b 68%);
}
.battle-room h1, .battle-room h2 { color: inherit; margin: 0; padding: 0; overflow-wrap: anywhere; }
.battle-room p { margin: .35rem 0 0; color: #e2ebcf; overflow-wrap: anywhere; }
.battle-seat { display: flex; align-items: center; gap: .75rem; margin-bottom: .65rem; }
.battle-seat .trail-pawn { font-size: 2.1rem; }
.battle-seat strong, .battle-seat small { display: block; overflow-wrap: anywhere; }
.st-key-battle-lobby, .st-key-battle-action, .st-key-battle-seat-1, .st-key-battle-seat-2 { border-radius: 18px; }
.st-key-battle-action [data-testid="stLatex"] {
  overflow-x: auto;
}
.battle-roll { display: flex; align-items: center; gap: .75rem; margin: 0 0 .7rem; }
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
.battle-board h2 { margin: 0; padding: 0; color: inherit; font-size: 1.15rem; }
.battle-board .trail-turn { margin: .2rem 0 0; color: var(--accent); overflow-wrap: anywhere; }
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
  font-size: clamp(.7rem, 2.2vw, .95rem); font-variant-numeric: tabular-nums;
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
.battle-board .trail-icon { display: grid; place-items: center; line-height: 1; }
.battle-board .trail-icon:empty { display: none; }
.battle-board .trail-item .trail-number, .battle-board .trail-end .trail-number, .battle-board .trail-occupied .trail-number {
  position: absolute; inset: 1% auto auto 8%; font-size: .72em;
}
.battle-board .trail-occupied .trail-icon { position: absolute; right: 6%; top: 7%; font-size: .65em; }
.battle-board .trail-pawns { display: flex; gap: 0; margin-top: 24%; }
.trail-pawn {
  position: relative; display: inline-grid; place-items: center; width: 1.2em; height: 1.2em;
  line-height: 1; vertical-align: middle; flex: none;
}
.battle-board .trail-pawn { font-size: clamp(.72rem, 2.25vw, 1.3rem); }
.battle-board .trail-occupied { box-shadow: inset 0 0 0 2px #284c32, inset 0 1px #ffffff40; }
.battle-board footer { padding: .75rem .85rem; font-size: .85rem; }
.battle-board .trail-players { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .5rem; }
.battle-board .trail-player { overflow-wrap: anywhere; padding: .4rem .5rem; border-radius: 9px; background: #2d5039; }
.battle-board .trail-current { box-shadow: inset 0 -2px var(--accent); }
.battle-board .trail-player small { display: block; color: #e1e9ce; margin-top: .15rem; }
.battle-board .trail-legend { margin: .7rem 0 0; color: #e1e9ce; }
@media (max-width: 480px) {
  .battle-board header, .battle-board footer { padding: .6rem; }
  .battle-board .trail-occupied .trail-number { font-size: .8em; }
  .battle-hero > img { object-position: 65% center; }
  .battle-board .trail-pawn { font-size: .7rem; }
}
</style>
"""


@lru_cache(maxsize=1)
def _hero_image():
    path = Path(__file__).with_name("forest-trail.webp")
    if not path.is_file():
        return ""
    data = b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/webp;base64,{data}" alt="">'


def hero_html():
    return (
        '<header class="battle-hero">' + _hero_image()
        + '<h1>Inequality Battle</h1><p>ตะลุยโลกอสมการ</p></header>'
    )


def pawn_html(player):
    animal = "🦊" if player == 1 else "🐰"
    return f'<span class="trail-pawn trail-p{player}" aria-hidden="true">{animal}</span>'


def item_html(item, label):
    return f'<span class="battle-chip"><i class="battle-icon battle-{item}" aria-hidden="true"></i>{escape(label)}</span>'


def game_board_html(state, mystery_spots):
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

            pawns = ""
            if occupants:
                classes.append("trail-occupied")
                labels.extend(f"ผู้เล่น {player} {PLAYER_ANIMALS[player]}" for player in occupants)
                pawns = '<span class="trail-pawns">' + "".join(map(pawn_html, occupants)) + "</span>"
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
    return (
        f'<section class="battle-board battle-{theme}" aria-label="กระดานเกม">'
        + f'<header><h2>กระดานเกม</h2><p class="trail-turn">ตาของ {escape(current_name)}</p></header>'
        + f'<div class="trail-grid">{"".join(tiles)}</div>'
        + f'<footer><div class="trail-players">{players}</div>'
        + '<p class="trail-legend">▶ เริ่ม · <i class="battle-icon battle-chest" aria-hidden="true"></i> หีบเสบียง · ⛺ จุดตั้งแคมป์</p></footer></section>'
    )
