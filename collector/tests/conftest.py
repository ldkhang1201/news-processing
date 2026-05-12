from __future__ import annotations

import pytest

from collector.settings import Settings


@pytest.fixture
def tmp_db(tmp_path) -> str:
    return str(tmp_path / "dedup.sqlite")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)
