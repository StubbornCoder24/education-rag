# 将本项目samples中的自编资料建立索引；可选PDF由命令行显式指定。
# live会把文本送至已配置模型服务；不会自动迁移其他项目的数据。

# 导入argparse：声明命令行模式、端口、文件等选项
import argparse
# 从pathlib导入Path，用对象处理路径而非手拼字符串
from pathlib import Path

# 从suite.core导入Config/Store/ROOT，供下方业务或测试调用
from suite.core import Config, Store, ROOT
# 从suite.rag导入RAG，供下方业务或测试调用
from suite.rag import RAG


# 沿用当前模式和数据目录，逐份入库样例；同内容复用由ingest负责。
def main():
    # 保存parser：命令行参数解析器，后面声明可接受的选项。
    parser = argparse.ArgumentParser()
    # 声明一个命令行选项及其默认值/限制，后面统一解析
    parser.add_argument("--pdf", type=Path, help="可选：读取本地真实文本PDF，保留物理页码")
    # 保存args：经解析的命令行参数或工具JSON参数，取决于当前入口。
    args = parser.parse_args()
    # 保存config：本次运行配置，包含数据目录、模型名和接口设置。
    config = Config.env()
    # 保存rag：知识入库与检索业务对象。
    rag = RAG(Store(config))
    # 把当前状态/结果打印到控制台，便于运行时核对
    print("索引模式：", config.mode, "；live会向模型服务发送文档片段。")
    # 依次遍历(ROOT / 'samples').glob('*.md')，当前项保存为path
    for path in (ROOT / "samples").glob("*.md"):
        # 把当前状态/结果打印到控制台，便于运行时核对
        print(rag.ingest(path.name, path.read_bytes()))
    # 仅当条件成立时执行下一分支：args.pdf
    if args.pdf:
        # 把当前状态/结果打印到控制台，便于运行时核对
        print(rag.ingest(args.pdf.name, args.pdf.read_bytes()))


# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == "__main__":
    # 调用main取得返回值
    main()
