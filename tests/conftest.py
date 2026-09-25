import pytest

from helpers import Recorder
from evoapi_mcp.client import EvolutionClient
from evoapi_mcp.config import EvolutionConfig


@pytest.fixture
def client():
    config = EvolutionConfig(
        base_url="http://evolution.test",
        api_token="test-token",
        instance_name="test-instance",
    )
    return EvolutionClient(config)


@pytest.fixture
def recorder():
    def build(routes):
        return Recorder(routes)

    return build
