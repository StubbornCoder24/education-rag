# 命令行启动入口：解析模式/端口/地址，交给FastAPI与Uvicorn提供本地页面及接口。
# 默认demo；live会产生真实模型调用。仅运行此入口本身不会自动初始化知识样例。

# 导入argparse：声明命令行模式、端口、文件等选项
import argparse
# 导入os：读取环境变量及设置当前进程配置
import os


# 解析启动参数后再导入应用，确保环境变量先于配置加载生效。
def main():
    # 保存parser：命令行参数解析器，后面声明可接受的选项。
    parser = argparse.ArgumentParser(description="职业教育知识库RAG独立启动入口")
    # 声明一个命令行选项及其默认值/限制，后面统一解析
    parser.add_argument("--mode", choices=["demo", "live"], default=os.getenv("APP_MODE", "demo"))
    # 声明一个命令行选项及其默认值/限制，后面统一解析
    parser.add_argument("--port", type=int, default=8001)
    # 声明一个命令行选项及其默认值/限制，后面统一解析
    parser.add_argument("--host", default="127.0.0.1")
    # 保存args：经解析的命令行参数或工具JSON参数，取决于当前入口。
    args = parser.parse_args()
    # 将读取args.mode保存到os.environ['APP_MODE']
    os.environ["APP_MODE"] = args.mode
    # 从suite.app导入create_app，供下方业务或测试调用
    from suite.app import create_app
    # 导入uvicorn：使用其公开工具，不在这里执行具体业务
    import uvicorn
    # 把当前状态/结果打印到控制台，便于运行时核对
    print("RAG页面：http://" + args.host + ":" + str(args.port) + "/rag")
    # 把当前状态/结果打印到控制台，便于运行时核对
    print("模式：", args.mode, "；原教学数据库与记录不会被迁移或覆盖。")
    # 启动HTTP服务处理页面/API请求，直到进程被停止
    uvicorn.run(create_app(), host=args.host, port=args.port)


# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == "__main__":
    # 调用main取得返回值
    main()
