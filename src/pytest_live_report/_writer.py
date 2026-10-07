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
        """记下报告文件的路径, 此时还不打开文件

        Args:
            path (Path): 报告文件的路径
        """
        # 存成绝对路径, 终端提示与 pytest 的错误信息里就不会出现相对路径
        self.path = Path(path).resolve()
        self._handle = None

    def open(self) -> None:
        """创建报告文件 (已存在则清空) 并打开它

        Raises:
            OSError: 目录建不出来或文件写不进去
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # newline 显式指定成 \n: 否则 Windows 上会写成 \r\n, 三个平台的产物不一致
        self._handle = self.path.open("w", encoding="utf-8", newline="\n")

    def write(self, text: str) -> None:
        """追加一段文本并立刻保存

        Args:
            text (str): 要写出的文本, 空串直接跳过

        Raises:
            RuntimeError: 文件还没打开, 或已经关闭
        """
        if not text:
            return
        handle = self._handle
        if handle is None or handle.closed:
            raise RuntimeError("report file is not open")
        handle.write(text)
        handle.flush()

    def finish(self, tail: str = "") -> None:
        """补上页尾并关闭文件

        Args:
            tail (str): 页尾内容, 空串表示只关闭文件
        """
        if self._handle is None or self._handle.closed:
            return
        self.write(tail)
        self._handle.close()

    def close(self) -> None:
        """关闭报告文件, 重复调用不受影响"""
        if self._handle is not None and not self._handle.closed:
            self._handle.close()
# endregion ---------------------------- 报告文件 ----------------------------
