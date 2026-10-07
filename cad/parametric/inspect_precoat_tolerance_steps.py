"""Reopen exported tolerance STEP files and check solid validity independently."""
import json
from pathlib import Path
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'cad/generated/precoat-tolerance-family-20261007'


def main():
    audit_path = DIRECTORY / 'geometry-and-feed-audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf8'))
    checks = []
    for case in audit['cases']:
        reader = STEPControl_Reader()
        path = DIRECTORY / (case['case'] + '.step')
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise RuntimeError(f'Cannot read {path}')
        reader.TransferRoots()
        shape = reader.OneShape()
        explorer = TopExp_Explorer(shape, TopAbs_SOLID)
        count, valid = 0, True
        while explorer.More():
            count += 1
            valid = valid and BRepCheck_Analyzer(explorer.Current()).IsValid()
            explorer.Next()
        if count != 17 or not valid:
            raise RuntimeError(f'{path.name}: {count} solids, validity {valid}')
        checks.append(dict(case=case['case'], solids=count, all_solids_valid=valid))
    audit['exported_STEP_reopen_check'] = checks
    audit['maximum_absolute_partition_closure_mm3'] = max(abs(c['partition_closure_mm3']) for c in audit['cases'])
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(cases=len(checks), solids_per_case=17, all_valid=True,
                         maximum_closure_mm3=audit['maximum_absolute_partition_closure_mm3'])))


if __name__ == '__main__':
    main()
