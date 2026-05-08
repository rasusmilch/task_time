from __future__ import annotations

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def isolate_loguru_sinks() -> None:
    logger.remove()
    yield
    logger.remove()
