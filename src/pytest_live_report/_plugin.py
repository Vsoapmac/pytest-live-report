# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : _plugin.py
# @Software: VSCode
# @Description: pytest 钩子函数的唯一汇总处, 负责把报告功能挂进 pytest 会话

"""把报告功能挂进 pytest 会话的全部钩子

第一条约定: 没配 `--live-report-path` 时钩子立刻返回, 报告完全不启动, 既不写文件
也不改终端输出.

第二条约定: 报告自己的问题绝不能弄挂用户的测试. 路径不可写这类情况只打一条终端
告警并关掉报告, 测试照常跑完.
"""

# ------------ standard library ------------
import inspect
import platform
import warnings
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Optional,
)

# ------------ third party ------------
import pytest

# ------------ this package ------------
from . import _render
from . import _store
from ._case import (
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    CaseData,
    strip_skip_prefix,
)
from ._render.case import render_case
from ._writer import ReportFile

# ------------ constants ------------
# 命令行选项名, 注册与取值都用它. pytest 会把连字符的选项名转成下划线, 所以
# 这里的取值是 `live_report_path`
OPTION_PATH = "live_report_path"
OPTION_TITLE = "live_report_title"
# 没传 --live-report-title 时用的标题; 标题永远非空, 所以判断报告开没开只能看路径
DEFAULT_REPORT_TITLE = "pytest report"
# 三个阶段按执行顺序排列, 找失败原因时也按这个顺序: setup 挂了后面的阶段不会跑,
# 所以最靠前的那份异常报告才是真正的失败原因
PHASE_ORDER = ("setup", "call", "teardown")
# 卡片 HTML 挂在测试报告上的属性名. xdist 的 worker 把卡片挂在这里, 随报告一起
# 传回控制器
ATTR_CARD = "_live_report_card"


# region ---------------------------- 私有函数 ----------------------------
def _report_path(config: pytest.Config) -> Optional[Path]:
    """解析报告文件路径, 相对路径按 rootdir 展开

    Args:
        config (pytest.Config): 本次会话的配置对象

    Returns:
        Optional[Path]: 报告文件的绝对路径; 没有配置选项时是 None, 调用方据此
            判断报告功能是否启用
    """
    raw = config.getoption(OPTION_PATH)
    if not raw:
        return None
    path = Path(raw)
    # 相对 rootdir 而不是当前工作目录: 在任何子目录里敲 pytest, 报告都落在
    # 同一个地方, 本地与 CI 的行为才一致
    return path if path.is_absolute() else config.rootpath / path


def _is_worker(config: pytest.Config) -> bool:
    """当前进程是不是 xdist 的 worker

    xdist 的 worker 会带上 `config.workerinput`, 单进程运行或没装 xdist 时没有
    这个属性.

    Args:
        config (pytest.Config): 本次会话的配置对象

    Returns:
        bool: True 表示这是 worker, 报告文件归控制器独占, 它一个字节都不该写
    """
    return hasattr(config, "workerinput")


def _env_info(config: pytest.Config) -> dict:
    """收集写进报告页头的环境信息

    Args:
        config (pytest.Config): 本次会话的配置对象

    Returns:
        dict: pytest / python / platform / rootdir 四项, 渲染时拼成一行
    """
    return {
        "pytest": pytest.__version__,
        "python": platform.python_version(),
        "platform": platform.system().lower(),
        "rootdir": str(config.rootpath),
    }


def _meta_line(env: dict) -> str:
    """把环境信息拼成页头里的一行

    Args:
        env (dict): `_env_info()` 的返回值

    Returns:
        str: 形如 `pytest=9.1.1 · python=3.12.12 · windows` 的一行文本
    """
    return " · ".join(f"{key}={value}" for key, value in env.items() if value)


def _run_info(config: pytest.Config, exitstatus: int, started: datetime) -> dict:
    """组装运行清单, 交给 `_render.run_manifest()` 渲染

    Args:
        config (pytest.Config): 本次会话的配置对象
        exitstatus (int): pytest 的退出码
        started (datetime): 会话开始时刻

    Returns:
        dict: 退出码, 计数, 起止时间与环境信息
    """
    return {
        "exitstatus": int(exitstatus),
        "counts": _store.get_counts(),
        "started": started.isoformat(),
        "ended": datetime.now().astimezone().isoformat(),
        "env": _env_info(config),
    }


def _notify(config: pytest.Config, message: str) -> None:
    """把一行普通提示写到终端

    Args:
        config (pytest.Config): 本次会话的配置对象
        message (str): 提示文案
    """
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(message)


def _warn_user(config: pytest.Config, message: str) -> None:
    """把报告自身的告警显示给用户, 不让测试因此中断

    优先写终端而不是 `warnings.warn`: 用户设了 `-W error` 时告警会被当成异常抛出,
    报告的问题反而把会话弄挂. 终端拿不到时再退回 `warnings.warn`.

    Args:
        config (pytest.Config): 本次会话的配置对象
        message (str): 告警文案, 调用方自带 `pytest-live-report: ` 前缀
    """
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(message)
        return
    try:
        warnings.warn(message)
    except Exception:  # 告警发不出去不算失败, 绝不能往外传
        pass


def _write_card(case: CaseData, report: Optional[Any] = None) -> None:
    """把一条用例的卡片写进报告, 并给状态计数加一

    控制器直接写文件; worker 把渲染好的 HTML 挂到测试报告上, 随报告一起传回控制器,
    自己一个字节都不写 -- 多个 worker 同时写同一个文件会互相覆盖.

    Args:
        case (CaseData): 已经填好的用例数据
        report (Optional[Any]): worker 侧用来传回卡片的那份 teardown 报告; 控制器传 None
    """
    # ====================================================================================================
    # 这个分支决定报告能不能拿到全部用例: worker 一旦自己写文件, 几份内容会互相覆盖;
    # 控制器一旦忘了从报告上取卡片, 这些用例在报告里就凭空消失. 取卡片见
    # `pytest_runtest_logreport`, 那边取完立刻删属性, 免得同一张卡片被写两次.
    # ====================================================================================================
    if report is not None:
        # 计数也在 worker 侧算好带过去: 控制器上没有这条用例的对象, 拿不到它的状态
        setattr(report, ATTR_CARD, {"html": render_case(case), "status": case.status})
        return

    config = _store.get_config()
    report_file = _store.get_report_file()
    if config is None or report_file is None:
        return
    try:
        report_file.write(render_case(case))
    except (OSError, RuntimeError) as exc:
        _warn_user(config, f"pytest-live-report: cannot write a case card ({exc})")
        return
    _store.count(case.status)


def _write_payload(config: pytest.Config, payload: dict) -> None:
    """把 worker 传回来的卡片写进报告, 并给状态计数加一

    Args:
        config (pytest.Config): 本次会话的配置对象
        payload (dict): worker 传回的卡片, 含 `html` (卡片 HTML) 与 `status` (状态名)
    """
    report_file = _store.get_report_file()
    if report_file is None:
        return
    try:
        report_file.write(payload["html"])
    except (OSError, RuntimeError) as exc:
        _warn_user(config, f"pytest-live-report: cannot write a case card ({exc})")
        return
    _store.count(payload["status"])


def _case_desc(item: pytest.Item) -> str:
    """取用例描述, 也就是测试函数自己的 docstring

    Args:
        item (pytest.Item): 当前用例

    Returns:
        str: 清掉多余缩进的 docstring 正文; 没有 docstring 时是空串
    """
    function = getattr(item, "function", None)
    raw = getattr(function, "__doc__", "") or ""
    # 必须走 cleandoc: docstring 原文带缩进, 直接渲染会是一层层阶梯
    return inspect.cleandoc(raw)


def _collect_phase(report: Any) -> dict:
    """把这次的阶段报告记下来, 并取回这条用例已经收集到的全部阶段

    报告上只带 `report.nodeid`, 所以靠 nodeid 找到同一条用例的记录.

    Args:
        report (Any): 刚收到的阶段报告

    Returns:
        dict: 阶段名 -> 报告; 记录刚建起来时只有本次这一份
    """
    nodeid = getattr(report, "nodeid", "")
    record = _store.ensure_phase(nodeid)
    record["reports"][report.when] = report
    return record["reports"]


def _case_duration(reports: dict) -> float:
    """取用例总耗时, 保留两位小数

    三个阶段要加起来: 每份报告只带自己那一阶段的耗时, 单看 teardown 就只有几百微秒.
    先加总再取整, 免得三次取整的误差累加到一起.

    Args:
        reports (dict): 用例的三个阶段报告

    Returns:
        float: 秒数, 已保留两位小数
    """
    durations = (float(getattr(report, "duration", 0.0) or 0.0) for report in reports.values())
    return round(sum(durations), 2)


def _case_traceback(reports: dict) -> str:
    """取 pytest 排版好的完整 traceback 原文

    Args:
        reports (dict): 用例的三个阶段报告

    Returns:
        str: `longreprtext` 原文; 没有失败阶段时是空串
    """
    failed = _pick_failed_report(reports)
    return "" if failed is None else (getattr(failed, "longreprtext", "") or "")


def _case_error(reports: dict) -> str:
    """取错误摘要, 也就是异常类型与它的消息

    Args:
        reports (dict): 用例的三个阶段报告

    Returns:
        str: 形如 "AssertionError: 500 != 200" 的一行; 没有异常时是空串
    """
    failed = _pick_failed_report(reports)
    if failed is None:
        return ""
    crash = getattr(getattr(failed, "longrepr", None), "reprcrash", None)
    if crash is None:
        return ""
    # 裸 assert 只有消息没有类型名, 这时 reprcrash.message 就是整行摘要
    return str(getattr(crash, "message", "") or "")


def _pick_failed_report(reports: dict) -> Optional[Any]:
    """挑出第一个失败的阶段报告

    Args:
        reports (dict): 用例的三个阶段报告

    Returns:
        Optional[Any]: setup / call / teardown 里第一份异常的; 全都正常时是 None
    """
    for when in PHASE_ORDER:
        report = reports.get(when)
        if report is not None and not _is_passed(report):
            return report
    return None


def _is_passed(report: Any) -> bool:
    """这份阶段报告是不是正常通过或正常跳过

    不用 `report.failed` 判断: 第三方插件可能给出别的 outcome (例如 pytest-rerunfailures
    的 "rerun"), 用 `failed` 判断会把它们当成通过, 失败的用例被画成绿卡.

    Args:
        report (Any): 一个阶段的测试报告

    Returns:
        bool: True 表示这份报告不需要按失败处理
    """
    return getattr(report, "outcome", None) in (STATUS_PASSED, STATUS_SKIPPED)


def _case_skip_reason(reports: dict) -> str:
    """取跳过原因

    跳过原因在 `longrepr` 三元组的第三项里, 形如
    `("path/to/test.py", 12, "Skipped: why")`; 直接 `str(longrepr)` 会把整个元组
    连引号一起渲染进报告.

    Args:
        reports (dict): 用例的三个阶段报告

    Returns:
        str: 去掉 `Skipped: ` 前缀的原因; 不是跳过用例时是空串
    """
    for when in PHASE_ORDER:
        report = reports.get(when)
        if report is None or getattr(report, "outcome", None) != STATUS_SKIPPED:
            continue
        longrepr = getattr(report, "longrepr", None)
        if isinstance(longrepr, tuple) and len(longrepr) >= 3:
            return strip_skip_prefix(str(longrepr[2]))
    return ""


def _case_status(reports: dict) -> str:
    """把三个阶段的报告合并成一个用例状态

    三份都要看: teardown 报告永远说自己 passed, 只看它会把失败的用例写成绿色, 而
    只看 call 又会漏掉 fixture 报错与 teardown 抛错.

    Args:
        reports (dict): 用例的三个阶段报告

    Returns:
        str: passed / failed / skipped 之一; 认不出的 outcome 一律按 failed
    """
    if _pick_failed_report(reports) is not None:
        return STATUS_FAILED
    for when in PHASE_ORDER:
        report = reports.get(when)
        if report is not None and getattr(report, "outcome", None) == STATUS_SKIPPED:
            return STATUS_SKIPPED
    return STATUS_PASSED
# endregion ---------------------------- 私有函数 ----------------------------


# region ---------------------------- 钩子函数 ----------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    """注册报告相关的命令行选项

    Args:
        parser (pytest.Parser): pytest 传进来的参数解析器
    """
    group = parser.getgroup("live-report", "pytest-live-report")
    group.addoption(
        "--live-report-path",
        action="store",
        default=None,
        metavar="PATH",
        help="Output report path, for example: output.html.",
    )
    group.addoption(
        "--live-report-title",
        action="store",
        default=DEFAULT_REPORT_TITLE,
        metavar="TITLE",
        help="Report title",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """会话开始: 打开报告文件并写页头

    Args:
        session (pytest.Session): 本次会话对象, `session.config` 才是配置
    """
    config = session.config
    path = _report_path(config)
    if path is None:
        return

    _store.reset()
    # ====================================================================================================
    # worker 不能开报告文件: 文件归控制器独占. 它照常登记配置与开始时刻, 只是把 bypass
    # 置上, 那样内容照收, 但一个字节都不写文件 -- 谁多开一次文件, 都会把控制器已经写好的
    # 内容覆盖掉.
    # ====================================================================================================
    if _is_worker(config):
        # 内容照收, 但报告文件不归它管: 卡片交给控制器写
        _store.set_config(config, bypass=True)
        _store.set_started(datetime.now().astimezone())
        return
    report_file = ReportFile(path)
    try:
        report_file.open()
    except OSError as exc:
        # 路径不可写只发一条告警: 报告插件不能弄挂用户的测试
        _warn_user(config, f"pytest-live-report: cannot write the report ({exc})")
        return

    title = config.getoption(OPTION_TITLE)
    head = _render.page_head(title, _meta_line(_env_info(config)))
    try:
        report_file.write(head)
    except (OSError, RuntimeError) as exc:
        _warn_user(config, f"pytest-live-report: cannot write the report ({exc})")
        return

    _store.set_report_file(report_file)
    _store.set_config(config)
    _store.set_started(datetime.now().astimezone())
    _notify(config, f"[live-report] report will be written to {report_file.path}")


def pytest_itemcollected(item: pytest.Item) -> None:
    """用例被收集时先把阶段记录建起来, 免得收尾时找不到

    Args:
        item (pytest.Item): 刚被收集到的用例
    """
    _store.ensure_phase(item.nodeid)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item):
    """包住一条用例的完整生命周期: 记下开始时刻与描述, 收尾时清掉"当前用例"

    Args:
        item (pytest.Item): 当前用例

    Returns:
        Any: 下游钩子的返回值, 原样交回 pytest
    """
    record = _store.ensure_phase(item.nodeid)
    record["started"] = datetime.now().astimezone()
    record["desc"] = _case_desc(item)
    # 用例期间就得有"当前用例", 否则 report.log() 没有地方落内容
    _store.set_current(
        CaseData(
            nodeid=item.nodeid,
            name=item.name,
            desc=record["desc"],
            started=record["started"],
        )
    )
    try:
        result = yield
    finally:
        _store.set_current(None)
    return result


# ====================================================================================================
# tryfirst 不能省: xdist 的 worker 也实现这个钩子, 它在那里就把报告序列化发回控制器.
# 晚于它执行的话卡片还没挂到报告上, 这些用例在报告里会凭空消失.
# ====================================================================================================
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report: Any) -> None:
    """收集阶段报告, 到 teardown 那一次把整条用例写成卡片

    这个钩子每条用例被调三次 (setup / call / teardown), 三份报告缺一不可: 只看 call
    会漏掉 fixture 报错与 teardown 抛错, 只看 teardown 则会把失败的用例写成绿色.

    Args:
        report (Any): pytest 的测试报告; 只有 teardown 那份会触发写盘
    """
    config = _store.get_config()
    if config is None:
        return

    # 控制器侧: worker 传回来的卡片在这里落盘. 取完立刻删属性, 免得同一张卡片被写两次
    payload = getattr(report, ATTR_CARD, None)
    if payload is not None:
        delattr(report, ATTR_CARD)
        _write_payload(config, payload)
        return

    # 控制器也会收到 worker 的报告, 但它自己不跑用例, 手上没有当前用例: 再往下走
    # 只会写出一堆空白卡
    current = _store.get_current()
    if current is None:
        return

    nodeid = getattr(report, "nodeid", "")
    reports = _collect_phase(report)
    if report.when != "teardown":
        return

    status = _case_status(reports)
    # 复用用例开始时建好的那份数据: 日志已经在它上面了, 重建会把日志丢掉
    case = current
    case.status = status
    case.finished = datetime.now().astimezone()
    case.duration = _case_duration(reports)
    if status == STATUS_FAILED:
        case.traceback = _case_traceback(reports)
        case.error = _case_error(reports)
    if status == STATUS_SKIPPED:
        case.skip_reason = _case_skip_reason(reports)
    # 阶段记录用完就扔: 用例规模可能上万, 攒着不放会一路吃内存
    _store.drop_phase(nodeid)
    # worker 把卡片挂到报告上传回控制器; 控制器自己写文件
    _write_card(case, report if _store.is_bypassed() else None)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """会话结束: 写页尾与运行清单, 然后关闭报告文件

    Args:
        session (pytest.Session): 本次会话对象, `session.config` 才是配置
        exitstatus (int): pytest 的退出码, 原样写进运行清单
    """
    config = session.config
    report_file = _store.get_report_file()
    if report_file is None:
        return
    started = _store.get_started()
    try:
        report_file.finish(_render.page_tail(_run_info(config, exitstatus, started)))
    except (OSError, RuntimeError) as exc:
        _warn_user(config, f"pytest-live-report: cannot finish the report ({exc})")
        return
    _store.set_report_file(None)
    _notify(config, f"[live-report] report finished: {report_file.path}")


def pytest_unconfigure(config: pytest.Config) -> None:
    """会话收尾兜底: `sessionfinish` 没跑到时也要把文件关掉

    不补页尾, 也不写运行清单: 半截报告正好说明这次没跑完. 正常流程下文件已经关掉,
    这里什么都不做.

    Args:
        config (pytest.Config): 本次会话的配置对象
    """
    report_file = _store.get_report_file()
    if report_file is not None:
        report_file.close()
        _store.set_report_file(None)
# endregion ---------------------------- 钩子函数 ----------------------------
