from pathlib import Path

from web.management.commands.export_static import (
    canonical_url, output_path, public_href, should_crawl,
)


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


def test_crawler_bounds_analytics_combinations_but_keeps_archive_navigation():
    assert not should_crawl("/performance/?period=30&league=MLB")
    assert not should_crawl("/results/?date=2026-08-14")
    assert should_crawl("/nfl/?season=2025&week=4")
    assert should_crawl("/game/MLB/401/")
    assert should_crawl("/game/MLB/401/?day=today")
    assert should_crawl("/?day=today&league=MLB")
