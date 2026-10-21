from data.db import get_connection


def test_database_path_can_be_configured_for_durable_storage(tmp_path, monkeypatch):
    database_path = tmp_path / "mounted-volume" / "nested" / "tenders.sqlite3"
    database_path.parent.mkdir(parents=True)
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(database_path))

    connection = get_connection()
    try:
        connection.execute("CREATE TABLE path_check (value TEXT)")
        connection.execute("INSERT INTO path_check VALUES ('persisted')")
        connection.commit()
    finally:
        connection.close()

    assert database_path.is_file()
    reopened = get_connection()
    try:
        assert reopened.execute("SELECT value FROM path_check").fetchone() == ("persisted",)
    finally:
        reopened.close()


def test_missing_configured_storage_directory_fails_without_creating_local_fallback(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "not-mounted" / "tenders.sqlite3"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(database_path))

    try:
        get_connection()
    except FileNotFoundError as exc:
        assert "mount or create the storage directory" in str(exc)
    else:
        raise AssertionError("A missing configured storage directory must fail clearly")

    assert not database_path.parent.exists()
