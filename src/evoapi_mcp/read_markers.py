import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STORE_VERSION = 1


def _merge_entry(a: dict | None, b: dict | None) -> dict:
    if a is None:
        return dict(b)
    if b is None:
        return dict(a)
    a_ts = int(a.get("lastMessageTimestamp", 0))
    b_ts = int(b.get("lastMessageTimestamp", 0))
    if a_ts > b_ts:
        return dict(a)
    if b_ts > a_ts:
        return dict(b)
    ids = sorted(set(a.get("lastMessageIds") or []) | set(b.get("lastMessageIds") or []))
    marked_at = max(a.get("markedAt") or "", b.get("markedAt") or "") or a.get("markedAt") or b.get("markedAt")
    return {"lastMessageTimestamp": a_ts, "lastMessageIds": ids, "markedAt": marked_at}


class ReadMarkerStore:
    def __init__(self, state_dir: Path, instance_name: str) -> None:
        self.path = Path(state_dir).expanduser() / f"{instance_name}.read-markers.json"
        self._chats: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                print(f"[WARNING] Read markers: ignoring unreadable {self.path}: not an object", file=sys.stderr)
                return {}
            chats = data.get("chats", {})
            if not isinstance(chats, dict):
                return {}
            return {jid: entry for jid, entry in chats.items() if isinstance(entry, dict)}
        except (ValueError, OSError) as error:
            print(f"[WARNING] Read markers: ignoring unreadable {self.path}: {error}", file=sys.stderr)
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"version": STORE_VERSION, "chats": self._chats}
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def get(self, jid: str) -> int | None:
        entry = self._chats.get(jid)
        return entry.get("lastMessageTimestamp") if entry else None

    def get_entry(self, jid: str) -> dict | None:
        entry = self._chats.get(jid)
        return dict(entry) if entry else None

    def set(self, jid: str, last_message_timestamp: int, last_message_ids: list[str] | None = None) -> dict:
        incoming = {
            "lastMessageTimestamp": int(last_message_timestamp),
            "lastMessageIds": list(last_message_ids) if last_message_ids else [],
            "markedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._chats[jid] = _merge_entry(self._chats.get(jid), incoming)

        on_disk = self._load()
        merged: dict[str, dict] = {}
        for key in set(on_disk) | set(self._chats):
            merged[key] = _merge_entry(on_disk.get(key), self._chats.get(key))
        self._chats = merged

        self._save()
        return dict(self._chats[jid])

    def all(self) -> dict[str, dict]:
        return {jid: dict(entry) for jid, entry in self._chats.items()}
