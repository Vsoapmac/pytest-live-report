# -*- coding: utf-8 -*-
# @Time    : 2026-09-13
# @Author  : Vsoapmac
# @File    : __init__.py
# @Software: VSCode
# @Description: 报告用到的静态资源: 页面骨架, 样式表与页面脚本

"""存放报告要用的页面骨架, 样式表与页面脚本

这个文件必须存在: `_render.page` 用 `importlib.resources` 按子包名定位资源, 没有
它只有部分加载器 (zipimport) 能找到 head.html / tail.html / style.css / app.js.
"""
