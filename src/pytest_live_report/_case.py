# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : _case.py
# @Software: VSCode
# @Description: 一条用例的数据模型, 不碰 HTML

"""存放一条用例的展示数据, 并提供两个解析 pytest 输出的小工具

卡片长什么样归 `_render.case`, 这个模块既不知道 HTML 也不知道 CSS 类名, 所以
钩子层与状态层都可以放心依赖它.
"""

# ------------ standard library ------------
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# ------------ constants ------------
# 用例的三种状态, 也是页面筛选按钮的三个取值
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
# pytest 给跳过原因加的前缀 (`pytest.skip("x")` 会写成 "Skipped: x"), 展示前剥掉,
# 否则卡片上会重复出现 Skipped
_SKIP_PREFIX = "Skipped: "


# region ---------------------------- 用例数据 ----------------------------
@dataclass
class CaseData:
    """一条用例的全部展示信息

    用例开始时先建好骨架 (nodeid / name / desc / started), 执行期间由 `report.*`
    往里追加日志, 收尾时钩子层再补上状态, 耗时与错误信息.
    """

    # pytest 的完整节点 id, 例如 tests/test_a.py::test_login
    nodeid: str = ""
    # 用例函数名, 作为卡片主标题
    name: str = ""
    # 用例函数的 docstring, 显示在卡片详情区的顶部; 没有就是空串
    desc: str = ""
    # passed / failed / skipped 之一
    status: str = STATUS_PASSED
    # 开始与结束时刻 (带本地时区); 取不到时是 None, 卡片上对应位置留空
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    # 三个阶段的耗时之和, 单位是秒, 已保留两位小数
    duration: float = 0.0
    # 跳过原因, 只有跳过用例非空; 已经剥掉 pytest 加的前缀
    skip_reason: str = ""
    # 错误摘要, 例如 "AssertionError: 500 != 200"; 通过用例是空串
    error: str = ""
    # 完整 traceback 原文; 通过用例是空串
    traceback: str = ""
    # 用例执行期间写下的日志行, 按调用顺序; 每项是 (时间戳, 已转义的 HTML 片段)
    logs: List[tuple] = field(default_factory=list)
    # 用例执行期间保存的截图, 按调用顺序; 每项是 (data URI, 图注或空串)
    shots: List[tuple] = field(default_factory=list)

    def json_record(self) -> dict:
        """取这条用例的机器可读记录, 供消费脚本提取执行信息

        这里只产出数据, 拼成页内 `<script>` 标签归 `_render.case`. 字段是公开契约
        (`v` 是版本号): 加字段可以, 改字段名就是破坏性变更.

        Returns:
            dict: 含 nodeid / name / status / duration / 起止时间 / 错误与跳过原因

        Example:
            >>> CaseData(nodeid="t.py::test_x", status="passed").json_record()["status"]
            'passed'
        """
        return {
            "v": 1,
            "nodeid": self.nodeid,
            "name": self.name,
            "desc": self.desc,
            "status": self.status,
            "duration": self.duration,
            "started": "" if self.started is None else self.started.isoformat(),
            "finished": "" if self.finished is None else self.finished.isoformat(),
            "error": self.error,
            "traceback": self.traceback,
            "skip_reason": self.skip_reason,
        }
# endregion ---------------------------- 用例数据 ----------------------------


# region ---------------------------- 结果解析 ----------------------------
def strip_skip_prefix(reason: str) -> str:
    """去掉 pytest 给跳过原因加的 `Skipped: ` 前缀

    Args:
        reason (str): pytest 给的原始跳过原因

    Returns:
        str: 去掉前缀的原因; 本来就没有前缀时原样返回

    Example:
        >>> strip_skip_prefix("Skipped: service unavailable")
        'service unavailable'
        >>> strip_skip_prefix("plain reason")
        'plain reason'
    """
    if reason.startswith(_SKIP_PREFIX):
        return reason[len(_SKIP_PREFIX):]
    return reason


def param_suffix(nodeid: str) -> str:
    """取 nodeid 末尾的参数化后缀, 例如 `test_login[admin]` 里的 `[admin]`

    Args:
        nodeid (str): 用例的完整节点 id

    Returns:
        str: 形如 `[admin]` 的后缀; nodeid 里没有方括号段时是空串

    Example:
        >>> param_suffix("tests/test_a.py::test_login[admin]")
        '[admin]'
        >>> param_suffix("tests/test_a.py::test_login")
        ''
    """
    tail = nodeid.rsplit("::", 1)[-1]
    start = tail.find("[")
    return tail[start:] if start != -1 else ""
# endregion ---------------------------- 结果解析 ----------------------------
