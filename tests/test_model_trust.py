"""The Performance page's conclusions, tested as claims rather than as markup.

Every test here is one way the page could flatter the model. The synthesis is the part of
the surface a reader trusts *instead of* reading the tables, so the failure mode is not a
broken layout — it is a confident sentence that is wrong.
"""

from __future__ import annotations

from services import model_trust


def _tally(hit, miss, rate=None, void=0, pending=0, small=False):
    decided = hit + miss
    out = {"hit": hit, "miss": miss, "void": void, "pending": pending,
           "hit_rate": (rate if rate is not None else (hit / decided if decided else None))}
    if small:
        out["small_sample"] = True
    return out


def _market(label, served_n, served_lift, recorded_n=None, recorded_lift=None, **extra):
    item = {"label": label, "served_n": served_n, "served_lift": served_lift,
            "recorded_n": recorded_n if recorded_n is not None else served_n,
            "recorded_lift": recorded_lift if recorded_lift is not None else served_lift}
    item.update(extra)
    return item


# --- the trust board ----------------------------------------------------------------

def test_a_huge_edge_on_a_tiny_sample_is_never_called_strong():
    """`batter_k` ran +41.8 over base on 22 graded props. Sorted on the number alone it
    outranks a market with 1,403 — which is the single easiest way for this page to
    mislead, and the reason sample can only ever demote."""
    tiers = {g["key"]: g for g in model_trust.trust_tiers([
        _market("Batter Ks", 22, 0.418),
        _market("Batter Hits", 1403, 0.057),
    ])}
    assert [m["label"] for m in tiers["early"]["markets"]] == ["Batter Ks"]
    assert "strong" not in tiers


def test_a_high_hit_rate_market_is_classified_on_lift_not_on_conversion():
    """1+ hit converts 66% and assists 62%; against their own base rates that ordering is
    the wrong way round. The tier must follow the base-rate comparison."""
    tiers = {g["key"]: g for g in model_trust.trust_tiers([
        _market("Batter Hits", 1403, 0.057),     # 66.4% against a 61% base
        _market("Assists", 128, 0.299),          # 62.5% against a 33% base
    ])}
    assert [m["label"] for m in tiers["strong"]["markets"]] == ["Assists"]
    assert [m["label"] for m in tiers["promising"]["markets"]] == ["Batter Hits"]


def test_a_flat_market_is_watch_and_a_losing_one_is_no_signal():
    """"No measured edge" and "below the rate it converts without us" are different
    findings, and reading them as the same thing retires the wrong market."""
    tiers = {g["key"]: g for g in model_trust.trust_tiers([
        _market("SP Hits Allowed", 340, 0.015),
        _market("Something Bad", 340, -0.06),
    ])}
    assert [m["label"] for m in tiers["watch"]["markets"]] == ["SP Hits Allowed"]
    assert [m["label"] for m in tiers["weak"]["markets"]] == ["Something Bad"]


def test_a_strong_market_that_has_given_its_edge_back_is_demoted_to_watch():
    tiers = {g["key"]: g for g in model_trust.trust_tiers(
        [_market("Points", 194, 0.251)], {"Points": -0.20})}
    assert "strong" not in tiers
    assert tiers["watch"]["markets"][0]["label"] == "Points"
    assert "edge down" in tiers["watch"]["markets"][0]["note"]


def test_empty_tiers_are_dropped_rather_than_rendered_empty():
    """An empty "Strong signal" heading reads as a measured finding. Usually it is just
    missing data, and the two must not look alike."""
    keys = [g["key"] for g in model_trust.trust_tiers([_market("Assists", 128, 0.299)])]
    assert keys == ["strong"]


def test_the_board_reads_the_stamped_starvation_flag_rather_than_guessing():
    board = model_trust.classify([_market("Batter Ks", 200, 0.30, starved=True)])
    assert "rarely offered" in board[0]["note"]


# --- the signal check ---------------------------------------------------------------

def test_the_weakest_clause_is_omitted_when_every_market_is_doing_well():
    """Forcing all three categories produces "the weakest market is +24 over base", which
    reads as criticism of a market that is working."""
    items = model_trust.signal_check(
        [_market("Assists", 128, 0.299), _market("Rebounds", 157, 0.334)],
        _tally(100, 50), 0.11, _tally(0, 0), None, "previous 30 days")
    assert [i["label"] for i in items] == ["Strongest", "Trend"]


def test_the_strongest_clause_ignores_a_market_too_small_to_lead():
    items = model_trust.signal_check(
        [_market("Batter Ks", 22, 0.418), _market("Rebounds", 157, 0.334)],
        _tally(100, 50), 0.11, _tally(0, 0), None, "previous 30 days")
    assert items[0]["subject"] == "Rebounds"


def test_a_starved_leader_says_so_in_the_same_breath():
    """"Batter Ks carries the strongest edge" is true and useless if 12% of it is ever
    offered. The caveat belongs in the sentence, not in a table three screens down."""
    items = model_trust.signal_check(
        [_market("Batter Ks", 40, 0.30, recorded_n=400, recorded_lift=0.16, starved=True)],
        _tally(100, 50), 0.11, _tally(0, 0), None, "previous 30 days")
    assert "clears the curation floor" in items[0]["text"]


# --- what this means ----------------------------------------------------------------

def test_a_high_hit_rate_over_a_high_base_is_not_reported_as_skill():
    """The central claim the page must never make. 63% looks strong; +1.2 over a 62% base
    is not, and the sentence has to lead with the second."""
    said = model_trust.what_this_means(
        [_market("Batter Hits", 1403, 0.012)], _tally(1717, 1006, 0.631), 0.012)
    assert "not materially above baseline" in said
    assert "63.1%" in said


def test_a_concentrated_edge_is_described_as_concentrated():
    said = model_trust.what_this_means(
        [_market("Assists", 128, 0.30), _market("Rebounds", 157, 0.33),
         _market("Batter Hits", 1403, 0.02)],
        _tally(1000, 600, 0.625), 0.07)
    assert "concentrated in" in said


def test_too_little_data_is_said_plainly_rather_than_scored():
    said = model_trust.what_this_means([], _tally(6, 4, 0.60), 0.10)
    assert "Too few graded predictions" in said


def test_a_missing_base_rate_is_stated_not_silently_treated_as_zero():
    said = model_trust.what_this_means([], _tally(100, 60, 0.625), None)
    assert "nothing to judge it against" in said


# --- score calibration --------------------------------------------------------------

def test_a_non_monotonic_ladder_is_not_described_as_monotonic():
    """The real ladder dips at 85–94 and recovers. "Higher scores perform better" is too
    strong a claim for that shape, and the wording has to stop at "directionally useful"."""
    bands = {"70–74": _tally(448, 235, 0.656), "75–79": _tally(271, 177, 0.605),
             "80–84": _tally(100, 49, 0.671), "99–100": _tally(262, 161, 0.619)}
    base = {"70–74": 0.58, "75–79": 0.58, "80–84": 0.56, "99–100": 0.36}
    reads = " ".join(model_trust.calibration_conclusions(bands, base))
    assert "not perfectly monotonic" in reads


def test_a_clean_ladder_is_allowed_to_say_so():
    bands = {"70–74": _tally(60, 40, 0.60), "80–84": _tally(65, 35, 0.65),
             "99–100": _tally(70, 30, 0.70)}
    base = {"70–74": 0.55, "80–84": 0.52, "99–100": 0.48}
    reads = " ".join(model_trust.calibration_conclusions(bands, base))
    assert "every band above the last performs better" in reads


def test_the_top_of_the_scale_is_reported_against_everything_below_it():
    bands = {"70–74": _tally(60, 40, 0.60), "90–94": _tally(70, 30, 0.70)}
    base = {"70–74": 0.58, "90–94": 0.40}
    reads = " ".join(model_trust.calibration_conclusions(bands, base))
    assert "90+" in reads and "outperform" in reads


def test_calibration_refuses_to_read_a_sample_that_cannot_support_it():
    bands = {"70–74": _tally(4, 3, 0.571, small=True)}
    reads = model_trust.calibration_conclusions(bands, {"70–74": 0.55})
    assert "Not enough graded predictions" in reads[0]


# --- direction, consistency, versions -----------------------------------------------

def test_over_under_is_compared_in_lift_and_names_the_sample_gap():
    said = model_trust.direction_conclusion(over=(0.126, 2245), under=(0.041, 478))
    assert "Over signals are outperforming Under" in said
    assert "Sample sizes differ substantially" in said


def test_one_sided_direction_data_says_the_comparison_cannot_be_made():
    said = model_trust.direction_conclusion(over=(0.126, 2245), under=(0.0, 0))
    assert "cannot be compared" in said


def test_a_narrow_band_of_windows_is_called_stable_not_a_decline():
    """62.9 / 63.1 / 59.4 spans under four points. Calling the latest week a decline would
    be noise with a headline."""
    windows = [
        {"label": "Last 7", "tally": _tally(405, 239, 0.629)},
        {"label": "Last 30", "tally": _tally(1717, 1006, 0.631)},
        {"label": "All time", "tally": _tally(2403, 1465, 0.621)},
    ]
    assert "stable" in model_trust.consistency_conclusion(windows)


def test_versions_that_lost_ground_are_reported_as_having_lost_ground():
    """A model page that frames every update as an improvement is not a model page."""
    groups = [
        {"label": "MLB Batter Hits", "current": {"version": "batter-hit-v6"},
         "change_vs_previous": -0.026},
        {"label": "MLB SP Hits Allowed", "current": {"version": "sp-v4"},
         "change_vs_previous": 0.116},
    ]
    said = model_trust.version_summary(groups)
    assert said.startswith("1 of 2")
    assert "MLB Batter Hits is behind" in said


def test_a_version_with_no_comparable_predecessor_is_not_counted_either_way():
    said = model_trust.version_summary(
        [{"label": "MLB Batter Ks", "current": {"version": "batter-k-v2"},
          "change_vs_previous": None}])
    assert "none yet with a comparable predecessor" in said
