from pathlib import Path

import pytest

from zotero_cli_cc.config import AppConfig

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
