# HTTP接口层：校验网页输入、调用业务对象并把结果返回前端，不在接口里重复实现业务流程。
# create_app可注入测试配置和模型替身，因此离线测试不必使用真实密钥或业务库。

# 导入json：在字符串与字典/列表间转换JSON数据
import json
# 导入sqlite3：使用本地SQLite数据库连接与异常类型
import sqlite3
# 导入time：取得时间戳和单调计时，保存创建时间与计算耗时
import time
# 导入uuid：生成文档、片段、任务、请求或记录的唯一标识
import uuid
# 从pathlib导入Path，用对象处理路径而非手拼字符串
from pathlib import Path
# 从fastapi导入FastAPI/UploadFile/File/Request，声明接口及文件/请求类型
from fastapi import FastAPI, UploadFile, File, Request
# 从fastapi.responses导入FileResponse/JSONResponse/StreamingResponse，生成JSON、文件或流式HTTP响应
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
# 从fastapi.staticfiles导入StaticFiles，提供本地静态资源
from fastapi.staticfiles import StaticFiles
# 从pydantic导入BaseModel/ConfigDict/Field，限制请求字段和输入长度
from pydantic import BaseModel, ConfigDict, Field
# 从core导入Config/Store/AppError/ROOT，供下方业务或测试调用
from .core import Config, Store, AppError, ROOT
# 从rag导入RAG，供下方业务或测试调用
from .rag import RAG

# 请求字段白名单：拒绝多余字段，避免把客户端未约定数据直接带进业务执行。
class Body(BaseModel):
    # 将调用ConfigDict取得返回值保存到model_config
    model_config = ConfigDict(extra='forbid')

# 问答入参：限制问题长度，并携带用户选择的检索策略。
class Question(Body):
    # 将调用Field取得返回值保存到question
    question: str = Field(min_length=1, max_length=4000)
    # 将'hybrid_rerank'保存到strategy
    strategy: str = 'hybrid_rerank'

# 回答反馈入参：关联执行记录，而非直接改写原回答。
class Feedback(Body):
    # 声明trace_id的类型，实际值由构造或调用方提供
    trace_id: str
    # 将调用Field取得返回值保存到rating
    rating: int = Field(ge=0, le=1)
    # 将调用Field取得返回值保存到comment
    comment: str = Field(default='', max_length=1000)

# 应用工厂：为当前配置构造存储、检索和可选Agent对象，再注册路由与静态页面。
def create_app(config=None, provider_factory=None):
    # 保存config：本次运行配置，包含数据目录、模型名和接口设置。
    config = config or Config.env()
    # 保存store：持久化存储对象，统一访问当前配置的SQLite库。
    store = Store(config)
    # 将根据条件选取两种候选值之一保存到kwargs
    kwargs = {'provider_factory': provider_factory} if provider_factory else {}
    # 保存rag：知识入库与检索业务对象。
    rag = RAG(store, **kwargs)
    # 保存app：当前FastAPI应用；测试可为它注入独立配置和模型替身。
    app = FastAPI(title='职业教育知识库RAG', version='1.0.0')
    # 将按位置组合多个值，供解包赋值或函数返回保存到(app.state.store, app.state.rag)
    app.state.store, app.state.rag = (store, rag)

    # 把已知业务错误变成可读响应；不把错误当成正常“查无记录”。
    @app.exception_handler(AppError)
    def application_error(request, error):
        # 将调用JSONResponse取得返回值返回调用方，后续由上一层继续处理
        return JSONResponse({'error': str(error)}, status_code=error.status)

    # 数据库异常保留类型/路径追踪，向页面提示操作未完成，不泄露底层SQL细节。
    @app.exception_handler(sqlite3.Error)
    def database_error(request, error):
        # 保存trace_id：本次执行记录的唯一编号，供页面和日志关联排错。
        trace_id = store.trace('api.database', None, 'failed', time.perf_counter(), {'path': request.url.path, 'type': type(error).__name__})
        # 将调用JSONResponse取得返回值返回调用方，后续由上一层继续处理
        return JSONResponse({'error': '数据库操作未完成，请核对文档与执行记录', 'trace_id': trace_id}, status_code=503)

    # 给前端显示真实运行模式与模型信息；只返回密钥是否配置，不返回密钥本身。
    @app.get('/api/health')
    def health():
        # 将构造字典，字段包括status/mode/embedding_backend/model/model_key_configured/data_type返回调用方，后续由上一层继续处理
        return {'status': 'ok', 'mode': config.mode, 'embedding_backend': rag.backend, 'model': config.model if config.mode == 'live' else '离线确定性演示（非大模型）', 'model_key_configured': bool(config.api_key), 'data_type': '个人实践/模拟业务'}

    # 列出当前模式可管理的文档，具体查询逻辑交给RAG。
    @app.get('/api/rag/documents')
    def documents():
        # 将调用rag.documents取得返回值返回调用方，后续由上一层继续处理
        return rag.documents()

    # 仅读取大小上限加1字节以检测超限；无论入库成败都关闭上传文件句柄。
    @app.post('/api/rag/documents')
    def upload(file: UploadFile=File(...)):
        # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
        try:
            # 将调用file.file.read取得返回值保存到content
            content = file.file.read(15 * 1024 * 1024 + 1)
            # 将调用rag.ingest取得返回值返回调用方，后续由上一层继续处理
            return rag.ingest(file.filename, content)
        finally:
            # 关闭资源，释放连接或文件占用
            file.file.close()

    # 删除指定文档及其索引；不按模型回答中的名字猜测删除对象。
    @app.delete('/api/rag/documents/{doc_id}')
    def delete(doc_id: str):
        # 调用rag.delete取得返回值
        rag.delete(doc_id)
        # 将构造字典，字段包括deleted返回调用方，后续由上一层继续处理
        return {'deleted': True}

    # 保留一次性JSON问答接口；网页流式入口是另一路由。
    @app.post('/api/rag/ask')
    def ask(body: Question):
        # 将调用rag.answer取得返回值返回调用方，后续由上一层继续处理
        return rag.answer(body.question, body.strategy)

    # 以SSE返回问答事件；响应头发出后，业务失败要靠error事件传给客户端。
    @app.post('/api/rag/ask/stream')
    def ask_stream(body: Question):
        # 桥接业务生成器和SSE文本帧，退出时关闭业务流，避免未完成结果被误报成功。
        def events():
            # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
            try:
                # 从contextlib导入closing，统一上下文退出时的清理行为
                from contextlib import closing
                # 进入资源上下文：closing(rag.answer_stream(body.question, body.strategy))；离开时按管理器约定提交/回滚或释放资源
                with closing(rag.answer_stream(body.question, body.strategy)) as stream:
                    # 依次遍历stream，当前项保存为event
                    for event in stream:
                        # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
                        yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
            except Exception as error:
                # HTTP响应头已发出；以明确终止事件通知前端清除未校验文本。
                # 将根据条件选取两种候选值之一保存到message
                message = str(error) if isinstance(error, AppError) else '本次生成未完成，请查看运行记录'
                # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
                yield 'data: ' + json.dumps({'type': 'error', 'message': message}, ensure_ascii=False) + '\n\n'
        # 将调用StreamingResponse取得返回值返回调用方，后续由上一层继续处理
        return StreamingResponse(events(), media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # 仅返回检索片段，用于定位召回问题，不额外生成答案。
    @app.post('/api/rag/retrieve')
    def retrieve(body: Question):
        # 将构造字典，字段包括sources返回调用方，后续由上一层继续处理
        return {'sources': rag.retrieve(body.question, body.strategy)}

    # 列出最近执行摘要，供页面定位耗时与失败；原始payload由详情接口按ID读取。
    @app.get('/api/traces')
    def traces():
        # 进入资源上下文：store.db()；离开时按管理器约定提交/回滚或释放资源
        with store.db() as db:
            # 将遍历输入、筛选并构造列表返回调用方，后续由上一层继续处理
            return [dict(row) for row in db.execute('SELECT id,project,session_id,created,status,elapsed_ms FROM traces ORDER BY created DESC LIMIT 100')]

    # 按明确trace_id读取原始证据，用于核对参数、工具结果、来源和usage。
    @app.get('/api/traces/{trace_id}')
    def trace(trace_id: str):
        # 进入资源上下文：store.db()；离开时按管理器约定提交/回滚或释放资源
        with store.db() as db:
            # 保存row：数据库取回的一条记录或正在处理的片段记录。
            row = db.execute('SELECT * FROM traces WHERE id=?', (trace_id,)).fetchone()
        # 仅当条件成立时执行下一分支：not row
        if not row:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError('记录不存在', 404)
        # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
        result = dict(row)
        # 将把JSON字符串解析成Python数据保存到result['payload']
        result['payload'] = json.loads(result['payload'])
        # 将读取result返回调用方，后续由上一层继续处理
        return result

    # 确认执行记录存在再保存评分，保持反馈与实际回答可追溯。
    @app.post('/api/feedback')
    def feedback(body: Feedback):
        # 进入资源上下文：store.db()；离开时按管理器约定提交/回滚或释放资源
        with store.db() as db:
            # 仅当条件成立时执行下一分支：not db.execute('SELECT id FROM traces WHERE id=?', (body.trace_id,)).fetchone()
            if not db.execute('SELECT id FROM traces WHERE id=?', (body.trace_id,)).fetchone():
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise AppError('记录不存在', 404)
            # 写入新记录，唯一约束负责拒绝冲突或按SQL规则复用
            db.execute('INSERT INTO feedback VALUES(?,?,?,?,?)', (uuid.uuid4().hex, body.trace_id, body.rating, body.comment, time.time()))
        # 将构造字典，字段包括saved返回调用方，后续由上一层继续处理
        return {'saved': True}
    # 调用app.mount取得返回值
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    # 返回本项目静态首页，脚本通过API与后端交互，不需要把密钥放到浏览器。
    @app.get('/')
    @app.get('/rag')
    def page():
        # 将调用FileResponse取得返回值返回调用方，后续由上一层继续处理
        return FileResponse(ROOT / 'static' / 'index.html')
    # 将读取app返回调用方，后续由上一层继续处理
    return app
