import importlib
import sys

import pytest


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOLUTION_BASE_URL", "http://evolution.test")
    monkeypatch.setenv("EVOLUTION_API_TOKEN", "t")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "test-instance")
    monkeypatch.setenv("EVOLUTION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EVOLUTION_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("evoapi_mcp.server", None)
    module = importlib.import_module("evoapi_mcp.server")
    yield module
    sys.modules.pop("evoapi_mcp.server", None)


def test_registers_new_tools(server):
    names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    assert {"mark_as_read", "download_media", "transcribe_audio", "transcribe_chat_audios"} <= names


def test_mark_as_read_description_forbids_automatic_use(server):
    tool = server.mcp._tool_manager.get_tool("mark_as_read")
    assert "NUNCA" in tool.description
    assert "comando explícito" in tool.description


def test_mark_as_read_accepts_list_and_isolates_failures(server, monkeypatch):
    calls = []

    def fake(client, store, chat, page_size=100):
        calls.append(chat)
        if chat == "bad":
            raise RuntimeError("boom")
        return {"requested": chat, "jid": chat, "phoneCleared": True}

    monkeypatch.setattr(server, "mark_chat_read", fake)

    out = server.mark_as_read(["a", "bad", "c"])

    assert calls == ["a", "bad", "c"]
    assert out[0]["phoneCleared"] is True
    assert out[1]["requested"] == "bad" and "boom" in out[1]["error"]
    assert out[2]["jid"] == "c"


def test_mark_as_read_accepts_single_string(server, monkeypatch):
    monkeypatch.setattr(server, "mark_chat_read", lambda client, store, chat, page_size=100: {"requested": chat})

    assert server.mark_as_read("5511999999999") == [{"requested": "5511999999999"}]


def test_list_chats_is_annotated_before_limit(server, monkeypatch):
    chats = [{"remoteJid": "a@lid", "unreadCount": 3}, {"remoteJid": "b@lid", "unreadCount": 4}]
    monkeypatch.setattr(server.client, "find_chats", lambda **kw: chats)
    seen = {}

    def fake_annotate(client, store, chats, page_size=100):
        seen["count"] = len(chats)
        for c in chats:
            c["unreadSource"] = "evolution"
        return chats

    monkeypatch.setattr(server, "annotate_chats_with_markers", fake_annotate)

    out = server.list_chats(limit=1)

    assert seen["count"] == 2
    assert out == [{"remoteJid": "a@lid", "unreadCount": 3, "unreadSource": "evolution"}]


def test_download_media_uses_configured_dir(server, monkeypatch, tmp_path):
    captured = {}

    def fake(client, media_dir, message_id):
        captured["dir"] = media_dir
        captured["id"] = message_id
        return {"path": "x"}

    monkeypatch.setattr(server, "download_media_to_disk", fake)

    assert server.download_media("MSG1") == {"path": "x"}
    assert captured == {"dir": server.config.media_dir, "id": "MSG1"}


def test_transcribe_tools_delegate(server, monkeypatch):
    monkeypatch.setattr(server, "transcribe_message", lambda client, config, message_id, language=None: {"text": f"{message_id}:{language}"})
    monkeypatch.setattr(server, "transcribe_chat_audios_in_page", lambda client, config, chat, limit=50, page=1, language=None: {"chat": chat, "limit": limit, "page": page})

    assert server.transcribe_audio("M", language="pt") == {"text": "M:pt"}
    assert server.transcribe_chat_audios("c", limit=5, page=2) == {"chat": "c", "limit": 5, "page": 2}
