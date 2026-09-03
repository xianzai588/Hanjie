"""
统一参数化轴承座几何生成器

用途：
- 为 P1A 结构静刚度公平筛选生成 7 个三维模型
- 确保除拓扑参数 N 和公平族定义外，所有几何由统一规则产生
- 避免人为独立修模导致的比较不公平

原则：
- 禁止手工绘制
- 所有模型由此脚本生成
- 几何规则可重复、可审查
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import json
from datetime import datetime
from pathlib import Path
import math


# 统一参数定义（V4 冻结）
@dataclass
class UnifiedParameters:
    """统一几何参数（所有模型共享）"""

    # 壳体（题面固定）
    shell_outer_diameter: float = 160.0  # mm
    shell_height: float = 200.0  # mm
    shell_thickness: float = 5.0  # mm

    # 轴承座（V4 设计）
    bearing_bore_diameter: float = 40.000  # mm，名义尺寸（FE用）
    seat_thickness: float = 12.0  # mm
    seat_outer_radius: float = 74.98  # mm
    seat_core_diameter: float = 82.0  # mm

    # 槽（V4 设计）
    slot_width: float = 4.0  # mm
    slot_root_radius: Optional[float] = None  # mm，待 Phase 1 确定

    # 材料（V4 冻结）
    material_qr450_density: float = 7200.0  # kg/m³
    material_q235_density: float = 7850.0  # kg/m³


@dataclass
class GeometryManifest:
    """几何清单（每个模型输出）"""

    model_id: str
    family: str  # 'FAIR_A' / 'FAIR_B' / 'Continuous'
    layout: str  # '4P' / '6P' / '8P' / 'Continuous'
    N: int  # 连接点数量，0=Continuous

    # 壳体
    shell: Dict[str, float]

    # 轴承座
    seat: Dict[str, Any]

    # 几何属性
    geometry: Dict[str, Optional[float]]

    # 制造属性
    manufacturing: Dict[str, Optional[int]]

    # 生成信息
    generation: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def to_json(self, filepath: Path) -> None:
        """保存为 JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


class BearingSeatGenerator:
    """统一参数化轴承座生成器"""

    def __init__(self, params: UnifiedParameters):
        self.params = params
        self.version = "1.0"

    def generate(
        self,
        N: int,
        family: str,
        wing_width_each: Optional[float] = None
    ) -> GeometryManifest:
        """
        生成轴承座几何

        Parameters:
        -----------
        N : int
            连接点数量（4/6/8）或 0（Continuous）
        family : str
            公平族（'FAIR_A' / 'FAIR_B' / 'Continuous'）
        wing_width_each : float, optional
            每个翼的有效连接宽度（mm）
            - FAIR-A: 根据 N 计算（总和 = 108 mm）
            - FAIR-B: 固定 18 mm
            - Continuous: None

        Returns:
        --------
        manifest : GeometryManifest
            几何清单
        """

        # 验证输入
        if family == 'Continuous':
            assert N == 0, "Continuous must have N=0"
            layout = 'Continuous'
        else:
            assert N in [4, 6, 8], "N must be 4, 6, or 8"
            layout = f'{N}P'

        # 确定 wing_width_each
        if family == 'FAIR_A':
            total_width = 108.0  # mm
            wing_width_each = total_width / N
        elif family == 'FAIR_B':
            wing_width_each = 18.0  # mm
        elif family == 'Continuous':
            wing_width_each = None
        else:
            raise ValueError(f"Unknown family: {family}")

        # 生成模型 ID
        model_id = f"{layout}-{family}" if family != 'Continuous' else 'Continuous'

        # 创建清单
        manifest = GeometryManifest(
            model_id=model_id,
            family=family,
            layout=layout,
            N=N,
            shell={
                'outer_diameter_mm': self.params.shell_outer_diameter,
                'height_mm': self.params.shell_height,
                'thickness_mm': self.params.shell_thickness
            },
            seat={
                'bore_nominal_diameter_mm': self.params.bearing_bore_diameter,
                'thickness_mm': self.params.seat_thickness,
                'outer_radius_mm': self.params.seat_outer_radius,
                'core_diameter_mm': self.params.seat_core_diameter,
                'slot_width_mm': self.params.slot_width if N > 0 else None,
                'slot_root_radius_mm': self.params.slot_root_radius if N > 0 else None,
                'effective_width_each_mm': wing_width_each,
                'effective_total_width_mm': wing_width_each * N if N > 0 else None
            },
            geometry={
                'planform_area_mm2': None,  # 待计算
                'solid_volume_mm3': None,  # 待计算
                'calculated_mass_kg': None  # 待计算
            },
            manufacturing={
                'slot_count': N if N > 0 else 0,
                'weld_segment_count': N if N > 0 else None,
                'nominal_total_weld_length_mm': None  # 待计算
            },
            generation={
                'generator_version': self.version,
                'timestamp': datetime.now().isoformat(),
                'rule': 'unified_parametric'
            }
        )

        # FAIR-A 断言
        if family == 'FAIR_A':
            total_width_check = manifest.seat['effective_total_width_mm']
            assert abs(total_width_check - 108.0) < 1e-6, \
                f"FAIR-A total width must be 108 mm, got {total_width_check}"

        # FAIR-B 断言
        if family == 'FAIR_B':
            width_each_check = manifest.seat['effective_width_each_mm']
            assert abs(width_each_check - 18.0) < 1e-6, \
                f"FAIR-B each width must be 18 mm, got {width_each_check}"

        return manifest

    def generate_all_p1a_models(self) -> Dict[str, GeometryManifest]:
        """生成 P1A 所有 7 个模型清单"""

        models = {}

        # Continuous
        models['Continuous'] = self.generate(N=0, family='Continuous')

        # FAIR-A: 4/6/8P
        for N in [4, 6, 8]:
            key = f'{N}P-FAIR-A'
            models[key] = self.generate(N=N, family='FAIR_A')

        # FAIR-B: 4/6/8P
        for N in [4, 6, 8]:
            key = f'{N}P-FAIR-B'
            models[key] = self.generate(N=N, family='FAIR_B')

        return models


def validate_geometry_manifest(manifest: GeometryManifest) -> Dict[str, bool]:
    """
    验证几何清单

    Returns:
    --------
    checks : dict
        检查结果
    """
    checks = {}

    # 基本字段存在性
    checks['has_model_id'] = bool(manifest.model_id)
    checks['has_family'] = manifest.family in ['FAIR_A', 'FAIR_B', 'Continuous']
    checks['has_layout'] = bool(manifest.layout)

    # N 值合理性
    if manifest.family == 'Continuous':
        checks['N_valid'] = manifest.N == 0
    else:
        checks['N_valid'] = manifest.N in [4, 6, 8]

    # 壳体参数
    checks['shell_od_valid'] = manifest.shell['outer_diameter_mm'] == 160.0
    checks['shell_height_valid'] = manifest.shell['height_mm'] == 200.0
    checks['shell_thickness_valid'] = manifest.shell['thickness_mm'] == 5.0

    # 轴承座参数
    checks['bore_valid'] = manifest.seat['bore_nominal_diameter_mm'] == 40.0
    checks['thickness_valid'] = manifest.seat['thickness_mm'] == 12.0
    checks['outer_radius_valid'] = manifest.seat['outer_radius_mm'] == 74.98

    # FAIR-A 特定检查
    if manifest.family == 'FAIR_A':
        total_width = manifest.seat.get('effective_total_width_mm')
        checks['fair_a_total_width'] = abs(total_width - 108.0) < 1e-6 if total_width else False

    # FAIR-B 特定检查
    if manifest.family == 'FAIR_B':
        width_each = manifest.seat.get('effective_width_each_mm')
        checks['fair_b_each_width'] = abs(width_each - 18.0) < 1e-6 if width_each else False

    return checks


def main():
    """生成 P1A 所有模型清单"""

    # 创建统一参数（槽根圆角待 Phase 1 确定）
    params = UnifiedParameters(slot_root_radius=None)

    # 创建生成器
    generator = BearingSeatGenerator(params)

    # 生成所有模型清单
    print("Generating P1A model manifests...")
    models = generator.generate_all_p1a_models()

    # 输出目录
    output_dir = Path(__file__).parent / 'configs'
    output_dir.mkdir(exist_ok=True)

    # 保存每个模型清单
    for model_id, manifest in models.items():
        filepath = output_dir / f'{model_id}.json'
        manifest.to_json(filepath)
        print(f"  Generated: {filepath.name}")

    # 验证所有清单
    print("\nValidating manifests...")
    all_valid = True
    for model_id, manifest in models.items():
        checks = validate_geometry_manifest(manifest)
        failed_checks = [k for k, v in checks.items() if not v]
        if failed_checks:
            print(f"  [FAIL] {model_id}: Failed checks: {failed_checks}")
            all_valid = False
        else:
            print(f"  [PASS] {model_id}: All checks passed")

    # 输出汇总表
    print("\nModel summary:")
    print(f"{'Model ID':<20} {'Family':<12} {'N':<4} {'Width Each':<12} {'Total Width':<12}")
    print("-" * 80)
    for model_id, manifest in models.items():
        width_each = manifest.seat.get('effective_width_each_mm')
        total_width = manifest.seat.get('effective_total_width_mm')
        width_each_str = f"{width_each:.1f}" if width_each else "N/A"
        total_width_str = f"{total_width:.1f}" if total_width else "N/A"
        print(f"{model_id:<20} {manifest.family:<12} {manifest.N:<4} {width_each_str:<12} {total_width_str:<12}")

    if all_valid:
        print("\n[SUCCESS] All manifests valid. Ready for Phase 1 geometry modeling.")
        return 0
    else:
        print("\n[ERROR] Some manifests invalid. Fix errors before proceeding.")
        return 1


if __name__ == '__main__':
    exit(main())
