# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : page.py
# @Software: VSCode
# @Description: 读取包内静态资源, 拼装报告页头, 页尾与 JSON 数据块

"""拼装报告的页头, 页尾与页面里的 JSON 数据块

模板 / 样式 / 脚本都随包分发 (放在 `static/` 子包里), 用户 `pip install` 之后
直接就能出报告, 不需要再配模板路径.

所有资源一律走 `importlib.resources` 读取: 手工拼 `__file__` 在源码目录下也能跑通,
但包一旦装成 wheel 就会指向别处.
"""

# ------------ standard library ------------
import json
from functools import lru_cache
from importlib.resources import files
from typing import (
    Any,
    Mapping,
    Optional,
)

# ------------ this package ------------
from .html import esc, json_script_value

# ------------ constants ------------
# `static` 是本包内的子包 (带 `__init__.py`), 资源名相对它取
_STATIC = "pytest_live_report._render.static"
# 客户端脚本靠这个元素 id 区分"跑完了"与"还在跑"
_RUN_ELEMENT_ID = "rpt-run"
# 非法 JSON 值 (NaN / Infinity) 会被 dumps 写成裸 `NaN` 令牌, 页面就解析不了, 故拒绝
_ALLOW_NAN = False
# 与 `head.html` / `tail.html` 里的占位符一一对应
_TOKEN_TITLE = "{{TITLE}}"
_TOKEN_META = "{{META}}"
_TOKEN_VERSION = "{{VERSION}}"
_TOKEN_CSS = "{{CSS}}"
_TOKEN_JS = "{{JS}}"
# 运行清单的占位符必须带双层花括号: 替换结果里含有 `id="rpt-run"`, 裸 `{run}` 会
# 命中自己的输出, 把清单拼出两块
_TOKEN_RUN = "{{RUN}}"


# region ---------------------------- 资源读取 ----------------------------
@lru_cache(maxsize=None)
def _read(name: str) -> str:
    """读一个包内静态文件, 整个进程只读一次盘

    Args:
        name (str): `static/` 下的文件名, 例如 "head.html"

    Returns:
        str: 文件全文, 按 UTF-8 解码

    Raises:
        FileNotFoundError: 包内没有这个资源
    """
    path = files(_STATIC).joinpath(name)
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise FileNotFoundError(
            f"pytest-live-report: 包内静态资源缺失: {name}\n"
            "Hint: 确认 `_render/static/` 下有 __init__.py, 且 pyproject.toml 已把 "
            "`_render/static/**` 配进 package-data, 然后重新安装."
        ) from exc


def css() -> str:
    """返回报告样式表全文"""
    return _read("style.css")


def js() -> str:
    """返回报告前端脚本全文"""
    return _read("app.js")


def _version() -> str:
    """返回本包版本号"""
    from .. import __version__

    return __version__
# endregion ---------------------------- 资源读取 ----------------------------


# region ---------------------------- 页面拼装 ----------------------------
def page_head(title: str, meta: str = "") -> str:
    """渲染报告页头, 样式与脚本都已内嵌

    Args:
        title (str): 报告标题, 同时用于页面标题与页内一级标题
        meta (str): 环境信息摘要行, 已经是拼好的纯文本

    Returns:
        str: 页面头部片段

    Example:
        >>> head = page_head("My project", "pytest 8.3.0 / Windows")
        >>> head.startswith("<!DOCTYPE html>")
        True
        >>> '<main id="rpt-cases">' in head
        True
    """
    out = _read("head.html")
    # 用 str.replace 而不是 str.format: 标题里的花括号和反斜杠必须原样落进去
    out = out.replace(_TOKEN_CSS, css())
    out = out.replace(_TOKEN_TITLE, esc(title))
    out = out.replace(_TOKEN_META, esc(meta))
    out = out.replace(_TOKEN_VERSION, json_script_value(_version()))
    return out


def page_tail(run: Optional[Mapping[str, Any]] = None) -> str:
    """渲染报告页尾: 运行清单与页面结尾

    Args:
        run (Optional[Mapping[str, Any]]): 运行信息, 键见 `run_manifest()`; 传 None
            表示会话被中断

    Returns:
        str: 页面尾部片段

    Example:
        >>> page_tail().rstrip().endswith("</html>")
        True
        >>> "rpt-run" in page_tail({"exitstatus": 0})
        True
    """
    out = _read("tail.html")
    out = out.replace(_TOKEN_JS, js())
    return out.replace(_TOKEN_RUN, "" if run is None else run_manifest(run))


def run_manifest(info: Mapping[str, Any]) -> str:
    """渲染机器可读的运行清单

    只有会话跑完才会写出这块 JSON, 页面与消费脚本靠它区分完整报告与截断报告.

    Args:
        info (Mapping[str, Any]): 运行信息, 认识的键有 `exitstatus`, `counts`
            (至少含 total / passed / failed / skipped), `started`, `ended` 与
            `env`; 表里没有的键原样透传

    Returns:
        str: 一个 `<script type="application/json" id="rpt-run">` 标签

    Example:
        >>> tag = run_manifest({"exitstatus": 0, "counts": {"total": 1}})
        >>> tag.startswith('<script type="application/json" id="rpt-run">')
        True
        >>> '"complete":true' in tag
        True
    """
    payload: dict = {
        "v": 1,
        "complete": True,
        "exitstatus": int(info.get("exitstatus", 0)),
        "counts": dict(info.get("counts") or {}),
        "started": info.get("started", ""),
        "ended": info.get("ended", ""),
        "env": dict(info.get("env") or {}),
    }
    for key, value in info.items():
        if key not in payload:
            payload[key] = value
    return json_script(payload, element_id=_RUN_ELEMENT_ID)


def json_script(
    payload: Any,
    *,
    element_id: Optional[str] = None,
    css_class: Optional[str] = None,
) -> str:
    """把数据渲染成页面可解析的 JSON 块

    Args:
        payload (Any): 要序列化的数据
        element_id (Optional[str]): `id` 属性, 不传就不写
        css_class (Optional[str]): `class` 属性, 不传就不写

    Returns:
        str: 完整的 `<script type="application/json">` 标签

    Example:
        >>> json_script({"a": 1}, css_class="x")
        '<script type="application/json" class="x">{"a":1}</script>'
    """
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=_ALLOW_NAN,
    ).replace("<", "\\u003c")
    attrs = 'type="application/json"'
    if element_id:
        attrs += f' id="{esc(element_id)}"'
    if css_class:
        attrs += f' class="{esc(css_class)}"'
    return f"<script {attrs}>{body}</script>"
# endregion ---------------------------- 页面拼装 ----------------------------
