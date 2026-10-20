# 交付回归入口：默认使用临时库跑离线测试并保存报告，避免污染运行数据。
# --live只针对自编样例真实调用；自动化中的确认是测试输入，不代表真实用户业务确认。

# 导入argparse：声明命令行模式、端口、文件等选项
import argparse
# 导入json：在字符串与字典/列表间转换JSON数据
import json
# 导入subprocess：使用独立进程执行回归或恢复验证
import subprocess
# 导入sys：访问解释器路径和导入搜索路径
import sys
# 导入tempfile：隔离临时测试目录，避免写运行中的业务库
import tempfile
# 导入time：取得时间戳和单调计时，保存创建时间与计算耗时
import time
# 导入uuid：生成文档、片段、任务、请求或记录的唯一标识
import uuid
# 从pathlib导入Path，用对象处理路径而非手拼字符串
from pathlib import Path

# 从suite.app导入create_app，供下方业务或测试调用
from suite.app import create_app
# 从suite.core导入Config/ROOT，供下方业务或测试调用
from suite.core import Config, ROOT

# 将'rag'保存到PROJECT
PROJECT = 'rag'


# 建立唯一报告目录，先跑回归，再用临时库检查完整链路。
def main():
    # 保存parser：命令行参数解析器，后面声明可接受的选项。
    parser = argparse.ArgumentParser()
    # 声明一个命令行选项及其默认值/限制，后面统一解析
    parser.add_argument('--live', action='store_true', help='使用本项目自编样例进行真实调用，有接口消耗')
    # 保存args：经解析的命令行参数或工具JSON参数，取决于当前入口。
    args = parser.parse_args()
    # 保存output：本次验证报告目录，使用唯一名称避免覆盖旧证据。
    output = ROOT / 'evaluation' / ('standalone_' + uuid.uuid4().hex[:12])
    # 按需建立目录，已存在时按给定选项处理
    output.mkdir(parents=True)
    # 保存report：本批验证结果，成功或异常路径都会保存。
    report = {'project': PROJECT, 'mode': 'live' if args.live else 'demo', 'started': time.time()}
    # 在成功或异常路径都保存本批回归报告，避免失败过程只留在控制台。
    def save():
        # 保存当前结果到指定文件，不修改原始输入文件
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # 把可能失败的步骤放入受控区域，由except报告错误、finally处理必要清理
    try:
        # 仅当条件成立时执行下一分支：not args.live
        if not args.live:
            # 进入资源上下文：tempfile.TemporaryDirectory(prefix='independent-check-')；离开时按管理器约定提交/回滚或释放资源
            with tempfile.TemporaryDirectory(prefix='independent-check-') as temp:
                # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
                result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pytest', 'tests', '-q', '--tb=short',
                    '-p', 'no:cacheprovider', '--basetemp', str(Path(temp) / 'pytest')], cwd=ROOT,
                    capture_output=True, text=True, encoding='utf-8')
            # 保存当前结果到指定文件，不修改原始输入文件
            (output / 'pytest.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
            # 将读取result.returncode保存到report['pytest_exit_code']
            report['pytest_exit_code'] = result.returncode
            # 仅当条件成立时执行下一分支：result.returncode
            if result.returncode:
                # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
                raise RuntimeError('自动化检查未通过，见本批pytest.txt')
        # 进入资源上下文：tempfile.TemporaryDirectory()；离开时按管理器约定提交/回滚或释放资源
        with tempfile.TemporaryDirectory() as temp:
            # 保存config：本次运行配置，包含数据目录、模型名和接口设置。
            config = Config.env()
            # 将按位置组合多个值，供解包赋值或函数返回保存到(config.data, config.mode)
            config.data, config.mode = Path(temp), 'live' if args.live else 'demo'
            # 保存app：当前FastAPI应用；测试可为它注入独立配置和模型替身。
            app = create_app(config)
            # 依次遍历(ROOT / 'samples').glob('*.md')，当前项保存为path
            for path in (ROOT / 'samples').glob('*.md'):
                # 按当前配置解析并建立该文档的检索索引
                app.state.rag.ingest(path.name, path.read_bytes())
            # 仅当条件成立时执行下一分支：PROJECT == 'rag'
            if PROJECT == 'rag':
                # 仅当条件成立时执行下一分支：args.live
                if args.live:
                    # 将遍历输入、筛选并构造列表保存到report['answers']
                    report['answers'] = [app.state.rag.answer(q) for q in ('while循环为什么更新变量？', '课程学费多少钱？')]
                else:
                    # 将按键或下标读取json.loads((ROOT / 'evaluation/rag_cases.json').read_text(encoding='utf-8'))中的内容保存到cases
                    cases = json.loads((ROOT / 'evaluation/rag_cases.json').read_text(encoding='utf-8'))['cases']
                    # 将创建有序列表，先置空再逐项加入保存到comparison
                    comparison = []
                    # 依次遍历('keyword', 'vector', 'hybrid', 'hybrid_rerank')，当前项保存为strategy
                    for strategy in ('keyword', 'vector', 'hybrid', 'hybrid_rerank'):
                        # 保存rows：数据库或响应中的多条记录，后续按当前任务筛选/排序。
                        rows = []
                        # 依次遍历cases，当前项保存为case
                        for case in cases:
                            # 保存result：调用返回的数据；是否成功还要按当前分支继续校验。
                            result = app.state.rag.answer(case['question'], strategy)
                            # 把构造字典，字段包括hit_at_4/abstained/answer加入rows，保持处理顺序
                            rows.append({**case, 'hit_at_4': any(s['name'] == case['gold_source'] and s['section'] == case['gold_section'] for s in result['sources']) if not case['expect_abstain'] else None,
                                'abstained': result['abstained'], 'answer': result['answer']})
                        # 把构造字典，字段包括strategy/retrieval_hits/answerable_count/abstain_correct/unanswerable_count/results加入comparison，保持处理顺序
                        comparison.append({'strategy': strategy, 'retrieval_hits': sum(row['hit_at_4'] is True for row in rows),
                            'answerable_count': 30, 'abstain_correct': sum(row['expect_abstain'] and row['abstained'] for row in rows),
                            'unanswerable_count': 10, 'results': rows})
                    # 将读取comparison保存到report['comparison']
                    report['comparison'] = comparison
            else:
                # 保存agent：工具调用与工单任务业务对象。
                agent = app.state.agent
                # 保存sid：测试或当前操作使用的会话编号。
                sid = agent.session()
                # 将遍历输入、筛选并构造列表保存到report['chat']
                report['chat'] = [agent.chat(sid, text) for text in ('查询订单支付状态', 'A001', '服务P001价格是多少')]
                # 保存task：包含草稿字段、版本、状态及工单关联的任务数据。
                task = agent.draft(sid, 'standalone-check', '订单A001云服务器无法连接')
                # 将调用agent.decide取得返回值保存到confirmed
                confirmed = agent.decide(sid, task['id'], task['version'], '确认')
                # 将调用agent.decide取得返回值保存到repeated
                repeated = agent.decide(sid, task['id'], task['version'], '确认')
                # 测试断言：确认confirmed['created'] and repeated['reused'] and (confirmed['ticket']['id'] == repeated['ticket']['id'])；不满足时用例失败
                assert confirmed['created'] and repeated['reused'] and confirmed['ticket']['id'] == repeated['ticket']['id']
                # 将构造字典，字段包括input_type/task/first/repeated保存到report['task_check']
                report['task_check'] = {'input_type': '临时库自动化模拟确认', 'task': task, 'first': confirmed, 'repeated': repeated}
            # 进入资源上下文：app.state.store.db()；离开时按管理器约定提交/回滚或释放资源
            with app.state.store.db() as db:
                # 将遍历输入、筛选并构造列表保存到report['traces']
                report['traces'] = [dict(row) for row in db.execute('SELECT * FROM traces ORDER BY created')]
        # 将True保存到report['temporary_database_removed']
        report['temporary_database_removed'] = True
    except Exception as error:
        # 将调用str取得返回值保存到report['error']
        report['error'] = str(error)
        # 调用save取得返回值
        save()
        # 中止当前正常流程并抛出错误；由外层统一记录或返回失败
        raise
    # 将取得当前时间戳保存到report['finished']
    report['finished'] = time.time()
    # 调用save取得返回值
    save()
    # 把当前状态/结果打印到控制台，便于运行时核对
    print('本项目独立检查完成：', output / 'report.json')
    # 把当前状态/结果打印到控制台，便于运行时核对
    print('demo结果是离线流程验证，不代表真实模型准确率；未修改运行业务库。')


# 仅当此文件作为入口直接运行时执行下面代码，被import时不启动
if __name__ == '__main__':
    # 调用main取得返回值
    main()
