# HTTP接口层：校验网页输入、调用业务对象并把结果返回前端，不在接口里重复实现业务流程。
# create_app可注入测试配置和模型替身，因此离线测试不必使用真实密钥或业务库。

import json
import hmac
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Request, Header, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from .core import Config, Store, AppError, ROOT
from .rag import RAG

# 异步入库任务表：只存在进程内，重启后任务丢失但文档已入库。
# 单进程演示用固定上限，超出后丢弃最旧的一条，避免服务长期运行后无限增长。
TASKS = {}
TASKS_LIMIT = 200


def remember_task(task_id, value):
    TASKS[task_id] = value
    while len(TASKS) > TASKS_LIMIT:
        TASKS.pop(next(iter(TASKS)))


# 写接口鉴权：设置了APP_TOKEN才启用；未设置时保持本地开发的开放行为。
def require_token(x_api_key: str = Header(default='')):
    expected = os.getenv('APP_TOKEN', '')
    if expected and not hmac.compare_digest(x_api_key or '', expected):
        raise AppError('未授权：写操作需要正确的 X-API-Key', 401)
    return True

# 请求字段白名单：拒绝多余字段，避免把客户端未约定数据直接带进业务执行。
class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')

# 问答入参：限制问题长度，并携带用户选择的检索策略。
class Question(Body):
    question: str = Field(min_length=1, max_length=4000)
    strategy: str = 'hybrid_rerank'
    # 可选会话编号：带上它会读最近几轮问答作为上下文
    session_id: str = Field(default='', max_length=64)

# 回答反馈入参：关联执行记录，而非直接改写原回答。
class Feedback(Body):
    trace_id: str
    rating: int = Field(ge=0, le=1)
    comment: str = Field(default='', max_length=1000)

# 应用工厂：为当前配置构造存储、检索和可选Agent对象，再注册路由与静态页面。
def create_app(config=None, provider_factory=None):
    config = config or Config.env()
    store = Store(config)
    kwargs = {'provider_factory': provider_factory} if provider_factory else {}
    rag = RAG(store, **kwargs)
    app = FastAPI(title='职业教育知识库RAG', version='1.0.0')
    app.state.store, app.state.rag = (store, rag)

    # 把已知业务错误变成可读响应；不把错误当成正常“查无记录”。
    @app.exception_handler(AppError)
    def application_error(request, error):
        return JSONResponse({'error': str(error)}, status_code=error.status)

    # 数据库异常保留类型/路径追踪，向页面提示操作未完成，不泄露底层SQL细节。
    @app.exception_handler(sqlite3.Error)
    def database_error(request, error):
        trace_id = store.trace('api.database', None, 'failed', time.perf_counter(), {'path': request.url.path, 'type': type(error).__name__})
        return JSONResponse({'error': '数据库操作未完成，请核对文档与执行记录', 'trace_id': trace_id}, status_code=503)

    # 给前端显示真实运行模式与模型信息；只返回密钥是否配置，不返回密钥本身。
    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'mode': config.mode, 'embedding_backend': rag.backend,
                'vector_store': config.vector_store, 'model': config.model if config.mode == 'live' else '离线确定性演示（非大模型）',
                'model_key_configured': bool(config.api_key), 'data_type': '知识库'}

    # 列出当前模式可管理的文档，具体查询逻辑交给RAG。
    @app.get('/api/rag/documents')
    def documents():
        return rag.documents()

    # 仅读取大小上限加1字节以检测超限；无论入库成败都关闭上传文件句柄。
    @app.post('/api/rag/documents', dependencies=[Depends(require_token)])
    def upload(file: UploadFile=File(...)):
        try:
            content = file.file.read(15 * 1024 * 1024 + 1)
            return rag.ingest(file.filename, content)
        finally:
            # 关闭资源，释放连接或文件占用
            file.file.close()

    # 删除指定文档及其索引；不按模型回答中的名字猜测删除对象。
    @app.delete('/api/rag/documents/{doc_id}', dependencies=[Depends(require_token)])
    def delete(doc_id: str):
        pending = rag.delete(doc_id)
        return {'deleted': True, 'milvus_cleanup_pending': True} if pending else {'deleted': True}

    # 大文件入库走后台线程，前端拿 task_id 轮询进度，不用一直等 HTTP 返回。
    @app.post('/api/rag/documents/async', dependencies=[Depends(require_token)])
    def upload_async(file: UploadFile=File(...)):
        content = file.file.read(15 * 1024 * 1024 + 1)
        file.file.close()
        if len(content) > 15 * 1024 * 1024:
            raise AppError('单文件最多15MB')
        task_id = uuid.uuid4().hex
        remember_task(task_id, {'status': 'running', 'name': file.filename})
        name = file.filename

        def run():
            try:
                TASKS[task_id].update(status='completed', result=rag.ingest(name, content))
            except Exception as error:  # 后台线程没人接异常，只能落到任务状态里
                TASKS[task_id].update(status='failed', error=str(error))

        threading.Thread(target=run, daemon=True).start()
        return {'task_id': task_id, 'status': 'running'}

    @app.get('/api/rag/tasks/{task_id}')
    def task_status(task_id: str):
        task = TASKS.get(task_id)
        if not task:
            raise AppError('任务不存在', 404)
        return task

    # 多轮会话只保存最近问答，用于承接“它/这个”这类指代。
    @app.post('/api/rag/sessions')
    def new_session():
        return {'session_id': uuid.uuid4().hex}

    # 保留一次性JSON问答接口；网页流式入口是另一路由。
    @app.post('/api/rag/ask')
    def ask(body: Question):
        return rag.answer(body.question, body.strategy, session_id=body.session_id)

    # 以SSE返回问答事件；响应头发出后，业务失败要靠error事件传给客户端。
    @app.post('/api/rag/ask/stream')
    def ask_stream(body: Question):
        # 桥接业务生成器和SSE文本帧，退出时关闭业务流，避免未完成结果被误报成功。
        def events():
            try:
                from contextlib import closing
                with closing(rag.answer_stream(body.question, body.strategy, session_id=body.session_id)) as stream:
                    for event in stream:
                        yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
            except Exception as error:
                # HTTP响应头已发出；以明确终止事件通知前端清除未校验文本。
                message = str(error) if isinstance(error, AppError) else '本次生成未完成，请查看运行记录'
                yield 'data: ' + json.dumps({'type': 'error', 'message': message}, ensure_ascii=False) + '\n\n'
        return StreamingResponse(events(), media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # 仅返回检索片段，用于定位召回问题，不额外生成答案。
    @app.post('/api/rag/retrieve')
    def retrieve(body: Question):
        return {'sources': rag.retrieve(body.question, body.strategy)}

    # 列出最近执行摘要，供页面定位耗时与失败；原始payload由详情接口按ID读取。
    @app.get('/api/traces')
    def traces():
        with store.db() as db:
            return [dict(row) for row in db.execute('SELECT id,project,session_id,created,status,elapsed_ms FROM traces ORDER BY created DESC LIMIT 100')]

    # 按明确trace_id读取原始证据，用于核对参数、工具结果、来源和usage。
    @app.get('/api/traces/{trace_id}')
    def trace(trace_id: str):
        with store.db() as db:
            row = db.execute('SELECT * FROM traces WHERE id=?', (trace_id,)).fetchone()
        if not row:
            raise AppError('记录不存在', 404)
        result = dict(row)
        result['payload'] = json.loads(result['payload'])
        return result

    # 确认执行记录存在再保存评分，保持反馈与实际回答可追溯。
    @app.post('/api/feedback')
    def feedback(body: Feedback):
        with store.db() as db:
            if not db.execute('SELECT id FROM traces WHERE id=?', (body.trace_id,)).fetchone():
                raise AppError('记录不存在', 404)
            db.execute('INSERT INTO feedback VALUES(?,?,?,?,?)', (uuid.uuid4().hex, body.trace_id, body.rating, body.comment, time.time()))
        return {'saved': True}
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    # 返回本项目静态首页，脚本通过API与后端交互，不需要把密钥放到浏览器。
    @app.get('/')
    @app.get('/rag')
    def page():
        return FileResponse(ROOT / 'static' / 'index.html')
    return app
