# 离线回归：用临时存储与必要的模型替身验证边界；通过测试不等于真实模型准确率。

import json
from unittest.mock import patch
import pytest
import requests
from fastapi.testclient import TestClient
from suite.app import create_app
from suite.core import Config, Provider, AppError

class StreamProvider(Provider):
    bad = False
    interrupted = False

    def embed(self, texts):
        return Provider(Config()).embed(texts)

    def chat_stream(self, messages):
        evidence = json.loads(messages[-1]['content'])['evidence']
        yield 'Redis保存'
        if self.interrupted:
            raise AppError('模拟连接中断', 502)
        yield '对话历史。'
        yield '[id:' + ('ffffffffffffffff' if self.bad else evidence[0]['id']) + ']'

def frames(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]

# 引用失败/中途错误必须发错误终态，不能同时发成功done。
@pytest.mark.parametrize('failure', ['', 'citation', 'disconnect'])
def test_sse_success_and_failure_never_emit_false_done(tmp_path, failure):
    class Fake(StreamProvider):
        bad = failure == 'citation'
        interrupted = failure == 'disconnect'
    app = create_app(Config(data=tmp_path, mode='live'), Fake)
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.md', 'Redis保存对话历史。'.encode())
    client = TestClient(app)
    response = client.post('/api/rag/ask/stream', json={'question': 'Redis保存什么', 'strategy': 'keyword'})
    assert response.headers['content-type'].startswith('text/event-stream')
    events = frames(response)
    assert any(e['type'] == 'sources' for e in events)
    assert any(e['type'] == 'delta' for e in events)
    assert events[-1]['type'] == ('error' if failure else 'done')
    with app.state.store.db() as db:
        traces = db.execute("SELECT status FROM traces WHERE project='rag.answer'").fetchall()
        assert [r['status'] for r in traces] == (['failed'] if failure else ['completed'])
    if not failure:
        assert '[id:' not in events[-1]['result']['answer']
        assert events[-1]['result']['trace_id']

# 关闭未完成业务生成器应留下取消记录，而非成功记录。
def test_reader_cancel_marks_cancelled(tmp_path):
    app = create_app(Config(data=tmp_path, mode='live'), StreamProvider)
    # 按当前配置解析并建立该文档的检索索引
    app.state.rag.ingest('a.md', 'Redis保存对话历史。'.encode())
    stream = app.state.rag.answer_stream('Redis保存什么', 'keyword')
    for event in stream:
        if event['type'] == 'delta':
            break
    # 关闭资源，释放连接或文件占用
    stream.close()
    with app.state.store.db() as db:
        row = db.execute("SELECT status FROM traces WHERE project='rag.answer'").fetchone()
        assert row['status'] == 'cancelled'

# 构造SSE替身检查结束/用量/异常、响应关闭及不重试。
@pytest.mark.parametrize('kind', ['ok', 'truncated', 'timeout', 'bad_json', 'length'])
def test_provider_stream_usage_closes_and_never_retries(kind):
    def data(value):
        return b'data: ' + json.dumps(value, ensure_ascii=False).encode()
    class Response:
        status_code = 200
        closed = False
        def iter_lines(self, **kwargs):
            yield data({'choices': [{'delta': {'content': '中文'}}]})
            if kind == 'timeout':
                raise requests.Timeout()
            if kind == 'bad_json':
                yield b'data: invalid'
                # 提前结束当前函数，不再执行后续分支
                return
            if kind == 'truncated':
                # 提前结束当前函数，不再执行后续分支
                return
            if kind == 'length':
                yield data({'choices': [{'delta': {}, 'finish_reason': 'length'}]})
                # 提前结束当前函数，不再执行后续分支
                return
            yield data({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
            yield data({'choices': [], 'usage': {'total_tokens': 12}})
            yield b'data: [DONE]'
        def close(self):
            # 把True保存为实例属性self.closed，供该对象的其他方法使用
            self.closed = True
    response = Response()
    provider = Provider(Config(mode='live', api_key='test-placeholder'))
    with patch('suite.core.requests.post', return_value=response) as post:
        if kind == 'ok':
            assert list(provider.chat_stream([])) == ['中文']
            assert provider.events[0]['usage']['total_tokens'] == 12
        else:
            with pytest.raises(AppError):
                # 构造列表
                list(provider.chat_stream([]))
        assert post.call_count == 1
        assert post.call_args.kwargs['json']['stream'] is True
    assert response.closed
    assert provider.events[0]['status'] == ('completed' if kind == 'ok' else 'failed')
