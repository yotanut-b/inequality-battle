from html import escape


BOARD_STYLE = """
<style>
.addition-trail {
  color: #17392b; background: #eaf3e6; border-radius: 16px; overflow: hidden;
}
.addition-trail header {
  background: #174d3a; color: #f1fae9; padding: .8rem 1rem;
}
.addition-trail h2 { margin: 0; padding: 0; color: inherit; font-size: 1.3rem; }
.addition-trail .trail-turn { margin: .3rem 0 0; overflow-wrap: anywhere; }
.addition-trail .trail-grid {
  display: grid; grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: clamp(2px, .6vw, 6px); padding: clamp(.4rem, 2vw, .85rem);
  background: repeating-radial-gradient(ellipse at top left,
    transparent 0 15px, #b2e3b319 16px 17px, transparent 18px 27px), #205741;
}
.addition-trail .trail-tile {
  position: relative; display: grid; place-items: center; aspect-ratio: 1;
  min-width: 0; border-radius: 18%; background: #dcf1d6;
  font-size: clamp(.7rem, 2.2vw, .95rem); font-variant-numeric: tabular-nums;
  box-shadow: inset 0 -2px #172f2026;
}
.addition-trail .trail-item { background: #f8dfa1; }
.addition-trail .trail-end { background: #f2f7df; }
.addition-trail .trail-icon { position: absolute; inset: 2% 7% auto auto; font-size: .7em; }
.addition-trail .trail-occupied .trail-number {
  position: absolute; inset: 1% auto auto 8%; font-size: .72em;
}
.addition-trail .trail-pawns { display: flex; gap: 1px; margin-top: 20%; }
.addition-trail .trail-pawn {
  display: inline-grid; place-items: center; width: 1.2em; height: 1.2em;
  line-height: 1; font-size: .78em; font-weight: 700; color: white;
}
.addition-trail .trail-p1 { background: #2659a5; border-radius: 50%; }
.addition-trail .trail-p2 { background: #96482c; border-radius: 25%; }
.addition-trail footer {
  display: flex; flex-wrap: wrap; gap: .35rem .9rem; padding: .55rem .8rem;
  font-size: .85rem;
}
</style>
"""


def addition_board_html(state, mystery_spots):
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

    return (
        BOARD_STYLE
        + '<section class="addition-trail" aria-label="กระดานป่าสมบัติการบวก">'
        + f'<header><h2>ป่าสมบัติการบวก</h2><p class="trail-turn">ตาของ {escape(current_name)}</p></header>'
        + f'<div class="trail-grid">{"".join(tiles)}</div>'
        + '<footer><span>▶ เริ่ม</span><span>🎁 ช่องไอเทม</span><span>🏁 เส้นชัย</span>'
        + f'<span><span class="trail-pawn trail-p1">1</span> {escape(names[0])} · ช่อง {positions[0] + 1}</span>'
        + f'<span><span class="trail-pawn trail-p2">2</span> {escape(names[1])} · ช่อง {positions[1] + 1}</span>'
        + '</footer></section>'
    )
