"""Application services: data access, schedules, snapshots, freshness.

Services own all SQLite access and external-data caching. Views and league
adapters go through these functions rather than querying the database ad hoc.
"""
