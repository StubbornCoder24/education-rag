# 包初始化：让本项目随带的PDF依赖可被导入；不启动服务，也不调用外部模型。

"""职业教育知识库RAG独立成品。"""
# 导入sys：访问解释器路径和导入搜索路径
import sys
# 从pathlib导入Path，用对象处理路径而非手拼字符串
from pathlib import Path

# 保存private_deps：本项目私有依赖路径，不是另一个项目的代码目录。
private_deps = Path(__file__).resolve().parent.parent / ".deps"
# 仅当条件成立时执行下一分支：private_deps.is_dir()
if private_deps.is_dir():
    # 调用sys.path.insert取得返回值
    sys.path.insert(0, str(private_deps))
