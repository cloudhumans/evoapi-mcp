import base64

import pytest

from helpers import GET_BASE64, run
from evoapi_mcp.client import EvolutionAPIError
from evoapi_mcp.media import download_media, extension_for, save_media

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


def test_download_media_calls_api_and_saves(client, recorder, tmp_path):
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert rec.bodies(GET_BASE64) == [{"message": {"key": {"id": "MSG1"}}}]
    assert (tmp_path / "MSG1.ogg").exists()
    assert result["cached"] is False


def test_download_media_skips_api_when_cached(client, recorder, tmp_path):
    (tmp_path / "MSG1.ogg").write_bytes(AUDIO_BYTES)
    rec = recorder({GET_BASE64: payload()})

    result = run(rec, lambda: download_media(client, tmp_path, "MSG1"))

    assert result["cached"] is True
    assert result["mimetype"] is None
    assert rec.count(GET_BASE64) == 0
