import pytest
from fastapi.testclient import TestClient

from suite.app import create_app
from suite.core import AppError, Config, Store
from suite.rag import RAG


@pytest.fixture
def milvus_app(tmp_path, monkeypatch):
    class FakeMilvus:
        key = "test-index"
        rows = {}
        fail_upsert = False
        fail_delete = False

        def __init__(self, uri, collection, backend, dimensions):
            assert backend == "demo_hash:1024"
            assert dimensions == 1024

        def upsert(self, chunks):
            self.rows.update(chunks)
            if chunks and self.fail_upsert:
                raise AppError("Milvus 测试写入失败", 503)

        def search(self, vector, limit):
            assert len(vector) == 1024
            return {chunk_id: 1.0 for chunk_id in list(self.rows)[:limit]}

        def delete(self, ids):
            if ids and self.fail_delete:
                raise AppError("Milvus 测试删除失败", 503)
            for chunk_id in ids:
                self.rows.pop(chunk_id, None)

    monkeypatch.setattr("suite.rag.MilvusStore", FakeMilvus)
    monkeypatch.delenv("APP_TOKEN", raising=False)
    config = Config(data=tmp_path, embedding_path="", reranker_path="")
    old = RAG(Store(config)).ingest("sample.md", "# 课件\n测试口令是青竹七号。".encode())
    config.vector_store = "milvus"
    config.milvus_uri = "http://standalone:19530"
    config.milvus_collection = "test_chunks"
    return create_app(config), old


def ask(client, strategy="vector"):
    response = client.post("/api/rag/ask", json={"question": "测试口令是什么？", "strategy": strategy})
    assert response.status_code == 200, response.text
    return response.json()


def upload(client, content):
    return client.post("/api/rag/documents", files={"file": ("sample.md", content.encode(), "text/markdown")})


def test_backfill_update_and_delete_through_api(milvus_app):
    app, old = milvus_app
    client = TestClient(app)
    assert client.get("/api/health").json()["vector_store"] == "milvus"
    first = ask(client)
    first_id = first["sources"][0]["id"]
    assert first["sources"][0]["version"] == 1
    assert "青竹七号" in first["answer"]
    assert {"operation": "vector_search", "backend": "milvus", "chunk_ids": [first_id]} in first["events"]

    updated = upload(client, "# 课件\n测试口令是青竹九号。").json()
    assert updated["id"] == old["id"] and updated["version"] == 2
    assert first_id not in app.state.rag.milvus.rows
    assert "青竹九号" in ask(client, "hybrid")["answer"]
    assert client.delete(f"/api/rag/documents/{old['id']}").json() == {"deleted": True}
    assert not app.state.rag.milvus.rows
    assert ask(client)["sources"] == []


def test_partial_milvus_write_preserves_old_version(milvus_app):
    app, old = milvus_app
    client = TestClient(app)
    before = ask(client)
    index = app.state.rag.milvus
    index.fail_upsert = True
    response = upload(client, "# 课件\n测试口令是青竹九号。")
    assert response.status_code == 503
    assert len(index.rows) == 2
    after = ask(client)
    assert after["sources"] == before["sources"]
    assert client.get("/api/rag/documents").json()[0]["id"] == old["id"]
    assert set(index.rows) == {before["sources"][0]["id"]}


def test_failed_delete_retries_after_restart(milvus_app):
    app, old = milvus_app
    client = TestClient(app)
    ask(client)
    index = app.state.rag.milvus
    index.fail_delete = True
    assert client.delete(f"/api/rag/documents/{old['id']}").json() == {
        "deleted": True, "milvus_cleanup_pending": True,
    }
    assert index.rows
    assert ask(client, "keyword")["sources"] == []
    restarted = TestClient(create_app(app.state.store.config))
    assert ask(restarted)["sources"] == []
    assert not index.rows
