from task_timer.settings import BackupSettings, BackupSettingsStore, UISettings, UISettingsStore


def test_settings_round_trip_persists_sort_flag(tmp_path) -> None:
    store = UISettingsStore(tmp_path)
    store.save(UISettings(sort_alphabetically=True))

    loaded = store.load()
    assert loaded.sort_alphabetically is True
    assert loaded.month_end_reminder_enabled is False


def test_settings_load_falls_back_when_missing_or_invalid_json(tmp_path) -> None:
    store = UISettingsStore(tmp_path)
    assert store.load().sort_alphabetically is False

    store.path.write_text("{invalid", encoding="utf-8")
    assert store.load().sort_alphabetically is False
    assert store.load().month_end_reminder_enabled is False


def test_settings_month_end_reminder_persists(tmp_path) -> None:
    store = UISettingsStore(tmp_path)
    store.save(
        UISettings(
            sort_alphabetically=True,
            month_end_reminder_enabled=True,
            month_end_reminder_show_startup_notice=False,
            month_end_reminder_show_close_notice=True,
            month_end_reminder_last_dismissed_local_date="2026-04-30",
        )
    )
    loaded = store.load()
    assert loaded.sort_alphabetically is True
    assert loaded.month_end_reminder_enabled is True
    assert loaded.month_end_reminder_show_startup_notice is False
    assert loaded.month_end_reminder_show_close_notice is True
    assert loaded.month_end_reminder_last_dismissed_local_date == "2026-04-30"


def test_existing_sort_setting_not_lost_when_reminder_settings_saved(tmp_path) -> None:
    store = UISettingsStore(tmp_path)
    store.path.write_text('{"sort_alphabetically": true}', encoding="utf-8")
    loaded = store.load()
    loaded.month_end_reminder_enabled = True
    store.save(loaded)
    reloaded = store.load()
    assert reloaded.sort_alphabetically is True
    assert reloaded.month_end_reminder_enabled is True


def test_backup_settings_created_automatically_on_first_load(tmp_path) -> None:
    store = BackupSettingsStore(tmp_path)
    loaded = store.load()
    assert store.path.exists()
    assert loaded == BackupSettings()
    text = store.path.read_text(encoding="utf-8")
    assert '\n  "son_keep_days": 14,' in text


def test_backup_settings_corrupt_json_falls_back_and_rewrites_defaults(tmp_path) -> None:
    store = BackupSettingsStore(tmp_path)
    store.path.write_text("oops", encoding="utf-8")
    loaded = store.load()
    assert loaded == BackupSettings()
    assert '"son_keep_days": 14' in store.path.read_text(encoding="utf-8")


def test_backup_settings_migrates_legacy_count_fields(tmp_path) -> None:
    store = BackupSettingsStore(tmp_path)
    store.path.write_text(
        '{\n  "son_keep_count": 5,\n  "father_keep_count": 3,\n  "grandfather_keep_count": 2,\n'
        '  "auto_backup_before_risky_operations": true,\n  "auto_backup_on_app_start": false,\n'
        '  "auto_backup_min_interval_minutes": 30\n}\n',
        encoding="utf-8",
    )
    loaded = store.load()
    assert loaded.son_keep_days == 5
    assert loaded.father_keep_days == 21
    assert loaded.grandfather_keep_days == 60
    rewritten = store.path.read_text(encoding="utf-8")
    assert "keep_count" not in rewritten
