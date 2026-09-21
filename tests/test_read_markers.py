import json
from pathlib import Path

from evoapi_mcp.read_markers import ReadMarkerStore

JID = "245814047813821@lid"


def test_get_on_missing_file_returns_none(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get(JID) is None
    assert store.all() == {}
    assert not store.path.exists()


def test_set_then_get_round_trips_and_persists(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")

    entry = store.set(JID, 1789732047)

    assert entry["lastMessageTimestamp"] == 1789732047
    assert "markedAt" in entry
    assert store.get(JID) == 1789732047
    assert ReadMarkerStore(tmp_path, "inst").get(JID) == 1789732047


def test_file_is_namespaced_by_instance(tmp_path):
    ReadMarkerStore(tmp_path, "a").set(JID, 1)
    ReadMarkerStore(tmp_path, "b").set(JID, 2)

    assert ReadMarkerStore(tmp_path, "a").get(JID) == 1
    assert ReadMarkerStore(tmp_path, "b").get(JID) == 2
    assert (tmp_path / "a.read-markers.json").exists()


def test_corrupted_file_starts_empty(tmp_path):
    (tmp_path / "inst.read-markers.json").write_text("{not json")

    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get(JID) is None
    store.set(JID, 5)
    assert json.loads((tmp_path / "inst.read-markers.json").read_text())["chats"][JID]["lastMessageTimestamp"] == 5


def test_write_is_atomic_and_leaves_no_tmp(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")
    store.set(JID, 1)
    store.set("x@g.us", 2)

    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    data = json.loads(store.path.read_text())
    assert data["version"] == 1
    assert set(data["chats"]) == {JID, "x@g.us"}


def test_creates_state_dir_on_first_write(tmp_path):
    store = ReadMarkerStore(tmp_path / "nested" / "dir", "inst")

    store.set(JID, 1)

    assert store.path.exists()
