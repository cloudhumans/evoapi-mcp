import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import FIND_MESSAGES, GET_BASE64, LID_JID, run
from evoapi_mcp.config import EvolutionConfig
from evoapi_mcp.transcription import (
    MISSING_KEY_MESSAGE,
    OPENAI_TRANSCRIPTIONS_URL,
    TranscriptionError,
    transcribe_chat_audios,
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
    assert result["transcriptPath"] == str(tmp_path / "MSG1.transcript.txt")
    assert Path(result["transcriptPath"]).read_text(encoding="utf-8") == "fechado o deal"
    assert post.call_count == 1


def test_cached_transcript_skips_openai(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO)
    (tmp_path / "MSG1.transcript.txt").write_text("já transcrito", encoding="utf-8")
    (tmp_path / "MSG1.transcript.json").write_text('{"model": "gpt-4o-mini-transcribe", "language": null}', encoding="utf-8")
    rec = recorder({})

    with patch("evoapi_mcp.transcription.requests.post") as post:
        result = run(rec, lambda: transcribe_message(client, make_config(tmp_path), "MSG1"))

    assert result["text"] == "já transcrito"
    assert result["cached"] is True
    assert result["model"] == "gpt-4o-mini-transcribe"
    assert result["language"] is None
    post.assert_not_called()
    assert rec.count(GET_BASE64) == 0


def test_cached_transcript_without_sidecar_reports_none(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO)
    (tmp_path / "MSG1.transcript.txt").write_text("já transcrito, sem sidecar", encoding="utf-8")
    rec = recorder({})

    with patch("evoapi_mcp.transcription.requests.post") as post:
        result = run(rec, lambda: transcribe_message(client, make_config(tmp_path), "MSG1", language="pt"))

    assert result["text"] == "já transcrito, sem sidecar"
    assert result["cached"] is True
    assert result["model"] is None
    assert result["language"] is None
    post.assert_not_called()


def test_cached_transcript_with_different_language_retranscribes(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO)
    (tmp_path / "MSG1.transcript.txt").write_text("versão antiga auto-detectada", encoding="utf-8")
    (tmp_path / "MSG1.transcript.json").write_text('{"model": "gpt-4o-mini-transcribe", "language": null}', encoding="utf-8")
    rec = recorder({})
    config = make_config(tmp_path)

    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "versão em pt"})) as post:
        result = run(rec, lambda: transcribe_message(client, config, "MSG1", language="pt"))

    assert post.call_count == 1
    assert result["text"] == "versão em pt"
    assert result["cached"] is False
    assert result["model"] == "gpt-4o-mini-transcribe"
    assert result["language"] == "pt"
    assert (tmp_path / "MSG1.transcript.txt").read_text(encoding="utf-8") == "versão em pt"
    import json as _json
    assert _json.loads((tmp_path / "MSG1.transcript.json").read_text(encoding="utf-8")) == {
        "model": "gpt-4o-mini-transcribe", "language": "pt",
    }


def test_cached_media_with_video_extension_refuses_without_openai_call(client, recorder, tmp_path):
    (tmp_path / "MSG1.mp4").write_bytes(b"fake-mp4-bytes")
    rec = recorder({})

    with patch("evoapi_mcp.transcription.requests.post") as post:
        with pytest.raises(TranscriptionError) as exc:
            run(rec, lambda: transcribe_message(client, make_config(tmp_path), "MSG1"))

    post.assert_not_called()
    assert "MSG1" in str(exc.value)


def test_cached_media_with_audio_extension_still_transcribes(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO)
    rec = recorder({})
    config = make_config(tmp_path)

    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "ok"})) as post:
        result = run(rec, lambda: transcribe_message(client, config, "MSG1"))

    assert post.call_count == 1
    assert result["text"] == "ok"


def audio_record(msg_id, ts, seconds=5, from_me=False):
    return {
        "key": {"id": msg_id, "fromMe": from_me, "remoteJid": LID_JID},
        "messageTimestamp": ts,
        "pushName": "Boaz",
        "messageType": "audioMessage",
        "message": {"audioMessage": {"seconds": seconds, "mimetype": "audio/ogg; codecs=opus"}},
    }


def text_record(msg_id, ts):
    return {"key": {"id": msg_id, "fromMe": False, "remoteJid": LID_JID}, "messageTimestamp": ts,
            "messageType": "conversation", "message": {"conversation": "oi"}}


def find_result(*records):
    return {"messages": {"total": len(records), "pages": 2, "currentPage": 1, "records": list(records),
                         "chatResolution": {"requested": LID_JID, "jid": LID_JID, "resolved": True}}}


def test_transcribes_only_audio_records_and_isolates_failures(client, recorder, tmp_path):
    rec = recorder({FIND_MESSAGES: find_result(text_record("T1", 1), audio_record("A1", 2), audio_record("A2", 3, seconds=9)),
                    GET_BASE64: audio_payload()})
    config = make_config(tmp_path)
    responses = iter([OpenAIResponse(200, {"text": "primeiro"}), OpenAIResponse(500, {"error": "boom"})])

    with patch("evoapi_mcp.transcription.requests.post", side_effect=lambda *a, **k: next(responses)):
        result = run(rec, lambda: transcribe_chat_audios(client, config, LID_JID, limit=10, page=1, language="pt"))

    assert result["scanned"] == 3
    assert result["pages"] == 2
    assert result["chatResolution"]["resolved"] is True
    assert [a["messageId"] for a in result["audios"]] == ["A1", "A2"]
    assert result["audios"][0]["text"] == "primeiro"
    assert result["audios"][0]["seconds"] == 5
    assert result["audios"][0]["pushName"] == "Boaz"
    assert result["audios"][0]["fromMe"] is False
    assert "500" in result["audios"][1]["error"]
    assert "text" not in result["audios"][1]
    body = rec.bodies(FIND_MESSAGES)[0]
    assert body["offset"] == 10


def test_transcribe_chat_audios_caps_at_max_audios(client, recorder, tmp_path):
    records = [text_record("T", 0)] + [audio_record(f"A{i}", i + 1) for i in range(12)]
    rec = recorder({FIND_MESSAGES: find_result(*records), GET_BASE64: audio_payload()})
    config = make_config(tmp_path)

    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "x"})):
        result = run(rec, lambda: transcribe_chat_audios(client, config, LID_JID, limit=50, page=1))

    assert len(result["audios"]) == 10
    assert result["skipped_over_cap"] == 2
    assert result["skipped_own"] == 0


def test_transcribe_chat_audios_skips_own_by_default(client, recorder, tmp_path):
    records = [audio_record("mine", 1, from_me=True), audio_record("theirs", 2, from_me=False)]
    rec = recorder({FIND_MESSAGES: find_result(*records), GET_BASE64: audio_payload()})
    config = make_config(tmp_path)

    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "x"})):
        result = run(rec, lambda: transcribe_chat_audios(client, config, LID_JID))

    assert [a["messageId"] for a in result["audios"]] == ["theirs"]
    assert result["skipped_own"] == 1


def test_transcribe_chat_audios_includes_own_when_asked(client, recorder, tmp_path):
    records = [audio_record("mine", 1, from_me=True), audio_record("theirs", 2, from_me=False)]
    rec = recorder({FIND_MESSAGES: find_result(*records), GET_BASE64: audio_payload()})
    config = make_config(tmp_path)

    with patch("evoapi_mcp.transcription.requests.post", return_value=OpenAIResponse(200, {"text": "x"})):
        result = run(rec, lambda: transcribe_chat_audios(client, config, LID_JID, include_own=True))

    assert sorted(a["messageId"] for a in result["audios"]) == ["mine", "theirs"]
    assert result["skipped_own"] == 0


def test_chat_audios_fails_fast_without_key(client, recorder, tmp_path):
    rec = recorder({FIND_MESSAGES: find_result(audio_record("A1", 2))})

    with pytest.raises(TranscriptionError):
        run(rec, lambda: transcribe_chat_audios(client, make_config(tmp_path, key=None), LID_JID))

    assert rec.count(FIND_MESSAGES) == 0
