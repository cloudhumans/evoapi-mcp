from typing import Any

from evoapi_mcp.client import GROUP_JID_SUFFIX, EvolutionAPIError, EvolutionClient
from evoapi_mcp.read_markers import ReadMarkerStore

REASON_GROUP = "group_receipts_unsupported"
REASON_NOT_FOUND = "chat_not_found"
REASON_NOTHING_NEW = "nothing_new"


def receipt_key(key: dict[str, Any]) -> dict[str, Any]:
    return {
        "remoteJid": key.get("remoteJidAlt") or key["remoteJid"],
        "fromMe": bool(key.get("fromMe")),
        "id": key["id"],
    }


def _records(result: Any) -> list[dict[str, Any]]:
    block = result.get("messages") if isinstance(result, dict) else None
    records = block.get("records") if isinstance(block, dict) else None
    return records if isinstance(records, list) else []


def _timestamp(record: dict[str, Any]) -> int:
    value = record.get("messageTimestamp")
    if isinstance(value, dict):
        value = value.get("low")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_unread(ts: int, message_id: str | None, marker_before: int | None, marker_ids: set[str]) -> bool:
    if marker_before is None:
        return True
    if ts > marker_before:
        return True
    if ts == marker_before and message_id not in marker_ids:
        return True
    return False


def _pending_keys(
    records: list[dict[str, Any]],
    marker_before: int | None,
    marker_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    marker_ids = marker_ids or set()
    seen: set[str] = set()
    pending: list[dict[str, Any]] = []
    for record in records:
        key = record.get("key") or {}
        message_id = key.get("id")
        if not message_id or key.get("fromMe") or message_id in seen:
            continue
        if not _is_unread(_timestamp(record), message_id, marker_before, marker_ids):
            continue
        seen.add(message_id)
        pending.append(receipt_key(key))
    return pending


def mark_chat_read(
    client: EvolutionClient,
    store: ReadMarkerStore,
    chat: str,
    page_size: int = 100,
) -> dict[str, Any]:
    jid, resolved = client.resolve_chat_jid_detail(chat)
    result: dict[str, Any] = {
        "requested": chat,
        "jid": jid,
        "resolved": resolved,
        "receiptsSent": 0,
        "phoneCleared": False,
        "reason": None,
        "markerTimestamp": None,
        "messagesScanned": 0,
    }

    records = _records(client.find_messages(chat_id=jid, limit=page_size))
    result["messagesScanned"] = len(records)

    if not resolved:
        result["reason"] = REASON_NOT_FOUND
        return result

    marker_entry = store.get_entry(jid)
    marker_before = marker_entry["lastMessageTimestamp"] if marker_entry else None
    marker_ids = set(marker_entry.get("lastMessageIds") or []) if marker_entry else set()
    pending = _pending_keys(records, marker_before, marker_ids)
    is_group = jid.endswith(GROUP_JID_SUFFIX)

    if is_group:
        result["reason"] = REASON_GROUP
    elif pending:
        client.mark_messages_read(pending)
        result["receiptsSent"] = len(pending)
        result["phoneCleared"] = True
    else:
        result["reason"] = REASON_NOTHING_NEW
        result["phoneCleared"] = None

    newest = max((_timestamp(r) for r in records), default=0)
    if newest:
        newest_ids = sorted({
            (record.get("key") or {}).get("id")
            for record in records
            if _timestamp(record) == newest and (record.get("key") or {}).get("id")
        })
        store.set(jid, newest, newest_ids)
        result["markerTimestamp"] = newest

    return result


def _last_message_timestamp(chat: dict[str, Any]) -> int | None:
    last = chat.get("lastMessage") or {}
    value = last.get("messageTimestamp")
    if value is None:
        return None
    return _timestamp({"messageTimestamp": value})


def _count_unread_since(
    client: EvolutionClient,
    jid: str,
    marker: int,
    page_size: int,
    marker_ids: set[str] | None = None,
) -> tuple[int, bool]:
    marker_ids = marker_ids or set()
    records = _records(client.find_messages(chat_id=jid, limit=page_size))
    count = sum(
        1 for r in records
        if not (r.get("key") or {}).get("fromMe")
        and _is_unread(_timestamp(r), (r.get("key") or {}).get("id"), marker, marker_ids)
    )
    return count, len(records) >= page_size


def annotate_chats_with_markers(
    client: EvolutionClient,
    store: ReadMarkerStore,
    chats: list[dict[str, Any]],
    page_size: int = 100,
) -> list[dict[str, Any]]:
    for chat in chats:
        jid = chat.get("remoteJid") or ""
        entry = store.get_entry(jid) if jid else None
        if not entry:
            chat["unreadSource"] = "evolution"
            continue

        marker = int(entry["lastMessageTimestamp"])
        marker_ids = set(entry.get("lastMessageIds") or [])
        last_ts = _last_message_timestamp(chat)

        if last_ts is not None and last_ts < marker:
            chat["unreadCount"] = 0
            chat["unreadSource"] = "local_marker"
            chat["readMarker"] = entry
            continue

        try:
            count, is_lower_bound = _count_unread_since(client, jid, marker, page_size, marker_ids)
        except EvolutionAPIError as error:
            client._log(f"Unread recount failed for {jid}: {error}", "WARNING")
            chat["unreadSource"] = "evolution"
            continue

        chat["unreadCount"] = count
        chat["unreadSource"] = "local_marker"
        chat["readMarker"] = entry
        if is_lower_bound:
            chat["unreadCountIsLowerBound"] = True

    return chats
