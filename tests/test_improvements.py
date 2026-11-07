"""本次新增能力的回归：缓存失效、引用支持度、多轮上下文、异步入库。"""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from suite.app import create_app  # noqa: E402
from suite.core import Config  # noqa: E402
from suite.rag import citation_support  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app(Config(data=tmp_path))


def test_retrieve_cache_invalidated_by_ingest(app):
    rag = app.state.rag
    rag.ingest("a.md", "# 循环\nwhile 循环需要更新变量".encode())
    first = rag.retrieve("while循环", "keyword")
    assert rag.retrieve("while循环", "keyword") is first  # 命中缓存返回同一对象

    rag.ingest("b.md", "# 循环\nwhile 循环在条件为真时重复执行".encode())
    second = rag.retrieve("while循环", "keyword")
    assert second is not first  # 文档变化后必须重新检索


def test_citation_support_marks_unrelated_sentence():
    sources = [{"id": "a" * 16, "text": "while 循环在条件为真时重复执行，需要更新循环变量。"}]
    report = citation_support("今天的天气不错[" + "a" * 16 + "]，适合出门散步。", sources)
    assert report["checked"] == 1
    assert report["weak"], "完全不相关的句子应被标为弱引用"


def test_multiturn_history_roundtrip(app):
    rag = app.state.rag
    rag.remember("s1", "while循环要注意什么", "要更新循环变量")
    rag.remember("s2", "别的会话", "不应该读到")
    history = rag.history("s1")
    assert [item["content"] for item in history] == ["while循环要注意什么", "要更新循环变量"]


def test_async_upload_reaches_completed(app, monkeypatch):
    monkeypatch.setenv("APP_TOKEN", "t")
    client = TestClient(app)
    response = client.post(
        "/api/rag/documents/async",
        files={"file": ("async.md", "# 标题\n异步入库内容".encode(), "text/markdown")},
        headers={"X-API-Key": "t"},
    )
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    deadline = time.time() + 5
    while time.time() < deadline:
        task = client.get(f"/api/rag/tasks/{task_id}").json()
        if task["status"] != "running":
            break
        time.sleep(0.05)
    assert task["status"] == "completed", task
    assert task["result"]["chunks"] >= 1
