# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : __init__.py
# @Software: VSCode
# @Description: pytest-live-report 包入口与公开别名

"""pytest-live-report: 边跑边写的 pytest HTML 报告

测试用例里只需要 `from pytest_live_report import live_report`, 然后调 `live_report.log()`.
插件本身由 `pyproject.toml` 里的 pytest11 entry point 自动加载, 用户不用配 conftest.
分析已经生成的报告用 `read_report("report.html")`, 一次拿到运行清单、状态统计与全部用例记录.
"""

# ------------ this package ------------
from ._report import live_report
from ._reader import read_report

__version__ = "0.3.0"

# 字母序, 只列公开名字
__all__ = [
    "__version__",
    "live_report",
    "read_report",
]
