"""Marks `styles/` as a package so Django can list it in STATICFILES_DIRS.

The Streamlit CSS loader that used to live here retired with the Streamlit app; the
stylesheet itself (`app.css`) is now collected by `collectstatic` and served by the
static site. Kept deliberately empty — `export_static` ignores `*.py` so nothing here
is ever published, but there is no reason to put anything here either.
"""
