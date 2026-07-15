from __future__ import annotations

from datetime import date, timedelta
from html import escape
from pathlib import Path
import re
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.config import DB_PATH, CURRENT_FEED
from src.ingest import import_feed
from src.metrics import hitter_game_logs, load_pa, team_recent
from src.mlb_api import schedule as mlb_schedule
from src.wnba_api import schedule as wnba_schedule
from src.wnba_opportunity import load_logs as load_wnba_logs, score_wnba_opportunities
from src.world_cup_api import schedule as world_cup_schedule
from src.opportunity import score_hit_opportunities

PACIFIC = ZoneInfo("America/Los_Angeles")

st.set_page_config(
    page_title="Sports Hub — Today",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
:root {
  --bg:#0c0f12;
  --surface:#151a20;
  --surface-2:#1c2229;
  --surface-3:#242b33;
  --text:#f5f3ef;
  --text-2:#d7d2cb;
  --muted:#9ea5ac;
  --line:#303840;
  --orange:#ff7a1a;
  --orange-2:#ff9a52;
  --orange-soft:#3a2215;
  --green:#69d193;
  --red:#ff8c82;
  --blue:#77aef5;
}
html, body, [class*="css"] {
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.stApp {
  color:var(--text);
  background:
    radial-gradient(circle at 10% -10%, rgba(255,122,26,.10), transparent 25%),
    var(--bg);
}
.block-container {
  max-width:1160px;
  padding-top:1.5rem;
  padding-bottom:2rem;
}
[data-testid="stVerticalBlock"] { gap:.42rem; }
[data-testid="stElementContainer"] { margin-bottom:0 !important; }
#MainMenu, footer,
[data-testid="stDeployButton"],
[data-testid="stToolbar"],
[data-testid="stToolbarActions"],
.stAppDeployButton {
  display:none !important;
  visibility:hidden !important;
}
header[data-testid="stHeader"] {
  background:transparent !important;
  height:0 !important;
  min-height:0 !important;
}

.page-title {
  margin:0 0 .42rem;
  color:var(--orange);
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size:1.9rem;
  line-height:1.12;
  letter-spacing:-.018em;
  font-weight:800;
}
.title-bar {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:1rem;
  margin:0 0 .45rem;
}

/* Native Today / Tomorrow segmented control */
[data-testid="stSegmentedControl"] {
  width: 232px !important;
  margin-left:auto !important;
}
[data-testid="stSegmentedControl"] > div {
  gap:0 !important;
  padding:0 !important;
  border:1px solid var(--line) !important;
  border-radius:999px !important;
  overflow:hidden !important;
  background:var(--surface-2) !important;
}
[data-testid="stSegmentedControl"] button {
  flex:1 1 50% !important;
  min-width:0 !important;
  width:50% !important;
  height:2.35rem !important;
  margin:0 !important;
  padding:0 .85rem !important;
  border:0 !important;
  border-radius:0 !important;
  color:var(--text-2) !important;
  background:var(--surface-2) !important;
  box-shadow:none !important;
  font-size:.9rem !important;
  font-weight:900 !important;
}
[data-testid="stSegmentedControl"] button + button {
  border-left:1px solid var(--line) !important;
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"] {
  color:#1a0d05 !important;
  background:var(--orange) !important;
}
[data-testid="stSegmentedControl"] button[aria-pressed="false"]:hover {
  color:var(--text) !important;
  background:var(--surface-3) !important;
}
.status-banner {
  display:flex;
  align-items:center;
  gap:.55rem;
  margin:.18rem 0 1.25rem;
  padding:.68rem .8rem;
  color:#f0d99f;
  background:#211d13;
  border:1px solid #5b4928;
  border-radius:10px;
  font-size:.88rem;
  line-height:1.35;
}
.section-row {
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin:0 0 .52rem;
}
.section-row h2 {
  margin:0;
  color:var(--text);
  font-size:1.25rem;
  line-height:1.15;
  letter-spacing:-.025em;
  font-weight:900;
}
.section-count {
  color:var(--muted);
  font-size:.78rem;
  font-weight:700;
}

/* league toggle buttons */
div[data-testid="stHorizontalBlock"]:has(button[kind]) { gap:.55rem; }
div[data-testid="stButton"] > button {
  min-height:2.45rem;
  height:2.45rem;
  padding:0 1rem;
  border-radius:999px;
  font-size:.92rem;
  font-weight:850;
  box-shadow:none;
}
div[data-testid="stButton"] > button[kind="primary"] {
  color:#1a0d05;
  background:var(--orange);
  border:1px solid var(--orange-2);
}
div[data-testid="stButton"] > button[kind="secondary"] {
  color:var(--text-2);
  background:var(--surface-2);
  border:1px solid var(--line);
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
  color:var(--text);
  background:var(--surface-3);
  border-color:#4b5660;
}
div[data-testid="stButton"] > button p { font-size:inherit !important; font-weight:inherit !important; }
.filter-note {
  color:var(--muted);
  font-size:.76rem;
  margin:.16rem 0 .72rem;
}

.schedule-grid {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:.8rem;
  margin-bottom:1.45rem;
}
.game-link { text-decoration:none !important; color:inherit !important; }
.game-card {
  min-height:156px;
  padding:.9rem;
  border:1px solid var(--line);
  border-radius:14px;
  background:linear-gradient(145deg,var(--surface-2),var(--surface));
  transition:transform .15s ease, border-color .15s ease, background .15s ease;
}
.game-card:hover {
  transform:translateY(-2px);
  border-color:#596570;
  background:linear-gradient(145deg,#242b33,#171c21);
}
.game-top {
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:.75rem;
}
.league-name {
  color:var(--orange-2);
  font-size:.76rem;
  font-weight:900;
  letter-spacing:.04em;
}
.game-time { color:var(--text); font-size:.82rem; font-weight:850; }
.teams {
  display:grid;
  grid-template-columns:1fr auto 1fr;
  gap:.65rem;
  align-items:center;
}
.team {
  display:flex;
  align-items:center;
  gap:.58rem;
  min-width:0;
}
.team.home { justify-content:flex-end; text-align:right; }
.team-logo {
  width:42px;
  height:42px;
  object-fit:contain;
  flex:0 0 42px;
}
.team-name {
  color:var(--text);
  font-size:1.03rem;
  line-height:1.15;
  font-weight:900;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.at-sign { color:var(--muted); font-size:.82rem; font-weight:800; }
.game-meta {
  margin-top:.72rem;
  padding-top:.62rem;
  border-top:1px solid var(--line);
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:.7rem;
  color:var(--muted);
  font-size:.76rem;
  line-height:1.25;
}
.analysis-chip {
  color:#ffd4b3;
  background:var(--orange-soft);
  border-radius:999px;
  padding:.22rem .46rem;
  font-size:.68rem;
  font-weight:850;
  white-space:nowrap;
}

.op-list { border:1px solid var(--line); border-radius:12px; overflow:hidden; margin-bottom:1.1rem; }
.op-row {
  display:grid;
  grid-template-columns:52px minmax(180px,1.2fr) minmax(180px,1fr) minmax(180px,1fr);
  gap:.9rem;
  align-items:center;
  padding:.72rem .82rem;
  background:var(--surface);
}
.op-row + .op-row { border-top:1px solid var(--line); }
.op-row:hover { background:var(--surface-2); }
.op-score {
  width:42px;
  height:42px;
  display:grid;
  place-items:center;
  border-radius:10px;
  color:var(--orange-2);
  background:var(--orange-soft);
  font-size:1rem;
  font-weight:950;
}
.op-identity { display:flex; align-items:center; gap:.68rem; min-width:0; }
.op-team-logo {
  width:38px;
  height:38px;
  object-fit:contain;
  flex:0 0 38px;
}
.op-player { color:var(--text); font-size:.96rem; font-weight:900; }
.op-market { color:var(--text-2); font-size:.8rem; font-weight:800; margin-top:.08rem; }
.op-team { color:var(--muted); font-size:.74rem; margin-top:.1rem; }
.evidence-title { font-size:.65rem; font-weight:900; letter-spacing:.05em; text-transform:uppercase; margin-bottom:.12rem; }
.evidence-good .evidence-title { color:var(--green); }
.evidence-risk .evidence-title { color:var(--red); }
.evidence-body { color:var(--text-2); font-size:.78rem; line-height:1.35; }

.back-link { display:inline-block; color:var(--orange-2) !important; text-decoration:none !important; font-weight:850; font-size:.86rem; margin-bottom:.8rem; }
.detail-header {
  display:grid;
  grid-template-columns:1fr auto 1fr;
  align-items:center;
  gap:1rem;
  padding:1rem 1.1rem;
  background:var(--surface);
  border:1px solid var(--line);
  border-radius:14px;
  margin-bottom:.8rem;
}
.detail-team { display:flex; align-items:center; gap:.75rem; }
.detail-team.home { justify-content:flex-end; text-align:right; }
.detail-logo { width:54px; height:54px; object-fit:contain; }
.detail-name { color:var(--text); font-size:1.2rem; font-weight:950; }
.detail-sub { color:var(--muted); font-size:.78rem; margin-top:.15rem; }
.detail-at { color:var(--muted); font-size:1rem; font-weight:900; }

[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:.4rem; margin-top:.35rem; }
[data-testid="stTabs"] button { font-size:.92rem; font-weight:850; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:10px; overflow:hidden; }
[data-testid="stAlert"] { background:var(--surface) !important; border:1px solid var(--line) !important; color:var(--text) !important; }

@media (max-width:900px) {
  .schedule-grid { grid-template-columns:1fr; }
  .op-row { grid-template-columns:46px 1fr; }
  .evidence-good,.evidence-risk { grid-column:2; }
}
@media (max-width:650px) {
  .block-container { padding-left:.7rem; padding-right:.7rem; }
  .page-title { font-size:1.65rem; }
  .title-bar { align-items:flex-start; flex-direction:column; gap:.55rem; }
  [data-testid="stSegmentedControl"] { width:100% !important; }
  .team-logo { width:36px; height:36px; flex-basis:36px; }
  .op-team-logo { width:32px; height:32px; flex-basis:32px; }
  .team-name { font-size:.92rem; }
  .detail-header { grid-template-columns:1fr; text-align:left; }
  .detail-team.home { justify-content:flex-start; text-align:left; }
  .detail-at { display:none; }
}

/* Force Streamlit's selected date state to use Sports Hub orange hues. */
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-selected="true"],
[data-testid="stSegmentedControl"] label:has(input:checked),
[data-baseweb="button-group"] button[aria-pressed="true"] {
  color:#241006 !important;
  background:linear-gradient(180deg, #ff9a52 0%, #f47a24 100%) !important;
  border-color:#ffad72 !important;
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"] *,
[data-testid="stSegmentedControl"] button[aria-selected="true"] *,
[data-testid="stSegmentedControl"] label:has(input:checked) * {
  color:#241006 !important;
}


/* Final Today/Tomorrow treatment: orange joined capsule with angled seam. */
[data-testid="stSegmentedControl"] {
  width:250px !important;
  margin-left:auto !important;
}
[data-testid="stSegmentedControl"] > div {
  position:relative !important;
  display:flex !important;
  gap:0 !important;
  padding:0 !important;
  border:1px solid #544137 !important;
  border-radius:999px !important;
  overflow:hidden !important;
  background:#302722 !important;
  isolation:isolate !important;
}
[data-testid="stSegmentedControl"] > div::after {
  content:"" !important;
  position:absolute !important;
  z-index:10 !important;
  top:-9px !important;
  left:50% !important;
  width:1px !important;
  height:calc(100% + 18px) !important;
  background:#6c5144 !important;
  transform:rotate(25deg) !important;
  pointer-events:none !important;
}
[data-testid="stSegmentedControl"] button,
[data-testid="stSegmentedControl"] label {
  position:relative !important;
  flex:1 1 50% !important;
  min-width:0 !important;
  width:50% !important;
  height:2.45rem !important;
  margin:0 !important;
  border:0 !important;
  border-radius:0 !important;
  box-shadow:none !important;
  background:#302722 !important;
  color:#ddcfc5 !important;
  font-size:.94rem !important;
  font-weight:850 !important;
}
[data-testid="stSegmentedControl"] button:first-child,
[data-testid="stSegmentedControl"] label:first-child {
  clip-path:polygon(0 0,100% 0,91% 100%,0 100%) !important;
  margin-right:-.55rem !important;
  padding-right:1.35rem !important;
  z-index:2 !important;
}
[data-testid="stSegmentedControl"] button:last-child,
[data-testid="stSegmentedControl"] label:last-child {
  clip-path:polygon(9% 0,100% 0,100% 100%,0 100%) !important;
  margin-left:-.55rem !important;
  padding-left:1.35rem !important;
  z-index:1 !important;
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-selected="true"],
[data-testid="stSegmentedControl"] label:has(input:checked),
div[role="radiogroup"] label:has(input:checked) {
  color:#241006 !important;
  background:#F47A24 !important;
  background-color:#F47A24 !important;
  border-color:#FFAA70 !important;
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"] *,
[data-testid="stSegmentedControl"] button[aria-selected="true"] *,
[data-testid="stSegmentedControl"] label:has(input:checked) * {
  color:#241006 !important;
}


/* Branded Today / Tomorrow date switch */
.date-toggle-wrap {
  display:flex;
  justify-content:flex-end;
  align-items:center;
}
.date-toggle {
  position:relative;
  display:grid;
  grid-template-columns:1fr 1fr;
  width:270px;
  height:48px;
  overflow:hidden;
  border:1px solid #4b403b;
  border-radius:18px;
  background:#20242b;
  box-shadow:0 8px 24px rgba(0,0,0,.20);
}
.date-toggle::after {
  content:"";
  position:absolute;
  z-index:4;
  top:-10px;
  left:50%;
  width:2px;
  height:68px;
  background:#66554c;
  transform:rotate(23deg);
  transform-origin:center;
  pointer-events:none;
}
.date-toggle a {
  position:relative;
  z-index:2;
  display:flex;
  align-items:center;
  justify-content:center;
  color:#f1ece7 !important;
  text-decoration:none !important;
  font-size:1rem;
  font-weight:800;
  letter-spacing:-.01em;
  transition:background .15s ease,color .15s ease;
}
.date-toggle a:first-child {
  clip-path:polygon(0 0,100% 0,89% 100%,0 100%);
  padding-right:14px;
  margin-right:-10px;
}
.date-toggle a:last-child {
  clip-path:polygon(11% 0,100% 0,100% 100%,0 100%);
  padding-left:14px;
  margin-left:-10px;
}
.date-toggle a.active {
  color:#241006 !important;
  background:linear-gradient(180deg,#ff9b56 0%,#f47a24 100%);
}
.date-toggle a:not(.active):hover {
  background:#2a3038;
}

/* Compact status chip */
.status-chip {
  display:inline-flex;
  align-items:center;
  gap:.5rem;
  width:auto;
  max-width:100%;
  margin:.15rem 0 .85rem;
  padding:.48rem .78rem;
  border:1px solid rgba(244,122,36,.42);
  border-radius:999px;
  color:#e9d6c8;
  background:rgba(244,122,36,.10);
  font-size:.87rem;
  font-weight:700;
  line-height:1.2;
}
.status-chip .status-dot {
  width:.55rem;
  height:.55rem;
  flex:0 0 auto;
  border-radius:50%;
  background:#f47a24;
  box-shadow:0 0 0 3px rgba(244,122,36,.15);
}

/* Consistent league chips */
div[data-testid="stButton"] > button {
  min-width:126px !important;
  height:42px !important;
  padding:0 .95rem !important;
  border:1px solid #3b4652 !important;
  border-radius:999px !important;
  background:#20262f !important;
  color:#e7e9ed !important;
  font-size:.94rem !important;
  font-weight:800 !important;
  box-shadow:none !important;
}
div[data-testid="stButton"] > button:hover {
  border-color:#f47a24 !important;
  color:#ffffff !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
  border-color:#ff9e5d !important;
  background:#f47a24 !important;
  color:#241006 !important;
}

/* Stronger cross-sport opportunity identity */
.op-sport {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:30px;
  height:30px;
  margin-right:.15rem;
  border:1px solid #3f4853;
  border-radius:10px;
  background:#242a32;
  font-size:1.05rem;
}
.op-team-logo {
  width:38px !important;
  height:38px !important;
  object-fit:contain;
  border-radius:9px;
  background:rgba(255,255,255,.04);
}
.op-identity {
  display:flex;
  align-items:center;
  gap:.62rem;
}
.op-player {
  font-size:1.02rem !important;
  font-weight:850 !important;
}
.op-market {
  margin-top:.08rem;
  font-size:.92rem !important;
}
.op-team {
  margin-top:.14rem;
  color:#aeb6c2 !important;
  font-size:.80rem !important;
}


/* --- Focused UI refinement: quieter status, simpler games, less orange --- */

/* Compact warning/status treatment */
.status-chip {
  display:inline-flex !important;
  align-items:center !important;
  gap:.45rem !important;
  width:auto !important;
  max-width:min(760px, 100%) !important;
  margin:.10rem 0 1rem !important;
  padding:.42rem .72rem !important;
  border:1px solid #4b423a !important;
  border-radius:999px !important;
  color:#cfc6bf !important;
  background:#201d1a !important;
  font-size:.82rem !important;
  font-weight:650 !important;
  line-height:1.15 !important;
}
.status-chip .status-dot {
  width:.48rem !important;
  height:.48rem !important;
  flex:0 0 auto !important;
  border-radius:50% !important;
  background:#c89b6b !important;
  box-shadow:none !important;
}

/* Quieter league filter chips */
div[data-testid="stButton"] > button {
  border-color:#38414b !important;
  background:#20262d !important;
  color:#e1e4e8 !important;
}
div[data-testid="stButton"] > button:hover {
  border-color:#6c7682 !important;
  color:#ffffff !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
  border-color:#f09a5e !important;
  background:#f47a24 !important;
  color:#241006 !important;
}

/* Simpler game cards */
.schedule-grid {
  gap:1rem !important;
}
.game-card {
  min-height:188px !important;
  padding:1rem 1.05rem .95rem !important;
  border:1px solid #343c45 !important;
  border-top:1px solid #46505a !important;
  background:#1b2026 !important;
  box-shadow:none !important;
}
.game-card:hover {
  border-color:#56616d !important;
  transform:translateY(-1px) !important;
}
.game-top {
  margin-bottom:.7rem !important;
}
.league-name {
  color:#aeb7c2 !important;
  font-size:.76rem !important;
  letter-spacing:.02em !important;
  font-weight:750 !important;
}
.game-time {
  color:#f0f2f4 !important;
  font-size:.88rem !important;
  font-weight:800 !important;
}
.teams {
  gap:.65rem !important;
  margin:.1rem 0 .72rem !important;
}
.team img {
  width:44px !important;
  height:44px !important;
}
.team-name {
  font-size:1.02rem !important;
  font-weight:800 !important;
}
.at-sign {
  color:#87919c !important;
  font-size:.84rem !important;
}
.game-meta {
  align-items:center !important;
  gap:.7rem !important;
  padding-top:.72rem !important;
  border-top:1px solid #313943 !important;
  color:#aeb6c0 !important;
  font-size:.78rem !important;
  line-height:1.25 !important;
}
.game-meta > span:first-child {
  display:-webkit-box !important;
  overflow:hidden !important;
  -webkit-line-clamp:2 !important;
  -webkit-box-orient:vertical !important;
}
.analysis-chip {
  flex:0 0 auto !important;
  border:1px solid #3a434d !important;
  color:#cbd1d8 !important;
  background:#252c34 !important;
  font-size:.72rem !important;
  font-weight:750 !important;
}

/* Reduce decorative orange in game/opportunity content */
.game-card,
.op-row {
  border-left-color:#343c45 !important;
}
.op-score {
  color:#ff9a55 !important;
  background:#3a2418 !important;
}
.evidence-good .evidence-title {
  color:#6bc68f !important;
}
.evidence-risk .evidence-title {
  color:#ef8e86 !important;
}


/* Definitive compact status treatment */
.status-row {
  display:flex !important;
  justify-content:flex-start !important;
  align-items:center !important;
  width:100% !important;
  margin:.15rem 0 1rem !important;
  padding:0 !important;
  background:transparent !important;
  border:0 !important;
}
.status-row .status-chip {
  display:inline-flex !important;
  align-items:center !important;
  gap:.45rem !important;
  width:max-content !important;
  max-width:min(720px, 100%) !important;
  min-height:0 !important;
  margin:0 !important;
  padding:.42rem .72rem !important;
  border:1px solid #4b423a !important;
  border-radius:999px !important;
  background:#201d1a !important;
  color:#d7cec7 !important;
  box-shadow:none !important;
  font-size:.82rem !important;
  font-weight:650 !important;
  line-height:1.2 !important;
}
.status-row .status-dot {
  width:.46rem !important;
  height:.46rem !important;
  flex:0 0 .46rem !important;
  border-radius:50% !important;
  background:#c89b6b !important;
  box-shadow:none !important;
}

</style>
""",
    unsafe_allow_html=True,
)


def format_game_time(raw: str | None) -> str:
    if not raw:
        return "Time TBD"
    try:
        timestamp = pd.to_datetime(raw, utc=True).to_pydatetime().astimezone(PACIFIC)
        return timestamp.strftime("%-I:%M %p PT")
    except Exception:
        return str(raw)


def first_or_fallback(items: list[str], fallback: str) -> str:
    return items[0] if items else fallback


def league_toggle(label: str, state_key: str) -> None:
    active = bool(st.session_state.get(state_key, False))
    if st.button(label, key=f"toggle_{state_key}", type="primary" if active else "secondary", width="stretch"):
        st.session_state[state_key] = not active
        st.rerun()



MLB_TEAM_ALIASES = {
    "ARI": {"ARI", "Arizona Diamondbacks", "Diamondbacks"},
    "ATL": {"ATL", "Atlanta Braves", "Braves"},
    "BAL": {"BAL", "Baltimore Orioles", "Orioles"},
    "BOS": {"BOS", "Boston Red Sox", "Red Sox"},
    "CHC": {"CHC", "Chicago Cubs", "Cubs"},
    "CWS": {"CWS", "CHW", "Chicago White Sox", "White Sox"},
    "CIN": {"CIN", "Cincinnati Reds", "Reds"},
    "CLE": {"CLE", "Cleveland Guardians", "Guardians"},
    "COL": {"COL", "Colorado Rockies", "Rockies"},
    "DET": {"DET", "Detroit Tigers", "Tigers"},
    "HOU": {"HOU", "Houston Astros", "Astros"},
    "KC": {"KC", "KCR", "Kansas City Royals", "Royals"},
    "LAA": {"LAA", "Los Angeles Angels", "Angels"},
    "LAD": {"LAD", "Los Angeles Dodgers", "Dodgers"},
    "MIA": {"MIA", "Miami Marlins", "Marlins"},
    "MIL": {"MIL", "Milwaukee Brewers", "Brewers"},
    "MIN": {"MIN", "Minnesota Twins", "Twins"},
    "NYM": {"NYM", "New York Mets", "NY Mets", "Mets"},
    "NYY": {"NYY", "New York Yankees", "NY Yankees", "Yankees"},
    "ATH": {"ATH", "OAK", "Athletics", "Oakland Athletics"},
    "PHI": {"PHI", "Philadelphia Phillies", "Phillies"},
    "PIT": {"PIT", "Pittsburgh Pirates", "Pirates"},
    "SD": {"SD", "SDP", "San Diego Padres", "Padres"},
    "SEA": {"SEA", "Seattle Mariners", "Mariners"},
    "SF": {"SF", "SFG", "San Francisco Giants", "Giants"},
    "STL": {"STL", "St. Louis Cardinals", "Cardinals"},
    "TB": {"TB", "TBR", "Tampa Bay Rays", "Rays"},
    "TEX": {"TEX", "Texas Rangers", "Rangers"},
    "TOR": {"TOR", "Toronto Blue Jays", "Blue Jays"},
    "WSH": {"WSH", "WSN", "Washington Nationals", "Nationals"},
}

def normalize_team_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def canonical_mlb_team(value: object) -> str | None:
    token = normalize_team_token(value)
    if not token:
        return None
    for abbr, aliases in MLB_TEAM_ALIASES.items():
        if token in {normalize_team_token(alias) for alias in aliases}:
            return abbr
    return None

def pbp_team_values_for_schedule(pa: pd.DataFrame, games: list[dict]) -> list[str]:
    scheduled = set()
    for game in games:
        for key in ("away_abbr", "home_abbr", "away", "home", "away_short", "home_short"):
            team = canonical_mlb_team(game.get(key))
            if team:
                scheduled.add(team)
    if not scheduled or pa.empty:
        return []
    values = set()
    for column in ("batting_team", "pitching_team", "BATTING TEAM", "PITCHING TEAM"):
        if column in pa.columns:
            for raw in pa[column].dropna().astype(str).unique():
                if canonical_mlb_team(raw) in scheduled:
                    values.add(raw)
    return sorted(values)

def logo_or_blank(url: str | None, alt: str) -> str:
    if not url:
        return '<div class="team-logo"></div>'
    return f'<img class="team-logo" src="{escape(url, quote=True)}" alt="{escape(alt, quote=True)}">'


def detail_logo(url: str | None, alt: str) -> str:
    if not url:
        return '<div class="detail-logo"></div>'
    return f'<img class="detail-logo" src="{escape(url, quote=True)}" alt="{escape(alt, quote=True)}">'


def game_card(game: dict, league: str) -> str:
    away = game.get("away_short") or game.get("away") or "TBD"
    home = game.get("home_short") or game.get("home") or "TBD"
    away_logo = logo_or_blank(game.get("away_logo"), away)
    home_logo = logo_or_blank(game.get("home_logo"), home)
    time = format_game_time(game.get("game_date"))
    game_id = game.get("game_pk") if league == "MLB" else game.get("game_id")
    href = f"?day={quote_plus(query_day)}&league={quote_plus(league)}&game={quote_plus(str(game_id))}"

    if league == "MLB":
        away_pitcher = game.get("away_pitcher") or "TBD"
        home_pitcher = game.get("home_pitcher") or "TBD"
        meta = f"{away_pitcher} vs {home_pitcher}"
        chip = "Analysis"
        league_label = "⚾️ MLB"
    elif league == "WNBA":
        venue = game.get("venue") or "Venue TBD"
        broadcast = game.get("broadcast") or ""
        meta = venue if not broadcast else f"{venue} · {broadcast}"
        chip = "Schedule"
        league_label = "🏀 WNBA"
    else:
        meta_parts = [game.get("round") or "World Cup"]
        if game.get("venue"):
            meta_parts.append(game["venue"])
        meta = " · ".join(meta_parts)
        chip = "Match"
        league_label = "⚽ World Cup"

    return (
        f'<a class="game-link" href="{href}" target="_self"><div class="game-card">'
        f'<div class="game-top"><span class="league-name">{league_label}</span>'
        f'<span class="game-time">{escape(time)}</span></div>'
        f'<div class="teams"><div class="team">{away_logo}<span class="team-name">{escape(away)}</span></div>'
        f'<div class="at-sign">@</div>'
        f'<div class="team home"><span class="team-name">{escape(home)}</span>{home_logo}</div></div>'
        f'<div class="game-meta"><span>{escape(meta)}</span><span class="analysis-chip">{escape(chip)}</span></div>'
        f'</div></a>'
    )


if not DB_PATH.exists():
    st.markdown('<div class="page-title">Today’s Sports Slate</div>', unsafe_allow_html=True)
    st.warning("No Sports Hub database exists yet.")
    feed = st.text_input("Current MLB workbook", value=str(CURRENT_FEED))
    if st.button("Import workbook", type="primary"):
        try:
            _, summary = import_feed(Path(feed).expanduser())
            st.success(f"Imported {summary['plate_appearances']:,} plate appearances from {summary['games']:,} games.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    st.stop()


@st.cache_data(show_spinner=False, ttl=900)
def cached_wnba_logs() -> pd.DataFrame:
    return load_wnba_logs()


@st.cache_data(show_spinner=False)
def data() -> pd.DataFrame:
    return load_pa()


pa = data()
wnba_logs = cached_wnba_logs()
latest = pa["game_date"].max().date()

initial_query_day = st.query_params.get("day", "today")
if initial_query_day not in {"today", "tomorrow"}:
    initial_query_day = "today"

if "selected_day" not in st.session_state:
    st.session_state.selected_day = "Tomorrow" if initial_query_day == "tomorrow" else "Today"

query_day = st.query_params.get("day", "today")
if query_day not in {"today", "tomorrow"}:
    query_day = "today"

selected_date = date.today() + (
    timedelta(days=1) if query_day == "tomorrow" else timedelta(0)
)
day_label = "Tomorrow" if query_day == "tomorrow" else "Today"
day_possessive = "Tomorrow’s" if query_day == "tomorrow" else "Today’s"

header_left, header_right = st.columns(
    [4.4, 1.45],
    vertical_alignment="center",
)
with header_left:
    st.markdown(
        f'<div class="page-title">{day_possessive} Sports Slate</div>',
        unsafe_allow_html=True,
    )
with header_right:
    today_class = "active" if query_day == "today" else ""
    tomorrow_class = "active" if query_day == "tomorrow" else ""
    st.markdown(
        '<div class="date-toggle-wrap"><div class="date-toggle">'
        f'<a class="{today_class}" href="?day=today" target="_self">Today</a>'
        f'<a class="{tomorrow_class}" href="?day=tomorrow" target="_self">Tomorrow</a>'
        '</div></div>',
        unsafe_allow_html=True,
    )

with st.sidebar:
    st.markdown("## 🟠 Sports Hub")
    st.caption(f"Viewing {day_label.lower()} · {selected_date:%A, %B %-d}")
    st.caption(f"MLB data through {latest:%B %-d, %Y}")
    if st.button("Refresh cached data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

try:
    mlb_games = mlb_schedule(selected_date)
    mlb_error = None
except Exception as exc:
    mlb_games = []
    mlb_error = str(exc)

try:
    wnba_games = wnba_schedule(selected_date)
    wnba_error = None
except Exception as exc:
    wnba_games = []
    wnba_error = str(exc)

try:
    world_cup_games = world_cup_schedule(selected_date)
    world_cup_error = None
except Exception as exc:
    world_cup_games = []
    world_cup_error = str(exc)

# Build the league list only after all schedule sources have loaded.
available_leagues: list[tuple[str, str, list[dict]]] = []
if mlb_games:
    available_leagues.append(("⚾️ MLB", "show_mlb", mlb_games))
if wnba_games:
    available_leagues.append(("🏀 WNBA", "show_wnba", wnba_games))
if world_cup_games:
    available_leagues.append(
        ("⚽ World Cup", "show_world_cup", world_cup_games)
    )

all_games = mlb_games + wnba_games + world_cup_games


query_game = st.query_params.get("game")
query_league = st.query_params.get("league")

# -------------------- GAME DEEP DIVE --------------------
if query_game and query_league:
    source = mlb_games if query_league == "MLB" else (wnba_games if query_league == "WNBA" else world_cup_games)
    game = next((g for g in source if str(g.get("game_pk") if query_league == "MLB" else g.get("game_id")) == str(query_game)), None)
    st.markdown(f'<a class="back-link" target="_self" href="?day={quote_plus(query_day)}">← Back to {day_label.lower()}’s slate</a>', unsafe_allow_html=True)
    if not game:
        st.error("This game could not be found for the selected date.")
        st.stop()

    away = game.get("away_short") or game.get("away") or "TBD"
    home = game.get("home_short") or game.get("home") or "TBD"
    away_sub = game.get("away") or away
    home_sub = game.get("home") or home
    st.markdown(
        f'<div class="detail-header">'
        f'<div class="detail-team">{detail_logo(game.get("away_logo"), away)}<div><div class="detail-name">{escape(away)}</div><div class="detail-sub">{escape(away_sub)}</div></div></div>'
        f'<div class="detail-at">@<div class="detail-sub">{escape(format_game_time(game.get("game_date")))}</div></div>'
        f'<div class="detail-team home"><div><div class="detail-name">{escape(home)}</div><div class="detail-sub">{escape(home_sub)}</div></div>{detail_logo(game.get("home_logo"), home)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if query_league in {"WNBA", "World Cup"}:
        label = "WNBA" if query_league == "WNBA" else "World Cup"
        st.info(f"{label} schedule navigation is live. Deeper team and player analysis is not connected yet.")
        st.stop()

    teams = [game.get("away"), game.get("home")]
    teams = [t for t in teams if t]
    teams_tab, players_tab = st.tabs(["Teams", "Players"])

    with teams_tab:
        cols = st.columns(2)
        for col, team in zip(cols, teams):
            with col:
                metrics = team_recent(pa, team, 10)
                st.subheader(team)
                if not metrics:
                    st.caption("No recent team data available.")
                else:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Hits/game", f"{metrics['hits_per_game']:.1f}")
                    m2.metric("TB/game", f"{metrics['tb_per_game']:.1f}")
                    m3.metric("K rate", f"{metrics['k_rate']:.1%}")
                    st.caption(f"Last {metrics['games']} games")
        st.warning("Sides and totals analysis will improve after probable pitchers, bullpen freshness, park, and weather are included.")

    with players_tab:
        opp = score_hit_opportunities(pa, teams)
        if opp.empty:
            st.info("No qualifying opportunities were found.")
        else:
            for _, row in opp.head(10).iterrows():
                support = list(row.support) if isinstance(row.support, list) else []
                risks = list(row.risks) if isinstance(row.risks, list) else []
                with st.expander(f"{int(row.opportunity_score)} · {row.player} — {row.market}"):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Opportunity", int(row.opportunity_score))
                    c2.metric("Stability", int(row.stability_score))
                    c3.metric("Last 25 PA hit rate", f"{row.last_25_hit_rate:.0%}")
                    c4.metric("PA/game", f"{row.pa_per_game:.2f}")
                    st.markdown("**Why it stands out**")
                    st.write(" · ".join(support) if support else "Current-season contact profile supports further review.")
                    st.markdown("**What could go wrong**")
                    st.write(" · ".join(risks) if risks else "Opponent and confirmed lineup context are incomplete.")
                    logs = hitter_game_logs(pa, int(row.batter_id), 10).copy()
                    if not logs.empty:
                        logs["game_date"] = pd.to_datetime(logs["game_date"]).dt.strftime("%b %-d")
                        logs = logs.rename(columns={"game_date":"Date","pitching_team":"Opponent","pa":"PA","hits":"H","total_bases":"TB","walks":"BB","strikeouts":"K","home_runs":"HR"})
                        st.dataframe(logs[["Date","Opponent","PA","H","TB","BB","K","HR"]], width="stretch", hide_index=True)
    st.stop()

# -------------------- TODAY / TOMORROW PAGE --------------------
unconfirmed_count = sum(1 for game in mlb_games if not game.get("away_pitcher") or not game.get("home_pitcher"))
if unconfirmed_count:
    status_text = f"{unconfirmed_count} MLB game{'s' if unconfirmed_count != 1 else ''} still has incomplete probable-pitcher context. MLB player rankings remain preliminary."
else:
    status_text = f"Probable pitchers are available for {day_label.lower()}’s MLB slate. Confirmed batting orders are not yet included."
st.markdown(
    '<div class="status-row">'
    '<div class="status-chip">'
    '<span class="status-dot"></span>'
    f'<span>{escape(status_text)}</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

if "show_mlb" not in st.session_state:
    st.session_state.show_mlb = False
if "show_wnba" not in st.session_state:
    st.session_state.show_wnba = False
if "show_world_cup" not in st.session_state:
    st.session_state.show_world_cup = False

if available_leagues:
    ratios = [1] * len(available_leagues) + [max(1, 7 - len(available_leagues))]
    filter_cols = st.columns(ratios, gap="small")
    for col, (label, key, _) in zip(filter_cols, available_leagues):
        with col:
            league_toggle(label, key)

active_keys = [key for _, key, _ in available_leagues if st.session_state.get(key, False)]
nothing_selected = not active_keys

visible_mlb = mlb_games if nothing_selected or st.session_state.show_mlb else []
visible_wnba = wnba_games if nothing_selected or st.session_state.show_wnba else []
visible_world_cup = world_cup_games if nothing_selected or st.session_state.show_world_cup else []

visible_games = (
    [(g, "MLB") for g in visible_mlb]
    + [(g, "WNBA") for g in visible_wnba]
    + [(g, "World Cup") for g in visible_world_cup]
)
visible_games.sort(
    key=lambda item: pd.to_datetime(
        item[0].get("game_date"),
        utc=True,
        errors="coerce",
    )
)

if mlb_error and (nothing_selected or st.session_state.show_mlb):
    st.info(f"MLB schedule could not be loaded: {mlb_error}")
if wnba_error and (nothing_selected or st.session_state.show_wnba):
    st.info(f"WNBA schedule could not be loaded: {wnba_error}")
if world_cup_error and (nothing_selected or st.session_state.show_world_cup):
    st.info(f"World Cup schedule could not be loaded: {world_cup_error}")

if visible_games:
    cards = "".join(game_card(game, league) for game, league in visible_games)
    st.markdown(f'<div class="schedule-grid">{cards}</div>', unsafe_allow_html=True)
else:
    st.info(f"No games were found for {day_label.lower()} with the selected league filters.")

# Top opportunities across sports currently shown.
all_opportunity_rows: list[dict] = []
opportunity_notes: list[str] = []

if visible_mlb:
    pbp_team_labels = pbp_team_values_for_schedule(pa, visible_mlb)
    mlb_opp = (
        score_hit_opportunities(pa, pbp_team_labels)
        if pbp_team_labels else pd.DataFrame()
    )
    if mlb_opp.empty and not pbp_team_labels:
        opportunity_notes.append(
            "MLB opportunity analysis is unavailable because the scheduled teams "
            "are not present in the imported play-by-play workbook."
        )
    else:
        mlb_team_logos: dict[str, str | None] = {}
        for game in visible_mlb:
            for side in ("away", "home"):
                for name_key in (side, f"{side}_short"):
                    name = game.get(name_key)
                    if name:
                        mlb_team_logos[str(name)] = game.get(f"{side}_logo")
        for _, row in mlb_opp.head(8).iterrows():
            support = list(row.support) if isinstance(row.support, list) else []
            risks = list(row.risks) if isinstance(row.risks, list) else []
            all_opportunity_rows.append({
                "league": "MLB",
                "score": int(row.opportunity_score),
                "stability": int(row.stability_score),
                "player": str(row.player),
                "market": str(row.market),
                "team": str(row.team),
                "image": mlb_team_logos.get(str(row.team)),
                "support": first_or_fallback(
                    support, "Current-season profile supports further review"
                ),
                "risk": first_or_fallback(
                    risks, "Opponent and lineup context are incomplete"
                ),
            })

if visible_wnba:
    scheduled_wnba_teams = {
        str(value)
        for game in visible_wnba
        for value in (
            game.get("away_abbr"), game.get("home_abbr"),
            game.get("away"), game.get("home"),
        )
        if value
    }
    wnba_opp = score_wnba_opportunities(
        wnba_logs,
        scheduled_wnba_teams,
    )
    if wnba_logs.empty:
        opportunity_notes.append(
            "WNBA player game logs have not been collected yet."
        )
    elif wnba_opp.empty:
        opportunity_notes.append(
            "No WNBA points, rebounds, or assists opportunities cleared the "
            "current role and sample requirements."
        )
    else:
        wnba_team_logos: dict[str, str | None] = {}
        for game in visible_wnba:
            for side in ("away", "home"):
                for name_key in (side, f"{side}_short", f"{side}_abbr"):
                    name = game.get(name_key)
                    if name:
                        wnba_team_logos[str(name)] = game.get(f"{side}_logo")
        for _, row in wnba_opp.head(8).iterrows():
            support = list(row.support) if isinstance(row.support, list) else []
            risks = list(row.risks) if isinstance(row.risks, list) else []
            image = row.headshot if isinstance(row.headshot, str) and row.headshot else (
                wnba_team_logos.get(str(row.team))
                or wnba_team_logos.get(str(row.team_abbr))
            )
            all_opportunity_rows.append({
                "league": "WNBA",
                "score": int(row.opportunity_score),
                "stability": int(row.stability_score),
                "player": str(row.player),
                "market": str(row.display_market),
                "team": str(row.team),
                "image": image,
                "support": first_or_fallback(
                    support, "Recent role and production support further review"
                ),
                "risk": first_or_fallback(
                    risks, "Injury and matchup context are not yet included"
                ),
            })

all_opportunity_rows.sort(
    key=lambda row: (row["score"], row["stability"]),
    reverse=True,
)

if visible_mlb or visible_wnba:
    leagues_with_analysis = []
    if visible_mlb:
        leagues_with_analysis.append("MLB")
    if visible_wnba:
        leagues_with_analysis.append("WNBA")
    st.markdown(
        '<div class="section-row"><h2>Top Opportunities</h2>'
        f'<span class="section-count">{" + ".join(leagues_with_analysis)} · preliminary</span></div>',
        unsafe_allow_html=True,
    )

    if all_opportunity_rows:
        rows_html = []
        for row in all_opportunity_rows[:8]:
            image_html = (
                f'<img class="op-team-logo" src="{escape(str(row["image"]), quote=True)}" '
                f'alt="{escape(row["team"], quote=True)}">'
                if row.get("image")
                else '<div class="op-team-logo"></div>'
            )
            rows_html.append(
                f'<div class="op-row">'
                f'<div class="op-score">{row["score"]}</div>'
                f'<div class="op-identity">'
                f'<span class="op-sport">{"⚾️" if row["league"] == "MLB" else "🏀" if row["league"] == "WNBA" else "⚽"}</span>'
                f'{image_html}<div>'
                f'<div class="op-player">{escape(row["player"])}</div>'
                f'<div class="op-market">{escape(row["market"])}</div>'
                f'<div class="op-team">{escape(row["team"])}</div>'
                f'</div></div>' 
                f'<div class="evidence-good"><div class="evidence-title">Why it stands out</div>'
                f'<div class="evidence-body">{escape(row["support"])}</div></div>'
                f'<div class="evidence-risk"><div class="evidence-title">What could go wrong</div>'
                f'<div class="evidence-body">{escape(row["risk"])}</div></div>'
                f'</div>'
            )
        st.markdown(
            f'<div class="op-list">{"".join(rows_html)}</div>',
            unsafe_allow_html=True,
        )
    elif opportunity_notes:
        for note in opportunity_notes:
            st.info(note)

