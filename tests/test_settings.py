from task_timer.settings import BackupSettings, BackupSettingsStore, UISettings, UISettingsStore


def test_settings_round_trip_persists_sort_flag(tmp_path) -> None:
    store = UISettingsStore(tmp_path)
    store.save(UISettings(sort_alphabetically=True))

    loaded = store.load()
    assert loaded.sort_alphabetically is True


def test_settings_load_falls_back_when_missing_or_invalid_json(tmp_path) -> None:
    store = UISettingsStore(tmp_path)
    assert store.load().sort_alphabetically is False

    store.path.write_text("{invalid", encoding="utf-8")
    assert store.load().sort_alphabetically is False


def test_backup_settings_created_automatically_on_first_load(tmp_path) -> None:
    store = BackupSettingsStore(tmp_path)
    loaded = store.load()
    assert store.path.exists()
    assert loaded == BackupSettings()
    text = store.path.read_text(encoding="utf-8")
    assert '\n  "son_keep_count": 14,' in text


def test_backup_settings_corrupt_json_falls_back_and_rewrites_defaults(tmp_path) -> None:
    store = BackupSettingsStore(tmp_path)
    store.path.write_text("oops", encoding="utf-8")
    loaded = store.load()
    assert loaded == BackupSettings()
    assert '"son_keep_count": 14' in store.path.read_text(encoding="utf-8")
