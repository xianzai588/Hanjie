"""根据当前提交清单生成一份机器可校验的发布哈希记录。"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="按当前提交清单生成发布哈希记录")
    parser.add_argument("revision", help="发布修订号，例如 RC10")
    args = parser.parse_args()
    if re.fullmatch(r"RC\d+", args.revision) is None:
        parser.error("修订号格式应为 RC 后跟数字")

    submission = ROOT / "deliverables" / "submission"
    manifest_path = submission / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [
        ROOT / "deliverables" / "COMPETITION-R1-技术包.zip",
        *(submission / name for name in manifest["files"]),
        manifest_path,
        submission / "提交说明.txt",
    ]
    entries = []
    for path in sorted(set(paths), key=lambda item: item.relative_to(ROOT).as_posix()):
        if not path.is_file():
            raise FileNotFoundError(path)
        relative = path.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(f"{digest}  {relative}")

    target = ROOT / "deliverables" / f"COMPETITION-R1-{args.revision}-SHA256.txt"
    content = "\n".join([
        f"# COMPETITION-R1-{args.revision} SHA256",
        f"# Generated: {date.today().isoformat()}",
        *entries,
        "",
    ])
    target.write_text(content, encoding="utf-8")
    print(f"已生成 {target.relative_to(ROOT).as_posix()}，共 {len(entries)} 项")


if __name__ == "__main__":
    main()
