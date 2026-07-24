from atlas.lib import query_archive as qa


def test_archive_and_retrieve(tmp_path):
    p = tmp_path / "archive.jsonl"
    qa.archive("SELECT sum(revenue) FROM finance WHERE region='EMEA'",
               source="emea_finance_csv", dialect="duckdb", metric="gross_margin",
               intent_tags=["margin", "period-compare"], result_hash="rh1",
               run_id="r1", path=p)
    hits = qa.retrieve(source="emea_finance_csv", metric="gross_margin",
                       intent_tags=["margin"], path=p)
    assert len(hits) == 1
    assert hits[0].id == "Q-0001"
    assert "revenue" in hits[0].sql


def test_identical_query_is_reused_not_duplicated(tmp_path):
    p = tmp_path / "archive.jsonl"
    sql = "SELECT sum(revenue) FROM finance"
    qa.archive(sql, source="s", dialect="duckdb", metric="revenue",
               intent_tags=["a"], path=p)
    aq = qa.archive("  SELECT   sum(revenue)   FROM finance ;", source="s",
                    dialect="duckdb", metric="revenue", intent_tags=["b"], path=p)
    assert aq.times_reused == 1                       # reused, not a new row
    assert set(aq.intent_tags) == {"a", "b"}           # tags merged
    assert qa.stats(path=p)["total"] == 1


def test_retrieve_ranks_by_tag_overlap(tmp_path):
    p = tmp_path / "archive.jsonl"
    qa.archive("SELECT 1", source="s", dialect="duckdb", metric="m",
               intent_tags=["margin", "period-compare", "by-product_line"], path=p)
    qa.archive("SELECT 2", source="s", dialect="duckdb", metric="m",
               intent_tags=["revenue"], path=p)
    hits = qa.retrieve(source="s", metric="m",
                       intent_tags=["margin", "period-compare"], path=p)
    assert hits[0].sql == "SELECT 1"                   # best tag overlap first


def test_source_and_metric_filters(tmp_path):
    p = tmp_path / "archive.jsonl"
    qa.archive("SELECT 1", source="a", dialect="duckdb", metric="m1",
               intent_tags=[], path=p)
    qa.archive("SELECT 2", source="b", dialect="duckdb", metric="m2",
               intent_tags=[], path=p)
    assert len(qa.retrieve(source="a", path=p)) == 1
    assert len(qa.retrieve(metric="m2", path=p)) == 1
