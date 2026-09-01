import json
import re
from pathlib import Path

import pytest

from web.management.commands.export_static import (
    canonical_url, output_path, public_href, should_crawl,
)
from scripts.publish_pages import validate_internal_links


def test_canonical_url_sorts_queries_and_rejects_external_links():
    assert canonical_url("?thr=90&day=today", "/") == "/?day=today&thr=90"
    assert canonical_url("https://example.com/") is None
    assert canonical_url("/static/app.css") is None
    assert canonical_url("?season=2025&amp;week=8", "/nfl/") == "/nfl/?season=2025&week=8"


def test_primary_export_paths_are_readable():
    assert output_path("/") == Path("index.html")
    assert output_path("/?day=tomorrow") == Path("tomorrow/index.html")
    assert output_path("/nfl/") == Path("nfl/index.html")
    query_path = output_path("/results/?date=2026-08-14")
    assert query_path.parts[:1] == ("view",)
    assert public_href(query_path) == f"/{query_path.parent.as_posix()}/"


def test_crawler_keeps_bounded_performance_controls_and_excludes_nfl_archive():
    """The NFL archive stays out of the static export until its week pages come with it.

    Exporting the index alone does not work: it links a page per week, so the audit
    fails on *its* links instead. That is the NFL schedule work, not a seed entry — and
    until then nothing may link to it, because a header-menu link appears on every page
    and turns one dead end into hundreds of broken links.
    """
    assert should_crawl("/performance/?period=30&market=hits&direction=over")
    assert not should_crawl("/performance/?period=30&league=MLB")
    assert not should_crawl("/performance/?period=30&league=MLB&market=hits")
    assert should_crawl("/results/?date=2026-08-14")
    assert not should_crawl("/results/?date=2026-08-14&league=MLB")
    assert not should_crawl("/nfl/?season=2025&week=4")
    assert not should_crawl("/nfl/")
    assert should_crawl("/game/MLB/401/")
    assert should_crawl("/game/MLB/401/?day=today")
    assert should_crawl("/?day=today&league=MLB")


def test_public_assets_are_not_cached_immutably():
    source = Path("web/management/commands/export_static.py").read_text()
    assert "max-age=300, must-revalidate" in source
    assert "max-age=31536000, immutable" not in source


def test_live_score_script_normalizes_espn_states_and_filters_by_game_state():
    """Filtering is client-side on purpose: the site is statically exported, so a
    URL-param state filter would multiply every published page by four."""
    source = Path("web/static/static-site.js").read_text()
    assert 'sourceState === "in" ? "live"' in source
    assert 'sourceState === "post" ? "final"' in source
    assert "data-state-filter" in Path("web/templates/web/today.html").read_text()
    assert "applyStateVisibility" in source
    # Live scores move cards between states, so the filter has to be re-applied after an
    # update — otherwise a game that just went final stays visible under "Upcoming".
    assert source.count("applyStateVisibility()") >= 2
    assert '["NCAAF", "football", "college-football", "80"]' in source
    assert '["NCAAF", "football", "college-football", "81"]' in source


def test_picks_shortlist_is_client_side_and_fully_wired():
    """The shortlist is device-local by design (no accounts, no backend): the script
    keys picks by the slate date the page declares, and the Results page joins them
    against rows it already renders. Each mount the script expects must exist."""
    source = Path("web/static/static-site.js").read_text()
    assert "sports-today-picks" in source and "localStorage" in source
    assert "slateDate" in source and "data-results-props" in source
    assert "data-slate-date" in Path("web/templates/web/base.html").read_text()
    assert "data-results-date" in Path("web/templates/web/results.html").read_text()


def test_phone_grid_redefinitions_keep_the_line_area():
    """`grid-area: line` with no `line` area in the active template puts the Last-10
    strip in an *implicit* column bolted onto the right of the grid — which squeezed
    every card's content into half its width on phones. Any narrow-viewport
    redefinition of .op-row's areas must therefore keep declaring the area."""
    css = Path("styles/app.css").read_text()
    narrow = css.split("@media (max-width: 650px)")[1]
    assert '"line  line"' in narrow


def test_pregame_times_carry_a_utc_stamp_for_device_local_rendering():
    """The exported HTML bakes in PT at publish time; the stamp lets the site script
    re-render each time in the reader's own timezone (travel just works). "Time TBD"
    has no instant, so it carries no stamp — the script must leave it alone."""
    from datetime import datetime, timezone

    from components.game_cards import game_card_html
    from domain.models import SlateGame

    game = SlateGame(league="MLB", game_id="1", status="scheduled",
                     start_time=datetime(2026, 8, 21, 23, 5, tzinfo=timezone.utc),
                     away_name="A", home_name="B")
    html = game_card_html(game, day="2026-08-21")
    assert 'data-start-utc="2026-08-21T23:05:00+00:00"' in html
    tbd = game_card_html(SlateGame(league="MLB", game_id="2", status="scheduled",
                                   away_name="A", home_name="B"), day="2026-08-21")
    assert "Time TBD" in tbd and "data-start-utc" not in tbd

    source = Path("web/static/static-site.js").read_text()
    assert "data-start-utc" in source and "Intl.DateTimeFormat" in source
    # htmx replaces the schedule fragment after load, discarding localized spans.
    assert "htmx:afterSwap" in source


def test_every_card_carries_an_explicit_state_class():
    """The filter selects `game-card--<state>` directly. Scheduled games once carried no
    modifier at all, which would have made "Upcoming" mean "not the other two"."""
    from domain.models import SlateGame
    from components.game_cards import game_card_html
    from datetime import datetime

    game = SlateGame(league="MLB", game_id="1", status="scheduled",
                     start_time=datetime(2026, 8, 19, 18, 0),
                     away_name="A", home_name="B")
    assert "game-card--pre" in game_card_html(game, day="2026-08-19")


def test_static_link_audit_rejects_server_query_links(tmp_path):
    (tmp_path / "index.html").write_text(
        '<a href="/performance/?market=hits">Broken static filter</a>'
    )
    try:
        validate_internal_links(tmp_path)
    except RuntimeError as exc:
        assert "query URL" in str(exc)
    else:
        raise AssertionError("query-only application links must fail the static audit")


# --- standards compliance (2026-08-17) ---------------------------------------------

# These build their own pages rather than reading the checked-in `site-dist/`.
#
# Reading the publish artefact meant asserting on *the last build* rather than on the
# current code, and skipping silently whenever it was absent — so a fresh clone reported
# green while checking nothing, and a run overlapping a publish skipped forty-five tests
# because the directory was mid-rewrite. The same blind spot let a page ship with a
# stale cached payload through a passing build, a passing publish and a passing live
# check on the same afternoon.
#
# The export still refuses to write outside the project (a path-traversal guard worth
# keeping), so this writes to a project-local scratch directory instead of a temp one,
# and uses the command's bounded mode: three pages, uncrawled, ~2s once per session.
_DIST = Path(__file__).resolve().parents[2] / ".test-export"

_STANDARDS_PAGES = "/,/results/,/performance/"


@pytest.fixture(scope="session", autouse=True)
def _built_pages():
    """Export the pages these tests assert on, once, from the code as it stands now."""
    import shutil

    from django.core.management import call_command

    call_command("export_static", out=_DIST, seeds=_STANDARDS_PAGES, no_crawl=True)
    yield _DIST
    shutil.rmtree(_DIST, ignore_errors=True)


def _index() -> str:
    return (_DIST / "index.html").read_text()


def test_the_slate_page_states_its_subject_in_exactly_one_h1():
    """The page had no <h1> at all — its only heading was <h2>Top Opportunities and the
    site name lived in a <footer>, so it announced no subject to a screen reader and no
    topic to a search engine. Exactly one, because two competing <h1>s is its own defect.
    """
    headings = re.findall(r"<h1[^>]*>(.*?)</h1>", _index(), re.S)
    assert len(headings) == 1, f"expected one <h1>, found {len(headings)}"
    assert headings[0].strip(), "the <h1> must not be empty"


def test_template_comments_do_not_leak_into_the_page():
    """Django's `{# #}` is single-line only. Written as a multi-line block, the
    continuation lines render as page text — which is how an explanatory comment about
    the <h1> ended up *inside* the <h1> on the first attempt."""
    html = _index()
    for phrase in ("screen reader met", "search engines saw", "Visually hidden because"):
        assert phrase not in html, f"template comment leaked into the page: {phrase!r}"


def test_the_page_carries_mobile_web_app_metadata():
    """This is read on a phone from the home screen. Without these the icon falls back to
    a screenshot, the status bar ignores the dark canvas, and launching shows browser
    chrome instead of running full-screen."""
    html = _index()
    for tag in ('name="theme-color"', 'rel="apple-touch-icon"',
                'name="apple-mobile-web-app-capable"', 'rel="manifest"'):
        assert tag in html, f"missing {tag}"


def test_home_screen_icons_are_sharp_versioned_pngs():
    """iOS otherwise keeps the previous touch icon or falls back to a screenshot."""
    import struct

    icon_dir = Path("web/static/icons")
    expected = {
        "apple-touch-icon-v3.png": (180, 180),
        "icon-192-v3.png": (192, 192),
        "icon-512-v2.png": (512, 512),
    }
    for name, size in expected.items():
        raw = (icon_dir / name).read_bytes()
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", raw[16:24]) == size
    template = Path("web/templates/web/base.html").read_text()
    assert "apple-touch-icon-v3.png" in template


def test_every_served_icon_is_actually_referenced():
    """An unreferenced file in a served static directory ships as junk on every deploy.
    It happened: three superseded app icons and a 1.25MB master sat in
    web/static/icons for weeks, uploaded on every publish, referenced by nothing
    (removed 2026-08-24; the master now lives unserved in icons/). Every file in the
    served icon directories must be named by the base template or the web manifest —
    add the reference or don't add the file."""
    referencers = (Path("web/templates/web/base.html").read_text()
                   + Path("web/static/site.webmanifest").read_text())
    for served in (Path("web/static/icons"), Path("web/static/favicons")):
        for f in served.iterdir():
            if f.name.startswith("."):
                continue
            assert f.name in referencers, f"{f} is served but referenced by nothing"


def test_a_keyboard_user_can_skip_the_navigation():
    """The nav renders before the slate, so without this a keyboard or switch user tabs
    through every filter pill and league toggle before reaching the first game."""
    html = _index()
    assert 'class="skip-link"' in html
    # The export canonicalises internal hrefs, so the skip link ships as "/#main" rather
    # than the bare "#main" written in the template. Match the fragment, not the form.
    assert re.search(r'class="skip-link"[^>]*href="[^"]*#main"', html)
    assert 'id="main"' in html, "the skip link needs a target"


def test_reduced_motion_is_respected():
    """The stylesheet animates a live-game dot and transitions several controls; none of
    it carries meaning that is lost when stilled."""
    css = (_DIST / "static" / "web.css").read_text()
    assert "prefers-reduced-motion" in css


def test_the_manifest_is_valid_and_launches_standalone():
    """`display: standalone` is what actually drops browser chrome; without it the rest
    of the metadata is decorative."""
    manifest = json.loads((_DIST / "static" / "site.webmanifest").read_text())
    assert manifest["display"] == "standalone"
    assert manifest["icons"], "a manifest with no icons gives the home screen nothing"
    for icon in manifest["icons"]:
        assert (_DIST / icon["src"].lstrip("/")).exists(), f"missing {icon['src']}"


# --- redirects are routes, not failures (2026-08-19) ---------------------------------

def test_the_exporter_follows_a_redirect_instead_of_recording_a_failure():
    """The NFL card links at a slate game by its ESPN id; the view redirects to the
    archive page keyed by the *feed* id, because the two sources key games differently.
    Treating that 302 as a failure meant no NFL matchup page could ever publish — the
    surface worked locally and was absent from the live site."""
    import inspect

    from web.management.commands import export_static

    src = inspect.getsource(export_static.Command.handle)
    assert "301, 302, 307, 308" in src, "redirect statuses must be handled"
    # The target has to be queued, or the page it points at is never rendered.
    assert "queue.append(target)" in src
    assert "redirects[url] = target" in src


def test_an_nfl_matchup_url_is_crawlable():
    from web.management.commands.export_static import canonical_url, should_crawl

    url = canonical_url("/nfl/game/45967-LVR@DEN/")
    assert should_crawl(url), "the redirect target must be allowed through"


def test_the_nfl_page_engine_version_moves_with_the_page_contents():
    """The matchup page cache is keyed by this string. Adding the matchup outlook without
    bumping it left every cached page serving the pre-change HTML."""
    from services.nfl_game_page import ENGINE_VERSION

    assert ENGINE_VERSION != "nfl-matchup-v1", (
        "bump ENGINE_VERSION whenever the rendered page changes, or cached pages go stale")


# --- accessible names (2026-08-19) ---------------------------------------------------

def _controls(page: str):
    """(accessible name, had an explicit aria-label) for every interactive element."""
    import re
    from html import unescape

    path = _DIST / page
    if not path.exists():
        return []
    html = path.read_text()
    out = []
    for m in re.finditer(r'<(a|button|summary)\b([^>]*)>(.*?)</\1>', html, re.S | re.I):
        attrs, inner = m.group(2), m.group(3)
        aria = re.search(r'aria-label="([^"]*)"', attrs)
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", inner))).strip()
        out.append((aria.group(1) if aria else text, bool(aria)))
    return out


def test_no_two_controls_on_a_page_share_an_accessible_name():
    """A full slate renders 40+ "Matchup →" links. Without a label naming the game they
    are indistinguishable in a screen reader's link list, and the visible text is only
    unambiguous because a sighted reader can see which card it sits in."""
    import collections

    for page in ("index.html", "results/index.html", "performance/index.html"):
        names = collections.Counter(name for name, _ in _controls(page))
        dupes = {n: c for n, c in names.items() if c > 1}
        assert not dupes, f"{page} has ambiguous control names: {dupes}"


def test_glyph_only_meaning_is_never_the_accessible_name():
    """Carets, ×, and the grade check are decoration beside a word that already says it.
    Announced, they become "up-pointing small triangle" in the middle of a sentence."""
    import re

    for page in ("index.html", "results/index.html"):
        for name, _ in _controls(page):
            assert not re.fullmatch(r"[^\w]*", name or "x"), f"{page}: bare-glyph control"
            for glyph in ("▴", "▾", "×", "✓", "✗", "🎯"):
                assert glyph not in name, f"{page}: {glyph!r} reaches the accessible name"


def test_the_slate_labels_most_of_its_controls():
    """Not every control needs one — "Performance" already says what it is — but the
    cards, pills and prop rows do, and they are the bulk of the page."""
    controls = _controls("index.html")
    labelled = sum(1 for _, has in controls if has)
    assert labelled / len(controls) >= 0.7, f"only {labelled}/{len(controls)} labelled"


def test_stylesheet_versions_track_their_own_contents():
    """A header rewrite once landed entirely in web.css while only app.css's hand-typed
    `?v=` string was bumped. The change was committed, pushed and deployed — and invisible,
    because browsers kept the stylesheet they had cached two days earlier."""
    import re

    from web.assets import asset_versions, stylesheet_version

    html = (_DIST / "index.html").read_text()
    versions = re.findall(r'\.css\?v=([0-9a-f]{10})\b', html)
    assert len(versions) >= 2, f"stylesheets must be content-versioned, got {versions!r}"
    assert len(set(versions)) == len(versions), "two stylesheets sharing a version"
    live = asset_versions()
    assert stylesheet_version("web.css") == live["v_web"]
    assert live["v_app"] != live["v_web"]


def test_a_changed_stylesheet_changes_its_version(tmp_path, monkeypatch):
    from django.conf import settings

    from web import assets

    monkeypatch.setattr(settings, "STATICFILES_DIRS", [tmp_path])
    monkeypatch.setattr(settings, "DEBUG", True)      # recompute, don't serve the cache
    (tmp_path / "web.css").write_text("a{}")
    before = assets.stylesheet_version("web.css")
    (tmp_path / "web.css").write_text("a{color:red}")
    assert assets.stylesheet_version("web.css") != before


# --- publishing must fail loudly (2026-08-20) ----------------------------------------

def test_a_failed_deploy_does_not_report_success():
    """wrangler failed mid-upload after the build and link audit passed. Python's prints
    are buffered, so they landed after wrangler's error and the run read as a success —
    the site served stale CSS for another twenty minutes while being reported live."""
    import inspect

    from scripts import publish_pages

    # The deploy moved out of `main` into `publish` on 2026-08-28, when `main` became
    # the wrapper that records a start/finish pair around it. The guard follows the
    # deploy, not the function name.
    src = inspect.getsource(publish_pages.publish)
    assert "code = subprocess.call" in src, "the exit code must be captured"
    assert "if code != 0" in src, "a non-zero wrangler exit must short-circuit"
    assert "PUBLISH FAILED" in src


def test_the_live_site_is_checked_against_what_was_built(monkeypatch, tmp_path):
    """Every local check reads site-dist — the thing we just wrote. Confirming the change
    reached the reader means asking the origin."""
    from scripts import publish_pages

    monkeypatch.setattr(publish_pages, "OUTPUT", tmp_path)
    (tmp_path / "index.html").write_text(
        '<link href="/static/web.css?v=abc1234567"><link href="/static/app.css?v=def8901234">'
    )

    class _Response:
        def __init__(self, body): self._body = body
        def read(self): return self._body.encode()
        def __enter__(self): return self
        def __exit__(self, *_): return False

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _Response("web.css?v=abc1234567 app.css?v=def8901234"))
    assert publish_pages.verify_live("https://example.test/", retry_delays=()) is True

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _Response("web.css?v=0000000000"))
    assert publish_pages.verify_live("https://example.test/", retry_delays=()) is False


def test_an_unreachable_site_is_not_reported_as_a_publish_failure(monkeypatch, tmp_path):
    """The deploy already succeeded; a network problem here is our inability to confirm,
    not evidence the publish broke.

    OUTPUT is redirected like its sibling tests: reading the real site-dist/ made this
    the one check in the file that still needed a prior publish, and it failed outright
    on a fresh clone rather than testing anything.
    """
    import urllib.error
    import urllib.request

    from scripts import publish_pages

    monkeypatch.setattr(publish_pages, "OUTPUT", tmp_path)
    (tmp_path / "index.html").write_text('<link href="/static/web.css?v=abc1234567">')

    real = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("down"))
    try:
        assert publish_pages.verify_live("https://example.test/", retry_delays=()) is True
    finally:
        urllib.request.urlopen = real


def test_the_hidden_attribute_actually_hides():
    """`element.hidden = true` relies on the UA rule `[hidden] { display: none }`, which
    an author `display` declaration beats at equal specificity. `.game-card` sets
    `display: flex` and `.schedule-grid` sets `display: grid`, so the game-state filter
    set a property that never applied — it changed its own label and hid nothing."""
    import re

    css = (_DIST / "static" / "web.css").read_text()
    rule = re.search(r'\[hidden\]\s*\{[^}]*display:\s*none\s*!important', css)
    assert rule, "an author-level [hidden] rule is required to beat .game-card's display"

    app = (_DIST / "static" / "app.css").read_text()
    for selector in (".game-card", ".schedule-grid"):
        assert re.search(rf'{re.escape(selector)}\s*\{{[^}}]*display:', app), (
            f"{selector} still sets display — the [hidden] override must stay")


def test_phone_card_columns_cannot_be_widened_by_their_own_content():
    """A bare `1fr` is `minmax(auto, 1fr)`: the track never shrinks below the widest
    card's *min-content* width. Cards are full of `white-space: nowrap` runs (the time
    pill, the "Best game" chip, the competition context), and nowrap min-content is the
    whole line — so one long context string ("Game 1 · Series · NYY leads 1-0") sized the
    single phone column to 465px inside a 361px grid and every card ran off the side of
    the screen. Floor both card grids at 0 so the content truncates instead."""
    css = Path("styles/app.css").read_text()
    phone = css[css.index("@media (max-width: 900px)"):]
    phone = phone[:phone.index("}", phone.index("}") + 1)]
    for selector in (".schedule-grid", ".op-list"):
        rule = re.search(rf'{re.escape(selector)}\s*\{{[^}}]*grid-template-columns:\s*([^;]+);',
                         phone)
        assert rule, f"{selector} must set its own column track on phones"
        assert "minmax(0" in rule.group(1), (
            f"{selector} phone track is `{rule.group(1).strip()}` — floor it at "
            "minmax(0, 1fr) or a long nowrap run will widen the card past the screen")


def test_a_long_competition_context_gets_a_second_line_rather_than_an_ellipsis():
    """"Game 1 · Series · NYY leads 1-0" needs 178px and the league row offers 68 on a
    phone (80 in the desktop column), so it truncated to "Game 1 …" — losing the series
    state, and on a doubleheader the game number is the only thing telling two otherwise
    identical cards apart. Wrapping gives the context the row's full width. Flex breaks a
    line on the item's hypothetical size, so a short context ("Week 1") still rides beside
    the league and costs no card height. The separator has to hang off the league name:
    led by `.game-context::before`, a wrapped context opens with a stray bullet."""
    css = Path("styles/app.css").read_text()
    top_left = re.search(r'\.game-top-left\s*\{([^}]*)\}', css)
    assert top_left and "flex-wrap: wrap" in top_left.group(1), (
        ".game-top-left must wrap or a long context truncates instead of dropping a line")
    assert not re.search(r'\.game-context::before\s*\{[^}]*content:\s*"·"', css), (
        "a leading separator puts a stray bullet at the head of a wrapped context line")
    assert re.search(r'\.game-top-left:has\(\.game-context\)\s+\.league-name::after\s*\{'
                     r'[^}]*content:\s*"·"', css), (
        "the separator hangs off the league name, and only when a context follows it")


def test_rollover_script_only_renders_where_a_day_index_exists():
    """`const index = {{ day_index }}` is a syntax error when day_index is absent.

    Matchup pages carry a slate_date too, so gating the block on that would have emitted
    `const index = ;` and taken the whole inline script down — including the redirect —
    on every game page. They also must not roll over: a game page addresses one game,
    not "today".
    """
    from pathlib import Path

    template = Path("web/templates/web/base.html").read_text(encoding="utf-8")
    assert "{% if slate_rollover %}" in template
    assert "{% if slate_date %}{% comment %}\n  The slate roll-over" not in template

    from datetime import date

    from web.today import build_context
    from django.http import QueryDict

    context = build_context(QueryDict(""), date.today())
    assert context["slate_rollover"] is True
    assert context["day_index"] == 0


def test_script_url_is_content_hashed_like_the_stylesheets():
    """A hand-typed ?v= on the script is the same bug the stylesheets already fixed:
    the roll-over shipped in static-site.js and the string would not have moved, so
    returning visitors would keep a cached copy that labels the wrong day."""
    from web.assets import asset_versions, stylesheet_version

    live = asset_versions()
    assert live["v_js"] == stylesheet_version("static-site.js")
    assert live["v_js"] not in ("", "0")

    from pathlib import Path
    template = Path("web/templates/web/base.html").read_text(encoding="utf-8")
    assert "static-site.js' %}?v={{ v_js }}" in template
    assert "?v=20260821-2" not in template


def test_verify_retries_before_calling_a_deploy_stale(monkeypatch, tmp_path):
    """Cloudflare needs a moment. Two deploys in three days were logged FAILED with
    deploy_exit 0 because the check read the edge before it had caught up — which makes
    a propagation lag and a real failure identical in the log."""
    from scripts import publish_pages

    monkeypatch.setattr(publish_pages, "OUTPUT", tmp_path)
    (tmp_path / "index.html").write_text('<link href="/static/web.css?v=abc1234567">')

    class _Response:
        def __init__(self, body): self._body = body
        def read(self): return self._body.encode()
        def __enter__(self): return self
        def __exit__(self, *_): return False

    bodies = iter(["stale page", "stale page", "web.css?v=abc1234567"])
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Response(next(bodies)))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    assert publish_pages.verify_live("https://example.test/", retry_delays=(0, 0, 0)) is True


def test_verify_still_fails_when_the_page_never_catches_up(monkeypatch, tmp_path):
    """The backoff must not turn a genuine bad deploy into a pass — a real mid-upload
    failure happened the same afternoon the lag did."""
    from scripts import publish_pages

    monkeypatch.setattr(publish_pages, "OUTPUT", tmp_path)
    (tmp_path / "index.html").write_text('<link href="/static/web.css?v=abc1234567">')

    class _Response:
        def read(self): return b"a permanently wrong page"
        def __enter__(self): return self
        def __exit__(self, *_): return False

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Response())
    monkeypatch.setattr("time.sleep", lambda _s: None)

    assert publish_pages.verify_live("https://example.test/", retry_delays=(0, 0)) is False


def test_each_verify_attempt_busts_the_edge_cache_afresh(monkeypatch, tmp_path):
    """One probe URL reused across retries would let the edge replay its cached copy,
    so the backoff would stare at a frozen page and still report failure."""
    from scripts import publish_pages

    monkeypatch.setattr(publish_pages, "OUTPUT", tmp_path)
    (tmp_path / "index.html").write_text('<link href="/static/web.css?v=abc1234567">')

    seen = []

    class _Response:
        def read(self): return b"stale"
        def __enter__(self): return self
        def __exit__(self, *_): return False

    def _urlopen(request, *a, **k):
        seen.append(request.full_url)
        return _Response()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    publish_pages.verify_live("https://example.test/", retry_delays=(0, 0))
    assert len(seen) == 3
    assert len(set(seen)) == 3, f"probe URLs repeated across attempts: {seen}"


def test_state_filter_also_filters_the_opportunity_list():
    """Filtering the slate to "live" left the picks list untouched, so the page showed
    live games above opportunities for games that finished hours ago — the two halves
    reading as unrelated when they describe the same slate."""
    from pathlib import Path

    js = Path("web/static/static-site.js").read_text(encoding="utf-8")
    assert "applyOpportunityVisibility" in js
    # Reuses the game id the pick UI already emits rather than adding a second one.
    assert 'op-row[data-pick-game-id]' in js
    # The visible set is built from the cards *after* they are filtered, so a live score
    # moving a game between states carries its picks along on the next tick.
    assert "cards.filter((card) => !card.hidden)" in js


def test_opportunity_rows_expose_the_game_they_belong_to():
    """The filter joins picks to games on this attribute; without it the join is silent
    and every pick would vanish whenever a state filter was applied."""
    from components.opportunity_feed import _pick_attrs
    from domain.models import Opportunity

    opp = Opportunity(
        league="MLB", player_id="1", player_name="A Batter", team_id="2",
        team_name="Reds", market="1+ Hit", threshold=1, opportunity_score=90,
        stability_score=80, supporting_evidence=[], negative_evidence=[],
        game_id="824636",
    )
    assert 'data-pick-game-id="824636"' in _pick_attrs(opp)


def test_every_page_the_header_menu_links_to_is_exported():
    """The menu points at these from *every* page, so one unexported target is not one
    broken link but hundreds — which is exactly what happened when the NFL archive was
    added to the menu while the crawler still skipped it (640 broken links)."""
    from web.management.commands.export_static import _SEEDS, should_crawl

    for path in ("/performance/", "/results/", "/standings/"):
        assert path in _SEEDS, f"{path} is linked from the header menu but never seeded"
        assert should_crawl(f"https://sports.sme327.com{path}"), f"{path} is not crawlable"


def test_day_today_is_the_index_not_a_hashed_duplicate():
    """The Today pill links "/?day=today". Falling through to the hashed catch-all gave
    it /view/home-<hash>/ — a byte-identical copy of the home page under a URL nobody
    could recognise — so the control read as broken and the site carried the page twice."""
    from web.management.commands.export_static import output_path

    assert output_path("/?day=today").as_posix() == "index.html"
    assert output_path("/").as_posix() == "index.html"
    assert output_path("/?day=tomorrow").as_posix() == "tomorrow/index.html"
    assert output_path("/?day=day-after").as_posix() == "day-after/index.html"


def test_every_menu_link_points_at_an_exported_page():
    """The invariant a hardcoded label list could not hold.

    The menu renders on *every* page, so one link to a page the exporter never built is
    not one dead link but one per page — the NFL archive proved that with 640. Naming
    which entries are unbuilt goes stale the moment one ships, and did. This resolves
    every href the menu actually renders and requires the exporter to produce it.
    """
    import re

    from django.test import Client

    from web.management.commands.export_static import _SEEDS, output_path, should_crawl

    html = Client().get("/").content.decode()
    panel = html[html.index('class="nav-menu-panel"'):html.index("</details>")]
    hrefs = re.findall(r'<a[^>]+href="([^"]+)"', panel)
    assert hrefs, "the menu rendered no links at all"
    for href in hrefs:
        assert should_crawl(href) or href in _SEEDS, f"{href} is linked but not crawlable"
        assert output_path(href), f"{href} has no export path"


def test_unbuilt_menu_entries_are_plain_text():
    """Whatever is not built yet must not be an anchor — that is what lets the menu
    double as a roadmap without breaking the export."""
    import re
    from pathlib import Path

    html = Path("web/templates/web/base.html").read_text(encoding="utf-8")
    panel = html[html.index('class="nav-menu-panel"'):html.index("</details>")]
    for match in re.finditer(r'<(\w+)[^>]*class="nav-future"', panel):
        assert match.group(1) != "a", "an unbuilt entry must not be a link"


def test_leagues_come_before_the_analysis_pages_in_the_menu():
    """Leagues first is how the reader thinks about the sport; Performance and Results
    sit at the bottom where they are found rather than tripped over."""
    from pathlib import Path

    html = Path("web/templates/web/base.html").read_text(encoding="utf-8")
    panel = html[html.index('class="nav-menu-panel"'):html.index("</details>")]
    assert panel.index("MLB") < panel.index("Performance")
    assert panel.index("WNBA") < panel.index("Daily Results")


def test_mlb_matchup_engine_version_moved_with_its_content():
    """The NFL page has had this guard for a while; the MLB page did not, and that is
    exactly how it broke. matchup_page_cache is keyed on ENGINE_VERSION, so a page that
    gains a field while the version stands still keeps serving the old payload — the
    ballpark note went through a full build and publish while Coors Field showed nothing.
    """
    from services.mlb_game_page import ENGINE_VERSION

    assert ENGINE_VERSION != "mlb-game-page-v1", (
        "bump ENGINE_VERSION whenever the rendered page changes, or cached pages go stale")
