"""Offline tests for the durable data store. No network: the S3 client is faked
and configuration comes from monkeypatched env vars."""

from __future__ import annotations

from pathlib import Path

from services import data_store as DS

_ENV = {
    "SPORTS_TODAY_S3_BUCKET": "bucket",
    "SPORTS_TODAY_S3_KEY_ID": "key",
    "SPORTS_TODAY_S3_SECRET": "secret",
}


def _configure(monkeypatch, **extra):
    for k, v in {**_ENV, **extra}.items():
        monkeypatch.setenv(k, v)


class _FakeClient:
    def __init__(self):
        self.uploaded = None

    def download_file(self, bucket, key, dest):
        Path(dest).write_text(f"db from {bucket}/{key}")

    def upload_file(self, src, bucket, key):
        self.uploaded = (Path(src).read_text(), bucket, key)


def test_unconfigured_is_noop(monkeypatch, tmp_path):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    dest = tmp_path / "sportshub.db"
    assert DS.is_configured() is False
    DS.ensure_db_available(dest)          # must NOT create or fetch anything
    assert not dest.exists()
    assert DS.download_db(dest) is False
    assert DS.publish_db(dest) is False


def test_is_configured_requires_all_keys(monkeypatch):
    monkeypatch.setenv("SPORTS_TODAY_S3_BUCKET", "b")
    monkeypatch.delenv("SPORTS_TODAY_S3_KEY_ID", raising=False)
    monkeypatch.delenv("SPORTS_TODAY_S3_SECRET", raising=False)
    assert DS.is_configured() is False


def test_download_writes_file(monkeypatch, tmp_path):
    _configure(monkeypatch)
    monkeypatch.setattr(DS, "_client", lambda: _FakeClient())
    dest = tmp_path / "nested" / "sportshub.db"
    assert DS.download_db(dest) is True
    assert dest.exists() and "bucket" in dest.read_text()


def test_ensure_available_skips_when_present(monkeypatch, tmp_path):
    _configure(monkeypatch)
    calls = []
    monkeypatch.setattr(DS, "download_db", lambda dest=None: calls.append(dest) or True)
    dest = tmp_path / "sportshub.db"
    dest.write_text("already here")
    DS.ensure_db_available(dest)
    assert calls == []                    # existing DB is used as-is, no fetch


def test_ensure_available_fetches_when_missing(monkeypatch, tmp_path):
    _configure(monkeypatch)
    monkeypatch.setattr(DS, "_client", lambda: _FakeClient())
    dest = tmp_path / "sportshub.db"
    DS.ensure_db_available(dest)
    assert dest.exists()


def test_publish_uploads(monkeypatch, tmp_path):
    _configure(monkeypatch, SPORTS_TODAY_DB_OBJECT="custom.db")
    fake = _FakeClient()
    monkeypatch.setattr(DS, "_client", lambda: fake)
    src = tmp_path / "sportshub.db"
    src.write_text("payload")
    assert DS.publish_db(src) is True
    assert fake.uploaded == ("payload", "bucket", "custom.db")


def test_publish_missing_file_is_false(monkeypatch, tmp_path):
    _configure(monkeypatch)
    monkeypatch.setattr(DS, "_client", lambda: _FakeClient())
    assert DS.publish_db(tmp_path / "nope.db") is False


def test_object_key_defaults_to_db_filename(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("SPORTS_TODAY_DB_OBJECT", raising=False)
    assert DS._object_key() == DS.DB_PATH.name
