from pathlib import Path
import yaml


ROOT = Path(__file__).parents[1]


def test_competition_r3_has_single_process_authority():
    process_history = yaml.safe_load((ROOT / "project/process.yaml").read_text(encoding="utf-8"))
    process_r3 = yaml.safe_load((ROOT / "project/process-r3.yaml").read_text(encoding="utf-8"))
    design = yaml.safe_load((ROOT / "project/competition-design.yaml").read_text(encoding="utf-8"))

    assert process_history["authority"] == "历史诊断基线（非COMPETITION-R3权威源）"
    assert design["process_source"] == "project/process-r3.yaml"

    p = process_r3["process"]["nominal"]
    d = design["process"]
    t = design["thermal_regime"]

    # 当前竞赛方案中仍保留的派生/索引字段必须与唯一工艺源一致，
    # 防止“process-r3.yaml 改了、design.yaml 没改”再次发生参数漂移。
    assert d["pass_count"] == 2
    assert d["wire_diameter_mm"] == p["filler_diameter_mm"] == 1.6
    assert d["feed_nominal_mm_s"] == p["filler_feed_rate_mm_s"] == 3.5
    assert t["start_temperature_c"] == p["preheat_c"] == 20.0
    assert t["interpass_limit_c"] == p["interpass_limit_c"] == 100.0

    assert p["current_a"] == 75.0
    assert p["voltage_v"] == 12.0
    assert p["travel_speed_mm_s"] == 1.65
    assert p["pulse_peak_a"] == 100
    assert p["pulse_base_a"] == 50
    assert p["pulse_duty"] == 0.5
    assert p["pulse_frequency_hz"] == 20
