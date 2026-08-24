# icons/ — unserved icon sources

This directory is **not served**. Everything the product ships lives in
`web/static/icons/` (app icons) and `web/static/favicons/` (per-league favicons),
and a test (`web/tests/test_static_export.py`) asserts every file there is
actually referenced — an unreferenced file in a served directory ships as junk
on every deploy, which is exactly what happened before 2026-08-24 (~1.3MB of
superseded icons and this master uploaded on every publish).

- `sports-today-1024-master.png` — the 1024×1024 master the served app icons
  (`apple-touch-icon-v3`, `icon-192-v3`, `icon-512-v2`) were derived from.
  Regenerate sizes from here; never place the master itself in `web/static/`.

Removed 2026-08-24, recoverable from git history: `sports_today_icons_v1/`
(a 13-SVG delivery bundle superseded by the inlined icon library in
`components/icons.py`) and the superseded `apple-touch-icon.png`,
`icon-192.png`, `icon-512.png`.
