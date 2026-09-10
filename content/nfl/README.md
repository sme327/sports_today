# content/nfl — hand-authored game notes

One TOML file per game, named by the **ESPN event id** the slate uses
(`401872656.toml`). Read by `services/nfl_game_notes.py` and rendered on that game's
pregame matchup page; the graded parts are recorded and settled by `services/nfl_leans.py`
and shown on `/leans/`.

Sections, in the order the page shows them:

| Table | What it is | Graded? |
|---|---|---|
| `[[availability]]` | The official injury report (`report_date`), plus `Departed` for players still in last season's numbers but no longer on the roster. An `impact` line (what this absence changes tonight) ranks the entry above the rest; entries without one collapse to name and status | — |
| `[[changes]]` | Who moved since last season, `direction = "in"` / `"out"` | — |
| `[shape]` | `headline`, `observations` (up to four `{ lead, text }` pairs, the bold lead first), `alternative`: the written read, before any line. Older notes may use plain `lines` | — |
| `[read]` | `game_script`: the expected shape of the game, hand-written, shown under The read and labelled as a read | — |
| `[[props]]` | **The prop board** (new notes): every posted line, `direction` over / under / **pass**; a pass carries no `confidence`. The page says "N calls out of M evaluated"; make pass common | **Calls yes**; a pass is recorded as evaluated, never graded |
| `[[falsifiers]]` | `condition` / `consequence`: what would change the read, written before kickoff as things to watch | — |
| `[[preline]]` | Directional reads written **before a line was posted**: `market` free text, `direction` over / under / avoid | **No** — no number |
| `[[leans]]` | *(older notes)* Calls against posted lines, ranked: `stat`, `line`, `direction` over / under, `confidence` high / moderate / low, `why` | **Yes** |
| `[[volume]]` | *(older notes)* Every posted attempts, completions or receptions line not already called in the two lists above; same fields, `stat` limited to `passing_att`, `passing_comp`, `receptions`, `rushing_att` | **Yes**, and the ledger also reports all volume calls together |
| `[[overs]]` | *(older notes)* The separate block at the foot, looking for overs in the posted lines; same fields, `direction` must be `over` | **Yes**, kept apart in the ledger |
| `[[sources]]` | `title`, `url` | — |

Rules:

- **Description, never forecast, and sourced.** Availability comes from the official
  injury report; roster changes and quotes from reporting named in the sources. Nothing
  here is consumed by scoring — the leans are a person's calls, and the page says so.
- **Statuses**: `Out`, `PUP`, `IR`, `Departed`, `Suspended` remove a player from the
  engine's spotlights (the 2025 feed cannot see an offseason). `Questionable` and
  `Doubtful` are shown and do nothing else. Player names must match the feed's and the
  box score's spelling (`Kenneth Walker III`, not `Ken Walker`).
- **Gradeable stats** are the keys of `LEAN_STATS` in `services/nfl_game_notes.py`:
  `passing_yds`, `passing_att`, `passing_comp`, `passing_td`, `passing_int`,
  `rushing_yds`, `rushing_att`, `receptions`, `receiving_yds`. A touchdown or a
  field-goal call belongs in `[[preline]]`, where nothing is graded.
- **Every posted pass-attempts and receptions line gets a call, every week** — in the
  leans, the overs, or the volume board — so the volume record is complete rather than
  a selection of the ones that looked good.
- **Say a thing once.** A thesis established in Tonight's matchup is referenced by a prop
  row, not re-explained: "secondary issue established above; pressure is the limiter;
  volume makes the over playable." Each section adds something, or it is cut.
- **Record and grade**: `python -m scripts.nfl_leans record` after writing or editing
  (idempotent; a grade already applied is kept), `grade` once the game is final. The
  daily run does both.
- A malformed file fails the build loudly (`tests/test_nfl_game_notes.py`), by design.

This is the seam a collector would fill: ESPN's injury report and roster are the
obvious pipe. Until then a note is written the day of the game and dated.
