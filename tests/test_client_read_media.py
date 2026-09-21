import pytest

from helpers import GET_BASE64, MARK_READ, run
from evoapi_mcp.client import EvolutionAPIError


def test_mark_messages_read_posts_keys_under_readMessages(client, recorder):
    rec = recorder({MARK_READ: {"message": "Read messages", "read": "success"}})
    keys = [{"remoteJid": "5511999999999@s.whatsapp.net", "fromMe": False, "id": "A1"}]

    result = run(rec, lambda: client.mark_messages_read(keys))

    assert rec.bodies(MARK_READ) == [{"readMessages": keys}]
    assert result["read"] == "success"


def test_mark_messages_read_rejects_empty_list(client, recorder):
    rec = recorder({})

    with pytest.raises(ValueError):
        run(rec, lambda: client.mark_messages_read([]))

    assert rec.count(MARK_READ) == 0


def test_get_media_base64_sends_only_the_message_key(client, recorder):
    rec = recorder({GET_BASE64: {"mediaType": "audioMessage", "base64": "QUJD", "mimetype": "audio/ogg"}})

    result = run(rec, lambda: client.get_media_base64("A1"))

    assert rec.bodies(GET_BASE64) == [{"message": {"key": {"id": "A1"}}}]
    assert result["mimetype"] == "audio/ogg"


def test_get_media_base64_rejects_blank_id(client, recorder):
    rec = recorder({})

    with pytest.raises(ValueError):
        run(rec, lambda: client.get_media_base64("  "))
