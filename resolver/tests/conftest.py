from __future__ import annotations

import pytest

from resolver.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)
