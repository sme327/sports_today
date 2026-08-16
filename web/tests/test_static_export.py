from pathlib import Path

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
