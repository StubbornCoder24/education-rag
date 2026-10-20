# 生成可分享的源码包与文件哈希清单，排除密钥、虚拟环境、运行库和原始调用记录。
# 包里只包含可交付源码材料；本机运行数据不会随着打包被删除。

"""打包可移植源码，不包含密钥、运行库、真实课件或原始会话轨迹。"""
# 导入hashlib：计算SHA256内容哈希，识别文件/请求内容变化
import hashlib
# 导入json：在字符串与字典/列表间转换JSON数据
import json
# 导入zipfile：创建源码压缩包并检查包完整性
import zipfile
# 从suite.core导入ROOT，供下方业务或测试调用
from suite.core import ROOT


# 筛选可交付文件，逐个计算SHA256，再写ZIP并做完整性检查。
def main():
    # 保存destination：生成源码ZIP的目标路径，不是运行数据目录。
    destination = ROOT.parent / "职业教育知识库RAG_独立版.zip"
    # 保存excluded：打包时排除的目录集合，避免携带环境、运行数据等。
    excluded = {".git", ".deps", ".venv", "env", "venv", ".idea", ".vscode", "node_modules", "runtime", "runtime_live", "__pycache__", ".pytest_cache"}
    # 保存files：通过打包过滤的源码文件列表。
    files = []
    # 依次遍历ROOT.rglob('*')，当前项保存为path
    for path in ROOT.rglob("*"):
        # 保存relative：文件相对项目根目录的位置，用于过滤和ZIP内命名。
        relative = path.relative_to(ROOT)
        # 仅当条件成立时执行下一分支：not path.is_file() or set(relative.parts) & excluded or (path.name.startswith('.env') and path.name != '.env.example')
        if not path.is_file() or set(relative.parts) & excluded or (path.name.startswith(".env") and path.name != ".env.example"):
            # 跳过本次循环余下步骤，继续处理下一项
            continue
        # 仅当条件成立时执行下一分支：relative.parts[0] == 'evaluation' and path.name not in {'rag_cases.json', '验收摘要.md'}
        if relative.parts[0] == "evaluation" and path.name not in {"rag_cases.json", "验收摘要.md"}:
            # 跳过本次循环余下步骤，继续处理下一项
            continue
        # 把读取path加入files，保持处理顺序
        files.append(path)
    # 保存manifest：源码路径及SHA256校验清单，用于检查交付内容一致性。
    manifest = [{"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(files)]
    # 进入资源上下文：zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED)；离开时按管理器约定提交/回滚或释放资源
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        # 依次遍历files，当前项保存为path
        for path in files:
            # 调用archive.write取得返回值
            archive.write(path, "职业教育知识库RAG_成品/" + path.relative_to(ROOT).as_posix())
        # 调用archive.writestr取得返回值
        archive.writestr("职业教育知识库RAG_成品/文件校验清单.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    # 进入资源上下文：zipfile.ZipFile(destination)；离开时按管理器约定提交/回滚或释放资源
    with zipfile.ZipFile(destination) as archive:
        # 测试断言：确认archive.testzip() is None；不满足时用例失败
        assert archive.testzip() is None
    # 把当前状态/结果打印到控制台，便于运行时核对
    print(destination)
    # 把当前状态/结果打印到控制台，便于运行时核对
    print("源码文件数：", len(files), "；不含运行数据或真实课件；完整原始验收记录保留在本机evaluation目录。")


# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == "__main__":
    # 调用main取得返回值
    main()
