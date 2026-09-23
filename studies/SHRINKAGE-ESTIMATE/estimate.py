"""基于TWI经验规则的角焊缝收缩量级筛查；不替代热—结构求解或实测。"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]

# TWI Job Knowledge 33 给出：焊脚不超过板厚3/4时，角焊缝横向收缩约0.8 mm/焊缝；
# 纵向收缩约0.8 mm/3 m焊缝。本题3.5/5=0.70，满足该经验规则的几何前提。
SEGMENTS = 6
SEGMENT_LENGTH_MM = 18.0
PLATE_THICKNESS_MM = 5.0
FILLET_LEG_MM = 3.5
TRANSVERSE_PER_SEGMENT_MM = 0.8
LONGITUDINAL_PER_3M_MM = 0.8
ASYMMETRY_FRACTION = 0.02

transverse_free = SEGMENTS * TRANSVERSE_PER_SEGMENT_MM
longitudinal_free = SEGMENTS * SEGMENT_LENGTH_MM / 3000 * LONGITUDINAL_PER_3M_MM
payload = {
    "version": "SHRINKAGE-ESTIMATE-2",
    "evidence_level": "TWI_empirical_screening_rule",
    "source": {
        "title": "TWI Job Knowledge 33 - Distortion: types and causes",
        "url": "https://www.twi-global.com/technical-knowledge/job-knowledge/distortion-types-and-causes-033",
        "rule": "fillet transverse shrinkage 0.8 mm per weld when leg <= 3/4 plate thickness; longitudinal 0.8 mm per 3 m"
    },
    "inputs": {"segments": SEGMENTS, "segment_length_mm": SEGMENT_LENGTH_MM, "plate_thickness_mm": PLATE_THICKNESS_MM, "fillet_leg_mm": FILLET_LEG_MM, "leg_to_thickness": FILLET_LEG_MM / PLATE_THICKNESS_MM, "asymmetry_fraction": ASYMMETRY_FRACTION},
    "free_shrinkage_mm": {"transverse_total": transverse_free, "longitudinal_total": longitudinal_free},
    "residual_asymmetry_screen_mm": {"transverse": transverse_free * ASYMMETRY_FRACTION, "longitudinal": longitudinal_free * ASYMMETRY_FRACTION},
    "thermal_allowance_comparison_mm": 0.0102,
    "exceeds_thermal_allowance_possible": transverse_free * ASYMMETRY_FRACTION > 0.0102,
    "decision": "横向收缩的2%不对称筛查已超过0.0102 mm，因此采用焊后终加工主路线；TWI经验规则针对钢件，QT450-10/Q235B异种接头仍须小试校准"
}
OUT = ROOT / "studies/SHRINKAGE-ESTIMATE/results/estimate.json"
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
