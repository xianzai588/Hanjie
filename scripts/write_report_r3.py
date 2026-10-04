"""兼容旧命令：正文维护于technical-report-v4-unified.md，不再回写旧内嵌正文。"""
from pathlib import Path
import runpy
if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1]/"deliverables/report/build_technical_report_pdf.py"), run_name="__main__")
