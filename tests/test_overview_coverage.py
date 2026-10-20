# 离线回归：用临时存储与必要的模型替身验证边界；通过测试不等于真实模型准确率。

# 从suite.app导入create_app，供下方业务或测试调用
from suite.app import create_app
# 从suite.core导入Config/Provider，供下方业务或测试调用
from suite.core import Config, Provider
# 从suite.rag导入overview_question，供下方业务或测试调用
from suite.rag import overview_question


# 刻意只给一个锚点，检验跨页后续块能补齐且不串入其他文档。
def test_overview_expands_cross_page_continuation_without_other_document(tmp_path):
    # 保存app：当前FastAPI应用；测试可为它注入独立配置和模型替身。
    app = create_app(Config(data=tmp_path))
    # 保存rag：知识入库与检索业务对象。
    rag = app.state.rag
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('概念.md', ('# 数据库概念\nCollection集合。\n' + '说明。'*700).encode())
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('无关.md', '私人无关内容。'.encode())
    # 进入资源上下文：app.state.store.db()；离开时按管理器约定提交/回滚或释放资源
    with app.state.store.db() as db:
        # 将按键或下标读取db.execute("SELECT id FROM documents WHERE name='概念.md'").fetchone()中的内容保存到doc
        doc = db.execute("SELECT id FROM documents WHERE name='概念.md'").fetchone()['id']
        # 保存chunks：清洗后的小片段列表，后续每段分别生成向量。
        chunks = db.execute('SELECT id FROM chunks WHERE doc_id=? ORDER BY rowid', (doc,)).fetchall()
        # 测试断言：确认len(chunks) >= 3；不满足时用例失败
        assert len(chunks) >= 3
        # 按条件更新记录，版本/状态条件可阻止过期操作
        db.execute('UPDATE chunks SET page=1,text=? WHERE id=?', ('数据库概念 Collection集合。', chunks[0]['id']))
        # 按条件更新记录，版本/状态条件可阻止过期操作
        db.execute('UPDATE chunks SET page=2,text=? WHERE id=?', ('Flush刷盘。Search向量检索。', chunks[1]['id']))
        # 按条件更新记录，版本/状态条件可阻止过期操作
        db.execute('UPDATE chunks SET page=3,text=? WHERE id=?', ('Query标量查询。Hybrid Search混合检索。', chunks[2]['id']))
    # 锚点只命中表格首段；后续定义缺少问题词，仍应通过位置扩展覆盖。
    # 将按键或下标读取rag.retrieve('Collection', 'keyword', top_k=1)中的内容保存到anchor
    anchor = rag.retrieve('Collection', 'keyword', top_k=1)[0]
    # 将读取lambda *args, **kwargs: [anchor]保存到rag.retrieve
    rag.retrieve = lambda *args, **kwargs: [anchor]
    # 将调用rag.context取得返回值保存到context
    context = rag.context('数据库概念有哪些', 'keyword', Provider(rag.config))
    # 将按顺序拼接字符串片段保存到text
    text = '\n'.join(r['text'] for r in context)
    # 测试断言：确认all((term in text for term in ('Collection', 'Flush', 'Search', 'Query', 'Hybrid')))；不满足时用例失败
    assert all(term in text for term in ('Collection', 'Flush', 'Search', 'Query', 'Hybrid'))
    # 测试断言：确认all((r['doc_id'] == doc for r in context))；不满足时用例失败
    assert all(r['doc_id'] == doc for r in context)
    # 测试断言：确认len(context) <= 12 and sum((len(r['text']) for r in context)) <= 10000；不满足时用例失败
    assert len(context) <= 12 and sum(len(r['text']) for r in context) <= 10000
    # 测试断言：确认len({r['id'] for r in context}) == len(context)；不满足时用例失败
    assert len({r['id'] for r in context}) == len(context)
    # 测试断言：确认len(rag.context('Collection是什么意思', 'keyword', Provider(rag.config))) == 1；不满足时用例失败
    assert len(rag.context('Collection是什么意思', 'keyword', Provider(rag.config))) == 1


# 只有规则识别的概览题扩上下文，普通单点题保持较小预算。
def test_overview_intent_is_not_every_question():
    # 测试断言：确认overview_question('Milvus中的概念有哪些')；不满足时用例失败
    assert overview_question('Milvus中的概念有哪些')
    # 测试断言：确认overview_question('包含哪些操作')；不满足时用例失败
    assert overview_question('包含哪些操作')
    # 测试断言：确认not overview_question('如何创建Collection')；不满足时用例失败
    assert not overview_question('如何创建Collection')
