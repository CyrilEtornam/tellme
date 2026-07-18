from tellme.config import Config, load_config, save_config


def test_defaults():
    cfg = Config()
    assert cfg.mute is False
    assert cfg.time.interval_minutes == 60
    assert cfg.events.lead_minutes == 5
    assert cfg.voice.model == "en_US-lessac-medium"
    assert cfg.calendars.use_eds is True
    assert cfg.calendars.use_google_api is False


def test_roundtrip(tmp_path):
    cfg = Config()
    cfg.mute = True
    cfg.time.interval_minutes = 30
    cfg.events.lead_minutes = 10
    cfg.voice.model = "en_GB-alba-medium"
    cfg.calendars.use_google_api = True

    path = tmp_path / "config.toml"
    save_config(cfg, path)
    loaded = load_config(path)

    assert loaded.mute is True
    assert loaded.time.interval_minutes == 30
    assert loaded.events.lead_minutes == 10
    assert loaded.voice.model == "en_GB-alba-medium"
    assert loaded.calendars.use_google_api is True


def test_load_missing_returns_defaults(tmp_path):
    loaded = load_config(tmp_path / "does-not-exist.toml")
    assert loaded.time.interval_minutes == 60


def test_from_dict_ignores_unknown_keys():
    cfg = Config.from_dict({"mute": True, "bogus": 1, "time": {"interval_minutes": 15, "x": 2}})
    assert cfg.mute is True
    assert cfg.time.interval_minutes == 15
