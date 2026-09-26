import base64
from pathlib import Path

import pytest

from helpers import GET_BASE64, run
from evoapi_mcp.client import EvolutionAPIError
from evoapi_mcp.media import AUDIO_EXTENSIONS, download_media, extension_for, save_media

AUDIO_BYTES = b"OggS\x00fake-opus-bytes"


def payload(**overrides):
    base = {
        "mediaType": "audioMessage",
        "fileName": "PTT-20260920.ogg",
        "caption": None,
        "size": {"fileLength": {"low": len(AUDIO_BYTES), "high": 0}},
        "mimetype": "audio/ogg; codecs=opus",
        "base64": base64.b64encode(AUDIO_BYTES).decode(),
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("mimetype,ext", [
    ("audio/ogg; codecs=opus", ".ogg"),
    ("audio/ogg", ".ogg"),
    ("image/jpeg", ".jpg"),
    ("image/webp", ".webp"),
    ("video/mp4", ".mp4"),
    ("application/pdf", ".pdf"),
    ("audio/mpeg", ".mp3"),
    ("application/x-unknown-thing", ".bin"),
    (None, ".bin"),
])
def test_extension_for(mimetype, ext):
    assert extension_for(mimetype) == ext


def test_save_media_writes_file_and_omits_base64(tmp_path):
    result = save_media(payload(), tmp_path / "media", "MSG1")

    path = tmp_path / "media" / "MSG1.ogg"
    assert path.read_bytes() == AUDIO_BYTES
    assert result["path"] == str(path)
    assert result["sizeBytes"] == len(AUDIO_BYTES)
    assert result["mimetype"] == "audio/ogg; codecs=opus"
    assert result["mediaType"] == "audioMessage"
    assert result["fileName"] == "PTT-20260920.ogg"
    assert result["cached"] is False
    assert "base64" not in result
    assert not list((tmp_path / "media").glob("*.tmp"))


def test_save_media_reuses_existing_file(tmp_path):
    save_media(payload(), tmp_path, "MSG1")
    (tmp_path / "MSG1.ogg").write_bytes(b"already here")

    result = save_media(payload(), tmp_path, "MSG1")

    assert result["cached"] is True
    assert (tmp_path / "MSG1.ogg").read_bytes() == b"already here"


def test_save_media_reuses_existing_file_under_different_mimetype(tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO_BYTES)

    result = save_media(payload(mimetype="image/jpeg"), tmp_path, "MSG1")

    assert result["cached"] is True
    assert result["path"] == str(tmp_path / "MSG1.ogg")
    assert not (tmp_path / "MSG1.jpg").exists()


def test_save_media_without_base64_raises(tmp_path):
    with pytest.raises(EvolutionAPIError):
        save_media({"mediaType": "conversation"}, tmp_path, "MSG1")


def test_audio_extensions_are_derived_from_known_extensions():
    assert AUDIO_EXTENSIONS == {".ogg", ".mp3", ".m4a"}


@pytest.mark.parametrize("message_id", ["../escape", "a/b", "a*b", "a[b]", "a b"])
def test_save_media_rejects_path_unsafe_message_id(tmp_path, message_id):
    with pytest.raises(ValueError):
        save_media(payload(), tmp_path, message_id)


def test_download_media_rejects_path_unsafe_message_id(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: payload()})

    with pytest.raises(ValueError):
        run(rec, lambda: download_media(client, tmp_path, "../escape"))

    assert rec.count(GET_BASE64) == 0


def test_download_media_calls_api_and_saves(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert rec.bodies(GET_BASE64) == [{"message": {"key": {"id": "MSG1"}}}]
    assert (tmp_path / "MSG1.ogg").exists()
    assert result["cached"] is False


def test_download_media_ignores_transcript_json_sidecar(client, recorder, tmp_path):
    (tmp_path / "MSG1.transcript.json").write_text('{"model": "m", "language": "pt"}')
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is False
    assert rec.count(GET_BASE64) == 1


def test_download_media_ignores_transcript_txt_sidecar(client, recorder, tmp_path):
    (tmp_path / "MSG1.transcript.txt").write_text("já transcrito")
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is False
    assert rec.count(GET_BASE64) == 1


def test_download_media_treats_txt_document_as_cached(client, recorder, tmp_path):
    (tmp_path / "MSG1.txt").write_bytes(b"plain text document contents")
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
    assert result["path"] == str(tmp_path / "MSG1.txt")
    assert rec.count(GET_BASE64) == 0


def test_download_media_treats_json_document_as_cached(client, recorder, tmp_path):
    (tmp_path / "MSG1.json").write_bytes(b'{"not": "a transcript sidecar"}')
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
    assert result["path"] == str(tmp_path / "MSG1.json")
    assert rec.count(GET_BASE64) == 0


def test_download_media_skips_api_when_cached(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO_BYTES)
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
    assert result["mimetype"] is None
    assert rec.count(GET_BASE64) == 0


@pytest.mark.parametrize("glob_order", ["media_first", "txt_first"])
def test_download_media_prefers_media_over_legacy_txt_sidecar(client, recorder, tmp_path, monkeypatch, glob_order):
    media = tmp_path / "MSG1.ogg"
    media.write_bytes(AUDIO_BYTES)
    legacy_txt = tmp_path / "MSG1.txt"
    legacy_txt.write_text("transcrição legada")
    ordered = [media, legacy_txt] if glob_order == "media_first" else [legacy_txt, media]
    monkeypatch.setattr(Path, "glob", lambda self, pattern: iter(ordered))
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
    assert result["path"] == str(media)
    assert rec.count(GET_BASE64) == 0


def test_download_media_still_returns_lone_txt_document(client, recorder, tmp_path):
    (tmp_path / "MSG1.txt").write_bytes(b"plain text document contents")
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
    assert result["path"] == str(tmp_path / "MSG1.txt")
    assert rec.count(GET_BASE64) == 0


def test_download_media_ignores_transcript_sidecars_alongside_legacy_txt(client, recorder, tmp_path, monkeypatch):
    media = tmp_path / "MSG1.ogg"
    media.write_bytes(AUDIO_BYTES)
    legacy_txt = tmp_path / "MSG1.txt"
    legacy_txt.write_text("transcrição legada")
    transcript_txt = tmp_path / "MSG1.transcript.txt"
    transcript_txt.write_text("já transcrito")
    transcript_json = tmp_path / "MSG1.transcript.json"
    transcript_json.write_text('{"model": "m", "language": "pt"}')
    ordered = [transcript_txt, legacy_txt, transcript_json, media]
    monkeypatch.setattr(Path, "glob", lambda self, pattern: iter(ordered))
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
    assert result["path"] == str(media)
    assert rec.count(GET_BASE64) == 0


@pytest.mark.parametrize("glob_order", ["ogg_first", "mp3_first"])
def test_download_media_is_deterministic_across_media_candidates(client, recorder, tmp_path, monkeypatch, glob_order):
    ogg = tmp_path / "MSG1.ogg"
    ogg.write_bytes(AUDIO_BYTES)
    mp3 = tmp_path / "MSG1.mp3"
    mp3.write_bytes(AUDIO_BYTES)
    ordered = [ogg, mp3] if glob_order == "ogg_first" else [mp3, ogg]
    monkeypatch.setattr(Path, "glob", lambda self, pattern: iter(ordered))
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["path"] == str(mp3)
