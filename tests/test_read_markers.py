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


def test_write_leaves_no_tmp_file_and_persists_all_entries(tmp_path):
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


def test_top_level_non_object_json_degrades_gracefully(tmp_path):
    (tmp_path / "inst.read-markers.json").write_text("[1, 2, 3]")

    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get(JID) is None
    assert store.all() == {}
    store.set(JID, 5)
    assert ReadMarkerStore(tmp_path, "inst").get(JID) == 5


def test_top_level_string_json_degrades_gracefully(tmp_path):
    (tmp_path / "inst.read-markers.json").write_text('"a string"')

    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get(JID) is None
    assert store.all() == {}
    store.set(JID, 5)
    assert ReadMarkerStore(tmp_path, "inst").get(JID) == 5


def test_top_level_null_json_degrades_gracefully(tmp_path):
    (tmp_path / "inst.read-markers.json").write_text("null")

    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get(JID) is None
    assert store.all() == {}
    store.set(JID, 5)
    assert ReadMarkerStore(tmp_path, "inst").get(JID) == 5


def test_set_stores_last_message_ids(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")

    entry = store.set(JID, 100, ["a", "b"])

    assert entry["lastMessageIds"] == ["a", "b"]
    assert store.get_entry(JID)["lastMessageIds"] == ["a", "b"]


def test_set_without_ids_defaults_to_empty_list(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")

    entry = store.set(JID, 100)

    assert entry["lastMessageIds"] == []


def test_concurrent_stores_merge_instead_of_clobbering(tmp_path):
    store_a = ReadMarkerStore(tmp_path, "inst")
    store_b = ReadMarkerStore(tmp_path, "inst")

    store_a.set("x@lid", 10)
    store_b.set("y@lid", 20)

    on_disk = ReadMarkerStore(tmp_path, "inst")
    assert on_disk.get("x@lid") == 10
    assert on_disk.get("y@lid") == 20


def test_set_never_moves_marker_backwards(tmp_path):
    store = ReadMarkerStore(tmp_path, "inst")
    store.set(JID, 100)

    store.set(JID, 50)

    assert store.get(JID) == 100


def test_set_with_equal_timestamp_unions_ids_across_stores(tmp_path):
    store_a = ReadMarkerStore(tmp_path, "inst")
    store_b = ReadMarkerStore(tmp_path, "inst")

    store_a.set(JID, 100, ["a"])
    store_b.set(JID, 100, ["b"])

    entry = ReadMarkerStore(tmp_path, "inst").get_entry(JID)
    assert entry["lastMessageTimestamp"] == 100
    assert sorted(entry["lastMessageIds"]) == ["a", "b"]


def test_malformed_entry_drops_non_dict_values(tmp_path):
    (tmp_path / "inst.read-markers.json").write_text(json.dumps({
        "version": 1,
        "chats": {
            "good@lid": {"lastMessageTimestamp": 5, "markedAt": "2026-09-21T14:30:45+00:00"},
            "bad@lid": "not-a-dict"
        }
    }))

    store = ReadMarkerStore(tmp_path, "inst")

    assert store.get("good@lid") == 5
    assert store.get("bad@lid") is None
    assert "good@lid" in store.all()
    assert "bad@lid" not in store.all()
