from __future__ import annotations

from datetime import date, timedelta
from html import escape
from pathlib import Path
import re
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from styles import load_css
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

load_css()


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

