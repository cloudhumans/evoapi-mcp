import sys
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

NUMBER = "5511999999999"
PERSONAL_JID = f"{NUMBER}@s.whatsapp.net"
LID_JID = "100000000000000@lid"
GROUP_JID = "120363000000000000@g.us"

FIND_MESSAGES = "/chat/findMessages/"
FIND_CHATS = "/chat/findChats/"
FIND_CONTACTS = "/chat/findContacts/"
SEND_TEXT = "/message/sendText/"
MARK_READ = "/chat/markMessageAsRead/"
GET_BASE64 = "/chat/getBase64FromMediaMessage/"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

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


def run(recorder_obj, call):
    with patch("evoapi_mcp.client.requests.request", side_effect=recorder_obj):
        return call()
