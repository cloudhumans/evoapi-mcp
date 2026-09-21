import pytest

from helpers import FIND_CHATS, FIND_MESSAGES, MARK_READ, GROUP_JID, LID_JID, NUMBER, PERSONAL_JID, LID_CHAT, run
from evoapi_mcp.chat_read import REASON_GROUP, REASON_NOT_FOUND, REASON_NOTHING_NEW, annotate_chats_with_markers, mark_chat_read
from evoapi_mcp.client import EvolutionAPIError
from evoapi_mcp.read_markers import ReadMarkerStore

OK = {"message": "Read messages", "read": "success"}


def record(msg_id, ts, from_me=False, remote_jid=LID_JID, alt=PERSONAL_JID):
    key = {"id": msg_id, "fromMe": from_me, "remoteJid": remote_jid}
    if alt:
        key["remoteJidAlt"] = alt
    return {"key": key, "messageTimestamp": ts, "message": {"conversation": msg_id}}


def page(*records):
    return {"messages": {"total": len(records), "pages": 1, "currentPage": 1, "records": list(records)}}


@pytest.fixture
def store(tmp_path):
    return ReadMarkerStore(tmp_path, "test-instance")


def test_lid_chat_sends_receipts_with_phone_jid(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10), record("B", 20)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    sent = rec.bodies(MARK_READ)[0]["readMessages"]
    assert sent == [
        {"remoteJid": PERSONAL_JID, "fromMe": False, "id": "A"},
        {"remoteJid": PERSONAL_JID, "fromMe": False, "id": "B"},
    ]
    assert result["phoneCleared"] is True
    assert result["receiptsSent"] == 2
    assert result["markerTimestamp"] == 20
    assert store.get(LID_JID) == 20


def test_number_is_resolved_to_lid_jid(client, store, recorder):
    rec = recorder({FIND_CHATS: [LID_CHAT], FIND_MESSAGES: page(record("A", 10)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, NUMBER))

    assert result["jid"] == LID_JID
    assert result["resolved"] is True
    assert rec.bodies(FIND_MESSAGES)[0]["where"] == {"key": {"remoteJid": LID_JID}}


def test_group_records_marker_but_sends_no_receipt(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10, remote_jid=GROUP_JID, alt=None))})

    result = run(rec, lambda: mark_chat_read(client, store, GROUP_JID))

    assert rec.count(MARK_READ) == 0
    assert result["phoneCleared"] is False
    assert result["reason"] == REASON_GROUP
    assert result["receiptsSent"] == 0
    assert store.get(GROUP_JID) == 10


def test_duplicate_ids_are_sent_once(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10), record("A", 10), record("B", 11)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert [k["id"] for k in rec.bodies(MARK_READ)[0]["readMessages"]] == ["A", "B"]
    assert result["receiptsSent"] == 2


def test_own_messages_and_already_marked_are_skipped(client, store, recorder):
    store.set(LID_JID, 15)
    rec = recorder({FIND_MESSAGES: page(record("old", 10), record("mine", 20, from_me=True), record("new", 30)), MARK_READ: OK})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert [k["id"] for k in rec.bodies(MARK_READ)[0]["readMessages"]] == ["new"]
    assert result["markerTimestamp"] == 30


def test_nothing_new_does_not_call_api_but_advances_marker(client, store, recorder):
    store.set(LID_JID, 10)
    rec = recorder({FIND_MESSAGES: page(record("old", 5), record("mine", 12, from_me=True))})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert rec.count(MARK_READ) == 0
    assert result["receiptsSent"] == 0
    assert result["phoneCleared"] is True
    assert result["reason"] == REASON_NOTHING_NEW
    assert store.get(LID_JID) == 12


def test_personal_jid_without_alt_is_sent_as_is(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page(record("A", 10, remote_jid=PERSONAL_JID, alt=None)), MARK_READ: OK})

    run(rec, lambda: mark_chat_read(client, store, PERSONAL_JID))

    assert rec.bodies(MARK_READ)[0]["readMessages"][0]["remoteJid"] == PERSONAL_JID


def test_unresolved_number_sends_nothing_and_records_no_marker(client, store, recorder):
    rec = recorder({FIND_CHATS: [], FIND_MESSAGES: page()})

    result = run(rec, lambda: mark_chat_read(client, store, "5500000000001"))

    assert result["resolved"] is False
    assert result["reason"] == REASON_NOT_FOUND
    assert result["receiptsSent"] == 0
    assert result["phoneCleared"] is False
    assert rec.count(MARK_READ) == 0
    assert result["markerTimestamp"] is None
    assert store.get(result["jid"]) is None


def test_empty_chat_uses_no_marker(client, store, recorder):
    rec = recorder({FIND_MESSAGES: page()})

    result = run(rec, lambda: mark_chat_read(client, store, LID_JID))

    assert result["markerTimestamp"] is None
    assert store.get(LID_JID) is None
    assert result["messagesScanned"] == 0


def chat(jid, unread, last_ts, last_from_me=False):
    return {
        "remoteJid": jid,
        "unreadCount": unread,
        "lastMessage": {"key": {"remoteJid": jid, "fromMe": last_from_me}, "messageTimestamp": last_ts},
    }


def test_chat_without_marker_keeps_evolution_count(client, store, recorder):
    rec = recorder({})
    chats = [chat(LID_JID, 7, 100)]

    out = run(rec, lambda: annotate_chats_with_markers(client, store, chats))

    assert out[0]["unreadCount"] == 7
    assert out[0]["unreadSource"] == "evolution"
    assert "readMarker" not in out[0]
    assert rec.count(FIND_MESSAGES) == 0


def test_marker_up_to_date_zeroes_count_without_http(client, store, recorder):
    store.set(LID_JID, 100)
    rec = recorder({})

    out = run(rec, lambda: annotate_chats_with_markers(client, store, [chat(LID_JID, 7, 100)]))

    assert out[0]["unreadCount"] == 0
    assert out[0]["unreadSource"] == "local_marker"
    assert out[0]["readMarker"]["lastMessageTimestamp"] == 100
    assert rec.count(FIND_MESSAGES) == 0


def test_newer_messages_are_counted_after_marker(client, store, recorder):
    store.set(LID_JID, 100)
    rec = recorder({FIND_MESSAGES: page(record("a", 90), record("b", 110), record("mine", 120, from_me=True), record("c", 130))})

    out = run(rec, lambda: annotate_chats_with_markers(client, store, [chat(LID_JID, 999, 130)]))

    assert out[0]["unreadCount"] == 2
    assert out[0]["unreadSource"] == "local_marker"
    assert "unreadCountIsLowerBound" not in out[0]
    assert rec.bodies(FIND_MESSAGES)[0]["offset"] == 100


def test_full_page_marks_count_as_lower_bound(client, store, recorder):
    store.set(LID_JID, 0)
    records = [record(str(i), i + 1) for i in range(3)]
    rec = recorder({FIND_MESSAGES: page(*records)})

    out = run(rec, lambda: annotate_chats_with_markers(client, store, [chat(LID_JID, 50, 3)], page_size=3))

    assert out[0]["unreadCount"] == 3
    assert out[0]["unreadCountIsLowerBound"] is True


def test_http_failure_falls_back_to_evolution_count(client, store, recorder, monkeypatch):
    store.set(LID_JID, 100)

    def boom(**kwargs):
        raise EvolutionAPIError("down")

    monkeypatch.setattr(client, "find_messages", lambda **kw: boom())

    out = annotate_chats_with_markers(client, store, [chat(LID_JID, 7, 130)])

    assert out[0]["unreadCount"] == 7
    assert out[0]["unreadSource"] == "evolution"


def test_chat_without_last_message_timestamp_recounts(client, store, recorder):
    store.set(LID_JID, 100)
    rec = recorder({FIND_MESSAGES: page(record("b", 110))})
    chats = [{"remoteJid": LID_JID, "unreadCount": 4}]

    out = run(rec, lambda: annotate_chats_with_markers(client, store, chats))

    assert out[0]["unreadCount"] == 1
