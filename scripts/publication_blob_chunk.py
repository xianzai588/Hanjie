"""Print one exact base64 chunk of a local Git blob for connector upload.

Use a 750000 byte chunk, divisible by 3, to avoid padding in intermediate
chunks. Full chunks generate 1000000 stdout chars, below exec's observed
1048576-character cap. This tool never reads credentials or publishes refs.
"""
from __future__ import annotations
import argparse
import base64
import fcntl
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
RAW_CHUNK_BYTES=750000


def cached_blob(sha):
    if not re.fullmatch(r"[0-9a-f]{40}",sha): raise ValueError("A literal 40-character Git blob SHA is required")
    size=int(subprocess.check_output(["git","cat-file","-s",sha],cwd=ROOT))
    if size>100_000_000: raise ValueError("Blob is too large for GitHub Git-Data API")
    git_dir=Path(subprocess.check_output(["git","rev-parse","--absolute-git-dir"],cwd=ROOT).decode().strip())
    cache=git_dir/"publication-blob-cache";cache.mkdir(exist_ok=True)
    destination=cache/sha
    with (cache/(sha+".lock")).open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not destination.exists() or destination.stat().st_size!=size:
            fd,tmp=tempfile.mkstemp(prefix=sha+"-",dir=cache)
            try:
                with os.fdopen(fd,"wb") as target:
                    subprocess.run(["git","cat-file","blob",sha],cwd=ROOT,check=True,stdout=target)
                if Path(tmp).stat().st_size!=size: raise ValueError("Git blob export length mismatch")
                os.replace(tmp,destination)
            finally:
                Path(tmp).unlink(missing_ok=True)
        fcntl.flock(lock,fcntl.LOCK_UN)
    return destination,size


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sha",required=True)
    p.add_argument("--chunk-index",required=True,type=int)
    args=p.parse_args();path,size=cached_blob(args.sha)
    start=args.chunk_index*RAW_CHUNK_BYTES
    if args.chunk_index<0 or (start>=size and not (size==0 and args.chunk_index==0)):
        raise ValueError("Chunk index is outside the blob")
    with path.open("rb") as f:f.seek(start);raw=f.read(RAW_CHUNK_BYTES)
    sys.stdout.write(base64.b64encode(raw).decode("ascii"))


if __name__=="__main__": main()
