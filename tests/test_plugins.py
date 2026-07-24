"""Phase 6: the copilot plugin framework — register without editing core code."""
from __future__ import annotations

from atlas.connectors.base import TableRef
from atlas.quality import plugins


def test_data_quality_copilot_is_registered():
    dq = plugins.get_copilot("data-quality")
    assert dq is not None and "clean layer" in dq.description


def test_data_quality_copilot_runs_via_plugin(dirty):
    dq = plugins.get_copilot("data-quality")
    summary = dq.run(dirty, TableRef("dirty"), "dirty_src")
    assert summary["score_after"] > summary["score_before"]


def test_new_copilot_plugs_in_without_core_edits():
    @plugins.register_copilot
    class _PiiCopilot(plugins.Copilot):
        id = "pii-demo"
        description = "demo PII scanner"

        def run(self, con, table, source, run_dir=None):
            return {"pii_columns": []}

    try:
        assert plugins.get_copilot("pii-demo") is not None
        assert "pii-demo" in {c.id for c in plugins.all_copilots()}
        assert plugins.get_copilot("pii-demo").run(None, None, "x") == {"pii_columns": []}
    finally:
        plugins.COPILOT_REGISTRY.pop("pii-demo", None)   # keep the registry clean
