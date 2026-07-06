import importlib.util
from pathlib import Path


def load_setup_module():
    path = Path(__file__).parents[1] / "setup.py"
    spec = importlib.util.spec_from_file_location("watch_setup", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_exit_codes():
    setup = load_setup_module()

    assert setup.exit_code_for_status({"missing_binaries": [], "has_key": True}) == 0
    assert setup.exit_code_for_status({"missing_binaries": ["ffmpeg"], "has_key": True}) == 2
    assert setup.exit_code_for_status({"missing_binaries": [], "has_key": False}) == 3
    assert setup.exit_code_for_status({"missing_binaries": ["ffmpeg"], "has_key": False}) == 4


def test_scaffold_config_creates_private_file(tmp_path, monkeypatch):
    setup = load_setup_module()
    config = tmp_path / ".config" / "watch" / ".env"
    monkeypatch.setattr(setup, "CONFIG_FILE", config)

    setup.scaffold_config()

    assert config.exists()
    assert oct(config.stat().st_mode & 0o777)[2:] == "600"
    assert "SETUP_COMPLETE=true" in config.read_text(encoding="utf-8")
