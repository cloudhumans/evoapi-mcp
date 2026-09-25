from pathlib import Path

from evoapi_mcp.config import EvolutionConfig

BASE = dict(base_url="http://evolution.test", api_token="t", instance_name="i")


def test_defaults_expand_home(monkeypatch):
    monkeypatch.delenv("EVOLUTION_STATE_DIR", raising=False)
    monkeypatch.delenv("EVOLUTION_MEDIA_DIR", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_TRANSCRIBE_MODEL", raising=False)

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.state_dir == Path.home() / ".local" / "state" / "evoapi-mcp"
    assert config.media_dir == Path.home() / "Downloads" / "whatsapp-media"
    assert config.openai_api_key is None
    assert config.openai_transcribe_model == "gpt-4o-mini-transcribe"


def test_directories_come_from_prefixed_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOLUTION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EVOLUTION_MEDIA_DIR", "~/media-x")

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.state_dir == tmp_path / "state"
    assert config.media_dir == Path.home() / "media-x"


def test_openai_settings_use_unprefixed_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.openai_api_key == "sk-test"
    assert config.openai_transcribe_model == "whisper-1"


def test_openai_key_can_be_passed_by_field_name(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = EvolutionConfig(**BASE, openai_api_key="sk-kw", _env_file=None)

    assert config.openai_api_key == "sk-kw"


def test_prefixed_openai_key_is_not_picked_up(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EVOLUTION_OPENAI_API_KEY", "sk-wrong")

    config = EvolutionConfig(**BASE, _env_file=None)

    assert config.openai_api_key is None
