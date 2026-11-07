"""Milvus 保存可从 SQLite 重建的向量索引。"""

import json
from contextlib import contextmanager
from functools import cached_property

from .core import AppError


class MilvusStore:
    timeout = 10
    batch_size = 256

    def __init__(self, uri, collection, backend, dimensions):
        self.uri = uri
        self.collection = collection
        self.backend = backend
        self.dimensions = dimensions
        self.key = json.dumps([uri, collection, backend])

    @contextmanager
    def connection(self):
        try:
            from pymilvus.exceptions import MilvusException
        except ImportError as error:
            raise AppError("Milvus 模式需要安装项目依赖 pymilvus", 503) from error
        try:
            yield self.client
        except MilvusException as error:
            raise AppError("Milvus 请求失败，请检查服务连接、集合配置与容器日志", 503) from error

    @cached_property
    def client(self):
        from pymilvus import DataType, MilvusClient

        client = MilvusClient(uri=self.uri, timeout=self.timeout)
        try:
            if not client.has_collection(self.collection, timeout=self.timeout):
                schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
                schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=32)
                schema.add_field(field_name="embedding_backend", datatype=DataType.VARCHAR, max_length=256)
                schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=self.dimensions)
                client.create_collection(self.collection, schema=schema, consistency_level="Strong",
                                         timeout=self.timeout)
            # 上一次初始化可能只建了集合，重试时补建索引并加载。
            if not client.list_indexes(self.collection, field_name="vector", timeout=self.timeout):
                indexes = client.prepare_index_params()
                indexes.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
                client.create_index(self.collection, indexes, timeout=self.timeout)
            client.load_collection(self.collection, timeout=self.timeout)
        except Exception:
            client.close()
            raise
        return client

    def upsert(self, chunks):
        if not chunks:
            return
        with self.connection() as client:
            for start in range(0, len(chunks), self.batch_size):
                data = [{"id": chunk_id, "vector": vector, "embedding_backend": self.backend}
                        for chunk_id, vector in chunks[start:start + self.batch_size]]
                if any(len(row["vector"]) != self.dimensions for row in data):
                    raise AppError("片段向量维度与 Milvus 集合不一致", 503)
                result = client.upsert(self.collection, data=data, timeout=self.timeout)
                if result.get("upsert_count", 0) != len(data):
                    raise AppError("Milvus 未确认写入全部向量", 503)

    def search(self, vector, limit):
        with self.connection() as client:
            result = client.search(self.collection, data=[vector], anns_field="vector", limit=limit,
                                   filter="embedding_backend == " + json.dumps(self.backend, ensure_ascii=False),
                                   search_params={"metric_type": "COSINE"}, consistency_level="Strong",
                                   timeout=self.timeout)
        return {hit["id"]: float(hit["distance"]) for hit in result[0]}

    def delete(self, ids):
        if not ids:
            return
        with self.connection() as client:
            for start in range(0, len(ids), self.batch_size):
                client.delete(self.collection, ids=ids[start:start + self.batch_size], timeout=self.timeout)
