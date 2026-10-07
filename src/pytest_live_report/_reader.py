# -*- coding: utf-8 -*-
# @Time    : 2026-10-07
# @Author  : Vsoapmac
# @File    : _reader.py
# @Software: VSCode
# @Description: 解析报告 HTML, 把内嵌的 JSON 还原成 Python 数据

"""读取一份报告 HTML, 取出运行清单与每条用例的记录

数据块由 `_render.page.json_script()` 写出, 这里按同一约定读回: `id="rpt-run"`
的是运行清单, `class="rpt-case-json"` 的是用例记录. 只用标准库, 不解析页面样式.
"""

# ------------ standard library ------------
import json
from pathlib import Path
from collections import Counter
from html.parser import HTMLParser
from typing import (
    List,
    Optional,
    Tuple,
    Union
)

# ------------ constants ------------
# 与写出端 `_render/page.py` 和 `_render/case.py` 一一对应, 改名要两边一起改
_RUN_ELEMENT_ID = "rpt-run"
_CASE_JSON_CLASS = "rpt-case-json"
_JSON_SCRIPT_TYPE = "application/json"


# region ---------------------------- HTML 解析 ----------------------------
class _JsonBlockParser(HTMLParser):
    """收集页面里所有 `<script type="application/json">` 块的属性与内容"""

    def __init__(self) -> None:
        super().__init__()
        # (属性字典, 块内容), 按出现顺序
        self.blocks: List[Tuple[dict, str]] = []
        # 正在收集的块的属性; None 表示当前不在 JSON 块里
        self._attrs: Optional[dict] = None
        self._chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag != "script":
            return
        attrs_dict = dict(attrs)
        if attrs_dict.get("type") == _JSON_SCRIPT_TYPE:
            self._attrs = attrs_dict
            self._chunks = []

    def handle_data(self, data: str) -> None:
        # 块内容可能分多次喂进来, 先攒着, 等结束标签再拼
        if self._attrs is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._attrs is not None:
            self.blocks.append((self._attrs, "".join(self._chunks)))
            self._attrs = None
            self._chunks = []


def _load_block(body: str, path: Path) -> dict:
    """解析一个 JSON 块, 坏掉的 JSON 统一报 ValueError

    Args:
        body (str): 块里的 JSON 原文
        path (Path): 报告文件路径, 只用于报错信息

    Returns:
        dict: 解析出来的数据

    Raises:
        ValueError: JSON 已经损坏
    """
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"pytest-live-report: 报告里的 JSON 块无法解析: {path}") from exc


def read_report(path: Union[str, Path]) -> dict:
    """解析一份报告 HTML, 返回运行清单与全部用例记录

    Args:
        path (Union[str, Path]): 报告 HTML 的路径

    Returns:
        dict: 三个键: `manifest` 是运行清单 (报告被中断时为 None), `counts` 是
            total / passed / failed / skipped 四项统计, `cases` 是用例记录列表,
            都是原始 JSON 数据, 未做二次加工

    Raises:
        FileNotFoundError: 路径下没有文件
        ValueError: 文件不是本插件生成的报告, 或某个 JSON 块已损坏

    Example:
        >>> report = read_report("report.html")
        >>> report["counts"]["total"] == len(report["cases"])
        True
    """
    report_path = Path(path)
    html = report_path.read_text(encoding="utf-8")

    parser = _JsonBlockParser()
    parser.feed(html)
    parser.close()

    manifest: Optional[dict] = None
    cases: List[dict] = []
    for attrs, body in parser.blocks:
        if attrs.get("id") == _RUN_ELEMENT_ID:
            manifest = _load_block(body, report_path)
        elif _CASE_JSON_CLASS in (attrs.get("class") or "").split():
            cases.append(_load_block(body, report_path))

    if manifest is None and not cases:
        raise ValueError(
            f"pytest-live-report: 文件里没有报告数据块, 不是本插件生成的报告: {report_path}"
        )

    # 计数一律按读到的 cases 现算: 完整报告与截断报告口径一致, 且总和永远等于 len(cases)
    tally = Counter(case["status"] for case in cases)
    counts = {
        "total": len(cases),
        "passed": tally.get("passed", 0),
        "failed": tally.get("failed", 0),
        "skipped": tally.get("skipped", 0),
    }
    return {"manifest": manifest, "counts": counts, "cases": cases}
# endregion ---------------------------- HTML 解析 ----------------------------
