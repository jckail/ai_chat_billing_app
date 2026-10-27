"""Real v5 SDK request behavior with an offline transport and synthetic settings."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
from supermemory import InternalServerError, Supermemory


@pytest.fixture
def memory(monkeypatch):
    config = ModuleType("app.core.config")
    config.settings = SimpleNamespace(SUPERMEMORY_ENABLED=True, SUPERMEMORY_API_KEY="test-key")
    monkeypatch.setitem(sys.modules, "app.core.config", config)
    path = Path(__file__).parents[1] / "app/services/memory_service.py"
    spec = importlib.util.spec_from_file_location("memory_retry_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    requests = []

    def unavailable(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(503, json={"error": "synthetic unavailable"})

    sdk = Supermemory(api_key="test-key", max_retries=1,
                      http_client=httpx.Client(transport=httpx.MockTransport(unavailable)))
    service = module.MemoryService()
    service._client = sdk
    yield service, sdk, requests
    sdk.close()


@pytest.mark.parametrize("operation,endpoint", [("profile", "profile"), ("search", "search")])
def test_failed_recall_reads_do_not_retry(memory, operation, endpoint):
    service, sdk, requests = memory
    with pytest.raises(InternalServerError):
        if operation == "profile":
            service._profile_sync("aichat:user-7")
        else:
            service._search_sync("aichat:user-7", "synthetic query")
    assert requests == [("POST", f"/ns/aichat:user-7/{endpoint}")]
    assert sdk.max_retries == 1  # Read options must not mutate the shared write client.


def test_off_path_write_keeps_existing_retry_policy(memory):
    service, sdk, requests = memory
    with pytest.raises(InternalServerError):
        service._profile_sync("aichat:user-7")
    assert requests == [("POST", "/ns/aichat:user-7/profile")]
    with pytest.raises(InternalServerError):
        service._remember_sync(7, 99, "synthetic question", "synthetic answer")
    assert requests == [("POST", "/ns/aichat:user-7/profile")] + [("POST", "/ns/aichat:user-7/document")] * 2
    assert sdk.max_retries == 1
