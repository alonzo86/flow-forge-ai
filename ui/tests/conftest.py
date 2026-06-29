from typing import List, Optional
from enum import Enum
from unittest.mock import MagicMock, patch

import pytest

from flow_forge_ai.config.config_handler import get_config_handler


@pytest.fixture(autouse=True)
def clear_config_cache():
    get_config_handler.cache_clear()


@pytest.fixture(autouse=True)
def mock_dbclient():
    with patch("flow_forge_ai.runtime._RuntimeListener") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield mock
