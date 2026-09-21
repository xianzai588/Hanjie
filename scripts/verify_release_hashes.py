"""按封版哈希记录校验产物。

记录文件格式（`#` 开头为注释，其余每行为 `<sha256>  <相对路径>`）：

    # COMPETITION-R1-RC3 SHA256
    <64位十六进制>  deliverables/COMPETITION-R1-技术包.zip

用法：
    python scripts/verify_release_hashes.py                      # 默认校验最新的 RC 记录
    python scripts/verify_release_hashes.py --record <记录文件>
    python scripts/verify_release_hashes.py --list               # 只列出全部记录文件

退出码：全部一致为 0；存在缺失或不一致为 1。

说明：历史 RC 记录是**当时快照**的校验值，其中的 ZIP 与 PDF 每次重建都会变，
因此只有最新一条记录能对当前工作树全部通过；校验历史记录需先检出对应提交。
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_DIR = ROOT / "deliverables"
RECORD_GLOB = "COMPETITION-R1-*-SHA256.txt"
_DIGEST = re.compile(r"^([0-9a-fA-F]{64})[ \t]{2}(.+)$")


def records() -> list[Path]:
    """按 RC 序号升序返回全部哈希记录文件。"""
    return sorted(RECORD_DIR.glob(RECORD_GLOB), key=lambda p: p.name)


def latest_record() -> Path:
    if not (found := records()):
        raise SystemExit(f"FAIL: 未找到任何封版哈希记录 {RECORD_DIR / RECORD_GLOB}")
    return found[-1]


def parse(path: Path) -> list[tuple[str, str]]:
    """解析记录文件；忽略空行与 `#` 注释，格式异常的行显式报错而非静默跳过。"""
    if not path.is_file():
        raise SystemExit(f"FAIL: 记录文件不存在：{path}")
    entries: list[tuple[str, str]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _DIGEST.match(line)
        if match is None:
            raise SystemExit(f"FAIL: {path.name} 第 {number} 行格式非法：{raw!r}")
        entries.append((match.group(1).lower(), match.group(2).strip()))
    if not entries:
        raise SystemExit(f"FAIL: {path.name} 没有任何可校验条目")
    return entries


def display(path: Path) -> str:
    """尽量显示为仓库内相对路径；仓库外路径原样显示。"""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def verify(path: Path) -> int:
    entries = parse(path)
    print(f"校验记录：{display(path)}")
    failures: list[str] = []
    for expected, relative in entries:
        target = ROOT / relative
        if not target.is_file():
            failures.append(f"缺失      {relative}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual == expected:
            print(f"  一致    {relative}")
        else:
            failures.append(f"不一致    {relative}")
            print(f"  不一致  {relative}")
            print(f"          记录 {expected}")
            print(f"          实际 {actual}")
    print()
    if failures:
        print(f"结果：{len(failures)}/{len(entries)} 项未通过")
        return 1
    print(f"结果：{len(entries)}/{len(entries)} 项全部一致")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="按封版哈希记录校验产物")
    parser.add_argument("--record", type=Path, help="指定记录文件；缺省用最新一条")
    parser.add_argument("--list", action="store_true", help="只列出全部记录文件后退出")
    args = parser.parse_args()
    if args.list:
        for path in records():
            print(display(path))
        return
    record = args.record.resolve() if args.record else latest_record()
    raise SystemExit(verify(record))


if __name__ == "__main__":
    main()
