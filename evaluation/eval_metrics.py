"""RAG 检索质量评测：按四种策略跑 40 题，输出 Recall@5 / MRR / 无答案误召回率。

用法：
    python evaluation/eval_metrics.py            # demo 模式（哈希向量，只验证脚本可跑）
    APP_MODE=live python evaluation/eval_metrics.py   # 真实向量，数字才有意义

说明：
- 结果写入 evaluation/metrics_report.json，同时打印一张表。
- 无答案题（expect_abstain=true）不计算 Recall，改为统计“仍然召回到资料”的比例，
  这个比例越低说明系统越不容易在没有依据时硬答。
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STRATEGIES = ["keyword", "vector", "hybrid", "hybrid_rerank"]
TOP_K = 5


def load_cases(name="rag_cases.json"):
    with open(ROOT / "evaluation" / name, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def hit(source, case):
    """命中判定：文件名一致；有 gold_page 就比页码，有 gold_section 就比章节。"""
    if source.get("name") != case["gold_source"]:
        return False
    page = case.get("gold_page")
    if page is not None:
        return source.get("page") == page
    gold = (case.get("gold_section") or "").strip()
    if not gold:
        return True
    return gold in (source.get("section") or "")


def evaluate(rag, cases):
    report = {}
    for strategy in STRATEGIES:
        recalls, reciprocal, unanswered_hit, unanswered_total = [], [], 0, 0
        for case in cases:
            sources = rag.retrieve(case["question"], strategy=strategy, top_k=TOP_K) or []
            if case.get("expect_abstain"):
                unanswered_total += 1
                if sources:
                    unanswered_hit += 1
                continue
            rank = next((i + 1 for i, s in enumerate(sources) if hit(s, case)), None)
            recalls.append(1.0 if rank and rank <= TOP_K else 0.0)
            reciprocal.append(1.0 / rank if rank else 0.0)
        report[strategy] = {
            "recall_at_5": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
            "mrr": round(sum(reciprocal) / len(reciprocal), 4) if reciprocal else 0.0,
            "answered_cases": len(recalls),
            "unanswered_false_recall": round(unanswered_hit / unanswered_total, 4) if unanswered_total else 0.0,
            "unanswered_cases": unanswered_total,
        }
    return report


def ensure_corpus(rag):
    if rag.documents():
        return
    for path in sorted((ROOT / "samples").glob("*")):
        if path.is_file():
            rag.ingest(path.name, path.read_bytes())


def main():
    os.environ.setdefault("APP_MODE", "demo")
    os.environ.setdefault("APP_DATA", str(ROOT / "runtime_eval"))
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="rag_cases.json", help="评测集文件名（放在 evaluation/ 下）")
    parser.add_argument("--no-ingest", action="store_true", help="库已有语料时跳过样例导入")
    args = parser.parse_args()
    from suite.core import Config, Store
    from suite.rag import RAG

    config = Config.env()
    store = Store(config)
    rag = RAG(store)
    if not args.no_ingest:
        ensure_corpus(rag)

    cases = load_cases(args.cases)
    report = evaluate(rag, cases)
    doc_count = len(rag.documents())

    print(f"\n模式: {config.mode} | 后端: {rag.backend} | 文档: {doc_count} | 用例: {len(cases)}")
    if doc_count < 3:
        print("⚠ 语料不足 3 篇，Recall 会接近 1.0，这组数字不能写进简历；请先导入多篇文档。")
    print()
    print(f"{'策略':<16}{'Recall@5':<12}{'MRR':<10}{'无答案误召回':<14}")
    print("-" * 54)
    for strategy, row in report.items():
        print(f"{strategy:<16}{row['recall_at_5']:<12}{row['mrr']:<10}{row['unanswered_false_recall']:<14}")

    out = ROOT / "evaluation" / "metrics_report.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump({"mode": config.mode, "backend": rag.backend, "report": report}, handle, ensure_ascii=False, indent=2)
    print(f"\n已写入 {out}")


if __name__ == "__main__":
    main()
