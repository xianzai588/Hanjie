"""Bind a rendered publication to its engineering inputs and output bytes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


def validate_ring_production_release(status: dict, process_version: str) -> None:
    """Only the active object's qualified gates can authorize production text."""
    gates = status.get('primary_baseline_verification', {})
    required = ('nominal_geometry_valid', 'precoat_geometry_valid',
                'current_route_fusion_verified', 'residual_position_verified',
                'bore_size_verified', 'complete_strength_verified',
                'actual_capacity_verified')
    if (status.get('physical_object') != 'complete_ring'
            or status.get('process_version') != process_version
            or status.get('production_release') is not True
            or any(gates.get(name) is not True for name in required)):
        raise ValueError('当前完整圆环尚未取得生产放行资格；使用--competition-entry生成参赛设计稿')


def validate_ring_geometry_identity(root: Path, structure: dict, manufacturing: dict) -> None:
    """Reject same-version result reuse after the active STEP entities change."""
    step = root/'cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step'
    entities = step.read_bytes().split(b'DATA;', 1)[1].split(b'ENDSEC;', 1)[0]
    canonical = hashlib.sha256(b''.join(entities.split())).hexdigest()
    raw = hashlib.sha256(entities).hexdigest()
    if structure.get('input_identity', {}).get('geometry_DATA_sha256') != canonical:
        raise ValueError('Current ring structure geometry differs from rendered STEP; rerun the requested calculation')
    if manufacturing['thermal_result']['mesh']['cache_key']['cad_data_sha256'] != raw:
        raise ValueError('Current ring thermal geometry differs from rendered STEP; rerun the requested calculation')
    for level in ('coarse', 'medium'):
        cold = json.loads((root/f'simulation/ring-baseline-manufacturing/results/{level}/cold-response.json').read_text())
        if cold['mesh']['current_precoat_STEP_DATA_sha256'] != canonical:
            raise ValueError('Current ring cold-response geometry differs from rendered STEP: '+level)


def fingerprints(root: Path, paths: list[Path]) -> dict[str, str]:
    result = {}
    for path in paths:
        path = path.resolve()
        name = path.relative_to(root.resolve()).as_posix()
        data = path.read_bytes()
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError('Publication dependency is an unresolved LFS pointer: '+name)
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def image_dependencies(root: Path, documents: list[Path]) -> list[Path]:
    images = []
    for document in documents:
        for relative in re.findall(r'!\[[^]]*\]\(([^)]+)\)', document.read_text(encoding='utf8')):
            if relative.startswith(('http://','https://')):
                raise ValueError('Publication requires a local image: '+relative)
            path = root/relative
            if not path.is_file():
                path = document.parent/relative
            images.append(path)
    return images


def verify_publication(root: Path, process_version: str) -> dict:
    record = json.loads((root/'output/pdf/ring-publication-build.json').read_text(encoding='utf8'))
    if record.get('process_version') != process_version:
        raise ValueError('PDF publication version is stale')
    for group in ('sources','outputs'):
        if not record.get(group):
            raise ValueError('PDF publication has no dependency ledger: '+group)
        for name, expected in record[group].items():
            path = (root/name).resolve()
            path.relative_to(root.resolve())
            if fingerprints(root,[path])[name] != expected:
                raise ValueError('PDF source/output changed since rendering: '+name)
    return record
