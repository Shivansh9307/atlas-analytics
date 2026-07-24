from atlas.lib.provenance import Claim, ProvenanceLedger
from atlas.lib.query_store import hash_query, hash_result


def test_hash_query_is_normalised_and_stable():
    a = hash_query("SELECT 1", "s", "duckdb")
    b = hash_query("  SELECT    1  ;", "s", "duckdb")
    assert a == b
    assert hash_query("SELECT 1", "other", "duckdb") != a


def test_hash_result_key_order_insensitive():
    r1 = [{"a": 1, "b": 2}]
    r2 = [{"b": 2, "a": 1}]
    assert hash_result(r1, ["a", "b"]) == hash_result(r2, ["a", "b"])


def test_ledger_records_and_resolves():
    led = ProvenanceLedger("r-test")
    led.record("c1", "EMEA Q2 GM = 56%", 56.0, "qh1", "rh1")
    assert led.resolves("c1")
    assert led.orphans(["c1", "c2"]) == ["c2"]  # c2 never recorded


def test_ledger_blocks_orphan_numbers():
    led = ProvenanceLedger("r-test")
    led.add(Claim("c1", "x", 1, query_hash="qh", result_hash=""))  # missing result hash
    assert not led.resolves("c1")
    assert led.orphans(["c1"]) == ["c1"]


def test_ledger_roundtrip(tmp_path):
    led = ProvenanceLedger("r-test")
    led.record("c1", "x", 1.0, "qh", "rh", evidence_tier="tested")
    led.attach_slide("c1", 3)
    p = led.save(tmp_path / "provenance.json")
    back = ProvenanceLedger.load(p)
    assert back.get("c1").slide_number == 3
    assert back.get("c1").evidence_tier == "tested"
