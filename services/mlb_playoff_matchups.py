"""Key Matchups for a postseason game: tactical questions, not prop questions.

On a postseason page the Prop Desk already answers "can Pivetta miss bats?" with the
evidence laid out, so Key Matchups stops asking it. It asks three questions about how the
*game* is likely to be played instead (decision log 2026-09-30):

1. **Can either lineup run up a starter's pitch count?** — each lineup's pitches per plate
   appearance against the starter's usual workload. A starter who averages 72 pitches is
   close to his hook after 18 batters; a patient lineup gets there sooner.
2. **Which lineup has the platoon advantage?** — how many of each lineup bat from the side
   opposite tonight's starter (switch hitters always do).
3. **Which bullpen is under more pressure?** — relief pitches each club has thrown over the
   last three days of the feed, and which relievers pitched on back-to-back days.

All three are counts from the play-by-play, worded as description. The bullpen question
names the dates it covers, because the feed runs a day behind and the answer goes stale
with it.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from domain.mlb_game_page import MLBKeyMatchup
from services.data_access import is_postseason
from services.mlb_prop_desk import PropDesk, Side, ends_plate_appearance, pitcher_appearances

_PATIENT = 0.08       # pitches per PA above the league before a lineup reads as patient


def _pitches_per_pa(pa: pd.DataFrame, batter_ids: set[str], hand: str | None) -> tuple[float, int]:
    rows = pa[pa["batter_id"].astype(str).isin(batter_ids) & ~is_postseason(pa)
              & ends_plate_appearance(pa)]
    if hand:
        rows = rows[rows["pitcher_hand"] == hand]
    pitches = pd.to_numeric(rows["pitch_count_pa"], errors="coerce").dropna()
    return (float(pitches.mean()) if len(pitches) else 0.0), len(pitches)


def _league_pitches_per_pa(pa: pd.DataFrame) -> float:
    rows = pa[~is_postseason(pa) & ends_plate_appearance(pa)]
    return float(pd.to_numeric(rows["pitch_count_pa"], errors="coerce").dropna().mean())


def pitch_count(pa: pd.DataFrame, desk: PropDesk) -> MLBKeyMatchup | None:
    league = _league_pitches_per_pa(pa)
    reads, chips, best = [], [], None
    for offense, defense in ((desk.away, desk.home), (desk.home, desk.away)):
        sp = defense.starter
        if sp is None or not offense.hitters:
            continue
        ppa, n = _pitches_per_pa(pa, {h.pid for h in offense.hitters}, sp.hand)
        if not n:
            continue
        reads.append(f"{offense.short}' nine see {ppa:.2f} pitches per plate appearance against "
                     f"{sp.throws}s (league {league:.2f}); {sp.name} averages "
                     f"~{sp.avg['pitches']:.0f} pitches and {sp.avg['bf']:.1f} batters a start")
        chips.append(f"{offense.short}: {ppa:.2f} P/PA")
        lift = ppa - league
        if lift >= _PATIENT and (best is None or lift > best[1]):
            best = (offense.short, lift)
    if not reads:
        return None
    return MLBKeyMatchup(
        title="Can either lineup run up a starter's pitch count?",
        advantage=best[0] if best else "Even",
        confidence="Moderate" if best else "Low",
        explanation=". ".join(reads) + ".",
        supporting_metrics=tuple(chips))


def _platoon_edge(side: Side, hand: str | None) -> tuple[int, int]:
    if not hand:
        return 0, len(side.hitters)
    edge = sum(1 for h in side.hitters if h.hand == "S" or (h.hand and h.hand != hand))
    return edge, len(side.hitters)


def platoon(desk: PropDesk) -> MLBKeyMatchup | None:
    pairs = []
    for offense, defense in ((desk.away, desk.home), (desk.home, desk.away)):
        sp = defense.starter
        if sp is None or not offense.hitters or not sp.hand:
            continue
        edge, n = _platoon_edge(offense, sp.hand)
        state = "confirmed" if offense.confirmed else "last game's"
        pairs.append((offense.short, edge, n, sp, state))
    if not pairs:
        return None
    explanation = "; ".join(
        f"{edge} of {n} in the {short}' {state} lineup bat from the other side of {sp.name} "
        f"({sp.throws})" for short, edge, n, sp, state in pairs) + ". Switch hitters count."
    advantage = "Even"
    if len(pairs) == 2 and abs(pairs[0][1] - pairs[1][1]) >= 2:
        advantage = max(pairs, key=lambda p: p[1])[0]
    return MLBKeyMatchup(
        title="Which lineup has the platoon advantage?",
        advantage=advantage,
        confidence="High" if all(p[4] == "confirmed" for p in pairs) else "Low",
        explanation=explanation,
        supporting_metrics=tuple(f"{short}: {edge}/{n}" for short, edge, n, _, _ in pairs),
        availability_note=None if all(p[4] == "confirmed" for p in pairs)
        else "Uses the last game's order where tonight's lineup is not posted.")


def bullpen(pa: pd.DataFrame, desk: PropDesk, days: int = 3) -> MLBKeyMatchup | None:
    if desk.data_through is None:
        return None
    start = desk.data_through - timedelta(days=days - 1)
    apps = pitcher_appearances(pa[pa["game_date"].dt.date >= start])
    if apps.empty:
        return None
    relief = apps[~apps["start"]]
    reads, chips, load = [], [], {}
    for side in (desk.away, desk.home):
        mine = relief[relief["team"] == side.team]
        pitches = int(mine["pitches"].sum())
        dates = mine.groupby("pitcher_id")["game_date"].apply(
            lambda d: sorted({pd.Timestamp(x).date() for x in d}))
        back_to_back = [pid for pid, ds in dates.items()
                        if any((b - a).days == 1 for a, b in zip(ds, ds[1:]))]
        names = mine.drop_duplicates("pitcher_id").set_index("pitcher_id")["pitcher_name"]
        b2b = ", ".join(str(names[p]).split()[-1] for p in back_to_back[:4])
        load[side.short] = pitches
        reads.append(f"{side.short} relievers ~{pitches} pitches"
                     + (f", with {b2b} on back-to-back days" if b2b else ""))
        chips.append(f"{side.short}: ~{pitches} relief pitches")
    span = f"{start.strftime('%b %-d')}–{desk.data_through.strftime('%-d')}"
    heavier = max(load, key=load.get)
    lighter = min(load, key=load.get)
    advantage = lighter if load[heavier] - load[lighter] >= 25 else "Even"
    return MLBKeyMatchup(
        title="Which bullpen is under more pressure?",
        advantage=advantage, confidence="Moderate",
        explanation="; ".join(reads) + f" ({span}).",
        supporting_metrics=tuple(chips),
        availability_note=(f"Through {desk.data_through.strftime('%b %-d')}, the feed's last "
                           "day. Relief pitches are reconstructed from play-by-play."))


def tactical(pa: pd.DataFrame, desk: PropDesk | None) -> tuple[MLBKeyMatchup, ...]:
    if desk is None or pa.empty:
        return ()
    pa = pa.assign(batter_id=pa["batter_id"].astype(str))
    out = (pitch_count(pa, desk), platoon(desk), bullpen(pa, desk))
    return tuple(m for m in out if m is not None)
