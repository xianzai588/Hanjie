"""封版哈希门禁：最新 SHA256 记录必须对当前工作树机器校验通过。"""
import subprocess
import sys
from pathlib import Path


def test_latest_record_verifies_against_working_tree():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(root / "scripts/verify_release_hashes.py")],
        capture_output=True, text=True, cwd=root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_record_covers_zip_and_every_packaged_entry():
    root = Path(__file__).parents[1]
    record = root / "deliverables/COMPETITION-R3-SHA256.txt"
    entries = [line.split(maxsplit=1)[1].strip() for line in
               record.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#")]
    assert entries[0] == "deliverables/COMPETITION-R3-焊接固定题技术包.zip"
    assert len(entries) == 27  # ZIP + 24 个清单文件（图集并入论文01号） + 提交说明.txt + manifest.json
    assert all(entry.startswith("deliverables/submission/") for entry in entries[1:])
