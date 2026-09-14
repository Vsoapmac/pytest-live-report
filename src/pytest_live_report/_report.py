# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : _report.py
# @Software: VSCode
# @Description: 测试用例里写报告内容的公开 API

"""测试用例里写报告内容的公开入口

用户只需要 `from pytest_live_report import live_report`, 其余都是内部实现.

写下的日志与截图除了渲染进卡片, 摘要也会写进卡片末尾的 JSON 记录: 日志给原始
文本, 截图给图注与大小, 图片数据只留在卡片 HTML 里, 不重复存一份.

这些方法只能在正在跑的用例里调用, 所以 Example 只是用法示例. 实际行为由
`tests/test_report.py` 逐条断言.
"""

# ------------ standard library ------------
import base64
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ------------ this package ------------
from . import _store
from ._case import param_suffix
from ._render import esc

# ------------ constants ------------
# 日志行的时间戳格式, 与卡片上其他地方保持一致
_STAMP_FORMAT = "%H:%M:%S"
# 按文件头认图片类型: 只看开头几个字节, 不引入任何图像库
_MAGIC_TYPES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)
# 单张超过这个大小就提醒一次, 但仍然内联: base64 会把体积再撑大约三分之一
_BIG_IMAGE_BYTES = 5 * 1024 * 1024


# region ---------------------------- 公开 API ----------------------------
class Span:
    """一段已经渲染好的行内 HTML, 由 `live_report.log()` 原样放进卡片"""

    __slots__ = ("html", "text")

    def __init__(self, html: str, text: str) -> None:
        """包住一段渲染好的行内 HTML, 以及它的原始文本

        Args:
            html (str): 已转义并带好标签的片段
            text (str): 未经转义的原始文本
        """
        self.html = html
        self.text = text

    def __repr__(self) -> str:  # pragma: no cover - 只为调试时看得懂
        """调试用的可读表示"""
        return f"Span({self.html!r})"


class Report:
    """报告 API 的唯一实例, 测试用例里用到的入口都挂在它上面"""

    def span_html(self, text: Any, *, bold: bool = False, code: bool = False) -> Span:
        """渲染一段带样式的行内 HTML, 交给 `live_report.log()` 原样嵌进卡片

        Args:
            text (Any): 要显示的内容, 一律转义
            bold (bool): 加粗
            code (bool): 等宽字体

        Returns:
            Span: 渲染好的片段, 直接当 `live_report.log()` 的参数用

        Example:
            >>> live_report.span_html("200 OK", bold=True, code=True).html
            '<span class="rpt-b rpt-code">200 OK</span>'
            >>> live_report.span_html("<b>").html
            '<span>&lt;b&gt;</span>'
            >>> live_report.span_html("<b>").text
            '<b>'
        """
        # 只拼字符串, 不看当前用例也不写报告, 所以在用例之外也能调
        classes = " ".join(
            name for name, on in (("rpt-b", bold), ("rpt-code", code)) if on
        )
        attr = f' class="{classes}"' if classes else ""
        return Span(f"<span{attr}>{esc(text)}</span>", str(text))

    def log(self, *parts: Any) -> None:
        """往当前用例的卡片里写一行日志

        参数像 `print` 一样按空格拼接, 内容里的换行会拆成报告里的多行.

        每行存两份: 原始文本给脚本读, HTML 给卡片显示.

        Args:
            *parts (Any): 要写入的内容; `span_html()` 的返回值原样嵌入, 其余转义

        Example:
            >>> live_report.log("POST /login", 200)
            >>> live_report.log("status", live_report.span_html("200 OK", bold=True))
        """
        case = _store.get_current()
        if case is None:
            _warn_no_case("live_report.log")
            return
        # 逐段取两份内容: 带样式的段只能从 HTML 取原文, 顺手记下这行有没有样式
        html_parts = []
        text_parts = []
        styled = False
        for part in parts:
            html_parts.append(_to_html(part))
            if isinstance(part, Span):
                styled = True
                text_parts.append(part.text)
            else:
                text_parts.append(str(part))
        line_text = " ".join(text_parts)
        line_html = " ".join(html_parts)
        stamp = _stamp()
        # 同一次调用的多行共用时间戳, 免得一句话被打上好几个时间
        for text, html in zip(line_text.split("\n"), line_html.split("\n")):
            case.logs.append((stamp, text, html, styled))

    def case_name(self, text: Any) -> None:
        """覆盖卡片标题, 不调就用测试函数名

        参数化后缀会保留: `test_login[admin]` 的标题显示成 `登录流程[admin]`.

        Args:
            text (Any): 显示名

        Example:
            >>> live_report.case_name("登录流程")           # 卡片标题变成 登录流程
            >>> live_report.case_name("登录流程[admin]")   # 参数化后缀会原样留下
        """
        case = _store.get_current()
        if case is None:
            _warn_no_case("live_report.case_name")
            return
        # 存纯文本, 转义交给渲染层
        case.name = f"{text}{param_suffix(case.nodeid)}"

    def case_desc(self, text: Any) -> None:
        """覆盖卡片描述, 不调就用测试函数自己的 docstring

        Args:
            text (Any): 描述正文

        Example:
            >>> live_report.case_desc("验证账号密码登录后的跳转")
        """
        case = _store.get_current()
        if case is None:
            _warn_no_case("live_report.case_desc")
            return
        case.desc = str(text)

    def save_image(self, path: Any, caption: Optional[str] = None) -> None:
        """把一张图片内联进当前用例的卡片

        除了 data URI, 还记下字节数与类型: 脚本靠这两项就能核对截图存进来了没有,
        不必再解一遍 base64.

        Args:
            path (Any): 图片路径
            caption (Optional[str]): 图注, 不传就不显示图注

        Raises:
            FileNotFoundError: 图片路径不是已存在的文件

        Example:
            >>> from pathlib import Path
            >>> shot = Path("home.png")
            >>> shot.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n")
            8
            >>> live_report.save_image(shot, caption="下单页")
            >>> shot.unlink()
        """
        case = _store.get_current()
        if case is None:
            _warn_no_case("live_report.save_image")
            return
        # 读文件与编码当场做完: 有问题立刻报出来, 别等写报告时才发现
        uri, size, mime = _data_uri(Path(str(path)))
        note = "" if caption is None else str(caption)
        case.shots.append((uri, note, size, mime))
# endregion ---------------------------- 公开 API ----------------------------


# region ---------------------------- 私有函数 ----------------------------
def _to_html(part: Any) -> str:
    """把一个参数转成卡片里的 HTML, `Span` 原样保留, 其余转义

    Args:
        part (Any): 任意内容, 例如字符串, 数字, 字典, 或 `span_html()` 的返回值

    Returns:
        str: 可以直接嵌进卡片的 HTML 片段
    """
    if isinstance(part, Span):
        return part.html
    return esc(part)


def _warn_no_case(api: str) -> None:
    """发一条告警, 说明这个入口只能在用例里调用

    Args:
        api (str): 入口名字, 例如 `live_report.log`, 只用于告警文案
    """
    warnings.warn(
        f"pytest-live-report: {api}() was called outside a test case, "
        f"the content was dropped.",
        stacklevel=3,
    )


def _sniff_mime(data: bytes) -> str:
    """按文件头判断图片类型

    Args:
        data (bytes): 图片字节, 只看开头的几个字节

    Returns:
        str: MIME 类型; 认不出来时按 `image/png` 处理
    """
    for magic, mime in _MAGIC_TYPES:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _data_uri(path: Path) -> tuple:
    """把一张图片读成可以直接放进 `<img src>` 的 data URI

    Args:
        path (Path): 图片路径, 必须是已存在的文件

    Returns:
        tuple: `(data URI, 图片字节数, MIME 类型)`

    Raises:
        FileNotFoundError: 路径不是已存在的文件; 消息里给出解析后的绝对路径
    """
    if not path.is_file():
        resolved = path if path.is_absolute() else Path.cwd() / path
        raise FileNotFoundError(
            f"pytest-live-report: live_report.save_image() cannot find the image:\n"
            f"  {resolved}\n"
            f"Hint: capture the image first, then pass its path in."
        )
    data = path.read_bytes()
    # 超限只提醒, 仍然内联: 报告要能单独发出去, 图片不能落成额外文件
    if len(data) > _BIG_IMAGE_BYTES:
        warnings.warn(
            f"pytest-live-report: image {path.name} is "
            f"{len(data) / 1024 / 1024:.1f} MB, inlining it will noticeably "
            f"bloat the report.",
            stacklevel=3,
        )
    mime = _sniff_mime(data)
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}", len(data), mime


def _stamp() -> str:
    """取当前时刻的日志时间戳

    Returns:
        str: 形如 "11:14:55" 的文本
    """
    return datetime.now().astimezone().strftime(_STAMP_FORMAT)
# endregion ---------------------------- 私有函数 ----------------------------


# 全局唯一实例: `__init__.py` 的公开别名都取自它
live_report = Report()
