"""Prepare a GitHub Git-Data-API publication from an immutable local commit.

This script is read-only with respect to branches and commits. Blob content is
not copied into the manifest. Existing base-tree blobs and repeated artifacts
are reused by Git SHA. GitHub connector calls happen in functions.exec.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE="9881addbb0dd070a0b1cecbc1fd554ce52c059ef"
RAW_CHUNK_BYTES=750000  # 1,000,000 base64 chars; below exec's 1 MiB stdout ceiling


def git(*args):
    return subprocess.run(["git",*args],cwd=ROOT,check=True,stdout=subprocess.PIPE).stdout


def entries(ref):
    result={}
    for record in git("ls-tree","-r","-z","--full-tree",ref).split(b"\0"):
        if not record: continue
        header,path=record.split(b"\t",1)
        mode,kind,sha=header.decode("ascii").split()
        result[path.decode("utf8")]={"mode":mode,"type":kind,"sha":sha}
    return result


def shallow_trees(source, base):
    def tree_paths(ref):
        result = {'': git('rev-parse', ref+'^{tree}').decode().strip()}
        for row in git('ls-tree', '-r', '-t', '-z', ref).split(b'\0'):
            if not row: continue
            header, path = row.split(b'\t', 1)
            mode, kind, sha = header.decode().split()
            if kind == 'tree': result[path.decode()] = sha
        return result
    existing = set(tree_paths(base).values())
    grouped = defaultdict(list)
    for path, sha in tree_paths(source).items():
        if sha not in existing: grouped[sha].append(path)
    result = []
    for sha, paths in grouped.items():
        elements = []
        for row in git('ls-tree', '-z', sha).split(b'\0'):
            if not row: continue
            header, path = row.split(b'\t', 1)
            mode, kind, child = header.decode().split()
            elements.append({'path':path.decode(), 'mode':mode, 'type':kind, 'sha':child})
        result.append({'sha':sha,'depth':max(path.count('/')+1 if path else 0 for path in paths),
                       'paths':paths,'elements':elements})
    return sorted(result,key=lambda row:(-row['depth'],row['sha']))


def prepare(source_ref,base_ref=BASE,branch="codex/complete-ring-deliverables"):
    source=git("rev-parse",source_ref+"^{commit}").decode().strip()
    base=git("rev-parse",base_ref+"^{commit}").decode().strip()
    if source==base: raise ValueError("Source is still the base commit; freeze a real reviewed local release commit first")
    parents=git("show","-s","--format=%P",source).decode().strip().split()
    if parents!=[base]: raise ValueError(f"Expected one release commit whose parent is {base}; actual parents: {parents}")
    old,new=entries(base),entries(source)
    already_remote={r["sha"] for r in old.values()}
    changes=[];upload_paths=defaultdict(list)
    for path in sorted(set(old)|set(new)):
        if old.get(path)==new.get(path): continue
        if path not in new:
            changes.append({"path":path,"mode":old[path]["mode"],"type":old[path]["type"],"sha":None})
            continue
        row={"path":path,**new[path]};changes.append(row)
        if row["sha"] not in already_remote:
            if row["type"]!="blob": raise ValueError(f"Cannot upload a new non-blob object: {path}")
            upload_paths[row["sha"]].append(path)
    uploads=[]
    for sha,paths in upload_paths.items():
        size=int(git("cat-file","-s",sha))
        if size>100_000_000: raise ValueError(f"Blob exceeds GitHub Git-Data size limit: {paths[0]} ({size} bytes)")
        if size>11_500_000: raise ValueError(f"Blob exceeds connector 16 MiB request ceiling after base64: {paths[0]}; publish checked package volumes")
        if size<1024:
            content=git("cat-file","blob",sha)
            if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
                raise ValueError(f"New LFS pointer without a supported LFS upload: {paths[0]}; ordinary-Git attributes must be set before the release commit")
        uploads.append({"sha":sha,"paths":paths,"bytes":size,"raw_chunk_bytes":RAW_CHUNK_BYTES,
                        "chunks":max(1,math.ceil(size/RAW_CHUNK_BYTES)),"base64_bytes":4*math.ceil(size/3)})
    return {"repository_full_name":"xianzai588/Hanjie","branch_name":branch,
            "base_commit_sha":base,"base_tree_sha":git("rev-parse",base+"^{tree}").decode().strip(),
            "source_local_commit_sha":source,"expected_tree_sha":git("rev-parse",source+"^{tree}").decode().strip(),
            "tree_elements":changes,"uploads":uploads,"shallow_tree_uploads":shallow_trees(source,base),
            "summary":{"changed_paths":len(changes),"unique_new_blobs":len(uploads),
                       "upload_bytes":sum(u["bytes"] for u in uploads),"largest_blob_bytes":max([u["bytes"] for u in uploads]+[0]),
                       "raw_read_calls":sum(u["chunks"] for u in uploads)},
            "protocol":{"read_chunk_script":"scripts/publication_blob_chunk.py",
                        "stdout_hard_ceiling_observed_chars":1048576,
                        "chunk_stdout_chars":1000000,"read_tool_max_output_tokens":300000,
                        "maximum_parallel_chunk_reads":4,
                        "instructions":"Upload each unique SHA once; verify returned SHA. Create tree on base_tree_sha; verify expected_tree_sha. Create one commit with parent base_commit_sha. update_ref force=false, expected_sha=base_commit_sha only after review freeze. No credentials are required or handled by these scripts."}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-ref",required=True,help="Reviewed and frozen local release commit SHA")
    p.add_argument("--base-ref",default=BASE)
    p.add_argument("--branch",default="codex/complete-ring-deliverables")
    p.add_argument("--output",required=True,type=Path,help="Scratch manifest destination")
    args=p.parse_args();manifest=prepare(args.source_ref,args.base_ref,args.branch)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"manifest":str(args.output),**manifest["summary"]},ensure_ascii=False))


if __name__=="__main__": main()
