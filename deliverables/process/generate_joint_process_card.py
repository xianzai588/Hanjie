"""兼容入口：当前竞赛工艺只允许由 generate_process_r3.py 生成。

此文件保留旧入口名以兼容外部调用，但不再包含任何历史6P/四道参数。
"""
from __future__ import annotations

from deliverables.process.generate_process_r3 import main

if __name__ == "__main__":
    main()
