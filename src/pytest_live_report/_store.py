# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : _store.py
# @Software: VSCode
# @Description: 报告系统的进程级状态, 供钩子层与 live_report API 共用

"""存放报告用到的全部模块级状态

`live_report.log()` 这类公开接口拿不到 `pytest.Config`, 却必须知道当前在跑哪条用例,
所以这些状态只能放在模块级变量里.

这里存的是: 报告文件句柄, 会话配置, 当前用例, 会话开始时刻与状态计数, 以及每条
用例的阶段记录.

嵌套会话 (在测试里再调一次 `pytest.main()`) 会互相覆盖这些变量, 目前不做处理.
"""

# ------------ standard library ------------
from datetime import datetime
from typing import Optional

# ------------ third party ------------
import pytest

# ------------ this package ------------
from ._case import CaseData
from ._writer import ReportFile

# ------------ constants ------------
# 本进程正在使用的报告文件; 报告没启用时是 None
_report_file: Optional[ReportFile] = None
# 当前正在跑的用例; 不在用例里时是 None
_current: Optional[CaseData] = None
# 本次会话的配置对象; 只拿到 live_report 的钩子靠它取配置, 同时它是"报告有没有启用"的
# 开关: 是 None 就说明这次会话没开报告
_config: Optional[pytest.Config] = None
# 本次会话是不是 xdist 的 worker: 它照常收集内容, 但不写报告文件
_is_bypassed: bool = False
# 本次会话的开始时刻, 收尾时写进运行清单
_started: Optional[datetime] = None
# 本次会话的计数: 状态名 -> 条数
_counts: dict = {}
# 正在执行的用例: nodeid -> {"started": 开始时刻, "desc": 用例描述,
# "reports": {阶段: 报告}}. pytest 的报告上只带 nodeid, 跨钩子只能靠它对上号.
# 一个进程一次只跑一条用例, 所以表里通常只有一项, 卡片写完立刻删掉.
_phases: dict = {}


# region ---------------------------- 报告文件 ----------------------------
def set_report_file(report_file: Optional[ReportFile]) -> None:
    """记下本次会话的报告文件, 传 None 表示报告被关掉"""
    global _report_file
    _report_file = report_file


def get_report_file() -> Optional[ReportFile]:
    """取本进程正在使用的报告文件, 报告没启用时返回 None"""
    return _report_file
# endregion ---------------------------- 报告文件 ----------------------------


# region ---------------------------- 会话配置 ----------------------------
def set_config(config: pytest.Config, bypass: bool = False) -> None:
    """记下本次会话的配置并启用报告

    Args:
        config (pytest.Config): 本次会话的配置对象
        bypass (bool): True 表示这是 xdist 的 worker, 只收集内容不写文件
    """
    global _config, _is_bypassed
    _config = config
    _is_bypassed = bypass


def get_config() -> Optional[pytest.Config]:
    """取本次会话的配置对象, 报告没启用时返回 None"""
    return _config


def is_bypassed() -> bool:
    """本次会话是不是 xdist 的 worker, 是则报告文件由控制器写"""
    return _is_bypassed
# endregion ---------------------------- 会话配置 ----------------------------


# region ---------------------------- 用例阶段记录 ----------------------------
def ensure_phase(nodeid: str) -> dict:
    """取一条用例的阶段记录, 没有就新建一条

    Args:
        nodeid (str): 用例的完整节点 id

    Returns:
        dict: 该用例的记录, 含开始时刻, 用例描述与三个阶段报告
    """
    record = _phases.get(nodeid)
    if record is None:
        record = {"started": None, "desc": "", "reports": {}}
        _phases[nodeid] = record
    return record


def get_phase(nodeid: str) -> Optional[dict]:
    """取一条用例的阶段记录, 还没建过时返回 None"""
    return _phases.get(nodeid)


def drop_phase(nodeid: str) -> None:
    """清掉一条用例的阶段记录, 卡片写完后立即调用"""
    _phases.pop(nodeid, None)
# endregion ---------------------------- 用例阶段记录 ----------------------------


# region ---------------------------- 会话时刻 ----------------------------
def set_started(moment: datetime) -> None:
    """记下会话开始时刻"""
    global _started
    _started = moment


def get_started() -> datetime:
    """取会话开始时刻, 还没有值时退回当前时刻"""
    return _started if _started is not None else datetime.now().astimezone()
# endregion ---------------------------- 会话时刻 ----------------------------


# region ---------------------------- 当前用例 ----------------------------
def set_current(case: Optional[CaseData]) -> None:
    """把一条用例设为当前用例, 公开接口写的内容都归它; 传 None 表示用例已结束"""
    global _current
    _current = case


def get_current() -> Optional[CaseData]:
    """取当前正在跑的用例, 不在用例里时返回 None"""
    return _current
# endregion ---------------------------- 当前用例 ----------------------------


# region ---------------------------- 计数 ----------------------------
def count(status: str) -> None:
    """给某个状态的计数加一, 状态只会是 passed / failed / skipped 之一"""
    _counts[status] = _counts.get(status, 0) + 1


def get_counts() -> dict:
    """取会话结束时写进运行清单的计数

    Returns:
        dict: total / passed / failed / skipped 四项, 缺的补 0
    """
    return {
        "total": sum(_counts.values()),
        "passed": _counts.get("passed", 0),
        "failed": _counts.get("failed", 0),
        "skipped": _counts.get("skipped", 0),
    }
# endregion ---------------------------- 计数 ----------------------------


# region ---------------------------- 会话生命周期 ----------------------------
def reset() -> None:
    """会话开始时清空全部状态, 免得上一次会话的数据留到这一次

    新增状态时必须同步加进这个函数, 否则会跨会话残留.
    """
    global _report_file, _current, _config, _is_bypassed, _started, _counts, _phases
    _report_file = None
    _current = None
    _config = None
    _is_bypassed = False
    _started = None
    _counts = {}
    _phases = {}
# endregion ---------------------------- 会话生命周期 ----------------------------
