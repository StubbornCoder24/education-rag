# 迁移指定已解析文档：只读离线库，重新生成真实向量后写独立live库。
# 不复用demo哈希向量；新向量全部成功后才在事务内替换，原离线库保持不变。

"""将指定文档的已解析片段重新向量化到live库；会发送文本到阿里云。"""
# 导入argparse：声明命令行模式、端口、文件等选项
import argparse
# 导入json：在字符串与字典/列表间转换JSON数据
import json
# 导入sqlite3：使用本地SQLite数据库连接与异常类型
import sqlite3
# 导入time：取得时间戳和单调计时，保存创建时间与计算耗时
import time
# 导入uuid：生成文档、片段、任务、请求或记录的唯一标识
import uuid
# 从contextlib导入closing，统一上下文退出时的清理行为
from contextlib import closing
# 从suite.core导入Config/Store/Provider/ROOT/AppError，供下方业务或测试调用
from suite.core import Config, Store, Provider, ROOT, AppError
# 从suite.rag导入RAG，供下方业务或测试调用
from suite.rag import RAG


# 显式选择一份文档；网络请求在写事务之前，避免失败时破坏旧live版本。
def main():
    # 保存parser：命令行参数解析器，后面声明可接受的选项。
    parser = argparse.ArgumentParser(description=__doc__)
    # 声明一个命令行选项及其默认值/限制，后面统一解析
    parser.add_argument('--name', required=True, help='离线知识库中已上传的文件名')
    # 保存args：经解析的命令行参数或工具JSON参数，取决于当前入口。
    args = parser.parse_args()
    # 保存config：本次运行配置，包含数据目录、模型名和接口设置。
    config = Config.env()
    # 将按位置组合多个值，供解包赋值或函数返回保存到(config.mode, config.data)
    config.mode, config.data = 'live', ROOT / 'runtime_live'
    # 仅当条件成立时执行下一分支：not config.api_key
    if not config.api_key:
        # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
        raise AppError('未配置DASHSCOPE_API_KEY，请在本机环境变量中配置，勿粘贴到聊天中')
    # 进入资源上下文：closing(sqlite3.connect((ROOT / 'runtime/app.db').as_uri() + '?mode=ro', uri=True))；离开时按管理器约定提交/回滚或释放资源
    with closing(sqlite3.connect((ROOT / 'runtime/app.db').as_uri() + '?mode=ro', uri=True)) as db:
        # 将读取sqlite3.Row保存到db.row_factory
        db.row_factory = sqlite3.Row
        # 将读取一条数据库结果，没有结果时返回None保存到doc
        doc = db.execute('SELECT * FROM documents WHERE name=?', (args.name,)).fetchone()
        # 仅当条件成立时执行下一分支：not doc
        if not doc:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError('离线库未找到指定文档')
        # 将构造或转换为字典保存到doc
        doc = dict(doc)
        # 保存chunks：清洗后的小片段列表，后续每段分别生成向量。
        chunks = [dict(r) for r in db.execute('SELECT * FROM chunks WHERE doc_id=? ORDER BY rowid', (doc['id'],))]
    # 仅当条件成立时执行下一分支：not chunks
    if not chunks:
        # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
        raise AppError('指定文档无可用片段')
    # 保存store：持久化存储对象，统一访问当前配置的SQLite库。
    store = Store(config)
    # 保存rag：知识入库与检索业务对象。
    rag = RAG(store)
    # 进入资源上下文：store.db()；离开时按管理器约定提交/回滚或释放资源
    with store.db() as db:
        # 保存old：已保存记录的快照；用于版本检查、复用或恢复历史。
        old = db.execute('SELECT * FROM documents WHERE name=?', (args.name,)).fetchone()
        # 同名文件内容哈希和Embedding后端均未变时复用原索引，避免重复消耗
        if old and old['sha'] == doc['sha'] and old['backend'] == rag.backend:
            # 把当前状态/结果打印到控制台，便于运行时核对
            print('真实索引已存在且内容未变，未重复调用Embedding。')
            # 提前结束当前函数，不再执行后续分支
            return
    # 保存provider：本次操作使用的模型适配器，events单独记录本次接口调用。
    provider = Provider(config)
    # 保存started：用单调时钟保存操作开始时刻，后面计算耗时。
    started = time.perf_counter()
    # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
    try:
        # 保存vectors：片段向量列表；入库时需要与片段一一对应。
        vectors = provider.embed([c['text'] for c in chunks])
        # 进入资源上下文：store.db()；离开时按管理器约定提交/回滚或释放资源
        with store.db() as db:
            # 开启写事务，后续修改一起提交或回滚
            db.execute('BEGIN IMMEDIATE')
            # 保存old：已保存记录的快照；用于版本检查、复用或恢复历史。
            old = db.execute('SELECT * FROM documents WHERE name=?', (args.name,)).fetchone()
            # 保存doc_id：文档标识；同名版本更新保留此标识并重建片段。
            doc_id = old['id'] if old else uuid.uuid4().hex
            # 保存version：当前草稿或文档版本，防止把旧确认用于新内容。
            version = old['version'] + 1 if old else 1
            # 写入新记录，唯一约束负责拒绝冲突或按SQL规则复用
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET sha=excluded.sha,version=excluded.version,backend=excluded.backend,updated=excluded.updated',
                       (doc_id, args.name, doc['sha'], version, rag.backend, time.time()))
            # 删除匹配记录，关联片段按外键约束处理
            db.execute('DELETE FROM chunks WHERE doc_id=?', (doc_id,))
            # 依次遍历zip(chunks, vectors)，当前项保存为(chunk, vector)
            for chunk, vector in zip(chunks, vectors):
                # 写入新记录，唯一约束负责拒绝冲突或按SQL规则复用
                db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex[:16], doc_id,
                    chunk['page'], chunk['section'], chunk['text'], json.dumps(vector)))
        # 将调用store.trace取得返回值保存到trace
        trace = store.trace('rag.live_index', None, 'completed', started,
            {'name': args.name, 'chunks': len(chunks), 'backend': rag.backend, 'events': provider.events})
        # 把当前状态/结果打印到控制台，便于运行时核对
        print('真实索引完成：', args.name, len(chunks), '个片段；记录', trace)
    except Exception as error:
        # 保存当前操作的状态、耗时和证据数据
        store.trace('rag.live_index', None, 'failed', started,
                    {'name': args.name, 'error': str(error), 'events': provider.events})
        # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
        raise


# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == '__main__':
    # 调用main取得返回值
    main()
