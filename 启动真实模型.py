# 便捷真实模式入口：固定本项目的runtime_live目录，再复用常规启动流程。
# 与demo数据隔离；密钥仍从本机环境变量读取，不写入这个文件。

"""阿里云百炼真实模型入口；与离线知识库使用不同数据目录。"""
import os
from pathlib import Path

# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == '__main__':
    os.environ['APP_MODE'] = 'live'
    os.environ['APP_DATA'] = str(Path(__file__).resolve().parent / 'runtime_live')
    from 启动项目 import main
    main()
