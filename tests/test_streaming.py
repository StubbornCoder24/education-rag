# 离线回归：用临时存储与必要的模型替身验证边界；通过测试不等于真实模型准确率。

# 导入json：在字符串与字典/列表间转换JSON数据
import json
# 从unittest.mock导入patch，替换网络/故障依赖进行离线验证
from unittest.mock import patch
# 导入pytest：组织离线测试用例、参数化与异常断言
import pytest
# 导入requests：向阿里云等已配置服务发出HTTP请求
import requests
# 从fastapi.testclient导入TestClient，供下方业务或测试调用
from fastapi.testclient import TestClient
# 从suite.app导入create_app，供下方业务或测试调用
from suite.app import create_app
# 从suite.core导入Config/Provider/AppError，供下方业务或测试调用
from suite.core import Config, Provider, AppError


class StreamProvider(Provider):
    # 将False保存到bad
    bad = False
    # 将False保存到interrupted
    interrupted = False

    def embed(self, texts):
        # 将调用Provider(Config()).embed取得返回值返回调用方，后续由上一层继续处理
        return Provider(Config()).embed(texts)

    def chat_stream(self, messages):
        # 将按键或下标读取json.loads(messages[-1]['content'])中的内容保存到evidence
        evidence = json.loads(messages[-1]['content'])['evidence']
        # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
        yield 'Redis保存'
        # 仅当条件成立时执行下一分支：self.interrupted
        if self.interrupted:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError('模拟连接中断', 502)
        # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
        yield '对话历史。'
        # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
        yield '[id:' + ('ffffffffffffffff' if self.bad else evidence[0]['id']) + ']'


def frames(response):
    # 将遍历输入、筛选并构造列表返回调用方，后续由上一层继续处理
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


# 引用失败/中途错误必须发错误终态，不能同时发成功done。
@pytest.mark.parametrize('failure', ['', 'citation', 'disconnect'])
def test_sse_success_and_failure_never_emit_false_done(tmp_path, failure):
    class Fake(StreamProvider):
        # 将读取failure == 'citation'保存到bad
        bad = failure == 'citation'
        # 将读取failure == 'disconnect'保存到interrupted
        interrupted = failure == 'disconnect'
    # 保存app：当前FastAPI应用；测试可为它注入独立配置和模型替身。
    app = create_app(Config(data=tmp_path, mode='live'), Fake)
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.md', 'Redis保存对话历史。'.encode())
    # 保存client：临时应用的HTTP测试客户端，不需要启动真实服务器。
    client = TestClient(app)
    # 保存response：接口或模型响应；随后还需检查HTTP状态及响应结构。
    response = client.post('/api/rag/ask/stream', json={'question': 'Redis保存什么', 'strategy': 'keyword'})
    # 测试断言：确认response.headers['content-type'].startswith('text/event-stream')；不满足时用例失败
    assert response.headers['content-type'].startswith('text/event-stream')
    # 保存events：本次操作累计的调用事件，便于复查顺序和消耗。
    events = frames(response)
    # 测试断言：确认any((e['type'] == 'sources' for e in events))；不满足时用例失败
    assert any(e['type'] == 'sources' for e in events)
    # 测试断言：确认any((e['type'] == 'delta' for e in events))；不满足时用例失败
    assert any(e['type'] == 'delta' for e in events)
    # 测试断言：确认events[-1]['type'] == ('error' if failure else 'done')；不满足时用例失败
    assert events[-1]['type'] == ('error' if failure else 'done')
    # 进入资源上下文：app.state.store.db()；离开时按管理器约定提交/回滚或释放资源
    with app.state.store.db() as db:
        # 将读取全部匹配数据库结果保存到traces
        traces = db.execute("SELECT status FROM traces WHERE project='rag.answer'").fetchall()
        # 测试断言：确认[r['status'] for r in traces] == (['failed'] if failure else ['completed'])；不满足时用例失败
        assert [r['status'] for r in traces] == (['failed'] if failure else ['completed'])
    # 仅当条件成立时执行下一分支：not failure
    if not failure:
        # 测试断言：确认'[id:' not in events[-1]['result']['answer']；不满足时用例失败
        assert '[id:' not in events[-1]['result']['answer']
        # 测试断言：确认events[-1]['result']['trace_id']；不满足时用例失败
        assert events[-1]['result']['trace_id']


# 关闭未完成业务生成器应留下取消记录，而非成功记录。
def test_reader_cancel_marks_cancelled(tmp_path):
    # 保存app：当前FastAPI应用；测试可为它注入独立配置和模型替身。
    app = create_app(Config(data=tmp_path, mode='live'), StreamProvider)
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.md', 'Redis保存对话历史。'.encode())
    # 将调用app.state.rag.answer_stream取得返回值保存到stream
    stream = app.state.rag.answer_stream('Redis保存什么', 'keyword')
    # 依次遍历stream，当前项保存为event
    for event in stream:
        # 仅当条件成立时执行下一分支：event['type'] == 'delta'
        if event['type'] == 'delta':
            # 退出当前循环，避免继续读取已经结束或足够的数据
            break
    # 关闭资源，释放连接或文件占用
    stream.close()
    # 进入资源上下文：app.state.store.db()；离开时按管理器约定提交/回滚或释放资源
    with app.state.store.db() as db:
        # 保存row：数据库取回的一条记录或正在处理的片段记录。
        row = db.execute("SELECT status FROM traces WHERE project='rag.answer'").fetchone()
        # 测试断言：确认row['status'] == 'cancelled'；不满足时用例失败
        assert row['status'] == 'cancelled'


# 构造SSE替身检查结束/用量/异常、响应关闭及不重试。
@pytest.mark.parametrize('kind', ['ok', 'truncated', 'timeout', 'bad_json', 'length'])
def test_provider_stream_usage_closes_and_never_retries(kind):
    def data(value):
        # 将按表达式计算得到新值：b'data: ' + json.dumps(value, ensure_ascii=False).encode()返回调用方，后续由上一层继续处理
        return b'data: ' + json.dumps(value, ensure_ascii=False).encode()
    class Response:
        # 将200保存到status_code
        status_code = 200
        # 将False保存到closed
        closed = False
        def iter_lines(self, **kwargs):
            # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
            yield data({'choices': [{'delta': {'content': '中文'}}]})
            # 仅当条件成立时执行下一分支：kind == 'timeout'
            if kind == 'timeout':
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise requests.Timeout()
            # 仅当条件成立时执行下一分支：kind == 'bad_json'
            if kind == 'bad_json':
                # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
                yield b'data: invalid'
                # 提前结束当前函数，不再执行后续分支
                return
            # 仅当条件成立时执行下一分支：kind == 'truncated'
            if kind == 'truncated':
                # 提前结束当前函数，不再执行后续分支
                return
            # 仅当条件成立时执行下一分支：kind == 'length'
            if kind == 'length':
                # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
                yield data({'choices': [{'delta': {}, 'finish_reason': 'length'}]})
                # 提前结束当前函数，不再执行后续分支
                return
            # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
            yield data({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
            # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
            yield data({'choices': [], 'usage': {'total_tokens': 12}})
            # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
            yield b'data: [DONE]'
        def close(self):
            # 把True保存为实例属性self.closed，供该对象的其他方法使用
            self.closed = True
    # 保存response：接口或模型响应；随后还需检查HTTP状态及响应结构。
    response = Response()
    # 保存provider：本次操作使用的模型适配器，events单独记录本次接口调用。
    provider = Provider(Config(mode='live', api_key='test-placeholder'))
    # 进入资源上下文：patch('suite.core.requests.post', return_value=response)；离开时按管理器约定提交/回滚或释放资源
    with patch('suite.core.requests.post', return_value=response) as post:
        # 仅当条件成立时执行下一分支：kind == 'ok'
        if kind == 'ok':
            # 测试断言：确认list(provider.chat_stream([])) == ['中文']；不满足时用例失败
            assert list(provider.chat_stream([])) == ['中文']
            # 测试断言：确认provider.events[0]['usage']['total_tokens'] == 12；不满足时用例失败
            assert provider.events[0]['usage']['total_tokens'] == 12
        else:
            # 进入资源上下文：pytest.raises(AppError)；离开时按管理器约定提交/回滚或释放资源
            with pytest.raises(AppError):
                # 构造列表
                list(provider.chat_stream([]))
        # 测试断言：确认post.call_count == 1；不满足时用例失败
        assert post.call_count == 1
        # 测试断言：确认post.call_args.kwargs['json']['stream'] is True；不满足时用例失败
        assert post.call_args.kwargs['json']['stream'] is True
    # 测试断言：确认response.closed；不满足时用例失败
    assert response.closed
    # 测试断言：确认provider.events[0]['status'] == ('completed' if kind == 'ok' else 'failed')；不满足时用例失败
    assert provider.events[0]['status'] == ('completed' if kind == 'ok' else 'failed')
