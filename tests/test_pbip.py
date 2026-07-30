"""PBIP emission: well-formedness, referential integrity, and honesty about .pbix.

What these tests can and cannot prove is worth stating up front. They verify every
JSON parses, that schema URLs match the constants recorded from Microsoft docs, that
every measure and column a visual references actually exists in the semantic model,
and that nothing claims a .pbix was produced. **They cannot prove Power BI Desktop
opens the file** — that needs a manual check on Windows, which is the stated exit
criterion for this feature.
"""
import json
import re

import pytest

from atlas.exporters.pbip import schemas as S
from atlas.exporters.pbip.pbir import Visual, column_field, measure_field, render_visual
from atlas.exporters.pbip.tmdl import (
    TmdlColumn, TmdlTable, dtype_to_tmdl, quote_name, render_table,
)
from atlas.orchestrator import run_analysis

Q = "who is about to churn"
SRC = dict(source="churn_fixture", table="churn", playbook="logistic")


@pytest.fixture(scope="module")
def pb(tmp_path_factory):
    res = run_analysis(Q, runs_root=tmp_path_factory.mktemp("pbip"), **SRC)
    assert res.status == "COMPLETE", res.blocked_reason
    return res.run_dir / "powerbi"


def _jsons(root):
    return list(root.rglob("*.json")) + list(root.rglob("*.pbip")) + \
        list(root.rglob("*.pbir")) + list(root.rglob("*.pbism")) + \
        list(root.rglob(".platform"))


# --------------------------- well-formedness ---------------------------
def test_project_tree_has_the_required_files(pb):
    name = "AtlasReport"
    for rel in (f"{name}.pbip",
                f"{name}.SemanticModel/definition.pbism",
                f"{name}.SemanticModel/definition/model.tmdl",
                f"{name}.SemanticModel/definition/database.tmdl",
                f"{name}.Report/definition.pbir",
                f"{name}.Report/definition/version.json",
                f"{name}.Report/definition/report.json",
                f"{name}.Report/definition/pages/pages.json",
                "LAYOUT_GUIDE.md", "PBIP_LIMITATIONS.md"):
        assert (pb / rel).exists(), f"missing {rel}"


def test_every_emitted_json_parses(pb):
    for p in _jsons(pb):
        json.loads(p.read_text())          # raises on malformed output


def test_no_placeholder_survives(pb):
    """A bare `{{` is NOT a placeholder here — Power Query M nests lists as
    `Table.TransformColumnTypes(t, {{"col", type}})`. Match the mustache form only."""
    for p in pb.rglob("*"):
        if p.is_file():
            leftover = re.findall(r"\{\{\s*[A-Za-z_]\w*\s*\}\}", p.read_text())
            assert not leftover, f"unfilled placeholder {leftover} in {p.name}"


def test_schema_urls_match_the_recorded_constants(pb):
    """These URLs are versioned and roll. If Microsoft moves one, this fails here
    rather than as a mystery load error in Power BI Desktop."""
    name = "AtlasReport"
    cases = [
        (f"{name}.pbip", S.PBIP_SCHEMA),
        (f"{name}.SemanticModel/definition.pbism", S.PBISM_SCHEMA),
        (f"{name}.Report/definition.pbir", S.PBIR_SCHEMA),
        (f"{name}.Report/definition/version.json", S.VERSION_SCHEMA),
        (f"{name}.Report/definition/report.json", S.REPORT_SCHEMA),
        (f"{name}.Report/definition/pages/pages.json", S.PAGES_SCHEMA),
    ]
    for rel, expected in cases:
        assert json.loads((pb / rel).read_text())["$schema"] == expected, rel


def test_version_string_matches_the_schema_pattern(pb):
    """versionMetadata enforces ^[1-9][0-9]*\\.(0|[1-9][0-9]*)\\.0$."""
    v = json.loads((pb / "AtlasReport.Report/definition/version.json").read_text())
    assert re.fullmatch(r"[1-9][0-9]*\.(0|[1-9][0-9]*)\.0", v["version"])


def test_pbir_points_at_the_sibling_semantic_model(pb):
    d = json.loads((pb / "AtlasReport.Report/definition.pbir").read_text())
    assert d["datasetReference"]["byPath"]["path"] == "../AtlasReport.SemanticModel"
    assert (pb / "AtlasReport.SemanticModel").is_dir()


# --------------------------- page / visual contracts ---------------------------
def _pages(pb):
    return sorted((pb / "AtlasReport.Report/definition/pages").glob("*/page.json"))


def test_pages_carry_every_required_property(pb):
    """page.json requires $schema, name, displayName, displayOption."""
    for p in _pages(pb):
        d = json.loads(p.read_text())
        for k in ("$schema", "name", "displayName", "displayOption"):
            assert k in d, f"{p.parent.name} missing {k}"
        assert d["displayOption"] == S.DISPLAY_FIT_TO_PAGE
        assert d["name"] == p.parent.name       # folder name must match the object


def test_page_order_lists_real_pages(pb):
    meta = json.loads((pb / "AtlasReport.Report/definition/pages/pages.json").read_text())
    on_disk = {p.parent.name for p in _pages(pb)}
    assert set(meta["pageOrder"]) == on_disk
    assert meta["activePageName"] in on_disk


def test_visual_names_obey_the_pbir_naming_rule(pb):
    """Must be word characters or hyphens, max 50 — otherwise Desktop ignores the
    file and treats it as a private user file, silently dropping the visual."""
    for v in pb.rglob("visuals/*/visual.json"):
        d = json.loads(v.read_text())
        assert re.fullmatch(r"[\w-]+", d["name"]), d["name"]
        assert len(d["name"]) <= 50
        assert d["name"] == v.parent.name       # folder must match the object name


def test_visuals_have_required_position_and_fit_the_canvas(pb):
    for v in pb.rglob("visuals/*/visual.json"):
        d = json.loads(v.read_text())
        assert d["$schema"] == S.VISUAL_SCHEMA
        pos = d["position"]
        for k in ("x", "y", "width", "height"):
            assert k in pos, f"{d['name']} position missing {k}"
        assert pos["x"] >= 0 and pos["y"] >= 0
        assert pos["x"] + pos["width"] <= S.CANVAS_W, f"{d['name']} overflows width"
        assert pos["y"] + pos["height"] <= S.CANVAS_H, f"{d['name']} overflows height"


def test_visuals_do_not_overlap_within_a_page(pb):
    """A laid-out report means visuals sit side by side, not stacked at the origin."""
    for page in _pages(pb):
        boxes = []
        for v in (page.parent / "visuals").glob("*/visual.json"):
            p = json.loads(v.read_text())["position"]
            boxes.append((p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = not (a[2] <= b[0] or b[2] <= a[0] or
                               a[3] <= b[1] or b[3] <= a[1])
                assert not overlap, f"{page.parent.name}: {a} overlaps {b}"


# --------------------------- referential integrity ---------------------------
def _model_measures(pb) -> set[str]:
    text = (pb / "AtlasReport.SemanticModel/definition/tables/_Measures.tmdl").read_text()
    return set(re.findall(r"measure '([^']+)'|measure (\w+) =", text)[0:0]) | {
        m.group(1) or m.group(2)
        for m in re.finditer(r"\tmeasure (?:'([^']+)'|(\S+)) =", text)}


def _model_columns(pb) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    tdir = pb / "AtlasReport.SemanticModel/definition/tables"
    for f in tdir.glob("*.tmdl"):
        text = f.read_text()
        tname = re.search(r"^table (?:'([^']+)'|(\S+))", text, re.M)
        name = (tname.group(1) or tname.group(2)) if tname else f.stem
        cols = {m.group(1) or m.group(2)
                for m in re.finditer(r"\tcolumn (?:'([^']+)'|(\S+))", text)}
        out[name] = cols
    return out


def test_every_measure_a_visual_references_exists_in_the_model(pb):
    """A visual bound to a measure that isn't in the model renders blank — the exact
    failure mode that looks like the dashboard 'just didn't work'."""
    have = _model_measures(pb)
    assert have, "no measures parsed out of _Measures.tmdl"
    for v in pb.rglob("visuals/*/visual.json"):
        d = json.loads(v.read_text())
        for role in (d["visual"].get("query", {}).get("queryState") or {}).values():
            for proj in role["projections"]:
                f = proj["field"]
                if "Measure" in f:
                    assert f["Measure"]["Property"] in have, \
                        f"{d['name']} references missing measure {f['Measure']['Property']}"


def test_every_column_a_visual_references_exists_in_the_model(pb):
    cols = _model_columns(pb)
    for v in pb.rglob("visuals/*/visual.json"):
        d = json.loads(v.read_text())
        for role in (d["visual"].get("query", {}).get("queryState") or {}).values():
            for proj in role["projections"]:
                f = proj["field"]
                if "Column" in f:
                    ent = f["Column"]["Expression"]["SourceRef"]["Entity"]
                    prop = f["Column"]["Property"]
                    assert ent in cols, f"{d['name']} references unknown table {ent}"
                    assert prop in cols[ent], \
                        f"{d['name']} references missing column {ent}[{prop}]"


def test_model_references_every_table_file(pb):
    model = (pb / "AtlasReport.SemanticModel/definition/model.tmdl").read_text()
    refs = set(re.findall(r"ref table (?:'([^']+)'|(\S+))", model))
    refs = {a or b for a, b in refs}
    files = {p.stem for p in
             (pb / "AtlasReport.SemanticModel/definition/tables").glob("*.tmdl")}
    assert refs == files


def test_tier_digest_agrees_across_model_and_guide(pb):
    from atlas.lib.risk_tiers import load_policy
    digest = load_policy().digest()
    assert digest in (pb / "AtlasReport.SemanticModel/definition/model.tmdl").read_text()
    assert digest in (pb / "LAYOUT_GUIDE.md").read_text()


def test_bucket_column_is_emitted_only_because_a_threshold_was_measured(pb):
    """The user's conditional: the band column exists because the data has a cliff,
    not as decoration."""
    t = (pb / "AtlasReport.SemanticModel/definition/tables/churn.tmdl").read_text()
    assert "'Payment Delay Bucket'" in t
    assert "SWITCH(" in t and "16.0" in t and "21.0" in t
    assert "threshold effect" in t          # the evidence travels with the column


# --------------------------- honesty about .pbix ---------------------------
def test_nothing_claims_a_pbix_was_produced(pb):
    """`.pbix` may appear only in the Save As instruction and the limitations file."""
    allowed = {"LAYOUT_GUIDE.md", "PBIP_LIMITATIONS.md"}
    for p in pb.rglob("*"):
        if p.is_file() and p.name not in allowed:
            assert ".pbix" not in p.read_text(), f"{p.name} mentions .pbix"


def test_limitations_state_the_windows_constraint_plainly(pb):
    txt = (pb / "PBIP_LIMITATIONS.md").read_text()
    assert "is **not** a `.pbix`" in txt
    assert "Windows" in txt
    assert "did not produce one and does not claim to have" in txt
    assert "manual check on Windows" in txt


def test_layout_guide_tabulates_every_visual_position(pb):
    guide = (pb / "LAYOUT_GUIDE.md").read_text()
    assert "| visual | type | x | y | w | h |" in guide
    n_visuals = len(list(pb.rglob("visuals/*/visual.json")))
    rows = len(re.findall(r"^\| .+ \| `\w+` \| \d+ \| \d+ \| \d+ \| \d+ \|$",
                          guide, re.M))
    assert rows == n_visuals, f"guide lists {rows} visuals, {n_visuals} emitted"
    assert "Save As" in guide


# --------------------------- unit-level TMDL ---------------------------
def test_tmdl_quotes_names_that_need_it():
    assert quote_name("Payment Delay") == "'Payment Delay'"
    assert quote_name("Simple") == "Simple"
    assert quote_name("it's") == "'it''s'"


def test_tmdl_uses_tab_indentation_at_the_right_depths():
    """The docs are explicit that wrong indentation is a parse error."""
    t = render_table(TmdlTable(name="T", columns=[TmdlColumn("A", "BIGINT")]))
    assert "\tcolumn A\n" in t
    assert "\t\tdataType: int64\n" in t
    assert "    column" not in t            # never spaces


def test_multiline_measure_is_indented_one_level_deeper_than_properties():
    class _M:
        name, expression, format_string, description = (
            "M", "SWITCH(\n    TRUE(),\n    1, 2\n)", '"0"', "")
    t = render_table(TmdlTable(name="T", measures=[_M()]))
    assert "\tmeasure M =\n" in t
    assert "\t\t\tSWITCH(" in t
    assert "\t\tformatString:" in t


def test_dtype_mapping():
    assert dtype_to_tmdl("BIGINT") == "int64"
    assert dtype_to_tmdl("DOUBLE") == "double"
    assert dtype_to_tmdl("VARCHAR") == "string"
    assert dtype_to_tmdl("BOOLEAN") == "boolean"


def test_visual_field_binding_shape():
    v = Visual(visual_type="card", x=0, y=0, width=10, height=10,
               roles={"Values": [measure_field("_Measures", "Churn Rate")]})
    d = render_visual(v, page="p", index=0)
    proj = d["visual"]["query"]["queryState"]["Values"]["projections"][0]
    assert proj["field"]["Measure"]["Expression"]["SourceRef"]["Entity"] == "_Measures"
    assert proj["field"]["Measure"]["Property"] == "Churn Rate"
    assert proj["queryRef"] == "_Measures.Churn Rate"


def test_column_binding_uses_Column_not_Measure():
    v = Visual(visual_type="clusteredColumnChart", x=0, y=0, width=10, height=10,
               roles={"Category": [column_field("churn", "Gender")]})
    d = render_visual(v, page="p", index=0)
    proj = d["visual"]["query"]["queryState"]["Category"]["projections"][0]
    assert "Column" in proj["field"] and "Measure" not in proj["field"]


def test_visual_names_are_stable_across_regeneration():
    """Content-derived names keep re-exports diff-clean, which is the point of PBIR."""
    v = Visual(visual_type="card", x=0, y=0, width=1, height=1, title="X")
    assert v.resolved_name("p", 0) == v.resolved_name("p", 0)
    other = Visual(visual_type="card", x=0, y=0, width=1, height=1, title="Y")
    assert v.resolved_name("p", 0) != other.resolved_name("p", 0)
