"""Regressões da leitura de mensagens, com a camada HTTP mockada."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from evoapi_mcp.client import EvolutionClient, InvalidPhoneNumberError
from evoapi_mcp.config import EvolutionConfig

NUMBER = "5511999999999"
PERSONAL_JID = f"{NUMBER}@s.whatsapp.net"
LID_JID = "100000000000000@lid"
GROUP_JID = "120363000000000000@g.us"

FIND_MESSAGES = "/chat/findMessages/"
FIND_CHATS = "/chat/findChats/"
FIND_CONTACTS = "/chat/findContacts/"
SEND_TEXT = "/message/sendText/"


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class Recorder:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        for fragment, payload in self.routes.items():
            if fragment in kwargs["url"]:
                return FakeResponse(payload)
        raise AssertionError(f"URL inesperada: {kwargs['url']}")

    def bodies(self, fragment):
        return [call["json"] for call in self.calls if fragment in call["url"]]

    def count(self, fragment):
        return len(self.bodies(fragment))


def make_messages(*texts, remote_jid=LID_JID, total=None):
    records = [
        {"key": {"remoteJid": remote_jid, "fromMe": False}, "message": {"conversation": text}}
        for text in texts
    ]
    return {
        "messages": {
            "total": total if total is not None else len(records),
            "pages": 1,
            "currentPage": 1,
            "records": records,
        }
    }


LID_CHAT = {
    "remoteJid": LID_JID,
    "pushName": None,
    "lastMessage": {"key": {"remoteJid": LID_JID, "remoteJidAlt": PERSONAL_JID}},
}
OTHER_CHAT = {"remoteJid": "5500000000000@s.whatsapp.net", "pushName": "Outra Pessoa"}


@pytest.fixture
def client():
    config = EvolutionConfig(
        base_url="http://evolution.test",
        api_token="test-token",
        instance_name="test-instance",
    )
    return EvolutionClient(config)


@pytest.fixture
def recorder():
    def build(routes):
        return Recorder(routes)

    return build


def run(recorder_obj, call):
    with patch("evoapi_mcp.client.requests.request", side_effect=recorder_obj):
        return call()


def test_find_messages_nests_the_chat_filter_under_where(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("oi")})

    run(rec, lambda: client.find_messages(chat_id=PERSONAL_JID, limit=20))

    body = rec.bodies(FIND_MESSAGES)[0]
    assert body["where"] == {"key": {"remoteJid": PERSONAL_JID}}
    assert "chatId" not in body


def test_find_messages_sends_the_page_size_as_offset(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("oi")})

    run(rec, lambda: client.find_messages(chat_id=PERSONAL_JID, limit=20))

    body = rec.bodies(FIND_MESSAGES)[0]
    assert body["offset"] == 20
    assert "limit" not in body


def test_find_messages_forwards_the_page_number(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("oi")})

    run(rec, lambda: client.find_messages(chat_id=PERSONAL_JID, limit=10, page=3))

    assert rec.bodies(FIND_MESSAGES)[0]["page"] == 3


def test_find_messages_omits_page_when_asking_for_the_first(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("oi")})

    run(rec, lambda: client.find_messages(chat_id=PERSONAL_JID, limit=10, page=1))

    assert "page" not in rec.bodies(FIND_MESSAGES)[0]


def test_find_messages_never_sends_query_to_the_api(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("falar de planilha")})

    run(rec, lambda: client.find_messages(query="planilha", chat_id=PERSONAL_JID))

    body = rec.bodies(FIND_MESSAGES)[0]
    assert "query" not in body
    assert "message" not in body["where"]


def test_a_bare_number_resolves_to_the_lid_jid_of_the_chat(client, recorder):
    rec = recorder({FIND_CHATS: [OTHER_CHAT, LID_CHAT], FIND_MESSAGES: make_messages("oi")})

    run(rec, lambda: client.find_messages(chat_id=NUMBER, limit=5))

    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": LID_JID}}


def test_get_messages_by_number_reaches_a_lid_chat(client, recorder):
    rec = recorder({FIND_CHATS: [OTHER_CHAT, LID_CHAT], FIND_MESSAGES: make_messages("oi")})

    run(rec, lambda: client.get_messages_by_number(number=NUMBER, limit=5))

    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": LID_JID}}


def test_a_group_jid_passes_through_without_a_chat_lookup(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("oi", remote_jid=GROUP_JID)})

    run(rec, lambda: client.find_messages(chat_id=GROUP_JID, limit=5))

    assert rec.count(FIND_CHATS) == 0
    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": GROUP_JID}}


def test_get_messages_by_number_accepts_a_group_jid(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("oi", remote_jid=GROUP_JID)})

    run(rec, lambda: client.get_messages_by_number(number=GROUP_JID, limit=5))

    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": GROUP_JID}}


def test_an_explicit_personal_jid_passes_through_without_a_chat_lookup(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("oi", remote_jid=PERSONAL_JID)})

    run(rec, lambda: client.find_messages(chat_id=PERSONAL_JID, limit=5))

    assert rec.count(FIND_CHATS) == 0


def test_a_resolved_jid_is_cached(client, recorder):
    rec = recorder({FIND_CHATS: [LID_CHAT], FIND_MESSAGES: make_messages("oi")})

    def two_reads():
        client.find_messages(chat_id=NUMBER, limit=5)
        client.find_messages(chat_id=NUMBER, limit=5)

    run(rec, two_reads)

    assert rec.count(FIND_CHATS) == 1
    assert rec.count(FIND_MESSAGES) == 2


def test_a_fallback_jid_is_not_cached(client, recorder):
    rec = recorder({FIND_CHATS: [], FIND_MESSAGES: make_messages()})

    def two_reads():
        client.find_messages(chat_id=NUMBER, limit=5)
        client.find_messages(chat_id=NUMBER, limit=5)

    run(rec, two_reads)

    assert rec.count(FIND_CHATS) == 2
    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": PERSONAL_JID}}


def test_an_unresolvable_number_still_queries_a_single_chat(client, recorder):
    rec = recorder({FIND_CHATS: [OTHER_CHAT], FIND_MESSAGES: make_messages()})

    run(rec, lambda: client.find_messages(chat_id=NUMBER, limit=5))

    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": PERSONAL_JID}}


def test_a_number_that_is_not_a_phone_number_is_rejected(client):
    with pytest.raises(InvalidPhoneNumberError):
        client.resolve_chat_jid("nope")


def test_query_filters_the_records_client_side(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("manda a planilha", "bom dia", "planilha ok")})

    result = run(rec, lambda: client.find_messages(query="PLANILHA", chat_id=PERSONAL_JID))

    texts = [r["message"]["conversation"] for r in result["messages"]["records"]]
    assert texts == ["manda a planilha", "planilha ok"]


def test_query_reports_the_scope_it_actually_scanned(client, recorder):
    rec = recorder({FIND_MESSAGES: make_messages("a", "b", "c", total=104195)})

    result = run(rec, lambda: client.find_messages(query="zzz", chat_id=PERSONAL_JID))

    report = result["messages"]["clientSideFilter"]
    assert report == {"query": "zzz", "scope": "current_page", "scanned": 3, "matched": 0}
    assert result["messages"]["records"] == []


def test_query_matches_a_media_caption(client, recorder):
    payload = {
        "messages": {
            "total": 1,
            "records": [
                {"key": {"remoteJid": LID_JID}, "message": {"imageMessage": {"caption": "a planilha"}}}
            ],
        }
    }
    rec = recorder({FIND_MESSAGES: payload})

    result = run(rec, lambda: client.find_messages(query="planilha", chat_id=PERSONAL_JID))

    assert len(result["messages"]["records"]) == 1


def test_send_text_does_not_strip_a_lid_jid_into_another_number(client, recorder):
    rec = recorder({SEND_TEXT: {"key": {"id": "X"}}})

    run(rec, lambda: client.send_text(number=LID_JID, text="oi"))

    assert rec.bodies(SEND_TEXT)[0]["number"] == LID_JID


def test_send_text_accepts_a_group_jid(client, recorder):
    rec = recorder({SEND_TEXT: {"key": {"id": "X"}}})

    run(rec, lambda: client.send_text(number=GROUP_JID, text="oi"))

    assert rec.bodies(SEND_TEXT)[0]["number"] == GROUP_JID


def test_send_text_still_normalizes_a_bare_number(client, recorder):
    rec = recorder({SEND_TEXT: {"key": {"id": "X"}}})

    run(rec, lambda: client.send_text(number="+55 11 99999-9999", text="oi"))

    assert rec.bodies(SEND_TEXT)[0]["number"] == NUMBER


def test_send_text_still_rejects_a_non_number(client):
    with pytest.raises(InvalidPhoneNumberError):
        client.send_text(number="123", text="oi")


def test_the_contacts_map_does_not_key_a_lid_by_its_opaque_id(client, recorder):
    contacts = [
        {"remoteJid": LID_JID, "pushName": "Fulano"},
        {"remoteJid": PERSONAL_JID, "pushName": "Ciclano"},
    ]
    rec = recorder({FIND_CONTACTS: contacts})

    contacts_map = run(rec, client._build_contacts_map)

    assert contacts_map == {NUMBER: "Ciclano"}


def test_find_chats_enriches_a_lid_chat_through_the_alt_number(client, recorder):
    contacts = [{"remoteJid": PERSONAL_JID, "pushName": "Ciclano"}]
    rec = recorder({FIND_CHATS: [dict(LID_CHAT)], FIND_CONTACTS: contacts})

    chats = run(rec, client.find_chats)

    assert chats[0]["pushName"] == "Ciclano"
    assert chats[0]["_enriched"] is True


def test_personal_jid_number_refuses_to_read_a_lid_as_a_phone_number():
    assert EvolutionClient._personal_jid_number(PERSONAL_JID) == NUMBER
    assert EvolutionClient._personal_jid_number(LID_JID) == ""
    assert EvolutionClient._personal_jid_number(GROUP_JID) == ""


def test_a_cached_jid_expires_with_the_contacts_ttl(client, recorder):
    rec = recorder({FIND_CHATS: [LID_CHAT], FIND_MESSAGES: make_messages("oi")})

    def read_twice_across_the_ttl():
        client.find_messages(chat_id=NUMBER, limit=5)
        stale = datetime.now() - client._cache_ttl - timedelta(seconds=1)
        client._jid_cache[NUMBER] = (LID_JID, stale)
        client.find_messages(chat_id=NUMBER, limit=5)

    run(rec, read_twice_across_the_ttl)

    assert rec.count(FIND_CHATS) == 2


def test_clear_cache_also_clears_the_jid_cache(client, recorder):
    rec = recorder({FIND_CHATS: [LID_CHAT], FIND_MESSAGES: make_messages("oi")})

    def read_clear_read():
        client.find_messages(chat_id=NUMBER, limit=5)
        client.clear_cache()
        client.find_messages(chat_id=NUMBER, limit=5)

    run(rec, read_clear_read)

    assert rec.count(FIND_CHATS) == 2
