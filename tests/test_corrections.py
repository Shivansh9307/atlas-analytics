from atlas.lib.corrections import log_correction, log_miss, miss_rate


def test_log_correction_assigns_id_and_promotion_hint(tmp_path):
    p = tmp_path / "corr.jsonl"
    c = log_correction("used net not gross margin", "use gross margin",
                       cls="metric-definition", scope="metric:gross_margin", path=p)
    assert c.id == "C-0001"
    assert "metrics.yaml" in c.promotion_hint          # promotable class


def test_analytical_correction_not_promotable(tmp_path):
    p = tmp_path / "corr.jsonl"
    c = log_correction("weak causal claim", "decompose first", cls="analytical", path=p)
    assert c.promotion_hint is None


def test_ids_increment(tmp_path):
    p = tmp_path / "corr.jsonl"
    log_correction("a", "b", path=p)
    c2 = log_correction("c", "d", path=p)
    assert c2.id == "C-0002"


def test_miss_rate(tmp_path):
    p = tmp_path / "miss.jsonl"
    log_miss("metric-ambiguity", prevented=True, path=p)
    log_miss("filter-leakage", prevented=False, path=p)
    log_miss("wrong-column", prevented=False, path=p)
    r = miss_rate(path=p)
    assert r["events"] == 3
    assert r["misses"] == 2
    assert round(r["miss_rate"], 3) == round(2 / 3, 3)
