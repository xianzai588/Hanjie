"""命令行入口：生成报告所用的当前证据摘要。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))

from hanjie.reporting.current_status import write_status_artifacts

if __name__=="__main__":
    print(write_status_artifacts(ROOT))
