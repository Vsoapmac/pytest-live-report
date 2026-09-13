# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : _writer.py
# @Software: VSCode
# @Description: 报告文件的打开, 追加与收尾

"""把报告文件的打开, 追加与收尾收在一个句柄里

报告是普通文件, pytest 运行期间被不断追加, 浏览器开着它就能看到新内容. 每次写完
都 flush 一次, 这样即使进程被强杀, 已经写出的部分仍然留在磁盘上.
"""

# ------------ standard library ------------
from pathlib import Path


# region ---------------------------- 报告文件 ----------------------------
class ReportFile:
    """报告文件的句柄, 只负责写字符串, 不关心内容是什么"""

    def __init__(self, path: Path) -> None:
        """记下目标路径, 文件此时还没打开

        Args:
            path (Path): 报告文件的路径, 父目录不存在时由 `open()` 创建
        """
        # 存成绝对路径, 终端提示与 pytest 的错误信息里就不会出现相对路径
        self.path = Path(path).resolve()
        self._handle = None

    def open(self) -> None:
        """创建文件 (已存在则清空) 并保持打开

        会话开始时调用一次. 文件在这一刻就被清空, 而不是等第一次写入: 上一轮的
        旧报告必须先消失, 否则里面会混着两次运行的结果.

        Raises:
            OSError: 目录建不出来或文件写不进去, 例如传了一个只读路径
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # newline 显式指定成 \n: 否则 Windows 上会写成 \r\n, 三个平台的产物不一致
        self._handle = self.path.open("w", encoding="utf-8", newline="\n")

    def write(self, text: str) -> None:
        """追加一段文本并立刻 flush

        Args:
            text (str): 要写出的片段; 空串直接跳过

        Raises:
            RuntimeError: 文件还没打开, 或者已经被 `finish()` / `close()` 关掉了
        """
        if not text:
            return
        handle = self._handle
        if handle is None or handle.closed:
            raise RuntimeError("report file is not open")
        handle.write(text)
        handle.flush()

    def finish(self, tail: str = "") -> None:
        """写完页尾并关闭文件

        Args:
            tail (str): 页尾片段; 传空串表示只关文件, 不补内容
        """
        if self._handle is None or self._handle.closed:
            return
        self.write(tail)
        self._handle.close()

    def close(self) -> None:
        """关闭文件, 重复调用不会有任何影响"""
        if self._handle is not None and not self._handle.closed:
            self._handle.close()
# endregion ---------------------------- 报告文件 ----------------------------
