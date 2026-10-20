# 离线回归：用临时存储与必要的模型替身验证边界；通过测试不等于真实模型准确率。

# 导入concurrent.futures：使用其公开工具，不在这里执行具体业务
import concurrent.futures
# 导入json：在字符串与字典/列表间转换JSON数据
import json
# 导入sqlite3：使用本地SQLite数据库连接与异常类型
import sqlite3
# 导入sys：访问解释器路径和导入搜索路径
import sys
# 从pathlib导入Path，用对象处理路径而非手拼字符串
from pathlib import Path
# 从unittest.mock导入patch，替换网络/故障依赖进行离线验证
from unittest.mock import patch
# 导入pytest：组织离线测试用例、参数化与异常断言
import pytest
# 从fastapi.testclient导入TestClient，供下方业务或测试调用
from fastapi.testclient import TestClient
# 调用sys.path.insert取得返回值
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# 从suite.app导入create_app，供下方业务或测试调用
from suite.app import create_app
# 从suite.core导入AppError/Config/Provider/Store，供下方业务或测试调用
from suite.core import AppError, Config, Provider, Store
# 从suite.rag导入RAG/extract/NO_ANSWER，供下方业务或测试调用
from suite.rag import RAG, extract, NO_ANSWER

@pytest.fixture
def app(tmp_path):
    # 将建立可注入配置的FastAPI应用返回调用方，后续由上一层继续处理
    return create_app(Config(data=tmp_path))

# 验证同名复用/版本替换、旧片段删除以及重新打开存储后的可见结果。
def test_rag_version_delete_persistence(app):
    # 保存rag：知识入库与检索业务对象。
    rag = app.state.rag
    # 将调用rag.ingest取得返回值保存到first
    first = rag.ingest('课程.md', '# 原文\nwhile循环需要更新变量。'.encode())
    # 将调用rag.ingest取得返回值保存到same
    same = rag.ingest('课程.md', '# 原文\nwhile循环需要更新变量。'.encode())
    # 测试断言：确认same['unchanged'] and same['version'] == 1；不满足时用例失败
    assert same['unchanged'] and same['version'] == 1
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('课程.md', '# 新版\n函数封装重复操作。'.encode())
    # 进入资源上下文：app.state.store.db()；离开时按管理器约定提交/回滚或释放资源
    with app.state.store.db() as db:
        # 测试断言：确认db.execute("SELECT count(*) FROM chunks WHERE text LIKE '%while%'").fetchone()[0] == 0；不满足时用例失败
        assert db.execute("SELECT count(*) FROM chunks WHERE text LIKE '%while%'").fetchone()[0] == 0
    # 将构造知识检索对象保存到reopened
    reopened = RAG(Store(app.state.store.config))
    # 测试断言：确认reopened.documents()[0]['version'] == 2；不满足时用例失败
    assert reopened.documents()[0]['version'] == 2
    # 调用reopened.delete取得返回值
    reopened.delete(first['id'])
    # 测试断言：确认not reopened.documents() and (not reopened.retrieve('函数'))；不满足时用例失败
    assert not reopened.documents() and (not reopened.retrieve('函数'))

# 新文件解析失败时，旧文档与旧版本必须继续保留。
def test_failed_ingest_keeps_old(app):
    # 保存rag：知识入库与检索业务对象。
    rag = app.state.rag
    # 将调用rag.ingest取得返回值保存到first
    first = rag.ingest('课程.md', '# 旧版\n旧版课程内容。'.encode())
    # 进入资源上下文：pytest.raises(AppError)；离开时按管理器约定提交/回滚或释放资源
    with pytest.raises(AppError):
        # 按当前配置解析并建立该文档的检索索引
        rag.ingest('课程.md', b'\xff\xff')
    # 测试断言：确认rag.documents()[0]['version'] == 1；不满足时用例失败
    assert rag.documents()[0]['version'] == 1
    # 测试断言：确认rag.documents()[0]['id'] == first['id']；不满足时用例失败
    assert rag.documents()[0]['id'] == first['id']

# 验证章节提取与不合法文件拒绝，不把PDF解析失败当空正文成功。
def test_pdf_and_markdown_metadata():
    # 保存units：带页码/章节的原文单元；先保留边界，再在单元内部切块。
    units = extract('a.md', '# 一级\n内容\n## 二级\n引用说明'.encode())
    # 测试断言：确认[u['section'] for u in units] == ['一级', '二级']；不满足时用例失败
    assert [u['section'] for u in units] == ['一级', '二级']
    # 进入资源上下文：pytest.raises(AppError)；离开时按管理器约定提交/回滚或释放资源
    with pytest.raises(AppError):
        # 调用extract取得返回值
        extract('bad.pdf', b'not a PDF')
    # 进入资源上下文：pytest.raises(AppError)；离开时按管理器约定提交/回滚或释放资源
    with pytest.raises(AppError):
        # 调用extract取得返回值
        extract('bad.exe', b'data')

# 走上传→问答→引用→反馈闭环，同时验证有限未知问题拒答。
def test_rag_citation_unknown_feedback(app):
    # 保存client：临时应用的HTTP测试客户端，不需要启动真实服务器。
    client = TestClient(app)
    # 将调用client.post取得返回值保存到upload
    upload = client.post('/api/rag/documents', files={'file': ('课程.md', '# 循环\nwhile循环应更新变量，避免死循环。'.encode())})
    # 测试断言：确认upload.status_code == 200；不满足时用例失败
    assert upload.status_code == 200
    # 将调用client.post('/api/rag/ask', json={'question': 'while循环为什么更新变量'}).json取得返回值保存到value
    value = client.post('/api/rag/ask', json={'question': 'while循环为什么更新变量'}).json()
    # 测试断言：确认value['sources'][0]['section'] == '循环'；不满足时用例失败
    assert value['sources'][0]['section'] == '循环'
    # 测试断言：确认'[' + value['sources'][0]['id'] + ']' in value['answer']；不满足时用例失败
    assert '[' + value['sources'][0]['id'] + ']' in value['answer']
    # 测试断言：确认client.post('/api/feedback', json={'trace_id': value['trace_id'], 'rating': 1}).status_code == 200；不满足时用例失败
    assert client.post('/api/feedback', json={'trace_id': value['trace_id'], 'rating': 1}).status_code == 200
    # 测试断言：确认client.post('/api/rag/ask', json={'question': '课程学费多少钱'}).json()['answer'] == NO_ANSWER；不满足时用例失败
    assert client.post('/api/rag/ask', json={'question': '课程学费多少钱'}).json()['answer'] == NO_ANSWER
    # 测试断言：确认client.post('/api/rag/ask', json={'question': ' ', 'strategy': 'vector'}).status_code == 400；不满足时用例失败
    assert client.post('/api/rag/ask', json={'question': ' ', 'strategy': 'vector'}).status_code == 400

# 离线哈希向量不能被真实Embedding检索直接混用。
def test_modes_do_not_mix_indexes(app):
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.txt', '变量与函数'.encode())
    # 保存config：本次运行配置，包含数据目录、模型名和接口设置。
    config = Config(data=app.state.store.config.data, mode='live')
    # 测试断言：确认not RAG(Store(config)).retrieve('变量', 'keyword')；不满足时用例失败
    assert not RAG(Store(config)).retrieve('变量', 'keyword')


# 复现代码下标/数组被误判引用的问题，确保原文摘录不被误拦。
def test_demo_document_brackets_are_not_citations(app):
    """代码下标、JSON数组、Markdown链接属于资料原文，不能当作伪造引用。"""
    # 保存rag：知识入库与检索业务对象。
    rag = app.state.rag
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('LangChain.md', (
        '# Redis对话历史\nRedis保存完整对话历史，向量库用于语义检索。\n'
        '读取 messages[0] 和 messages[i]；数组为 [1, 2]，空列表 []。\n'
        '[文档](https://example.invalid)\n'
    ).encode())
    # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
    result = rag.answer('为什么不用向量库替代Redis存整条对话历史')
    # 测试断言：确认not result['abstained']；不满足时用例失败
    assert not result['abstained']
    # 测试断言：确认'messages[0]' in result['answer']；不满足时用例失败
    assert 'messages[0]' in result['answer']
    # 测试断言：确认'Redis保存完整对话历史' in result['answer']；不满足时用例失败
    assert 'Redis保存完整对话历史' in result['answer']
    # 测试断言：确认all(('[' + source['id'] + ']' in result['answer'] for source in result['sources']))；不满足时用例失败
    assert all('[' + source['id'] + ']' in result['answer'] for source in result['sources'])


# 原文含方括号时，离线拒答分支仍应正常返回资料不足。
def test_demo_refusal_with_bracketed_evidence(app):
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('课程.md', '课程内容包括列表[0]，资料不提供学费。'.encode())
    # 测试断言：确认app.state.rag.answer('课程学费多少钱')['answer'] == NO_ANSWER；不满足时用例失败
    assert app.state.rag.answer('课程学费多少钱')['answer'] == NO_ANSWER


# 只兼容ID格式差异，不放宽“必须属于本次来源”的约束。
@pytest.mark.parametrize('unknown', [False, True])
@pytest.mark.parametrize('style', ['id:{}', ' {} ', ' id: {} '])
def test_live_prefixed_citation_is_normalized_but_unknown_rejected(tmp_path, unknown, style):
    class PrefixedProvider(Provider):
        def embed(self, texts):
            # 将调用Provider(Config()).embed取得返回值返回调用方，后续由上一层继续处理
            return Provider(Config()).embed(texts)

        def chat(self, messages, **kwargs):
            # 将按键或下标读取json.loads(messages[-1]['content'])中的内容保存到evidence
            evidence = json.loads(messages[-1]['content'])['evidence']
            # 将根据条件选取两种候选值之一保存到citation
            citation = 'ffffffffffffffff' if unknown else evidence[0]['id']
            # 将构造字典，字段包括role/content返回调用方，后续由上一层继续处理
            return {'role': 'assistant', 'content': 'Redis保存对话历史。 [' + style.format(citation) + ']'}

    # 保存rag：知识入库与检索业务对象。
    rag = RAG(Store(Config(data=tmp_path, mode='live')), PrefixedProvider)
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('说明.md', 'Redis保存对话历史。'.encode())
    # 仅当条件成立时执行下一分支：unknown
    if unknown:
        # 进入资源上下文：pytest.raises(AppError, match='引用')；离开时按管理器约定提交/回滚或释放资源
        with pytest.raises(AppError, match='引用'):
            # 调用rag.answer取得返回值
            rag.answer('Redis保存什么', 'keyword')
    else:
        # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
        result = rag.answer('Redis保存什么', 'keyword')
        # 测试断言：确认'[id:' not in result['answer']；不满足时用例失败
        assert '[id:' not in result['answer']
        # 测试断言：确认'[' + result['sources'][0]['id'] + ']' in result['answer']；不满足时用例失败
        assert '[' + result['sources'][0]['id'] + ']' in result['answer']

# 用超时替身验证单次失败停止与事件记录，不产生真实网络费用。
def test_request_failure_no_retry_and_trace(app):
    # 保存config：本次运行配置，包含数据目录、模型名和接口设置。
    config = Config(data=app.state.store.config.data, mode='live', api_key='offline-test-placeholder')
    # 保存provider：本次操作使用的模型适配器，events单独记录本次接口调用。
    provider = Provider(config)
    # 导入requests：向阿里云等已配置服务发出HTTP请求
    import requests
    # 进入资源上下文：patch('suite.core.requests.post', side_effect=requests.Timeout('offline'))；离开时按管理器约定提交/回滚或释放资源
    with patch('suite.core.requests.post', side_effect=requests.Timeout('offline')) as mocked:
        # 进入资源上下文：pytest.raises(AppError, match='超时')；离开时按管理器约定提交/回滚或释放资源
        with pytest.raises(AppError, match='超时'):
            # 调用provider.chat取得返回值
            provider.chat([{'role': 'user', 'content': '测试'}])
        # 测试断言：确认mocked.call_count == 1；不满足时用例失败
        assert mocked.call_count == 1
    # 测试断言：确认provider.events[0]['status'] == 'failed'；不满足时用例失败
    assert provider.events[0]['status'] == 'failed'

# 模型输出也需校验：排序越界和缺引用都不能当成功答案。
def test_invalid_rerank_and_missing_citation_blocked(tmp_path):

    class InvalidRAG(Provider):

        def embed(self, texts):
            # 将调用Provider(Config()).embed取得返回值返回调用方，后续由上一层继续处理
            return Provider(Config()).embed(texts)

        def chat(self, messages, tools=None, tool_choice='auto', json_mode=False):
            # 将构造字典，字段包括role/content返回调用方，后续由上一层继续处理
            return {'role': 'assistant', 'content': '{"order":[999]}' if json_mode else '无引用答案'}
    # 保存app：当前FastAPI应用；测试可为它注入独立配置和模型替身。
    app = create_app(Config(data=tmp_path, mode='live'), InvalidRAG)
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.md', '# 循环\nwhile循环需要更新变量'.encode())
    # 进入资源上下文：pytest.raises(AppError, match='重排序')；离开时按管理器约定提交/回滚或释放资源
    with pytest.raises(AppError, match='重排序'):
        # 调用app.state.rag.answer取得返回值
        app.state.rag.answer('while循环')
    # 进入资源上下文：pytest.raises(AppError, match='引用')；离开时按管理器约定提交/回滚或释放资源
    with pytest.raises(AppError, match='引用'):
        # 调用app.state.rag.answer取得返回值
        app.state.rag.answer('while循环', 'vector')

# 独立RAG只暴露自己的页面/API，不应依赖或误开放Agent接口。
def test_rag_http_scope(app):
    # 保存client：临时应用的HTTP测试客户端，不需要启动真实服务器。
    client = TestClient(app)
    # 测试断言：确认client.get('/').status_code == 200；不满足时用例失败
    assert client.get('/').status_code == 200
    # 测试断言：确认client.get('/rag').status_code == 200；不满足时用例失败
    assert client.get('/rag').status_code == 200
    # 测试断言：确认client.get('/agent').status_code == 404；不满足时用例失败
    assert client.get('/agent').status_code == 404
    # 测试断言：确认client.post('/api/agent/sessions').status_code == 404；不满足时用例失败
    assert client.post('/api/agent/sessions').status_code == 404
    # 测试断言：确认not hasattr(app.state, 'agent')；不满足时用例失败
    assert not hasattr(app.state, 'agent')
