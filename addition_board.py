from html import escape


GAME_STYLE = """
<style>
.battle-hero {
  position: relative; isolation: isolate; overflow: hidden;
  padding: clamp(1.35rem, 5vw, 3rem); border-radius: 24px; color: #faf8ff;
  background: radial-gradient(ellipse at 88% 18%, #51458a 0%, transparent 52%),
    linear-gradient(125deg, #141b37, #282653);
}
.battle-hero::after {
  content: "≤"; position: absolute; z-index: -1; inset: 48% 5% auto auto;
  transform: translateY(-50%) rotate(-12deg); color: #ffffff12;
  font: 800 clamp(8rem, 20vw, 16rem)/1 system-ui, sans-serif;
}
.battle-hero h1 { color: inherit; padding: 0; font-size: clamp(1.8rem, 5vw, 3.5rem); line-height: 1.15; }
.battle-hero p { margin: .45rem 0 0; color: #e4dcff; font-size: clamp(1rem, 3vw, 1.45rem); }
.battle-meta { margin: .25rem 0; overflow-wrap: anywhere; }
.battle-meta strong { font-size: 1.1rem; }
.battle-meta p { margin: .2rem 0 0; }
.st-key-battle-lobby, .st-key-battle-action { border-radius: 18px; }
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
  display: grid; grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: clamp(3px, .6vw, 7px); padding: clamp(.45rem, 2vw, .9rem);
  background: var(--frame);
}
.battle-board .trail-tile {
  position: relative; display: grid; place-items: center; aspect-ratio: 1;
  min-width: 0; border-radius: 22%; background: var(--tile-alt); color: #f0f3ff;
  font-size: clamp(.7rem, 2.2vw, .95rem); font-variant-numeric: tabular-nums;
  box-shadow: inset 0 1px #ffffff23, inset 0 -2px #00000028;
}
.battle-board .trail-item { background: #f9d887; color: #422a02; }
.battle-board .trail-end { background: var(--accent); color: #172439; }
.battle-board .trail-icon { position: absolute; inset: 4% 7% auto auto; font-size: .74em; line-height: 1; }
.battle-board .trail-occupied .trail-number {
  position: absolute; inset: 1% auto auto 8%; font-size: .72em;
}
.battle-board .trail-pawns { display: flex; gap: 1px; margin-top: 20%; }
.battle-board .trail-pawn {
  display: inline-grid; place-items: center; width: 1.2em; height: 1.2em;
  line-height: 1; font-size: .82em; font-weight: 700;
  outline: 1px solid #151d33;
}
.battle-board .trail-p1 { background: #80dcff; color: #0d3450; border-radius: 50%; }
.battle-board .trail-p2 { background: #ff9fc7; color: #501e3a; border-radius: 25%; }
.battle-board footer { padding: .75rem .85rem; font-size: .85rem; }
.battle-board .trail-players { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .5rem; }
.battle-board .trail-player { overflow-wrap: anywhere; }
.battle-board .trail-player small { display: block; color: #cbd4ec; margin-top: .15rem; }
.battle-board .trail-legend { margin: .7rem 0 0; color: #cbd4ec; }
@media (max-width: 480px) {
  .battle-board header, .battle-board footer { padding: .6rem; }
  .battle-board .trail-occupied .trail-number { font-size: .8em; }
}
</style>
"""


def game_board_html(state, mystery_spots):
    positions = (state["p1_pos"], state["p2_pos"])
    names = (state["p1_name"], state["p2_name"])
    current_name = names[0 if state["turn"] == "Player 1" else 1]
    tiles = []

    for row in range(8):
        # Only the display order changes. Room positions still count from 0 to 63.
        indices = range(row * 8, (row + 1) * 8)
        for index in indices if row % 2 == 0 else reversed(indices):
            occupants = [player for player, pos in enumerate(positions, start=1) if pos == index]
            classes = ["trail-tile"]
            labels = [f"ช่อง {index + 1}"]
            icon = ""
            if index in (0, 63):
                classes.append("trail-end")
                labels.append("จุดเริ่มต้น" if index == 0 else "เส้นชัย")
                icon = "▶" if index == 0 else "🏁"
            elif index in mystery_spots:
                classes.append("trail-item")
                labels.append("ช่องไอเทม")
                icon = "🎁"

            pawns = ""
            if occupants:
                classes.append("trail-occupied")
                labels.extend(f"ผู้เล่น {player}" for player in occupants)
                pawns = '<span class="trail-pawns">' + "".join(
                    f'<span class="trail-pawn trail-p{player}">{player}</span>'
                    for player in occupants
                ) + "</span>"
            tiles.append(
                f'<div class="{" ".join(classes)}" role="img" aria-label="{escape(" · ".join(labels))}">'
                f'<span class="trail-number">{index + 1}</span>'
                f'<span class="trail-icon" aria-hidden="true">{icon}</span>{pawns}</div>'
            )

    topic = state["topic"]
    theme = topic if topic in ("addition", "multiplication", "linear") else "addition"
    players = "".join(
        f'<div class="trail-player"><span class="trail-pawn trail-p{player}">{player}</span> '
        f'{escape(names[player - 1])}<small>ช่อง {positions[player - 1] + 1}'
        f' · ระดับ {state[f"p{player}_level"]}</small></div>'
        for player in (1, 2)
    )
    return (
        f'<section class="battle-board battle-{theme}" aria-label="กระดานเกม">'
        + f'<header><h2>กระดานเกม</h2><p class="trail-turn">ตาของ {escape(current_name)}</p></header>'
        + f'<div class="trail-grid">{"".join(tiles)}</div>'
        + f'<footer><div class="trail-players">{players}</div>'
        + '<p class="trail-legend">▶ เริ่ม · 🎁 ช่องไอเทม · 🏁 เส้นชัย</p></footer></section>'
    )
