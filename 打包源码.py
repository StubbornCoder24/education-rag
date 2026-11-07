# 生成可分享的源码包与文件哈希清单，排除密钥、虚拟环境、运行库和原始调用记录。
# 包里只包含可交付源码材料；本机运行数据不会随着打包被删除。

"""打包可移植源码，不包含密钥、运行库、真实课件或原始问答记录。"""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from suite.core import ROOT

# 目录级排除：虚拟环境、IDE、缓存、Git 历史都不能进源码包。
EXCLUDED_DIRS = {".deps", ".venv", "env", "venv", ".idea", ".vscode", "node_modules", "__pycache__", ".pytest_cache", ".git"}
# 运行数据按前缀排除：runtime、runtime_live、runtime_eval 都是本机数据库。
EXCLUDED_PREFIXES = ("runtime",)
# evaluation 只保留可复现本文档命令所需的脚本与最新一份报告，历史批次留在本机。
EVALUATION_FILES = {"eval_metrics.py", "rag_cases.json", "pdf_cases.json", "langchain_cases.json", "metrics_report.json", "独立性验收.json"}
# 打包后自检：这些后缀一旦出现说明排除规则失效。
FORBIDDEN_SUFFIX = (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".sqlite3-wal",
                    ".sqlite3-shm", ".log", ".pem", ".key", ".p12", ".pfx", ".pdf", ".docx", ".zip", ".7z")


def wanted(path, relative):
    if set(relative.parts) & EXCLUDED_DIRS:
        return False
    if relative.parts[0].startswith(EXCLUDED_PREFIXES):
        return False
    if relative.parts[0] == "evaluation" and path.name not in EVALUATION_FILES:
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    return True


# 筛选可交付文件，逐个计算SHA256，再写ZIP并做完整性检查。
def main():
    destination = ROOT.parent / "职业教育知识库RAG_独立版.zip"
    try:
        tracked = subprocess.check_output(["git", "ls-files", "-z", "--cached"], cwd=ROOT, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("请在已安装 Git 的项目仓库中运行打包命令。") from error
    files = []
    for name in tracked.decode("utf-8").split("\0"):
        if not name:
            continue
        relative = Path(name)
        path = ROOT / relative
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT) and wanted(path, relative):
            files.append(path)
    leaked = [str(path.relative_to(ROOT)) for path in files if path.name.lower().endswith(FORBIDDEN_SUFFIX)]
    if leaked:
        raise SystemExit("打包中止：以下文件不应进入源码包 " + "、".join(leaked))
    manifest = [{"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(files)]
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "职业教育知识库RAG_成品/" + path.relative_to(ROOT).as_posix())
        archive.writestr("职业教育知识库RAG_成品/文件校验清单.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert not [name for name in names if name.lower().endswith(FORBIDDEN_SUFFIX)], "源码包内仍混入运行数据"
    print(destination)
    print("源码文件数：", len(files), "；不含运行数据或真实资料；完整原始验收记录保留在本机evaluation目录。")


# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == "__main__":
    main()
