import sys
from pathlib import Path

# ensure repo root importable regardless of pytest invocation dir
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from atlas.connectors.registry import Registry
from atlas.lib.query_store import QueryStore

FIXTURE = ROOT / "tests" / "fixtures" / "emea_margin.csv"


@pytest.fixture(scope="session", autouse=True)
def _ensure_fixture():
    if not FIXTURE.exists():
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "tests" / "fixtures" / "make_fixture.py")], check=True)


@pytest.fixture
def store(tmp_path):
    return QueryStore(tmp_path / "run")


@pytest.fixture
def finance(store):
    reg = Registry()
    con = reg.connector("emea_finance_csv", store=store)
    yield con
    con.close()
