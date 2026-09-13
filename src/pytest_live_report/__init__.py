# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : __init__.py
# @Software: VSCode
# @Description: pytest-live-report 包入口与公开别名

"""pytest-live-report: 边跑边写的 pytest HTML 报告

测试用例里只需要 `from pytest_live_report import report`, 然后调 `report.log()`.
插件本身由 `pyproject.toml` 里的 pytest11 entry point 自动加载, 用户不用配 conftest.
"""

# ------------ this package ------------
from ._report import report

__version__ = "0.1.0"

# 字母序, 只列公开名字
__all__ = [
    "__version__",
    "report",
]

