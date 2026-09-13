# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : __init__.py
# @Software: VSCode
# @Description: 所有产出 HTML 的东西都收在这个包里, 这里只做重导出

"""把一个报告页面的拼装代码收在一起, 只对外重导出函数

包内分层:
    - `html.py`:  转义与共用小工具, 纯字符串处理
    - `page.py`:  页面骨架, 页头 / 页尾 / 运行清单 / JSON 块
    - `case.py`:  单条用例的卡片
    - `static/`:  模板, 样式表与页面脚本

对外只暴露函数, 不暴露子模块: 以后包内怎么拆文件, 调用方都不用改. 包内部要用某个
函数时直接 `from ._render.case import render_case`, 不要依赖这里的重导出.
"""

# ------------ this package ------------
from .case import render_case
from .html import duration_text, esc, optional_block, time_text
from .page import (
    json_script,
    page_head,
    page_tail,
    run_manifest,
)

# 字母序, 只列公开名字
__all__ = [
    "duration_text",
    "esc",
    "json_script",
    "optional_block",
    "page_head",
    "page_tail",
    "render_case",
    "run_manifest",
    "time_text",
]
