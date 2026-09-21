import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import GET_BASE64, run
from evoapi_mcp.config import EvolutionConfig
from evoapi_mcp.transcription import (
    MISSING_KEY_MESSAGE,
    OPENAI_TRANSCRIPTIONS_URL,
    TranscriptionError,
    transcribe_file,
    transcribe_message,
)

AUDIO = b"OggS\x00fake"


class OpenAIResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clear_openai_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_TRANSCRIBE_MODEL", raising=False)


def audio_payload():
    return {"mediaType": "audioMessage", "mimetype": "audio/ogg; codecs=opus",
            "base64": base64.b64encode(AUDIO).decode(), "fileName": "a.ogg"}


def make_config(tmp_path, key="sk-test"):
    return EvolutionConfig(base_url="http://evolution.test", api_token="t", instance_name="i",
                           media_dir=tmp_path, openai_api_key=key, _env_file=None)


def test_transcribe_file_posts_multipart_with_model_and_language(tmp_path):
    audio = tmp_path / "a.ogg"
    audio.write_bytes(AUDIO)
    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "olá"})) as post:
        text = transcribe_file(audio, "sk-test", "whisper-1", language="pt")

    assert text == "olá"
    args, kwargs = post.call_args
    assert args[0] == OPENAI_TRANSCRIPTIONS_URL
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["data"] == {"model": "whisper-1", "response_format": "json", "language": "pt"}
    assert "file" in kwargs["files"]


def test_transcribe_file_omits_language_when_none(tmp_path):
    audio = tmp_path / "a.ogg"
    audio.write_bytes(AUDIO)
    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "x"})) as post:
        transcribe_file(audio, "sk", "m")

    assert "language" not in post.call_args.kwargs["data"]


def test_transcribe_file_http_error_becomes_transcription_error(tmp_path):
    audio = tmp_path / "a.ogg"
    audio.write_bytes(AUDIO)
    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(401, {"error": {"message": "bad key"}})):
        with pytest.raises(TranscriptionError) as exc:
            transcribe_file(audio, "sk", "m")

    assert "401" in str(exc.value)


def test_missing_key_fails_before_any_http(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: audio_payload()})
    config = make_config(tmp_path, key=None)

    with pytest.raises(TranscriptionError) as exc:
        run(rec, lambda: transcribe_message(client, config, "MSG1"))

    assert str(exc.value) == MISSING_KEY_MESSAGE
    assert "OPENAI_API_KEY" in MISSING_KEY_MESSAGE
    assert rec.count(GET_BASE64) == 0


def test_non_audio_media_is_rejected_with_its_type(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: {**audio_payload(), "mediaType": "imageMessage", "mimetype": "image/jpeg"}})

    with pytest.raises(TranscriptionError) as exc:
        run(rec, lambda: transcribe_message(client, make_config(tmp_path), "MSG1"))

    assert "imageMessage" in str(exc.value)


def test_transcribe_message_downloads_calls_openai_and_caches(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: audio_payload()})
    config = make_config(tmp_path)

    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "fechado o deal"})) as post:
        result = run(rec, lambda: transcribe_message(client, config, "MSG1", language="pt"))

    assert result["text"] == "fechado o deal"
    assert result["cached"] is False
    assert result["model"] == "gpt-4o-mini-transcribe"
    assert result["audioPath"] == str(tmp_path / "MSG1.ogg")
    assert Path(result["transcriptPath"]).read_text(encoding="utf-8") == "fechado o deal"
    assert post.call_count == 1


def test_cached_transcript_skips_openai(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO)
    (tmp_path / "MSG1.txt").write_text("já transcrito", encoding="utf-8")
    rec = recorder({})

    with patch("evoapi_mcp.transcription.requests.post") as post:
        result = run(rec, lambda: transcribe_message(client, make_config(tmp_path), "MSG1"))

    assert result["text"] == "já transcrito"
    assert result["cached"] is True
    post.assert_not_called()
    assert rec.count(GET_BASE64) == 0
