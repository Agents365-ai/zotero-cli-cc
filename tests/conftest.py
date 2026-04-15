import os
from pathlib import Path

import pytest

from zotero_cli_cc.config import AppConfig

# Default ZOT_FORMAT for tests.
# Many existing tests assert `"some text" in result.output`. Under the new
# contract, human prose goes to stderr while JSON envelopes go to stdout. The
# JSON envelope still contains the error message text, so defaulting tests to
# JSON mode keeps substring checks working against stdout.
# test_agent_interface.py explicitly clears this to exercise TTY auto-detect.
os.environ.setdefault("ZOT_FORMAT", "table")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def test_db_path() -> Path:
    return FIXTURES_DIR / "zotero.sqlite"


@pytest.fixture
def test_config(test_db_path: Path) -> AppConfig:
    return AppConfig(data_dir=str(test_db_path.parent))


@pytest.fixture
def test_data_dir() -> Path:
    return FIXTURES_DIR
