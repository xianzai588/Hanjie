"""旧工艺卡入口转向当前权威工艺生成器，避免R2参数回流。"""
from pathlib import Path
import runpy
if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("generate_process_r3.py")), run_name="__main__")
