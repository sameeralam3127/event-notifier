import importlib

from fastapi.testclient import TestClient


def test_masked_password_reuses_saved_database_password(tmp_path, monkeypatch):
    db_path = tmp_path / "event_notifier.db"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("EVENT_NOTIFIER_DB_PATH", str(db_path))
    monkeypatch.setenv("EVENT_NOTIFIER_UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("APP_ENV", "development")

    import backend.database as database
    import backend.main as main

    importlib.reload(database)
    importlib.reload(main)

    original_config = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "sender@example.com",
        "password": "real-app-password",
        "from_email": "sender@example.com",
    }

    with TestClient(main.app) as client:
        assert client.post("/api/configure-smtp", json=original_config).status_code == 200
        loaded = client.get("/api/get-smtp-config").json()
        assert loaded["password"] == main.MASKED_PASSWORD

        masked_config = {
            **original_config,
            "host": "smtp2.example.com",
            "password": main.MASKED_PASSWORD,
        }
        assert client.post("/api/configure-smtp", json=masked_config).status_code == 200

    saved = database.get_smtp_config()
    assert saved["host"] == "smtp2.example.com"
    assert saved["password"] == "real-app-password"
