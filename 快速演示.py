"""面试现场演示：入库 → 三个问题带引用回答 → 四种检索策略对比。

临时库运行，不改动 runtime 里的演示数据。
用法：python -X utf8 快速演示.py
"""

import tempfile
import time
from pathlib import Path

from suite.app import create_app
from suite.core import Config


def step(title, text):
    print(f"\n▶ {title}")
    for line in str(text).splitlines():
        print("   " + line)


def main():
    with tempfile.TemporaryDirectory(prefix="demo-") as tmp:
        app = create_app(Config(data=Path(tmp)))
        rag = app.state.rag
        for path in sorted((Path(__file__).parent / "samples").glob("*")):
            if path.is_file():
                rag.ingest(path.name, path.read_bytes())

        documents = rag.documents()
        step("① 入库结果", "\n".join(f"{item['name']} · {item['chunks']} 块 · v{item['version']}" for item in documents))
        print(f"\n当前 backend：{rag.backend}")

        questions = [
            "while循环为什么要更新变量？",
            "RAG文档处理有哪些步骤？",
            "课程学费是多少钱？",
        ]
        for index, question in enumerate(questions, 1):
            started = time.perf_counter()
            result = rag.answer(question, "hybrid_rerank")
            elapsed = (time.perf_counter() - started) * 1000
            answer = result["answer"] if len(result["answer"]) <= 300 else result["answer"][:300] + "…"
            note = "已拒答" if result["abstained"] else f"引用 {len(result['sources'])} 条"
            step(f"问题 {index}：{question}", f"{answer}\n（{elapsed:.0f}ms，{note}）")

        print("\n▶ 检索策略对比（同一问题，前 3 条是否命中样例文档）")
        probe = "while循环为什么要更新变量？"
        for strategy in ("keyword", "vector", "hybrid", "hybrid_rerank"):
            rows = rag.retrieve(probe, strategy=strategy, top_k=3)
            # 单文档样例里文件名都一样，用章节名才能看出排序差异
            labels = "、".join(f"{(row['section'] or '正文')[:10]}#{row['id'][:4]}" for row in rows) or "（无）"
            print(f"   {strategy:<14} {len(rows)} 条 | {labels}")

        print("\ndemo 模式只摘录原文，不调用大模型；设置 APP_MODE=live 与 DASHSCOPE_API_KEY 后才生成回答。")


if __name__ == "__main__":
    main()
