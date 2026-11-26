from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path


GAME_STYLE = """
<style>
.battle-hero {
  position: relative; isolation: isolate; overflow: hidden;
  display: grid; align-content: center; min-height: clamp(13rem, 31vw, 24rem);
  padding: clamp(1.35rem, 5vw, 3rem); border-radius: 24px; color: #faf8ff;
  background: radial-gradient(ellipse at 88% 18%, #51458a 0%, transparent 52%),
    linear-gradient(125deg, #141b37, #282653);
}
.battle-hero > img {
  position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
  object-position: center 52%; z-index: -2;
}
.battle-hero::after {
  content: ""; position: absolute; z-index: -1; inset: 0;
  background: linear-gradient(90deg,#101329ed,#101329b5 37%,#10132912 75%);
}
.battle-hero h1 { color: inherit; padding: 0; font-size: clamp(1.8rem, 5vw, 3.5rem); line-height: 1.15; }
.battle-hero p { margin: .45rem 0 0; color: #e4dcff; font-size: clamp(1rem, 3vw, 1.45rem); }
.battle-meta { margin: .25rem 0; overflow-wrap: anywhere; }
.battle-meta strong { font-size: 1.1rem; }
.battle-meta p { margin: .2rem 0 0; }
.battle-inventory { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .45rem; }
.battle-chip {
  display: inline-flex; align-items: center; gap: .35rem; padding: .24rem .6rem;
  border-radius: 999px; background: #262849; color: #f3f0ff; font-size: .82rem;
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
  padding: 1.1rem 1.3rem; border-radius: 18px; color: #f7f2ff;
  background: radial-gradient(ellipse at top right,#59498d,#232342 62%);
}
.battle-room h1, .battle-room h2 { color: inherit; margin: 0; padding: 0; overflow-wrap: anywhere; }
.battle-room p { margin: .35rem 0 0; color: #e3daf8; overflow-wrap: anywhere; }
.battle-seat { display: flex; align-items: center; gap: .75rem; margin-bottom: .65rem; }
.battle-seat .trail-pawn { font-size: 1.8rem; }
.battle-seat strong, .battle-seat small { display: block; overflow-wrap: anywhere; }
.st-key-battle-lobby, .st-key-battle-action, .st-key-battle-seat-1, .st-key-battle-seat-2 { border-radius: 18px; }
.st-key-battle-action [data-testid="stLatex"] {
  overflow-x: auto;
}
.battle-roll { display: flex; align-items: center; gap: .75rem; margin: 0 0 .7rem; }
.battle-roll strong {
  display: grid; place-items: center; width: 2.6rem; aspect-ratio: 1;
  border-radius: .65rem; background: #ede7ff; color: #382267; font-size: 1.45rem;
}
.battle-board {
  --accent: #7ee4cb; --tile-alt: #263b4c; --frame: #192f3d;
  color: #f1f5ff; background: #151d33; border: 1px solid #36415c;
  border-radius: 20px; overflow: hidden;
}
.battle-board.battle-multiplication { --accent: #ffd092; --tile-alt: #45384a; --frame: #362d41; }
.battle-board.battle-linear { --accent: #d3beff; --tile-alt: #373c62; --frame: #292f51; }
.battle-board header { padding: .85rem 1rem; border-bottom: 1px solid #ffffff23; }
.battle-board h2 { margin: 0; padding: 0; color: inherit; font-size: 1.15rem; }
.battle-board .trail-turn { margin: .2rem 0 0; color: var(--accent); overflow-wrap: anywhere; }
.battle-board .trail-grid {
  --tile-gap: clamp(3px, .85vw, 9px);
  display: grid; grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: var(--tile-gap); padding: clamp(.45rem, 2vw, 1rem);
  background: radial-gradient(ellipse at 50% 28%, var(--frame), #141a32);
}
.battle-board .trail-tile {
  position: relative; display: grid; place-items: center; aspect-ratio: 1;
  min-width: 0; border-radius: 22%; background: var(--tile-alt); color: #f0f3ff;
  font-size: clamp(.7rem, 2.2vw, .95rem); font-variant-numeric: tabular-nums;
  box-shadow: inset 0 1px #ffffff23, inset 0 -2px #00000028;
}
.battle-board .trail-right::after, .battle-board .trail-down::before {
  content: ""; position: absolute; background: var(--accent); opacity: .65; border-radius: 1px;
}
.battle-board .trail-right::after { left: 100%; width: var(--tile-gap); height: 2px; }
.battle-board .trail-down::before { top: 100%; height: var(--tile-gap); width: 2px; }
.battle-board .trail-item { background: linear-gradient(145deg,#ffe8ab,#d9a953); color: #422a02; }
.battle-board .trail-end { background: linear-gradient(135deg,#eefaff,var(--accent)); color: #172439; }
.battle-board .trail-icon { display: grid; place-items: center; line-height: 1; }
.battle-board .trail-icon:empty { display: none; }
.battle-board .trail-item .trail-number, .battle-board .trail-end .trail-number, .battle-board .trail-occupied .trail-number {
  position: absolute; inset: 1% auto auto 8%; font-size: .72em;
}
.battle-board .trail-occupied .trail-icon { position: absolute; right: 6%; top: 7%; font-size: .65em; }
.battle-board .trail-pawns { display: flex; gap: 1px; margin-top: 20%; }
.trail-pawn {
  position: relative; display: inline-grid; place-items: center; width: 1.25em; height: 1.4em;
  line-height: 1; font-weight: 850; color: #101b36; flex: none;
}
.trail-pawn::before { content: ""; position: absolute; inset: 0; }
.trail-pawn b { position: relative; font-size: .72em; }
.trail-p1::before { clip-path: polygon(50% 0,96% 31%,84% 78%,50% 100%,16% 78%,4% 31%);
  background: linear-gradient(120deg,#e5ffff 0 28%,#81efff 29% 65%,#36a9f6 66%); }
.trail-p2::before { clip-path: polygon(20% 5%,78% 5%,100% 40%,73% 94%,25% 94%,0 40%);
  background: linear-gradient(135deg,#ffe5f3 0 24%,#ff9cd4 25% 64%,#f157a8 65%); }
.battle-board .trail-pawn { font-size: .8em; }
.battle-board .trail-occupied { box-shadow: inset 0 0 0 1px var(--accent), inset 0 1px #ffffff23; }
.battle-board footer { padding: .75rem .85rem; font-size: .85rem; }
.battle-board .trail-players { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .5rem; }
.battle-board .trail-player { overflow-wrap: anywhere; padding: .4rem .5rem; border-radius: 9px; background: #242c47; }
.battle-board .trail-current { box-shadow: inset 0 -2px var(--accent); }
.battle-board .trail-player small { display: block; color: #cbd4ec; margin-top: .15rem; }
.battle-board .trail-legend { margin: .7rem 0 0; color: #cbd4ec; }
@media (max-width: 480px) {
  .battle-board header, .battle-board footer { padding: .6rem; }
  .battle-board .trail-occupied .trail-number { font-size: .8em; }
  .battle-hero > img { object-position: 65% center; }
}
</style>
"""


@lru_cache(maxsize=1)
def _hero_image():
    path = Path(__file__).with_name("battle-arena.webp")
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
    return f'<span class="trail-pawn trail-p{player}" aria-hidden="true"><b>{player}</b></span>'


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
                labels.append("จุดเริ่มต้น" if index == 0 else "เส้นชัย")
                icon = "▶" if index == 0 else "🏁"
            elif index in mystery_spots:
                classes.append("trail-item")
                labels.append("ช่องไอเทม")
                icon = '<i class="battle-icon battle-chest"></i>'

            pawns = ""
            if occupants:
                classes.append("trail-occupied")
                labels.extend(f"ผู้เล่น {player}" for player in occupants)
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
        f' · ระดับ {state[f"p{player}_level"]}</small></div>'
        for player in (1, 2)
    )
    return (
        f'<section class="battle-board battle-{theme}" aria-label="กระดานเกม">'
        + f'<header><h2>กระดานเกม</h2><p class="trail-turn">ตาของ {escape(current_name)}</p></header>'
        + f'<div class="trail-grid">{"".join(tiles)}</div>'
        + f'<footer><div class="trail-players">{players}</div>'
        + '<p class="trail-legend">▶ เริ่ม · <i class="battle-icon battle-chest" aria-hidden="true"></i> ช่องไอเทม · 🏁 เส้นชัย</p></footer></section>'
    )
