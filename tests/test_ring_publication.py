import json
import hashlib
from pathlib import Path
import pytest

from hanjie.reporting.publication import fingerprints, image_dependencies, verify_publication, validate_ring_production_release, validate_ring_geometry_identity


def test_same_version_geometry_change_cannot_reseal_old_engineering(tmp_path):
    step=tmp_path/'cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step'
    step.parent.mkdir(parents=True)
    entity=b'\n#1=PART(40.0);\n'
    step.write_bytes(b'HEADER;old-date;ENDSEC;DATA;'+entity+b'ENDSEC;')
    canonical=hashlib.sha256(b''.join(entity.split())).hexdigest()
    structure={'input_identity':{'geometry_DATA_sha256':canonical}}
    manufacture={'thermal_result':{'mesh':{'cache_key':{'cad_data_sha256':hashlib.sha256(entity).hexdigest()}}}}
    for level in ('coarse','medium'):
        path=tmp_path/f'simulation/ring-baseline-manufacturing/results/{level}/cold-response.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'mesh':{'current_precoat_STEP_DATA_sha256':canonical}}))
    validate_ring_geometry_identity(tmp_path,structure,manufacture)
    step.write_bytes(b'HEADER;new-date;ENDSEC;DATA;'+entity+b'ENDSEC;')
    validate_ring_geometry_identity(tmp_path,structure,manufacture)
    step.write_bytes(b'HEADER;new-date;ENDSEC;DATA;'+entity.replace(b'40.0',b'41.0')+b'ENDSEC;')
    with pytest.raises(ValueError,match='geometry differs'):
        validate_ring_geometry_identity(tmp_path,structure,manufacture)


def test_old_object_and_truthy_strings_cannot_authorize_ring_production():
    names = ('nominal_geometry_valid', 'precoat_geometry_valid',
             'current_route_fusion_verified', 'residual_position_verified',
             'bore_size_verified', 'complete_strength_verified', 'actual_capacity_verified')
    qualified = dict(physical_object='complete_ring', process_version='R2',
                     production_release=True, primary_baseline_verification=dict.fromkeys(names, True))
    validate_ring_production_release(qualified, 'R2')
    for change in ({'physical_object': 'eight_wing'}, {'process_version': 'old'},
                   {'production_release': 'true'}, {'production_release': False}):
        with pytest.raises(ValueError, match='完整圆环'):
            validate_ring_production_release({**qualified, **change}, 'R2')
    for missing in names:
        gates = {**qualified['primary_baseline_verification'], missing: 'true'}
        with pytest.raises(ValueError, match='完整圆环'):
            validate_ring_production_release({**qualified, 'primary_baseline_verification': gates,
                                              'historical_eight_wing': {'all_checks_passed': True}}, 'R2')


def sealed(tmp_path):
    (tmp_path/'output/pdf').mkdir(parents=True)
    source=tmp_path/'assessment.json'
    output=tmp_path/'output/pdf/report.pdf'
    source.write_text('{"process_version":"R2","axis_um":31.0}')
    output.write_bytes(b'%PDF-test-rendered')
    record={'process_version':'R2','sources':fingerprints(tmp_path,[source]),
            'outputs':fingerprints(tmp_path,[output])}
    (tmp_path/'output/pdf/ring-publication-build.json').write_text(json.dumps(record))
    return source,output


def test_same_version_engineering_change_requires_rerender(tmp_path):
    source,_=sealed(tmp_path)
    verify_publication(tmp_path,'R2')
    source.write_text('{"process_version":"R2","axis_um":33.0}')
    with pytest.raises(ValueError,match='changed since rendering'):
        verify_publication(tmp_path,'R2')


def test_output_replacement_and_stale_version_are_rejected(tmp_path):
    _,output=sealed(tmp_path)
    with pytest.raises(ValueError,match='version is stale'):
        verify_publication(tmp_path,'R3')
    output.write_bytes(b'%PDF-old-delivery')
    with pytest.raises(ValueError,match='changed since rendering'):
        verify_publication(tmp_path,'R2')


def test_local_images_are_part_of_render_dependencies(tmp_path):
    (tmp_path/'docs').mkdir()
    image=tmp_path/'docs/field.png'
    image.write_bytes(b'image')
    document=tmp_path/'docs/report.md'
    document.write_text('![场](field.png)')
    assert image_dependencies(tmp_path,[document])==[image]
    pointer=tmp_path/'missing.step'
    pointer.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 100\n')
    with pytest.raises(ValueError,match='unresolved LFS pointer'):
        fingerprints(tmp_path,[pointer])
