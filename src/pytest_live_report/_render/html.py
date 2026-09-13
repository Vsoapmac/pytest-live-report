# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : html.py
# @Software: VSCode
# @Description: HTML 转义与几个共用的小工具

"""转义与格式化字符串的小工具集合

这一层不碰文件, 不碰状态, 只做纯字符串处理, 所以可以单独跑 doctest 验证.
"""

# ------------ standard library ------------
import json
from datetime import datetime
from html import escape
from typing import Any, Optional


def esc(text: Any) -> str:
    """转义 HTML 元字符, 单双引号一并处理

    报告里所有来自用户的内容 (用例名, 日志, traceback) 都要过这一层. 函数名保持
    三个字母的短名, 因为它要在一行里出现很多次.

    Args:
        text (Any): 任意取值, 内部先过 `str()`

    Returns:
        str: 可以直接拼进 HTML 正文或属性值的文本

    Example:
        >>> esc('<b>"x"</b>')
        '&lt;b&gt;&quot;x&quot;&lt;/b&gt;'
    """
    return escape(str(text), quote=True)


def json_script_value(value: Any) -> str:
    """把一个值渲染成能安全放进 `<script>` 的 JS 字面量

    只给 `head.html` 里的 `var RPT_VERSION=...` 用, 页面数据一律走 `json_script()`.

    Args:
        value (Any): 要嵌入的值, 通常就是版本号字符串

    Returns:
        str: 该值的 JSON 形式, `<` 已转义

    Example:
        >>> json_script_value("0.1.0")
        '"0.1.0"'
    """
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def duration_text(duration: float) -> str:
    """把秒数格式化成卡片上显示的耗时文本

    Args:
        duration (float): 秒数

    Returns:
        str: 形如 "12.34s" 的文本

    Example:
        >>> duration_text(12.3449)
        '12.34s'
    """
    return f"{duration:.2f}s"


def time_text(moment: Optional[datetime]) -> str:
    """把时刻格式化成卡片上显示的时间

    Args:
        moment (Optional[datetime]): 带本地时区的时刻; 缺失时传 None

    Returns:
        str: 形如 "11:14:55" 的文本; 时刻缺失时是空串

    Example:
        >>> time_text(None)
        ''
    """
    return "" if moment is None else moment.strftime("%H:%M:%S")


def optional_block(css_class: str, text: str, template: str) -> str:
    """按模板渲染一个可选的区块, 文本为空时什么都不输出

    Args:
        css_class (str): 区块的类名, 替换模板里的 `{css}`
        text (str): 区块正文, 会被转义
        template (str): 含 `{css}` 与 `{text}` 两个占位符的 HTML 模板

    Returns:
        str: 渲染好的区块; 文本为空时是空串

    Example:
        >>> optional_block("rp-x", "", '<p class="{css}">{text}</p>')
        ''
        >>> optional_block("rp-x", "hi", '<p class="{css}">{text}</p>')
        '<p class="rp-x">hi</p>'
    """
    if not text:
        return ""
    return template.format(css=css_class, text=esc(text))
