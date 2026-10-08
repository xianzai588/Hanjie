"""Publish a large ZIP in bounded Git blobs and restore it with SHA256 checks."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
PARTS = HERE / 'package-parts'
ARCHIVE = HERE / '焊接固定题-参赛设计报告包.zip'
PART_BYTES = 8 * 1024 * 1024


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def split_package(archive=ARCHIVE):
    archive = Path(archive)
    record = {'schema': 'hanjie-package-volumes-v1', 'archive_name': archive.name,
              'bytes': archive.stat().st_size, 'sha256': digest(archive), 'parts': []}
    with tempfile.TemporaryDirectory(prefix='package-volumes-', dir=HERE) as staging:
        stage = Path(staging) / 'parts'
        stage.mkdir()
        with archive.open('rb') as stream:
            for index, block in enumerate(iter(lambda: stream.read(PART_BYTES), b''), 1):
                name = f'part-{index:03d}.bin'
                (stage / name).write_bytes(block)
                record['parts'].append({'file': name, 'bytes': len(block),
                                        'sha256': hashlib.sha256(block).hexdigest()})
        if sum(row['bytes'] for row in record['parts']) != record['bytes']:
            raise ValueError('Archive changed while splitting')
        (stage / 'manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
        if PARTS.exists():
            shutil.rmtree(PARTS)
        os.replace(stage, PARTS)
    return record


def restore_package(output=ARCHIVE):
    output = Path(output)
    record = json.loads((PARTS / 'manifest.json').read_text())
    if record.get('schema') != 'hanjie-package-volumes-v1' or not record.get('parts'):
        raise ValueError('Missing or unsupported package volume manifest')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.rebuilding.zip')
    try:
        combined = hashlib.sha256()
        size = 0
        with temporary.open('wb') as target:
            for index, row in enumerate(record['parts'], 1):
                if row['file'] != f'part-{index:03d}.bin':
                    raise ValueError('Unexpected volume path or order')
                part = PARTS / row['file']
                if part.stat().st_size != row['bytes'] or digest(part) != row['sha256']:
                    raise ValueError('Missing or corrupt package volume: '+row['file'])
                with part.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        target.write(block)
                        combined.update(block)
                        size += len(block)
        if size != record['bytes'] or combined.hexdigest() != record['sha256']:
            raise ValueError('Restored archive differs from the release SHA256')
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Restored archive failed ZIP CRC verification')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', action='store_true')
    parser.add_argument('--output', type=Path, default=ARCHIVE)
    args = parser.parse_args()
    if args.split:
        result = split_package()
        print(json.dumps({'parts': len(result['parts']), 'bytes': result['bytes'],
                          'sha256': result['sha256']}))
    else:
        print(restore_package(args.output))
