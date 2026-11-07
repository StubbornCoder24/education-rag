# 迁移指定已解析文档：只读离线库，重新生成真实向量后写独立live库。
# 不复用demo哈希向量；新向量全部成功后才在事务内替换，原离线库保持不变。

"""将指定文档的已解析片段重新向量化到live库；会发送文本到阿里云。"""
import argparse
import json
import sqlite3
import time
import uuid
from contextlib import closing
from suite.core import Config, Store, Provider, ROOT, AppError
from suite.rag import RAG

# 显式选择一份文档；网络请求在写事务之前，避免失败时破坏旧live版本。
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # 声明一个命令行选项及其默认值/限制，后面统一解析
    parser.add_argument('--name', required=True, help='离线知识库中已上传的文件名')
    args = parser.parse_args()
    config = Config.env()
    config.mode, config.data = 'live', ROOT / 'runtime_live'
    if not config.api_key:
        raise AppError('未配置DASHSCOPE_API_KEY，请在本机环境变量中配置，勿粘贴到聊天中')
    with closing(sqlite3.connect((ROOT / 'runtime/app.db').as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        doc = db.execute('SELECT * FROM documents WHERE name=?', (args.name,)).fetchone()
        if not doc:
            raise AppError('离线库未找到指定文档')
        doc = dict(doc)
        chunks = [dict(r) for r in db.execute('SELECT * FROM chunks WHERE doc_id=? ORDER BY rowid', (doc['id'],))]
    if not chunks:
        raise AppError('指定文档无可用片段')
    store = Store(config)
    rag = RAG(store)
    with store.db() as db:
        old = db.execute('SELECT * FROM documents WHERE name=?', (args.name,)).fetchone()
        # 同名文件内容哈希和Embedding后端均未变时复用原索引，避免重复消耗
        if old and old['sha'] == doc['sha'] and old['backend'] == rag.backend:
            print('真实索引已存在且内容未变，未重复调用Embedding。')
            # 提前结束当前函数，不再执行后续分支
            return
    provider = Provider(config)
    started = time.perf_counter()
    try:
        vectors = provider.embed([c['text'] for c in chunks])
        with store.db() as db:
            # 开启写事务，后续修改一起提交或回滚
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM documents WHERE name=?', (args.name,)).fetchone()
            doc_id = old['id'] if old else uuid.uuid4().hex
            version = old['version'] + 1 if old else 1
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET sha=excluded.sha,version=excluded.version,backend=excluded.backend,updated=excluded.updated',
                       (doc_id, args.name, doc['sha'], version, rag.backend, time.time()))
            # 删除匹配记录，关联片段按外键约束处理
            db.execute('DELETE FROM chunks WHERE doc_id=?', (doc_id,))
            for chunk, vector in zip(chunks, vectors):
                db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex[:16], doc_id,
                    chunk['page'], chunk['section'], chunk['text'], json.dumps(vector)))
        trace = store.trace('rag.live_index', None, 'completed', started,
            {'name': args.name, 'chunks': len(chunks), 'backend': rag.backend, 'events': provider.events})
        print('真实索引完成：', args.name, len(chunks), '个片段；记录', trace)
    except Exception as error:
        # 保存当前操作的状态、耗时和证据数据
        store.trace('rag.live_index', None, 'failed', started,
                    {'name': args.name, 'error': str(error), 'events': provider.events})
        raise

# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == '__main__':
    main()
