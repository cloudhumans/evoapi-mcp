import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STORE_VERSION = 1


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

    def set(self, jid: str, last_message_timestamp: int) -> dict:
        entry = {
            "lastMessageTimestamp": int(last_message_timestamp),
            "markedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._chats[jid] = entry
        self._save()
        return dict(entry)

    def all(self) -> dict[str, dict]:
        return {jid: dict(entry) for jid, entry in self._chats.items()}
