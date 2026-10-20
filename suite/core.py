# 基础设施：配置从环境变量读取，Store管理SQLite，Provider封装阿里云请求。
# 业务规则放在rag/agent中；这里统一处理连接、输入校验、用量与错误，不输出密钥。

# 导入hashlib：计算SHA256内容哈希，识别文件/请求内容变化
import hashlib
# 导入json：在字符串与字典/列表间转换JSON数据
import json
# 导入os：读取环境变量及设置当前进程配置
import os
# 导入re：匹配文件格式、词项、编号和引用等文本规则
import re
# 导入sqlite3：使用本地SQLite数据库连接与异常类型
import sqlite3
# 导入time：取得时间戳和单调计时，保存创建时间与计算耗时
import time
# 导入uuid：生成文档、片段、任务、请求或记录的唯一标识
import uuid
# 从contextlib导入contextmanager，统一上下文退出时的清理行为
from contextlib import contextmanager
# 从dataclasses导入dataclass，根据字段声明生成配置对象初始化方法
from dataclasses import dataclass
# 从pathlib导入Path，用对象处理路径而非手拼字符串
from pathlib import Path

# 导入numpy：提供向量数组、范数和点积计算
import numpy as np
# 导入requests：向阿里云等已配置服务发出HTTP请求
import requests

# 保存ROOT：当前独立项目根目录，后续静态文件/样例/默认数据都相对此路径定位。
ROOT = Path(__file__).resolve().parent.parent


# 业务可解释错误：携带用户可见信息与HTTP状态，供接口统一返回。
class AppError(Exception):
    # 保留可解释错误消息及HTTP状态，由接口处理器决定响应形式。
    def __init__(self, message, status=400):
        # 调用super().__init__取得返回值
        super().__init__(message)
        # 把读取status保存为实例属性self.status，供该对象的其他方法使用
        self.status = status


# 运行配置：区分demo/live、独立数据目录、聊天模型与Embedding模型。
@dataclass
class Config:
    # 将按表达式计算得到新值：ROOT / 'runtime'保存到data
    data: Path = ROOT / "runtime"
    # 保存mode：demo/live运行模式，决定使用替身还是调用真实接口。
    mode: str = "demo"
    # 将空字符串保存到api_key
    api_key: str = ""
    # 将'https://dashscope.aliyuncs.com/compatible-mode/v1'保存到base_url
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # 将'qwen-plus'保存到model
    model: str = "qwen-plus"
    # 将'text-embedding-v4'保存到embedding_model
    embedding_model: str = "text-embedding-v4"
    # 将1024保存到dimensions
    dimensions: int = 1024

    # 从环境变量构造配置；仅校验取值，不把密钥打印到日志。
    @classmethod
    def env(cls):
        # 保存mode：demo/live运行模式，决定使用替身还是调用真实接口。
        mode = os.getenv("APP_MODE", "demo")
        # 仅当条件成立时执行下一分支：mode not in {'demo', 'live'}
        if mode not in {"demo", "live"}:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("APP_MODE只能为demo或live")
        # 将调用cls取得返回值返回调用方，后续由上一层继续处理
        return cls(Path(os.getenv("APP_DATA", str(ROOT / "runtime"))), mode,
                   os.getenv("DASHSCOPE_API_KEY", ""),
                   os.getenv("MODEL_BASE_URL", cls.base_url),
                   os.getenv("CHAT_MODEL", "qwen-plus"))


# SQLite持久化入口：建立本项目表结构，并集中管理事务和连接关闭。
class Store:
    # 保存配置并建立表结构；实例可重开已有数据库，不会清空原记录。
    def __init__(self, config):
        # 把读取config保存为实例属性self.config，供该对象的其他方法使用
        self.config = config
        # 按需建立目录，已存在时按给定选项处理
        config.data.mkdir(parents=True, exist_ok=True)
        # 把按表达式计算得到新值：config.data / 'app.db'保存为实例属性self.path，供该对象的其他方法使用
        self.path = config.data / "app.db"
        # 进入资源上下文：self.db()；离开时按管理器约定提交/回滚或释放资源
        with self.db() as db:
            # 创建缺失表结构；IF NOT EXISTS不会清空已有数据
            db.executescript("""
            CREATE TABLE IF NOT EXISTS documents(
              id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,sha TEXT NOT NULL,
              version INTEGER NOT NULL,backend TEXT NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks(
              id TEXT PRIMARY KEY,doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              page INTEGER,section TEXT,text TEXT NOT NULL,vector TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS traces(
              id TEXT PRIMARY KEY,project TEXT NOT NULL,session_id TEXT,created REAL NOT NULL,
              status TEXT NOT NULL,elapsed_ms REAL NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feedback(
              id TEXT PRIMARY KEY,trace_id TEXT NOT NULL REFERENCES traces(id),rating INTEGER NOT NULL,
              comment TEXT NOT NULL,created REAL NOT NULL);
            """)

    # 上下文管理器：正常退出提交，异常回滚，最后显式关闭连接以避免Windows文件占用。
    @contextmanager
    def db(self):
        # 保存db：SQLite连接，离开上下文时提交/回滚并关闭。
        db = sqlite3.connect(self.path, timeout=10)
        # 将读取sqlite3.Row保存到db.row_factory
        db.row_factory = sqlite3.Row
        # 每个连接都启用外键，documents删除后关联chunks才会按约束级联清理。
        # 启用当前SQLite连接的约束/运行设置
        db.execute("PRAGMA foreign_keys=ON")
        # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
        try:
            # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
            yield db
            # 提交当前连接尚未提交的修改，使其持久保存
            db.commit()
        except BaseException:
            # 撤回本次事务未完成的修改，避免半成品数据
            db.rollback()
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise
        finally:
            # 关闭资源，释放连接或文件占用
            db.close()

    # 为一次操作分配唯一记录ID，保存状态、耗时和payload；这是排错证据，不是模型准确率。
    def trace(self, project, session, status, start, payload):
        # 保存trace_id：本次执行记录的唯一编号，供页面和日志关联排错。
        trace_id = uuid.uuid4().hex
        # 进入资源上下文：self.db()；离开时按管理器约定提交/回滚或释放资源
        with self.db() as db:
            # 写入新记录，唯一约束负责拒绝冲突或按SQL规则复用
            db.execute("INSERT INTO traces VALUES(?,?,?,?,?,?,?)", (
                trace_id, project, session, time.time(), status,
                round((time.perf_counter() - start) * 1000, 2), json.dumps(payload, ensure_ascii=False)))
        # 将读取trace_id返回调用方，后续由上一层继续处理
        return trace_id


# 给本地检索构造词项：英文数字串小写化，中文取单字和连续双字；不是模型tokenizer。
def tokens(text):
    # 将统一为小写，避免大小写导致匹配不一致保存到text
    text = text.lower()
    # 将调用re.findall取得返回值保存到words
    words = re.findall(r"[a-z0-9_]+", text)
    # 依次遍历re.findall('[\\u4e00-\\u9fff]+', text)，当前项保存为run
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        # 调用words.extend取得返回值
        words.extend(run)
        # 调用words.extend取得返回值
        words.extend(run[i:i + 2] for i in range(len(run) - 1))
    # 将读取words返回调用方，后续由上一层继续处理
    return words


# 外部模型适配器：业务只调用embed/chat等方法，网络请求细节集中在此。
class Provider:
    # 每次业务操作使用独立事件列表，便于把该次接口用量归到对应trace。
    def __init__(self, config):
        # 把读取config保存为实例属性self.config，供该对象的其他方法使用
        self.config = config
        # 把创建有序列表，先置空再逐项加入保存为实例属性self.events，供该对象的其他方法使用
        self.events = []

    # 发起一次模型HTTP调用并记录耗时/usage；失败直接上报，不偷偷自动重试。
    def request(self, path, payload):
        # 仅当条件成立时执行下一分支：not self.config.api_key
        if not self.config.api_key:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("live模式未配置DASHSCOPE_API_KEY", 503)
        # 保存单调计时起点；后续用时间差计算本次操作耗时，不受系统时钟校准影响。
        start = time.perf_counter()
        # 保存event：一次模型调用或流事件的数据，用于记录状态/用量/增量。
        event = {"operation": path, "model": payload.get("model"), "status": "failed"}
        # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
        try:
            # 保存response：接口或模型响应；随后还需检查HTTP状态及响应结构。
            response = requests.post(self.config.base_url.rstrip("/") + "/" + path,
                                     headers={"Authorization": "Bearer " + self.config.api_key},
                                     json=payload, timeout=(10, 90))
            # 检查HTTP是否失败，失败时停止本次业务而非继续当作正常结果
            if response.status_code >= 400:
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise AppError("模型接口失败，HTTP " + str(response.status_code) + "；未自动重试", 502)
            # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
            result = response.json()
            # 仅当条件成立时执行下一分支：not isinstance(result, dict)
            if not isinstance(result, dict):
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise ValueError("invalid response")
            # 更新event的相关字段，保留其他已有字段
            event.update(status="completed", usage=result.get("usage"))
            # 仅当条件成立时执行下一分支：result.get('choices')
            if result.get("choices"):
                # 将按键读取字段，缺少时采用给定默认值保存到event['response']
                event["response"] = result["choices"][0].get("message")
            # 将读取result返回调用方，后续由上一层继续处理
            return result
        except requests.RequestException:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("模型连接失败或超时；本次停止，未自动重试", 502) from None
        except (ValueError, KeyError, TypeError):
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("模型返回结构无效", 502) from None
        finally:
            # 将调用round取得返回值保存到event['elapsed_ms']
            event["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 2)
            # 把读取event加入self.events，保持处理顺序
            self.events.append(event)

    # 逐段读取真实模型响应；要求完整结束，异常/截断不能被记成成功答案。
    def chat_stream(self, messages):
        """读取百炼兼容接口的真实增量；未完整结束的流不得当作成功。"""
        # 仅当条件成立时执行下一分支：not self.config.api_key
        if not self.config.api_key:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("live模式未配置DASHSCOPE_API_KEY", 503)
        # 保存started：用单调时钟保存操作开始时刻，后面计算耗时。
        started = time.perf_counter()
        # 保存event：一次模型调用或流事件的数据，用于记录状态/用量/增量。
        event = {"operation": "chat/completions", "model": self.config.model,
                 "stream": True, "status": "failed"}
        # 保存response：接口或模型响应；随后还需检查HTTP状态及响应结构。
        response = None
        # 将按位置组合多个值，供解包赋值或函数返回保存到(pieces, finished, terminated)
        pieces, finished, terminated = [], False, False
        # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
        try:
            # 保存response：接口或模型响应；随后还需检查HTTP状态及响应结构。
            response = requests.post(self.config.base_url.rstrip('/') + '/chat/completions',
                headers={"Authorization": "Bearer " + self.config.api_key},
                json={"model": self.config.model, "messages": messages, "stream": True,
                      "stream_options": {"include_usage": True}, "temperature": 0, "max_tokens": 3200},
                timeout=(10, 90), stream=True)
            # 检查HTTP是否失败，失败时停止本次业务而非继续当作正常结果
            if response.status_code >= 400:
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise AppError("模型接口失败，HTTP " + str(response.status_code) + "；未自动重试", 502)
            # 依次遍历response.iter_lines(chunk_size=1)，当前项保存为line
            for line in response.iter_lines(chunk_size=1):
                # 仅当条件成立时执行下一分支：not line or not line.startswith(b'data:')
                if not line or not line.startswith(b'data:'):
                    # 跳过本次循环余下步骤，继续处理下一项
                    continue
                # 将去除字符串首尾空白保存到data
                data = line[5:].strip()
                # 仅当条件成立时执行下一分支：data == b'[DONE]'
                if data == b'[DONE]':
                    # 保存terminated：是否收到协议结束标记，与正常停止原因一起判断完整性。
                    terminated = True
                    # 退出当前循环，避免继续读取已经结束或足够的数据
                    break
                # 保存frame：从一条完整SSE数据解析出的JSON对象，不是任意网络字节块。
                frame = json.loads(data.decode('utf-8'))
                # 仅当条件成立时执行下一分支：frame.get('error')
                if frame.get('error'):
                    # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                    raise AppError("模型流返回错误；未自动重试", 502)
                # 仅当条件成立时执行下一分支：frame.get('usage')
                if frame.get('usage'):
                    # 将按键或下标读取frame中的内容保存到event['usage']
                    event['usage'] = frame['usage']
                # 依次遍历frame.get('choices', [])，当前项保存为choice
                for choice in frame.get('choices', []):
                    # 保存reason：模型结束原因；length等非正常停止不能当成功完成。
                    reason = choice.get('finish_reason')
                    # 检查模型结束原因，区分正常停止与截断等未完成情况
                    if reason is not None:
                        # 检查模型结束原因，区分正常停止与截断等未完成情况
                        if reason != 'stop':
                            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                            raise AppError("模型输出未完整结束：" + str(reason), 502)
                        # 保存finished：是否收到模型正常停止原因，防止截断被误认为结束。
                        finished = True
                    # 将按键读取字段，缺少时采用给定默认值保存到text
                    text = choice.get('delta', {}).get('content')
                    # 仅当条件成立时执行下一分支：text
                    if text:
                        # 仅当条件成立时执行下一分支：not isinstance(text, str)
                        if not isinstance(text, str):
                            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                            raise ValueError('invalid delta')
                        # 把读取text加入pieces，保持处理顺序
                        pieces.append(text)
                        # 仅当条件成立时执行下一分支：sum(map(len, pieces)) > 16000
                        if sum(map(len, pieces)) > 16000:
                            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                            raise AppError("模型回答超过长度限制", 502)
                        # 逐步把当前事件/内容交给调用方，恢复迭代后才继续执行；不等于新增模型请求
                        yield text
            # 仅当条件成立时执行下一分支：not terminated or not finished
            if not terminated or not finished:
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise AppError("模型流中断，回答未完成；未自动重试", 502)
            # 更新event的相关字段，保留其他已有字段
            event.update(status='completed', response={'role': 'assistant', 'content': ''.join(pieces)})
        except GeneratorExit:
            # 将'cancelled'保存到event['status']
            event['status'] = 'cancelled'
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise
        except requests.RequestException:
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("模型连接失败或超时；本次停止，未自动重试", 502) from None
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("模型流返回结构无效", 502) from None
        finally:
            # 仅当条件成立时执行下一分支：response is not None
            if response is not None:
                # 关闭资源，释放连接或文件占用
                response.close()
            # 将调用round取得返回值保存到event['elapsed_ms']
            event['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 2)
            # 把读取event加入self.events，保持处理顺序
            self.events.append(event)

    # 将输入文本列表按顺序变成向量；demo用哈希替身，live分批请求并检查数量和维度。
    def embed(self, texts):
        # 仅当条件成立时执行下一分支：self.config.mode == 'demo'
        if self.config.mode == "demo":
            # 保存vectors：片段向量列表；入库时需要与片段一一对应。
            vectors = []
            # 依次遍历texts，当前项保存为text
            for text in texts:
                # 保存vec：离线哈希特征数组，只用于demo流程，不是真实语义模型。
                vec = np.zeros(self.config.dimensions)
                # 依次遍历tokens(text)，当前项保存为word
                for word in tokens(text):
                    # 保存digest：内容哈希，判断重复请求内容是否被更换，不计算语义相似度。
                    digest = hashlib.sha256(word.encode()).digest()
                    # 把1按当前运算累加/合并到vec[int.from_bytes(digest[:4], 'big') % len(vec)]，保留已有值
                    vec[int.from_bytes(digest[:4], "big") % len(vec)] += 1
                # 将向量除以自身长度做归一化；零向量以1作分母防止除零，仍保持零向量。
                vec /= np.linalg.norm(vec) or 1
                # 把调用vec.tolist取得返回值加入vectors，保持处理顺序
                vectors.append(vec.tolist())
            # 把构造字典，字段包括operation/mode/usage加入self.events，保持处理顺序
            self.events.append({"operation": "embeddings", "mode": "demo_hash", "usage": None})
            # 将读取vectors返回调用方，后续由上一层继续处理
            return vectors
        # 保存values：累计各批真实Embedding结果，供片段顺序对应写入。
        values = []
        # 按输入顺序分批向量化，返回index排序后再拼接，保持片段与向量一一对应。
        # 依次遍历range(0, len(texts), 10)，当前项保存为offset
        for offset in range(0, len(texts), 10):
            # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
            result = self.request("embeddings", {"model": self.config.embedding_model,
                "input": texts[offset:offset + 10], "dimensions": self.config.dimensions})
            # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
            try:
                # 保存rows：数据库或响应中的多条记录，后续按当前任务筛选/排序。
                rows = sorted(result["data"], key=lambda item: item["index"])
                # 将遍历输入、筛选并构造列表保存到batch
                batch = [row["embedding"] for row in rows]
                # 仅当条件成立时执行下一分支：len(batch) != len(texts[offset:offset + 10])
                if len(batch) != len(texts[offset:offset + 10]):
                    # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                    raise ValueError()
                # 依次遍历batch，当前项保存为vector
                for vector in batch:
                    # 仅当条件成立时执行下一分支：len(vector) != self.config.dimensions or not np.isfinite(vector).all()
                    if len(vector) != self.config.dimensions or not np.isfinite(vector).all():
                        # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                        raise ValueError()
                # 调用values.extend取得返回值
                values.extend(batch)
            except (KeyError, TypeError, ValueError):
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise AppError("Embedding返回数量或维度无效", 502) from None
        # 将读取values返回调用方，后续由上一层继续处理
        return values

    # 一次性聊天请求，可附工具说明或JSON输出约束；响应仍需业务层继续检查。
    def chat(self, messages, tools=None, tool_choice="auto", json_mode=False):
        # 保存payload：业务结果或模型请求的结构化数据，键名属于接口约定。
        payload = {"model": self.config.model, "messages": messages, "stream": False,
                   "max_tokens": 3200, "temperature": 0}
        # 仅当条件成立时执行下一分支：tools
        if tools:
            # 更新payload的相关字段，保留其他已有字段
            payload.update(tools=tools, tool_choice=tool_choice)
        # 仅当条件成立时执行下一分支：json_mode
        if json_mode:
            # 将构造字典，字段包括type保存到payload['response_format']
            payload["response_format"] = {"type": "json_object"}
        # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
        result = self.request("chat/completions", payload)
        # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
        try:
            # 将按键或下标读取result['choices'][0]中的内容保存到message
            message = result["choices"][0]["message"]
            # 仅当条件成立时执行下一分支：message.get('role') != 'assistant'
            if message.get("role") != "assistant":
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise ValueError()
            # 将读取message返回调用方，后续由上一层继续处理
            return message
        except (KeyError, TypeError, IndexError, ValueError):
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise AppError("回答消息结构无效", 502) from None


# 约束外部文本非空且不过长，返回去除首尾空白后的字符串。
def required_text(text, limit=4000):
    # 仅当条件成立时执行下一分支：not isinstance(text, str) or not text.strip() or len(text) > limit
    if not isinstance(text, str) or not text.strip() or len(text) > limit:
        # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
        raise AppError("请输入非空文本，长度不超过" + str(limit))
    # 将去除字符串首尾空白返回调用方，后续由上一层继续处理
    return text.strip()


# 模型结构化输出仍需解析和校验；只接受JSON对象，不执行模型生成的代码。
def parse_json(text):
    # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
    try:
        # 将把JSON字符串解析成Python数据保存到value
        value = json.loads(text)
        # 仅当条件成立时执行下一分支：not isinstance(value, dict)
        if not isinstance(value, dict):
            # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
            raise ValueError()
        # 将读取value返回调用方，后续由上一层继续处理
        return value
    except (ValueError, TypeError):
        # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
        raise AppError("模型未返回有效JSON对象；本次停止", 502) from None
