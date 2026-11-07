# 离线回归：用临时存储与必要的模型替身验证边界；通过测试不等于真实模型准确率。

import concurrent.futures
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from suite.app import create_app
from suite.core import AppError, Config, Provider, Store
from suite.rag import RAG, extract, NO_ANSWER

@pytest.fixture
def app(tmp_path):
    return create_app(Config(data=tmp_path))

# 验证同名复用/版本替换、旧片段删除以及重新打开存储后的可见结果。
def test_rag_version_delete_persistence(app):
    rag = app.state.rag
    first = rag.ingest('课程.md', '# 原文\nwhile循环需要更新变量。'.encode())
    same = rag.ingest('课程.md', '# 原文\nwhile循环需要更新变量。'.encode())
    assert same['unchanged'] and same['version'] == 1
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('课程.md', '# 新版\n函数封装重复操作。'.encode())
    with app.state.store.db() as db:
        assert db.execute("SELECT count(*) FROM chunks WHERE text LIKE '%while%'").fetchone()[0] == 0
    reopened = RAG(Store(app.state.store.config))
    assert reopened.documents()[0]['version'] == 2
    reopened.delete(first['id'])
    assert not reopened.documents() and (not reopened.retrieve('函数'))

# 新文件解析失败时，旧文档与旧版本必须继续保留。
def test_failed_ingest_keeps_old(app):
    rag = app.state.rag
    first = rag.ingest('课程.md', '# 旧版\n旧版课程内容。'.encode())
    with pytest.raises(AppError):
        # 按当前配置解析并建立该文档的检索索引
        rag.ingest('课程.md', b'\xff\xff')
    assert rag.documents()[0]['version'] == 1
    assert rag.documents()[0]['id'] == first['id']

# 验证章节提取与不合法文件拒绝，不把PDF解析失败当空正文成功。
def test_pdf_and_markdown_metadata():
    units = extract('a.md', '# 一级\n内容\n## 二级\n引用说明'.encode())
    assert [u['section'] for u in units] == ['一级', '二级']
    with pytest.raises(AppError):
        extract('bad.pdf', b'not a PDF')
    with pytest.raises(AppError):
        extract('bad.exe', b'data')

# 走上传→问答→引用→反馈闭环，同时验证有限未知问题拒答。
def test_rag_citation_unknown_feedback(app):
    client = TestClient(app)
    upload = client.post('/api/rag/documents', files={'file': ('课程.md', '# 循环\nwhile循环应更新变量，避免死循环。'.encode())})
    assert upload.status_code == 200
    value = client.post('/api/rag/ask', json={'question': 'while循环为什么更新变量'}).json()
    assert value['sources'][0]['section'] == '循环'
    assert '[' + value['sources'][0]['id'] + ']' in value['answer']
    assert client.post('/api/feedback', json={'trace_id': value['trace_id'], 'rating': 1}).status_code == 200
    assert client.post('/api/rag/ask', json={'question': '课程学费多少钱'}).json()['answer'] == NO_ANSWER
    assert client.post('/api/rag/ask', json={'question': ' ', 'strategy': 'vector'}).status_code == 400

# 离线哈希向量不能被真实Embedding检索直接混用。
def test_modes_do_not_mix_indexes(app):
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.txt', '变量与函数'.encode())
    config = Config(data=app.state.store.config.data, mode='live', embedding_path='')
    assert not RAG(Store(config)).retrieve('变量', 'keyword')

# 复现代码下标/数组被误判引用的问题，确保原文摘录不被误拦。
def test_demo_document_brackets_are_not_citations(app):
    """代码下标、JSON数组、Markdown链接属于资料原文，不能当作伪造引用。"""
    rag = app.state.rag
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('LangChain.md', (
        '# Redis对话历史\nRedis保存完整对话历史，向量库用于语义检索。\n'
        '读取 messages[0] 和 messages[i]；数组为 [1, 2]，空列表 []。\n'
        '[文档](https://example.invalid)\n'
    ).encode())
    result = rag.answer('为什么不用向量库替代Redis存整条对话历史')
    assert not result['abstained']
    assert 'messages[0]' in result['answer']
    assert 'Redis保存完整对话历史' in result['answer']
    assert all('[' + source['id'] + ']' in result['answer'] for source in result['sources'])

# 原文含方括号时，离线拒答分支仍应正常返回资料不足。
def test_demo_refusal_with_bracketed_evidence(app):
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('课程.md', '课程内容包括列表[0]，资料不提供学费。'.encode())
    assert app.state.rag.answer('课程学费多少钱')['answer'] == NO_ANSWER

# 只兼容ID格式差异，不放宽“必须属于本次来源”的约束。
@pytest.mark.parametrize('unknown', [False, True])
@pytest.mark.parametrize('style', ['id:{}', ' {} ', ' id: {} '])
def test_live_prefixed_citation_is_normalized_but_unknown_rejected(tmp_path, unknown, style):
    class PrefixedProvider(Provider):
        def embed(self, texts):
            return Provider(Config()).embed(texts)

        def chat(self, messages, **kwargs):
            evidence = json.loads(messages[-1]['content'])['evidence']
            citation = 'ffffffffffffffff' if unknown else evidence[0]['id']
            return {'role': 'assistant', 'content': 'Redis保存对话历史。 [' + style.format(citation) + ']'}

    rag = RAG(Store(Config(data=tmp_path, mode='live')), PrefixedProvider)
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('说明.md', 'Redis保存对话历史。'.encode())
    if unknown:
        with pytest.raises(AppError, match='引用'):
            rag.answer('Redis保存什么', 'keyword')
    else:
        result = rag.answer('Redis保存什么', 'keyword')
        assert '[id:' not in result['answer']
        assert '[' + result['sources'][0]['id'] + ']' in result['answer']

# 用超时替身验证单次失败停止与事件记录，不产生真实网络费用。
def test_request_failure_no_retry_and_trace(app):
    config = Config(data=app.state.store.config.data, mode='live', api_key='offline-test-placeholder')
    provider = Provider(config)
    import requests
    with patch('suite.core.requests.post', side_effect=requests.Timeout('offline')) as mocked:
        with pytest.raises(AppError, match='超时'):
            provider.chat([{'role': 'user', 'content': '测试'}])
        # 新实现对超时重试一次，因此这里是2次调用
        assert mocked.call_count == 2
    assert provider.events[0]['status'] == 'failed'

# 模型输出也需校验：排序越界和缺引用都不能当成功答案。
def test_invalid_rerank_and_missing_citation_blocked(tmp_path):

    class InvalidRAG(Provider):

        def embed(self, texts):
            return Provider(Config()).embed(texts)

        def chat(self, messages, tools=None, tool_choice='auto', json_mode=False):
            return {'role': 'assistant', 'content': '{"order":[999]}' if json_mode else '无引用答案'}
    # 关掉本地重排，强制走 LLM 重排分支，才能验证无效索引会被拦截
    app = create_app(Config(data=tmp_path, mode='live', reranker_path=''), InvalidRAG)
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.md', '# 循环\nwhile循环需要更新变量'.encode())
    with pytest.raises(AppError, match='重排序'):
        app.state.rag.answer('while循环')
    with pytest.raises(AppError, match='引用'):
        app.state.rag.answer('while循环', 'vector')

# 独立RAG只暴露自己的页面/API，不应依赖或误开放Agent接口。
def test_rag_http_scope(app):
    client = TestClient(app)
    assert client.get('/').status_code == 200
    assert client.get('/rag').status_code == 200
    assert client.get('/agent').status_code == 404
    assert client.post('/api/agent/sessions').status_code == 404
    assert not hasattr(app.state, 'agent')
