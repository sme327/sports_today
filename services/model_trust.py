"""The Performance page's conclusions — is there signal, where, and how much to trust it.

**Why this is a service and not a renderer.** Every sentence and every classification here
is a *judgement about the model*, and a judgement has to be testable without going through
HTML. `components/results_feed` renders what this module decides; nothing here emits markup.

**The one rule the whole module obeys: a hit rate is meaningless on its own.**
`services/base_rates` explains why at length — a batter getting 1+ hit happens ~61% of the
time unprompted, a starter striking out 8+ happens ~13% of the time, and ranked against one
shared average the rare-event markets look bad no matter how well they are picked. So every
verdict below is stated in **lift over the market's own base rate**, gated on **sample
size**, and only then coloured by **recent trend**. A market is never called strong for
converting often, and never called weak for converting rarely.

Nothing here forecasts. "Assists carry the strongest edge" is a statement about 179 graded
predictions, not a claim about tomorrow's.
"""

from __future__ import annotations

# Thresholds. Deliberately blunt: the page is a trust dashboard, and a classification that
# moves on a 0.3-point difference is not a trust signal, it is noise with a label.
MIN_SAMPLE = 30          # matches services.grading.MIN_SAMPLE — below this, say so
STRONG_SAMPLE = 100      # "strong" needs more than the bare minimum to be believable
STRONG_LIFT = 0.10       # +10 points over base = the curation floor's own design target
PROMISING_LIFT = 0.05    # the starvation flag's threshold, reused: a real but smaller edge
FLAT_LIFT = 0.02         # inside ±2 points is no measured edge in either direction
COOLING_LIFT = 0.15      # a fall this large demotes a strong market to "watch"

TIERS: list[tuple[str, str, str]] = [
    ("strong", "Strong signal", "Beats its own base rate by 10+ points on a real sample."),
    ("promising", "Promising", "A measurable edge, on a smaller sample or a smaller margin."),
    ("watch", "Watch", "No measured edge either way — or an edge that has fallen sharply."),
    ("weak", "No signal", "At or below the rate the market converts without us."),
    ("early", "Too early to say", "Too few graded predictions to judge. Not a verdict."),
]


def pts(value: float | None, *, signed: bool = True) -> str:
    """A percentage-point difference, in the one unit this page uses: points."""
    if value is None:
        return "—"
    sign = "+" if (signed and value >= 0) else ""
    return f"{sign}{value * 100:.1f} pts"


def _served(item: dict) -> tuple[int, float | None]:
    """The served sample and its lift — what the page's other tables actually read."""
    return item.get("served_n") or 0, item.get("served_lift")


# --------------------------------------------------------------- trust board ---
def classify(coverage: list[dict], trend: dict[str, float] | None = None) -> list[dict]:
    """Each market sorted into one trust tier, from the diagnostics already on the page.

    ``coverage`` rows come from ``web.analytics.performance_context`` (label, recorded and
    served n/lift, plus the starvation basis). ``trend`` maps label → change in served lift
    against the previous period of the same length, when both periods have a real sample.

    **Judged on the served props, not on everything recorded.** The tier answers "how much
    should I trust what this page shows me", and every other table here reads served rows.
    A market whose scale cannot reach the floor is a *scoring* problem, and it is reported
    as one: the recorded edge stays visible in "What's working" and the row is annotated
    ``starved`` rather than promoted on the strength of props nobody was ever offered.

    Sample size can only demote. A +41.8-point edge on 22 graded props is "too early to
    say", never "strong" — that is the whole discipline of this page.
    """
    trend = trend or {}
    out: list[dict] = []
    for item in coverage:
        label = item["label"]
        n, lift = _served(item)
        delta = trend.get(label)
        notes: list[str] = []

        if lift is None or n < MIN_SAMPLE:
            # The tier's own blurb already says "too few graded predictions", and the chip
            # carries n — a third statement of the same fact is noise.
            tier = "early"
            if not n:
                notes.append("nothing served yet")
        elif lift < -FLAT_LIFT:
            tier = "weak"
        elif lift < PROMISING_LIFT:
            tier = "watch"
        elif lift < STRONG_LIFT or n < STRONG_SAMPLE:
            tier = "promising"
            if n < STRONG_SAMPLE:
                notes.append(f"n={n:,}")
        else:
            tier = "strong"
            # A strong tier that has given most of its edge back is not a strong tier. The
            # demotion needs both periods to carry a real sample, or a quiet fortnight
            # would read as a broken model.
            if delta is not None and delta <= -COOLING_LIFT:
                tier = "watch"
                notes.append(f"edge down {pts(delta, signed=False)} on the previous period")

        if delta is not None and tier != "watch":
            if delta >= COOLING_LIFT:
                notes.append(f"improving, {pts(delta)}")
            elif delta <= -COOLING_LIFT:
                notes.append(f"cooling, {pts(delta)}")
        if item.get("starved"):
            notes.append("edge measured but rarely offered")
        out.append({"label": label, "tier": tier, "lift": lift, "n": n,
                    "note": " · ".join(notes)})
    order = {key: index for index, (key, _, _) in enumerate(TIERS)}
    out.sort(key=lambda row: (order[row["tier"]], -(row["lift"] or -9)))
    return out


def trust_tiers(coverage: list[dict], trend: dict[str, float] | None = None) -> list[dict]:
    """``classify`` grouped into the non-empty tiers, in order. Empty tiers are dropped:
    an empty "Strong signal" heading claims the model was measured and found wanting, when
    the truth may be that nothing has enough data yet."""
    rows = classify(coverage, trend)
    groups = []
    for key, label, blurb in TIERS:
        members = [row for row in rows if row["tier"] == key]
        if members:
            groups.append({"key": key, "label": label, "blurb": blurb, "markets": members})
    return groups


# ------------------------------------------------------------- signal check ---
def signal_check(coverage: list[dict], overall: dict, overall_lift: float | None,
                 prior: dict, prior_lift: float | None, prior_label: str,
                 min_sample: int = MIN_SAMPLE) -> list[dict]:
    """Two or three observations, in the order a reader needs them: strongest, weakest,
    trend. Each narrates a figure computed elsewhere on the page and never computes its
    own — so the executive summary cannot disagree with the table that backs it.

    A category is omitted when the data does not support saying anything. Forcing all
    three produces sentences like "the weakest market is +24 over base", which reads as a
    criticism of a market that is doing well.
    """
    items: list[dict] = []
    ranked = [c for c in coverage
              if c.get("recorded_lift") is not None and (c.get("served_n") or 0) >= min_sample]

    if ranked:
        best = max(ranked, key=lambda c: c["served_lift"] or -9)
        n, lift = _served(best)
        if lift is not None and lift >= FLAT_LIFT:
            text = (f"is the strongest edge on this slate — {pts(lift)} over its own base "
                    f"rate across {n:,} graded predictions.")
            if best.get("starved"):
                share = n / best["recorded_n"] if best.get("recorded_n") else 0
                text = text[:-1] + (f", though only {share:.0%} of what it predicts ever "
                                    f"clears the curation floor.")
            items.append({"label": "Strongest", "subject": best["label"], "text": text})

        worst = min(ranked, key=lambda c: c["served_lift"] if c["served_lift"] is not None else 9)
        wn, wlift = _served(worst)
        if wlift is not None and worst["label"] != (items[0]["subject"] if items else None):
            if wlift < -FLAT_LIFT:
                items.append({"label": "Weakest", "subject": worst["label"],
                              "text": f"is running below the rate it converts without us "
                                      f"({pts(wlift)}, n={wn:,})."})
            elif wlift < PROMISING_LIFT:
                items.append({"label": "Weakest", "subject": worst["label"],
                              "text": f"shows no measured edge either way "
                                      f"({pts(wlift)} over base, n={wn:,})."})

    rate, prior_rate = overall.get("hit_rate"), prior.get("hit_rate")
    decided_prior = prior["hit"] + prior["miss"]
    if rate is not None and overall_lift is not None:
        text = f"Overall hit rate is {rate:.1%}, {pts(overall_lift)} over baseline"
        if prior_rate is not None and decided_prior >= min_sample:
            delta = (rate - prior_rate) * 100
            word = "up" if delta >= 0 else "down"
            text += f" — {word} {abs(delta):.1f} points on the {prior_label}"
            if prior_lift is not None:
                text += f", which ran {pts(prior_lift)}"
        items.append({"label": "Trend", "subject": None, "text": text + "."})
    return items


def what_this_means(coverage: list[dict], overall: dict, overall_lift: float | None,
                    min_sample: int = MIN_SAMPLE) -> str:
    """One sentence answering "so is it working?" — the whole point of the page.

    **A high hit rate is never allowed to stand in for skill here.** 1+ hit converts 66%
    against a 61% base rate; saying "66% accurate" about that is technically true and
    completely misleading, and it is the single easiest way for this page to flatter the
    model. So the sentence leads with the baseline-adjusted figure in every branch, and
    when the two disagree it says so explicitly.
    """
    rate = overall.get("hit_rate")
    decided = overall["hit"] + overall["miss"]
    if rate is None or decided < min_sample:
        return ("Too few graded predictions in this selection to say whether the model is "
                "showing signal. Widen the period or clear a filter.")
    if overall_lift is None:
        return (f"Hit rate is {rate:.1%}, but no base rate could be measured for this "
                f"selection, so there is nothing to judge it against.")

    strong = [c for c in coverage
              if (c.get("served_lift") or 0) >= STRONG_LIFT
              and (c.get("served_n") or 0) >= min_sample]
    strong.sort(key=lambda c: -(c["served_lift"] or 0))
    names = [c["label"] for c in strong[:2]]
    served_total = sum((c.get("served_n") or 0) for c in coverage)
    concentrated = (served_total and strong
                    and sum(c["served_n"] for c in strong) / served_total < 0.35)

    if overall_lift < FLAT_LIFT:
        tail = (f" The edge that exists is concentrated in {_join(names)}, which is a small "
                f"share of what gets served." if strong else "")
        return (f"Raw hit rate is {rate:.1%}, but performance is not materially above "
                f"baseline for this cohort ({pts(overall_lift)}).{tail}")
    if overall_lift < STRONG_LIFT:
        if concentrated:
            return (f"Accuracy is {pts(overall_lift)} above baseline overall, but most of "
                    f"that edge is concentrated in {_join(names)} rather than spread across "
                    f"the slate.")
        return (f"The model is modestly ahead of baseline over this period "
                f"({pts(overall_lift)} on {decided:,} graded predictions)"
                + (f", with the clearest separation in {_join(names)}." if names else "."))
    return (f"The model is showing meaningful predictive signal over this period — "
            f"{pts(overall_lift)} over baseline on {decided:,} graded predictions"
            + (f", with the strongest separation in {_join(names)}." if names else "."))


def _join(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


# ------------------------------------------------------------- calibration ---
def calibration_conclusions(bands: dict, band_base: dict | None = None,
                            overall_lift: float | None = None) -> list[str]:
    """Does a higher score actually mean a better outcome? Two or three plain findings.

    **Read in lift, not in raw rate.** The 99–100 band is almost purely 1+ hit while the
    70–74 band is half WNBA and SP lines, so a raw-rate reading of this table cannot tell
    a well-scored band from a band full of common events. That distinction is the entire
    diagnostic.

    Deliberately refuses to describe a monotonic relationship the sample cannot support:
    the wording tops out at "directionally useful" unless every adjacent step rises.
    """
    band_base = band_base or {}
    reliable = [(label, tally) for label, tally in bands.items()
                if not tally.get("small_sample") and tally["hit_rate"] is not None]
    small = [label for label, tally in bands.items()
             if tally.get("small_sample") and (tally["hit"] + tally["miss"]) > 0]
    if len(reliable) < 2:
        out = ["Not enough graded predictions yet to judge whether higher scores perform "
               "better."]
        if small:
            out.append(f"The {_join(small)} band{'s' if len(small) > 1 else ''} "
                       f"{'remain' if len(small) > 1 else 'remains'} too small to read.")
        return out

    have_base = all(band_base.get(label) is not None for label, _ in reliable)
    values = ([tally["hit_rate"] - band_base[label] for label, tally in reliable] if have_base
              else [tally["hit_rate"] for _, tally in reliable])
    labels = [label for label, _ in reliable]
    unit = "over base" if have_base else "hit rate"
    out: list[str] = []

    span = values[-1] - values[0]
    rising_steps = sum(1 for a, b in zip(values, values[1:]) if b > a)
    steps = len(values) - 1
    if span > 0.03 and rising_steps == steps:
        out.append(f"Score is doing its job: every band above the last performs better "
                   f"{unit}, {pts(span)} from {labels[0]} to {labels[-1]}.")
    elif span > 0.03:
        out.append(f"Score is directionally useful, but not perfectly monotonic — "
                   f"{labels[-1]} runs {pts(span)} above {labels[0]} {unit}, with "
                   f"{steps - rising_steps} of {steps} steps going the wrong way.")
    elif span < -0.03:
        out.append(f"Higher score bands have not performed better in this sample: "
                   f"{labels[-1]} runs {pts(span)} against {labels[0]} {unit}.")
    else:
        out.append(f"Score is not separating outcomes in this sample — the top and bottom "
                   f"bands are within {abs(span) * 100:.1f} points of each other {unit}.")

    # The question a reader actually has about the top of the scale.
    high = [(label, tally) for label, tally in reliable if _band_floor(label) >= 90]
    if high and have_base:
        hit = sum(tally["hit"] for _, tally in high)
        miss = sum(tally["miss"] for _, tally in high)
        pooled = sum((tally["hit_rate"] - band_base[label]) * (tally["hit"] + tally["miss"])
                     for label, tally in high) / max(hit + miss, 1)
        rest = [(label, tally) for label, tally in reliable if _band_floor(label) < 90]
        if rest:
            rest_n = sum(tally["hit"] + tally["miss"] for _, tally in rest)
            rest_lift = sum((tally["hit_rate"] - band_base[label]) * (tally["hit"] + tally["miss"])
                            for label, tally in rest) / max(rest_n, 1)
            gap = pooled - rest_lift
            if abs(gap) >= 0.03:
                word = "outperform" if gap > 0 else "underperform"
                out.append(f"Predictions scored 90+ {word} everything below them by "
                           f"{pts(abs(gap), signed=False)} over base (n={hit + miss:,}).")
            else:
                out.append(f"Predictions scored 90+ are not separating from lower-confidence "
                           f"ones ({pts(gap)} over base, n={hit + miss:,}).")

    # A flat stretch in the middle is a real, actionable finding about the scale.
    flat = _flat_run(labels, values)
    if flat:
        out.append(f"Scores between {flat[0]} and {flat[-1]} are not separating from each "
                   f"other.")
    if small:
        out.append(f"The {_join(small)} band{'s' if len(small) > 1 else ''} "
                   f"{'remain' if len(small) > 1 else 'remains'} small; read "
                   f"{'them' if len(small) > 1 else 'it'} as an observation, not a rate.")
    return out


def _band_floor(label: str) -> int:
    try:
        return int(label.split("–")[0].split("-")[0])
    except ValueError:
        return 0


def _flat_run(labels: list[str], values: list[float]) -> list[str]:
    """The longest run of 3+ adjacent bands whose lift spans under 3 points."""
    best: list[str] = []
    for start in range(len(values)):
        for end in range(start + 3, len(values) + 1):
            window = values[start:end]
            if max(window) - min(window) < 0.03 and (end - start) > len(best):
                best = labels[start:end]
    return best


# ------------------------------------------------------- direction + windows ---
def direction_conclusion(over: tuple[float, int] | None, under: tuple[float, int] | None,
                         min_sample: int = MIN_SAMPLE) -> str:
    """One sentence on Over vs Under, in lift over each side's own base rate.

    The two sides do **not** share a base event rate across the market mix — Over props are
    mostly 1+ hit at a 61% base, Under props are mostly SP hits allowed at 48% — so a raw
    hit-rate comparison here says almost nothing about the model. Sample asymmetry is
    stated whenever it is large, because it usually is.
    """
    if not over or not under or not over[1] or not under[1]:
        side = "Over" if over and over[1] else "Under" if under and under[1] else None
        if side is None:
            return ""
        lift, n = over if side == "Over" else under
        return (f"Only {side} predictions were served in this selection "
                f"({pts(lift)} over base, n={n:,}), so the two sides cannot be compared.")
    (strong_label, (strong_lift, strong_n)), (weak_label, (weak_lift, weak_n)) = (
        (("Over", over), ("Under", under)) if over[0] >= under[0]
        else (("Under", under), ("Over", over)))
    gap = (strong_lift - weak_lift) * 100
    text = (f"{strong_label} signals are outperforming {weak_label} by {gap:.1f} points of "
            f"lift ({pts(strong_lift)} against {pts(weak_lift)}).")
    if min(strong_n, weak_n) < min_sample:
        text += (f" The {weak_label.lower() if weak_n < strong_n else strong_label.lower()} "
                 f"side has only {min(strong_n, weak_n):,} graded predictions, so treat the "
                 f"gap as an observation.")
    elif max(strong_n, weak_n) >= 3 * min(strong_n, weak_n):
        text += (f" Sample sizes differ substantially ({strong_n:,} against {weak_n:,}), "
                 f"which is a fact about what the slate offers, not about the sides.")
    return text


def consistency_conclusion(windows: list[dict], min_sample: int = MIN_SAMPLE) -> str:
    """Is performance stable? Read off the same windows the row displays.

    Stability is judged on the spread of the windows that carry a real sample, not on the
    latest one moving — a 30-day figure that wanders three points inside a band that spans
    three points is stable, and calling that a decline would be noise with a headline.
    """
    usable = [w for w in windows
              if w["tally"]["hit_rate"] is not None
              and (w["tally"]["hit"] + w["tally"]["miss"]) >= min_sample]
    if len(usable) < 2:
        return ""
    rates = [w["tally"]["hit_rate"] for w in usable]
    low, high = min(rates), max(rates)
    band = f"{low:.0%}–{high:.0%}" if high - low >= 0.01 else f"{low:.0%}"
    latest = usable[0]
    baseline = usable[-1]
    delta = (latest["tally"]["hit_rate"] - baseline["tally"]["hit_rate"]) * 100
    if high - low < 0.04:
        return (f"Performance has been stable around {band} across every window with a "
                f"real sample.")
    word = "stronger" if delta > 0 else "weaker"
    return (f"Performance spans {band} across these windows, with {latest['label']} "
            f"{abs(delta):.1f} points {word} than {baseline['label'].lower()}.")


# ---------------------------------------------------------- model versions ---
def version_summary(groups: list[dict]) -> str:
    """"N of M current model versions are outperforming the versions they replaced."

    **Never frames an update as an improvement on its own.** A version that lost ground is
    counted as having lost ground, and when the sample is too small to tell, it is counted
    as neither. The whole reason to keep superseded engines on this page is that the answer
    is sometimes no.
    """
    comparable = [g for g in groups
                  if not g.get("retired") and g.get("current")
                  and g.get("change_vs_previous") is not None]
    if not comparable:
        live = [g for g in groups if not g.get("retired") and g.get("current")]
        if live:
            return (f"{len(live)} live model version{'s' if len(live) != 1 else ''}, none yet "
                    f"with a comparable predecessor on this ledger.")
        return ""
    better = [g for g in comparable if g["change_vs_previous"] > 0]
    worse = [g for g in comparable if g["change_vs_previous"] < 0]
    text = (f"{len(better)} of {len(comparable)} current model versions are outperforming "
            f"the versions they replaced")
    if worse:
        names = _join([g["label"] for g in worse])
        text += f"; {names} {'is' if len(worse) == 1 else 'are'} behind"
    small = [g for g in comparable if g.get("comparison_small")]
    if small:
        text += (f". {_join([g['label'] for g in small])} "
                 f"{'rests' if len(small) == 1 else 'rest'} on a sample too small to call")
    return text + "."
