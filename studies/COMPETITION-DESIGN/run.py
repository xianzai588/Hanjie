"""重建参赛修订计算和名义装配实体，校验失败时禁止生成可用结果。"""
from pathlib import Path
import csv
import json
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from hanjie.domain.competition_design import run_design
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

ROOT = Path(__file__).resolve().parents[2]

# OCC 会把导出时刻写进 STEP 头部 FILE_NAME，使同几何重建得到仅差时间戳的新内容；
# 该文件由 Git LFS 托管且登记进 SHA256 冻结记录，因此把时间戳归一化为固定值，
# 保证几何不变时产物逐字节一致，避免每次都向 LFS 写入一个仅时间戳不同的新对象。
STEP_TIMESTAMP_EPOCH = b"1970-01-01T00:00:00"


def normalize_step_timestamp(path: Path, epoch: bytes = STEP_TIMESTAMP_EPOCH) -> None:
    """把 STEP 头部 FILE_NAME 的导出时间替换为固定值；按字节处理以保证除该字段外零改动。"""
    data = path.read_bytes()
    patched, count = re.subn(rb"(FILE_NAME\('[^']*',')([^']*)(')", rb"\g<1>" + epoch + rb"\g<3>", data, count=1)
    if count != 1:
        raise ValueError(f"未能在 STEP 头部找到唯一的 FILE_NAME 时间戳：{path}")
    path.write_bytes(patched)


def fixed(value):
    """CSV 定点输出：抑制二进制浮点表示噪声（如 0.04360000000000001），保留双精度有效位。"""
    return f"{value:.15g}" if isinstance(value, float) else value


def main():
    result, bodies, _ = run_design(ROOT)
    # 公差分配本身不是残余变形证据；仅将完整三算例通过后的
    # 数值结果绑定到当前设计，实物工艺评定仍单列。
    numerical_dir = ROOT / "simulation/competition-r4/results"
    verification_files = {
        "position": "verification.json",
        "static_service": "service-verification.json",
        "process_temperature": "process-temperature-verification.json",
    }
    if all((numerical_dir/name).exists() for name in verification_files.values()):
        verification = {key: json.loads((numerical_dir/name).read_text(encoding="utf-8"))
                        for key, name in verification_files.items()}
        accepted = (verification["position"]["position_design_pass"]
                    and verification["position"].get("bore_size_design_pass",False)
                    and verification["static_service"]["static_service_design_pass"]
                    and verification["process_temperature"]["process_temperature_design_pass"])
        current_geometry = all(
            Path(json.loads((numerical_dir/case/"input.json").read_text(encoding="utf-8"))["seat_geometry"]).name
            == "8P-R2-t15.step" for case in verification["position"]["cases"])
        thermal_fixture=all(json.loads((numerical_dir/case/"input.json").read_text(encoding="utf8")).get('fixture_thermal')
                            for case in verification["position"]["cases"])
        if accepted and current_geometry and thermal_fixture:
            result["precision"].update({
                "thermal_residual_design_verified": True,
                "verified_thermal_position_mm": verification["position"]["thermal_position_worst_mm"],
                "verified_position_budget_mm": verification["position"]["position_budget_mm"],
            })
            result["release"].update({
                "design_verified": True,
                "design_verification_scope": "current 15 mm CAD; cold residual position, incremental static service envelope and segment-start temperature under declared numerical inputs",
                "physical_validation_recommended": True,
                "product_conformity_claimed": False,
            })
            result["numerical_verification"] = verification
    g = result["geometry"]
    checks = [all(g["shape_validity"].values()), g["bottom_route_allowed"],
              all(row["clear"] for row in g["poses"]), g["torch_feed_intersection_mm3"] < 1e-6,
              g["torch_feed_clearance_mm"] >= 1.5,
              max(g["cartridge_intersections_mm3"].values()) < 1e-6,
              result["precision"]["design_budget_closes"],
              max(g["witness_intersections_mm3"].values())<1e-6,
              g["witness_minimum_clearance_mm"]>=.2]
    if not all(checks):
        raise ValueError("参赛设计内部检查未通过："+json.dumps(result, ensure_ascii=False))
    out = ROOT / "studies/COMPETITION-DESIGN/results"
    cad = ROOT / "cad/generated/competition-design"
    out.mkdir(parents=True, exist_ok=True)
    cad.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    for shape in bodies.values():
        if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
            raise ValueError("STEP转换失败")
    assembly = cad / "competition-assembly-r4.step"
    staging = assembly.with_name('competition-assembly-new.step')
    if writer.Write(str(staging)) != IFSelect_RetDone:
        raise ValueError("STEP写入失败")
    staging.replace(assembly)
    normalize_step_timestamp(assembly)
    (out / "assessment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "result.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["category", "metric", "value"])
        for category in ("process", "precision", "fixture"):
            for key, value in result[category].items():
                if isinstance(value, (float, int, bool)):
                    writer.writerow([category, key, fixed(value)])
    print(json.dumps({"process":result["process"], "precision":result["precision"],
                      "torch_feed_gap_mm":g["torch_feed_clearance_mm"],"checks":checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
