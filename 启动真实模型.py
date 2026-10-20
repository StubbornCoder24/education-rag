# 便捷真实模式入口：固定本项目的runtime_live目录，再复用常规启动流程。
# 与demo数据隔离；密钥仍从本机环境变量读取，不写入这个文件。

"""阿里云百炼真实模型入口；与离线知识库使用不同数据目录。"""
# 导入os：读取环境变量及设置当前进程配置
import os
# 从pathlib导入Path，用对象处理路径而非手拼字符串
from pathlib import Path


# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == '__main__':
    # 将'live'保存到os.environ['APP_MODE']
    os.environ['APP_MODE'] = 'live'
    # 将调用str取得返回值保存到os.environ['APP_DATA']
    os.environ['APP_DATA'] = str(Path(__file__).resolve().parent / 'runtime_live')
    # 从启动项目导入main，供下方业务或测试调用
    from 启动项目 import main
    # 调用main取得返回值
    main()
