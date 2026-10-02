"""生成当前批次的封版哈希记录（COMPETITION-R3）。

覆盖技术包 zip 与包内全部 27 个条目（manifest 25 个文件＋提交说明.txt＋manifest.json）。
ZIP 与两份 PDF 含生成时间戳，属于快照校验值；重新构建会得到不同哈希，须重新生成记录。

用法：先运行 `python deliverables/build_submission.py`，再运行本脚本；
随后 `python scripts/verify_release_hashes.py` 应全部一致。
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "deliverables/submission"
RECORD = ROOT / "deliverables/COMPETITION-R3-SHA256.txt"
ARCHIVE = ROOT / "deliverables/COMPETITION-R3-焊接固定题技术包.zip"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads((SUB / "manifest.json").read_text(encoding="utf-8"))
    names = [*manifest["files"], "提交说明.txt", "manifest.json"]
    with zipfile.ZipFile(ARCHIVE) as bundle:
        packaged = set(bundle.namelist())
    missing = [name for name in names if name not in packaged]
    if missing:
        raise SystemExit(f"FAIL: ZIP 缺少条目 {missing}")
    lines = [
        "# COMPETITION-R3 SHA256",
        "# 封版：R3 修复批次——导航五维对齐与悬空章节引用清理、胀套接触反力跨网格披露、"
        "载荷一阶推导入库（08e）、图纸 GB/T 324 焊缝符号与 GB/T 1182 公差框及标题栏、"
        "封版哈希记录机器校验恢复。",
        "# ZIP 与两份 PDF 含生成时间戳，本表对 ZIP 为快照校验值；重新构建会得到不同哈希，须重新生成记录。",
        "# 校验：python scripts/verify_release_hashes.py",
        f"{digest(ARCHIVE)}  deliverables/{ARCHIVE.name}",
    ]
    lines += [f"{digest(SUB / name)}  deliverables/submission/{name}" for name in names]
    RECORD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {RECORD.name}：ZIP＋{len(names)} 个包内条目")


if __name__ == "__main__":
    main()
