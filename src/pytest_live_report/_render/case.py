# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : case.py
# @Software: VSCode
# @Description: 把一条用例渲染成报告里的一张卡片

"""拼装单条用例的卡片 HTML

卡片是整条攒好再一次性写出的, 页面上的 DOM 顺序就是最终的视觉顺序.

HTML 结构必须与 `static/` 下的模板与脚本对齐, 改一边就要改另一边:
    - 页面脚本靠 `data-rpt-status` 筛选, 靠 `data-rpt-name` 搜索, 靠
      `data-rpt-duration` 展示耗时
    - 页面脚本靠 `.rpt-case` 数卡片, 靠 `.rpt-case-head` 响应点击展开
"""

# ------------ this package ------------
from .._case import CaseData
from .html import duration_text, esc, optional_block, time_text
from .page import json_script

# ------------ constants ------------
# 徽标上显示的状态文字, 与 `CaseData.status` 的三种取值一一对应
_BADGE_TEXT = {
    "passed": "PASSED",
    "failed": "FAILED",
    "skipped": "SKIPPED",
}


# region ---------------------------- 卡片拼装 ----------------------------
def render_case(case: CaseData) -> str:
    """把一条用例渲染成报告里的一张卡片

    Args:
        case (CaseData): 已经填好的用例数据

    Returns:
        str: 一个完整的 `<section class="rpt-case">` 元素, 以换行结尾

    Example:
        >>> from pytest_live_report._case import CaseData
        >>> card = render_case(CaseData(nodeid="tests/test_a.py::test_x",
        ...                             name="test_x", duration=0.42))
        >>> card.startswith('<section class="rpt-case" data-rpt-status="passed"')
        True
        >>> 'data-rpt-duration="0.42"' in card
        True
        >>> card.rstrip().endswith("</section>")
        True
    """
    return "".join(
        [
            _open_tag(case),
            _head(case),
            _body(case),
            # 机器可读记录放卡片末尾: 消费脚本按 `class="rpt-case-json"` 抓它
            json_script(case.json_record(), css_class="rpt-case-json"),
            "\n</section>\n",
        ]
    )


def _open_tag(case: CaseData) -> str:
    """渲染卡片的开标签, 把状态, 搜索字段与耗时挂在数据属性上

    Args:
        case (CaseData): 用例数据

    Returns:
        str: `<section class="rpt-case" ...>` 开标签
    """
    # 搜索字段把标题, 节点 id 与描述并在一个属性里, 页面脚本只需一次小写匹配
    haystack = " ".join(part for part in (case.name, case.nodeid, case.desc) if part)
    return (
        '<section class="rpt-case"'
        f' data-rpt-status="{esc(case.status)}"'
        f' data-rpt-name="{esc(haystack.lower())}"'
        f' data-rpt-duration="{case.duration:.2f}">\n'
    )


def _head(case: CaseData) -> str:
    """渲染卡片头部: 展开箭头, 状态徽标, 用例名, 节点 id 与耗时

    Args:
        case (CaseData): 用例数据

    Returns:
        str: `.rpt-case-head` 区块; 没有用例名时不输出标题元素
    """
    badge = _BADGE_TEXT.get(case.status, case.status.upper())
    name_html = "" if not case.name else f'<span class="rpt-name">{esc(case.name)}</span>'
    return (
        '<div class="rpt-case-head">\n'
        '<span class="rpt-chev">&#9654;</span>\n'
        f'<span class="rpt-badge">{esc(badge)}</span>\n'
        f"{name_html}\n"
        f'<span class="rpt-id">{esc(case.nodeid)}</span>\n'
        f'<span class="rpt-dur">{duration_text(case.duration)}</span>\n'
        "</div>\n"
    )


def _when(case: CaseData) -> str:
    """渲染起止时间与耗时那一行

    Args:
        case (CaseData): 用例数据

    Returns:
        str: `.rpt-when` 区块
    """
    return (
        '<div class="rpt-when">\n'
        f"<span>Start {esc(time_text(case.started))}</span>\n"
        f"<span>End {esc(time_text(case.finished))}</span>\n"
        f"<span>Duration {duration_text(case.duration)}</span>\n"
        "</div>\n"
    )


def _skip(case: CaseData) -> str:
    """渲染跳过原因

    Args:
        case (CaseData): 用例数据

    Returns:
        str: `.rpt-skipwhy` 区块; 没有跳过原因时是空串
    """
    return optional_block(
        "rpt-skipwhy",
        case.skip_reason,
        '<div class="{css}">Skip reason: <b>{text}</b></div>\n',
    )


def _error(case: CaseData) -> str:
    """渲染错误摘要与完整 traceback

    Args:
        case (CaseData): 用例数据

    Returns:
        str: `.rpt-error` 区块; 错误与 traceback 都没有时是空串
    """
    if not case.error and not case.traceback:
        return ""
    return (
        '<div class="rpt-error">\n'
        f'<div class="rpt-error-head">{esc(case.error)}</div>\n'
        f'<pre class="rpt-tb">{esc(case.traceback)}</pre>\n'
        "</div>\n"
    )


def _log(case: CaseData) -> str:
    """渲染用例执行期间写下的日志

    折起来放, 默认展开: 默认折叠的话出错时用户还要多点一次才能看到现场.

    每行日志存了原文与 HTML 两份, 卡片只贴 HTML 那一份.

    Args:
        case (CaseData): 用例数据

    Returns:
        str: 一个 `<details class="rpt-log">` 区块; 一行日志都没有时是空串
    """
    if not case.logs:
        return ""
    lines = "".join(
        f'<div class="rpt-line"><span class="rpt-ts">{esc(stamp)}</span>'
        f'<span class="rpt-msg">{html}</span></div>\n'
        for stamp, _text, html, _styled in case.logs
    )
    return (
        f'<details class="rpt-log" open><summary>Log ({len(case.logs)})</summary>\n'
        f'<div class="rpt-body">\n{lines}</div>\n</details>\n'
    )


def _shots(case: CaseData) -> str:
    """渲染用例执行期间保存的截图

    图片是 base64 data URI, 直接放 `<img src>`; 页面脚本靠 `.rpt-shot img` 点击时
    弹大图, 这个类名不能改.

    每张截图还存了字节数与类型, 那是给脚本读的, 卡片上不显示.

    Args:
        case (CaseData): 用例数据

    Returns:
        str: 一串 `<figure class="rpt-shot">`; 一张图都没有时是空串
    """
    if not case.shots:
        return ""
    return "".join(
        f'<figure class="rpt-shot"><img src="{esc(uri)}" alt="">'
        + ("" if not note else f"<figcaption>{esc(note)}</figcaption>")
        + "</figure>\n"
        for uri, note, _size, _mime in case.shots
    )


def _body(case: CaseData) -> str:
    """渲染卡片的详情区: 描述, 起止时间, 跳过原因, 错误块, 日志与截图

    Args:
        case (CaseData): 用例数据

    Returns:
        str: `.rpt-case-body` 区块
    """
    blocks = [
        optional_block("rpt-desc", case.desc, '<p class="{css}">{text}</p>\n'),
        _when(case),
        _skip(case),
        _error(case),
        _log(case),
        _shots(case),
    ]
    return '<div class="rpt-case-body">\n' + "".join(blocks) + "</div>\n"
# endregion ---------------------------- 卡片拼装 ----------------------------
