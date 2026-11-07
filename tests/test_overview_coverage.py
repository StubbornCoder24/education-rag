# 离线回归：用临时存储与必要的模型替身验证边界；通过测试不等于真实模型准确率。

from suite.app import create_app
from suite.core import Config, Provider
from suite.rag import overview_question

# 刻意只给一个锚点，检验跨页后续块能补齐且不串入其他文档。
def test_overview_expands_cross_page_continuation_without_other_document(tmp_path):
    app = create_app(Config(data=tmp_path))
    rag = app.state.rag
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('概念.md', ('# 数据库概念\nCollection集合。\n' + '说明。'*700).encode())
    # 按当前配置解析并建立该文档的检索索引
    rag.ingest('无关.md', '私人无关内容。'.encode())
    with app.state.store.db() as db:
        doc = db.execute("SELECT id FROM documents WHERE name='概念.md'").fetchone()['id']
        chunks = db.execute('SELECT id FROM chunks WHERE doc_id=? ORDER BY rowid', (doc,)).fetchall()
        assert len(chunks) >= 3
        db.execute('UPDATE chunks SET page=1,text=? WHERE id=?', ('数据库概念 Collection集合。', chunks[0]['id']))
        db.execute('UPDATE chunks SET page=2,text=? WHERE id=?', ('Flush刷盘。Search向量检索。', chunks[1]['id']))
        db.execute('UPDATE chunks SET page=3,text=? WHERE id=?', ('Query标量查询。Hybrid Search混合检索。', chunks[2]['id']))
    # 锚点只命中表格首段；后续定义缺少问题词，仍应通过位置扩展覆盖。
    anchor = rag.retrieve('Collection', 'keyword', top_k=1)[0]
    rag.retrieve = lambda *args, **kwargs: [anchor]
    context = rag.context('数据库概念有哪些', 'keyword', Provider(rag.config))
    text = '\n'.join(r['text'] for r in context)
    assert all(term in text for term in ('Collection', 'Flush', 'Search', 'Query', 'Hybrid'))
    assert all(r['doc_id'] == doc for r in context)
    assert len(context) <= 12 and sum(len(r['text']) for r in context) <= 10000
    assert len({r['id'] for r in context}) == len(context)
    assert len(rag.context('Collection是什么意思', 'keyword', Provider(rag.config))) == 1

# 只有规则识别的概览题扩上下文，普通单点题保持较小预算。
def test_overview_intent_is_not_every_question():
    assert overview_question('Milvus中的概念有哪些')
    assert overview_question('包含哪些操作')
    assert not overview_question('如何创建Collection')
