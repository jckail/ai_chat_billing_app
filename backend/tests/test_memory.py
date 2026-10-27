import asyncio
import re
import time
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.messages import get_recent_messages, prepare_messages_for_llm
from app.core.config import settings
from app.db.database import Base
from app.models.transactions import UserThreadMessage
from app.services import memory_service as ms
from app.services.anthropic_service import anthropic_service


class FakeSM:
    """Records every SDK call; mirrors the v5 client surface used by MemoryService."""

    def __init__(self, fail=False):
        self.fail, self.adds, self.searches, self.profile_calls = fail, [], [], []
        self.ns_updates, self.deletes, self.options = [], [], []
        self.namespaces = NS(update=lambda ns, **kw: self.ns_updates.append((ns, kw)))
        self.documents = NS(delete=lambda ns, **kw: self.deletes.append((ns, kw)))

    def with_options(self, **kwargs):
        self.options.append(kwargs)
        return self

    def profile(self, ns, **kw):
        self.profile_calls.append((ns, kw))
        if self.fail:
            raise RuntimeError("boom")
        return NS(profile=NS(static=[NS(memory="Likes concise answers")], dynamic=[NS(memory="Building a billing app")]))

    def search(self, ns, **kw):
        self.searches.append((ns, kw))
        if self.fail:
            raise RuntimeError("boom")
        return NS(results=[NS(memory="Uses Kafka")])

    def add(self, ns, **kw):
        if self.fail:
            raise RuntimeError("boom")
        self.adds.append((ns, kw))


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setattr(settings, "SUPERMEMORY_ENABLED", True)
    monkeypatch.setattr(settings, "SUPERMEMORY_API_KEY", "test-key")
    s = ms.MemoryService()
    s._client = FakeSM()
    return s


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def test_namespace_valid_and_bounded():
    assert ms.MemoryService.namespace(42) == "aichat:user-42"
    ns = ms.MemoryService.namespace("a b/c" * 50)
    assert re.fullmatch(r"[a-zA-Z0-9_:-]+", ns) and len(ns) <= 100


def test_disabled_by_default():
    s = ms.MemoryService()
    assert not s.enabled
    assert asyncio.run(s.recall(1, "hi")) is None
    asyncio.run(s.remember(1, 1, "a", "b"))  # no client needed, no error


def test_recall_returns_system_text(svc):
    out = asyncio.run(svc.recall(7, "what stack?"))
    assert "Likes concise answers" in out and "Uses Kafka" in out
    ns, kw = svc._client.searches[0]
    assert ns == "aichat:user-7" and kw["search_mode"] == "memories"
    assert kw["rerank"] == "order" and kw["rewrite_query"] is True and kw["threshold"] == 0.4 and kw["limit"] == 5
    flt = {"field": "source", "operator": "eq", "value": "aichat"}
    assert kw["filter"] == flt and svc._client.profile_calls[0][1]["filter"] == flt
    assert kw["timeout"] == ms.CALL_TIMEOUT
    assert svc._client.options == [{"max_retries": 0}, {"max_retries": 0}]


def test_profile_cached_between_turns(svc):
    asyncio.run(svc.recall(7, "one"))
    asyncio.run(svc.recall(7, "two"))
    assert len(svc._client.profile_calls) == 1 and len(svc._client.searches) == 2


def test_recall_bounded_by_budget_and_uses_partial_results(svc, monkeypatch):
    monkeypatch.setattr(ms, "RECALL_BUDGET", 0.2)

    def slow(ns, **kw):
        time.sleep(1.0)
        return NS(results=[])

    svc._client.search = slow

    async def timed():
        t0 = time.monotonic()
        return await svc.recall(7, "q"), time.monotonic() - t0

    out, elapsed = asyncio.run(timed())
    assert elapsed < 0.9 and "Likes concise answers" in out


def test_fail_open(svc):
    svc._client = FakeSM(fail=True)
    assert asyncio.run(svc.recall(1, "q")) is None
    asyncio.run(svc.remember(1, 1, "a", "b"))  # must not raise


def test_remember_uses_thread_id_in_metadata(svc):
    asyncio.run(svc.remember(7, 99, "hello", "hi there"))
    ns, kw = svc._client.adds[0]
    assert ns == "aichat:user-7" and kw["id"] == "thread-99" and kw["task_type"] == "memory"
    md = kw["metadata"]
    assert md["thread_id"] == 99 and "hello" in kw["content"]
    assert md["source"] == "aichat" and md["kind"] == "chat-turn" and md["user"] == "7"
    assert md["date"] == kw["date"] and kw["date"].endswith("+00:00")
    assert kw["group"] == {"source": "aichat"} and "dreaming" not in kw and len(kw["supporting_context"]) <= 1500


def test_namespace_context_pushed_once_and_fail_open(svc):
    for t in (1, 2, 3):
        asyncio.run(svc.remember(7, t, "a", "b"))
    asyncio.run(svc.remember(8, 1, "a", "b"))
    assert [n for n, _ in svc._client.ns_updates] == ["aichat:user-7", "aichat:user-8"]
    assert len(svc._client.ns_updates[0][1]["supporting_context"]) <= 1500

    svc2 = ms.MemoryService()
    svc2._client = FakeSM()
    svc2._client.namespaces = NS(update=lambda ns, **kw: (_ for _ in ()).throw(RuntimeError("x")))
    asyncio.run(svc2.remember(1, 1, "a", "b"))
    assert len(svc2._client.adds) == 1 and not svc2._prepared  # add kept, setup retried later


def test_forget_thread_deletes_thread_document(svc):
    asyncio.run(svc.forget_thread(7, 99))
    assert svc._client.deletes == [("aichat:user-7", {"ids": ["thread-99"]})]
    svc._client.documents = NS(delete=lambda ns, **kw: (_ for _ in ()).throw(RuntimeError("x")))
    asyncio.run(svc.forget_thread(7, 99))  # must not raise


def _seed(db, n):
    t0 = datetime(2026, 1, 1)
    for i in range(n):
        db.add(UserThreadMessage(thread_id=1, user_id=1, content=f"m{i}", role="user" if i % 2 == 0 else "assistant",
                                 created_at=t0 + timedelta(minutes=i)))
    db.commit()


def test_history_takes_newest_messages_in_order(db):
    _seed(db, 25)  # m0 user ... m24 user
    msgs = asyncio.run(get_recent_messages(db, 1))
    # newest 10 are m15..m24; m15 is an assistant turn and is trimmed so the window starts with the user
    assert [m["content"] for m in msgs] == [f"m{i}" for i in range(16, 25)]


def test_prepare_messages_does_not_duplicate_current(db):
    _seed(db, 3)
    last = db.query(UserThreadMessage).order_by(UserThreadMessage.message_id.desc()).first()
    msgs = asyncio.run(prepare_messages_for_llm(1, last.content, db, exclude_message_id=last.message_id))
    assert [m["content"] for m in msgs].count(last.content) == 1


def test_system_param_reaches_anthropic(monkeypatch):
    calls = []

    def create(**kw):
        calls.append(kw)
        return NS(content=[NS(text="ok")])

    monkeypatch.setattr(anthropic_service, "client", NS(messages=NS(create=create)))
    msgs = [{"role": "user", "content": "hi"}]
    out = asyncio.run(anthropic_service.create_chat_completion(messages=msgs, model="m", system="REMEMBERED"))
    asyncio.run(anthropic_service.create_chat_completion(messages=msgs, model="m"))
    assert out["content"] == "ok"
    assert calls[0]["system"] == "REMEMBERED" and "system" not in calls[1]
