from task_timer.settings import UISettings, UISettingsStore


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
