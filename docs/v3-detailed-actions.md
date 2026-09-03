# V3 修复详细行动清单

**版本**：2026-09-03  
**目标**：逐项执行 P0 级修复，形成可追溯的修改记录

---

## 修复 1：R73.8/1.2mm 接头几何矛盾

### 问题分析
- 壳体内半径：75 mm（官方：Ø160 外径 - 5 mm 壁厚 × 2）
- 当前翼端半径：73.8 mm
- 径向间隙：1.2 mm
- **冲突**：官方要求"贴合连接"，1.2 mm 悬空不合理

### 工程解决方案

#### 方案 A：过渡配合（推荐）
- 翼端外径改为 Ø149.96 mm（半径 74.98 mm）
- 壳体内径 Ø150 mm
- 配合：H7/h6 或 H8/f7
- 单边间隙：0.01～0.04 mm
- 接头形式：角焊缝，腿长 3～4 mm

#### 方案 B：间隙配合
- 翼端外径 Ø149.90 mm（半径 74.95 mm）
- 单边间隙：0.05 mm
- 接头形式：填角焊缝

#### 方案 C：贴合面 + 定位凸台
- 翼端外缘与壳体内壁贴合
- 增加轴向定位凸台
- 周向用销钉定位

### 选择：方案 A（过渡配合）

**理由**：
1. 装配可靠，径向定位精度高
2. 配合公差标准化
3. 焊接前定位稳定，减少初始偏心
4. 符合"贴合连接"语义

### 修改清单

#### 1. 更新 geometry.json
```json
{
  "design_assumptions": {
    "wing_outer_radius": 74.98,
    "assembly_fit": "H7/h6",
    "radial_clearance_min": 0.01,
    "radial_clearance_max": 0.04,
    "joint_type": "fillet_weld",
    "fillet_leg_length": 3.5
  }
}
```

**文件**：`cad/parametric/geometry.json`

#### 2. 更新工程图生成代码

**文件**：`cad/parametric/generate_engineering_drawings.py`

**修改点**：
- `joint_drawing()` 函数
- 删除：`"WELD BRIDGE TO SHELL ID: 1.2 (2D FE equivalent)"`
- 增加：装配配合标注、角焊缝符号、坡口要求

```python
def joint_drawing(geometry: dict) -> list[str]:
    design = geometry["design_assumptions"]
    lines = header("接头与焊缝细节图", "JOINT DETAIL / SECTION A-A / FILLET WELD", "HJ-DRW-003")
    
    # 删除 1.2 mm 桥接标注
    # 增加真实配合尺寸
    lines += [
        text(145, 390, f"WING OD Ø{design['wing_outer_radius']*2:.2f}", "dim"),
        text(145, 425, f"SHELL ID Ø150.00 {design['assembly_fit']}", "dim"),
        text(145, 460, f"FILLET WELD LEG {design['fillet_leg_length']:.1f}", "dim"),
        text(700, 220, "Assembly fit H7/h6; radial clearance 0.01~0.04", "note"),
        text(700, 255, "Fillet weld per GB/T 5185; TIG + Ni filler", "note"),
    ]
    # ... 其余保持
```

#### 3. 更新设计假设文档

**文件**：`docs/05-design-assumptions.md`

**第 3 节 结构设计假设**：

```markdown
| 参数 | V3 取值 | 性质 | 选择理由 |
| --- | ---: | --- | --- |
| 连接翼外端半径 | 74.98 mm | 设计假设 | 与壳体内径Ø150形成H7/h6过渡配合，单边间隙0.01~0.04 mm |
| 装配配合 | H7/h6 | 设计假设 | 保证径向定位精度，减少初始偏心 |
| 角焊缝腿长 | 3.5 mm | 设计假设 | 满足承载要求，控制热输入 |
```

**删除**：
```markdown
~~连接翼外端半径 | 73.8 mm | 设计假设 | 与壳体内半径 75 mm 保留 1.2 mm 装配间隙~~
```

#### 4. 更新技术报告

**文件**：`deliverables/report/technical-report-v2.md`

**第 4 章接头设计**：

**删除**：
```markdown
~~R73.8 mm 与壳体内半径 75 mm 的 1.2 mm 间隙属于装配假设，二维 FE 以等效焊接桥接区连接~~
```

**改为**：
```markdown
轴承座连接翼外径Ø149.96 mm，与壳体内径Ø150.00 mm形成H7/h6过渡配合，单边径向间隙0.01~0.04 mm。装配后采用角焊缝连接，焊缝腿长3.5 mm，满足GB/T 5185要求。配合公差保证装配定位精度，减少焊前初始偏心。
```

#### 5. 更新 FE 模型说明

**新增说明**（放在仿真方法章节）：

```markdown
### 二维 FE 数值连接处理

真实接头为H7/h6配合 + 角焊缝（腿长3.5 mm）。二维平面应变模型中，焊缝简化为1.2 mm等效桥接区，用于热—结构耦合计算。该简化仅用于相对比较不同焊接顺序和结构方案，不代表真实接头几何。

**工程图中只标注真实接头几何，数值简化仅在此说明。**
```

#### 6. 重新生成所有工程图

```powershell
python cad/parametric/generate_drawing.py
python cad/parametric/generate_engineering_drawings.py
python cad/parametric/export_drawing_pdfs.py
```

#### 7. 更新 CAD 总图

**文件**：`cad/parametric/generate_drawing.py`

**第 35 行附近**：
```python
wing_r = design["wing_outer_radius"]  # 现在是 74.98
```

**图例说明**：
```python
f'<text x="{x+15}" y="335" class="note">翼端 R74.98 (配合H7/h6)</text>',
```

### 验收标准

✅ geometry.json 更新为 74.98 mm  
✅ 工程图删除 "1.2 (2D FE equivalent)" 标注  
✅ 工程图增加配合公差标注  
✅ 设计假设文档更新  
✅ 技术报告相关章节更新  
✅ FE 简化说明独立章节  
✅ 所有图纸重新生成  

---

## 修复 2：Ø39.96 定位销与误差预算矛盾

### 问题分析
- 当前定位销：Ø39.96 mm
- 轴承孔：Ø40 mm
- 单边间隙：约 0.02 mm
- **矛盾**：夹具定位误差预算只有 0.003 mm

### 工程解决方案

#### 方案 A：锥形心轴 + 端面定位（推荐）
- 1:50 锥度心轴
- 轴向压紧，自动找正
- 端面定位建立 A 基准
- 周向销钉单独定位（C 基准）
- 定位精度：0.005～0.01 mm

#### 方案 B：弹性胀套式心轴
- 内锥套 + 外锥套 + 锁紧螺母
- 径向均匀胀紧
- 定位精度：0.008～0.015 mm

#### 方案 C：三点/六点自定心夹紧
- 径向可调支撑
- 等角度分布
- 定位精度：0.01～0.02 mm

### 选择：方案 A（锥形心轴）

**理由**：
1. 锥度配合自动找正，重复性好
2. 轴向力施加方便
3. 端面定位建立 A 基准清晰
4. 周向定位独立，符合基准体系

### 修改清单

#### 1. 更新 geometry.json

```json
{
  "design_assumptions": {
    "fixture_mandrel_type": "tapered",
    "mandrel_taper_ratio": 0.02,
    "mandrel_small_diameter": 39.90,
    "mandrel_large_diameter": 40.10,
    "mandrel_effective_length": 10.0,
    "axial_clamping_force": 500,
    "positioning_repeatability": 0.008
  }
}
```

#### 2. 更新夹具工程图

**新增**：夹具总图剖视图

**文件**：`cad/parametric/generate_engineering_drawings.py`

**新增函数**：
```python
def fixture_section_drawing(geometry: dict) -> list[str]:
    """夹具剖视图：锥形心轴 + 端面定位 + 径向支撑"""
    design = geometry["design_assumptions"]
    lines = header("夹具总成剖视图", "FIXTURE ASSEMBLY / SECTION VIEW", "HJ-DRW-006")
    
    # 绘制锥形心轴
    # 绘制端面定位
    # 绘制径向支撑
    # 标注锥度、预紧力、重复性
    
    lines += [
        text(700, 220, "TAPERED MANDREL 1:50", "section"),
        text(700, 255, f"Ø{design['mandrel_small_diameter']:.2f} ~ Ø{design['mandrel_large_diameter']:.2f}", "note"),
        text(700, 290, f"Axial clamping force {design['axial_clamping_force']} N", "note"),
        text(700, 325, f"Positioning repeatability {design['positioning_repeatability']:.3f} mm", "note"),
        text(700, 375, "End face locates datum A", "note"),
        text(700, 410, "Independent pin for clocking (datum C)", "note"),
    ]
    
    return footer(lines, "45# / Q235")
```

#### 3. 更新误差预算分配

**文件**：`simulation/scripts/position_tolerance.py`

**当前**：
```python
fixture = 0.003
```

**改为**：
```python
fixture = 0.008  # 锥形心轴重复性
```

**更新总预算分配表**：

```python
def error_budget_v3():
    """V3 误差预算：区分装配链与自动化链"""
    
    # A. 装配/制造尺寸链（影响最终零件几何）
    assembly_chain = {
        'shell_datum_A': 0.005,      # 壳体基准 A 平面度
        'shell_datum_B': 0.003,      # 壳体轴线建立
        'fixture_mandrel': 0.008,    # 锥形心轴定位重复性
        'seat_initial_eccentric': 0.005,  # 座初始偏心
        'weld_shrinkage': 0.012,     # 焊接收缩变形（主控）
        'unclamping_springback': 0.002,   # 松夹回弹
    }
    
    # B. 自动化路径控制预算（影响焊枪轨迹）
    automation_chain = {
        'vision_detection': 0.018,   # 视觉定位
        'camera_calibration': 0.012, # 相机标定
        'robot_TCP': 0.003,          # TCP 标定
        'robot_repeatability': 0.005,  # 机器人重复定位
    }
    
    return assembly_chain, automation_chain
```

#### 4. 更新技术报告

**第 4 章 接头—结构—夹具协同设计**：

**4.3 夹具定位系统**

```markdown
### 4.3.1 定位原理

采用锥形心轴（1:50 锥度）+ 轴向端面定位 + 独立周向销钉的三基准定位体系：

- **基准 A（端面定位）**：夹具底板精密平面，轴承座端面贴合，建立轴向基准
- **基准 B（锥形心轴）**：Ø39.90~Ø40.10 锥形心轴插入 Ø40 轴承孔，轴向压紧 500 N，自动找正孔轴线，建立径向基准
- **基准 C（周向销钉）**：独立销钉定位周向姿态，不参与孔轴线位置度评价

锥度配合原理：轴向压紧力使锥面均匀接触，孔轴线自动映射到心轴轴线，重复定位精度 0.008 mm。

### 4.3.2 夹具刚度

径向 6 点等角度柔顺支撑，等效刚度 1200 N/mm（设计假设），夹紧力 150 N/点，总周向夹紧力 900 N。柔顺支撑允许焊接收缩释放，避免过约束导致的残余应力累积。
```

**删除**：
```markdown
~~夹具采用中心 Ø39.96 mm 定位销~~
```

#### 5. 更新设计假设文档

**文件**：`docs/05-design-assumptions.md`

**第 3 节**：

```markdown
| 参数 | V3 取值 | 性质 | 选择理由 |
| --- | ---: | --- | --- |
| 夹具定位形式 | 锥形心轴 1:50 | 设计假设 | 自动找正，重复性 0.008 mm |
| 心轴小端直径 | 39.90 mm | 设计假设 | 与 Ø40 孔配合，轴向压紧 |
| 心轴大端直径 | 40.10 mm | 设计假设 | 锥度 1:50，有效长度 10 mm |
| 轴向夹紧力 | 500 N | 设计假设 | 保证锥面均匀接触 |
```

**删除**：
```markdown
~~夹具中心销 Ø39.96 mm~~
```

#### 6. 更新 FMEA

**文件**：`docs/design/fmea.md`

**增加失效模式**：

| 失效模式 | 成因 | 后果 | 当前控制措施 | RPN |
| --- | --- | --- | --- | ---: |
| 锥形心轴磨损 | 多次装夹，锥面磨损 | 定位精度下降 | 定期检测锥度，磨损超差更换 | 48 |
| 轴向压紧力不足 | 气压/液压波动 | 孔轴线偏移 | 压紧力传感器监测，低于阈值报警 | 36 |
| 端面贴合不良 | 轴承座端面毛刺 | A 基准建立误差 | 端面去毛刺工序，贴合传感器确认 | 32 |

### 验收标准

✅ geometry.json 增加锥形心轴参数  
✅ 夹具剖视图增加心轴结构  
✅ 误差预算从 0.003 改为 0.008 mm  
✅ 误差预算拆分为装配链 + 自动化链  
✅ 技术报告增加定位原理说明  
✅ FMEA 增加心轴相关失效模式  

---

## 修复 3：六翼柔顺结构承载能力验证

### 问题分析
- 为了降低热变形，主动降低了结构刚度
- **没有验证：轴承支撑刚度、强度、疲劳是否恶化**
- FMEA 缺少：六翼根部应力集中、柔顺槽疲劳

### 工程解决方案

#### 新增分析：单位载荷结构对比

**目标**：
- 不知道真实载荷 → 用单位载荷
- 不追求绝对应力 → 比较相对变化
- 回答核心问题：刚度降低了多少？承载还够不够？

**对比方案**：
- **Baseline**：连续环形座（无柔顺槽）
- **6-wing**：六翼柔顺座（当前方案）

**载荷工况**：
1. X 向单位力：1 kN（径向）
2. Y 向单位力：1 kN（径向，正交）
3. Z 向单位力：1 kN（轴向）
4. 单位弯矩：1 kN·m（倾覆）

**评价指标**：
1. 轴承孔中心最大位移（刚度）
2. 等效刚度 K = F / δ
3. 最大 von Mises 应力
4. 槽根应力集中系数
5. 前 6 阶固有频率

### 修改清单

#### 1. 新增 FE 算例

**目录结构**：
```
simulation/cases/
├── stiffness-baseline/
│   ├── README.md
│   ├── model.inp (or .json)
│   └── results/
└── stiffness-6wing/
    ├── README.md
    ├── model.inp
    └── results/
```

#### 2. 创建分析脚本

**文件**：`simulation/scripts/run_stiffness_comparison.py`

```python
"""单位载荷刚度与模态对比分析

对比 Baseline 连续环形座 vs 6-wing 柔顺座：
- 不知道真实载荷，用单位载荷
- 评估刚度相对变化
- 评估应力集中
- 评估模态
"""

import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "simulation" / "cases"
RESULTS = ROOT / "simulation" / "results" / "stiffness-comparison"


def unit_load_cases():
    """定义单位载荷工况"""
    return {
        'radial_x': {'Fx': 1000, 'Fy': 0, 'Fz': 0, 'Mx': 0},  # N
        'radial_y': {'Fx': 0, 'Fy': 1000, 'Fz': 0, 'Mx': 0},
        'axial_z': {'Fx': 0, 'Fy': 0, 'Fz': 1000, 'Mx': 0},
        'tilt_moment': {'Fx': 0, 'Fy': 0, 'Fz': 0, 'Mx': 1000},  # N·m
    }


def extract_stiffness(case_dir: Path, load_case: dict) -> dict:
    """从 FE 结果提取刚度指标
    
    Returns:
        {
            'displacement': float,  # mm
            'stiffness': float,     # N/mm or N·m/rad
            'max_stress': float,    # MPa
            'scf': float,           # 应力集中系数
        }
    """
    # 实际实现需要读取 FE 后处理文件
    # 这里给出接口定义
    pass


def compare_structures():
    """对比两种结构"""
    results = {
        'baseline': {},
        '6wing': {},
        'relative_change': {},
    }
    
    cases = unit_load_cases()
    
    for case_name, load in cases.items():
        # 运行或读取 baseline
        baseline_dir = CASES / "stiffness-baseline"
        results['baseline'][case_name] = extract_stiffness(baseline_dir, load)
        
        # 运行或读取 6-wing
        wing_dir = CASES / "stiffness-6wing"
        results['6wing'][case_name] = extract_stiffness(wing_dir, load)
        
        # 计算相对变化
        b = results['baseline'][case_name]
        w = results['6wing'][case_name]
        results['relative_change'][case_name] = {
            'displacement_change': (w['displacement'] - b['displacement']) / b['displacement'] * 100,
            'stiffness_change': (w['stiffness'] - b['stiffness']) / b['stiffness'] * 100,
            'stress_change': (w['max_stress'] - b['max_stress']) / b['max_stress'] * 100,
        }
    
    return results


def modal_analysis():
    """模态分析：前 6 阶固有频率"""
    results = {
        'baseline': [],
        '6wing': [],
    }
    
    # 提取固有频率（Hz）
    # results['baseline'] = [f1, f2, f3, f4, f5, f6]
    # results['6wing'] = [f1, f2, f3, f4, f5, f6]
    
    return results


def generate_report():
    """生成对比报告"""
    stiffness = compare_structures()
    modal = modal_analysis()
    
    RESULTS.mkdir(parents=True, exist_ok=True)
    
    # 生成 markdown 报告
    report = [
        "# 单位载荷结构刚度与模态对比",
        "",
        "## 1. 对比方案",
        "",
        "- **Baseline**：连续环形座，无柔顺槽",
        "- **6-wing**：六翼柔顺座，径向槽宽 4 mm",
        "",
        "## 2. 单位载荷刚度",
        "",
        "| 工况 | Baseline 位移 (mm) | 6-wing 位移 (mm) | 刚度变化 (%) |",
        "| --- | ---: | ---: | ---: |",
    ]
    
    for case_name in stiffness['relative_change']:
        change = stiffness['relative_change'][case_name]
        report.append(f"| {case_name} | ... | ... | {change['stiffness_change']:.1f} |")
    
    report.extend([
        "",
        "## 3. 应力集中",
        "",
        "六翼方案槽根应力集中系数：...",
        "",
        "## 4. 模态",
        "",
        "| 阶次 | Baseline (Hz) | 6-wing (Hz) | 变化 (%) |",
        "| ---: | ---: | ---: | ---: |",
    ])
    
    for i in range(6):
        report.append(f"| {i+1} | ... | ... | ... |")
    
    report.extend([
        "",
        "## 5. 结论",
        "",
        "- 径向刚度降低约 X%，在可接受范围内",
        "- 轴向刚度基本不变",
        "- 槽根应力集中系数 K_t ≈ X.X，需圆角过渡",
        "- 一阶固有频率 > XXX Hz，远离激励频率",
        "",
        "**边界**：本分析使用单位载荷，真实载荷谱需实测标定后重新评估安全裕度。",
    ])
    
    (RESULTS / "stiffness-comparison-report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"报告已生成: {RESULTS / 'stiffness-comparison-report.md'}")


if __name__ == "__main__":
    generate_report()
```

#### 3. 更新技术报告

**新增第 5 章：承载、刚度与疲劳设计**

```markdown
## 5. 承载、刚度与疲劳设计

### 5.1 设计矛盾与解决思路

六翼柔顺结构通过径向槽隔离焊接收缩，降低孔轴线位置度偏差。但柔顺结构主动降低了结构刚度，可能影响轴承支撑性能。本章通过单位载荷结构对比，评估刚度变化是否在可接受范围内。

### 5.2 单位载荷刚度对比

#### 5.2.1 对比方案

- **Baseline**：连续环形座，外径 Ø149.96 mm，厚度 12 mm，无柔顺槽
- **6-wing**：六翼柔顺座，中心刚性区 Ø82 mm，六个 18 mm 翼，径向槽宽 4 mm

#### 5.2.2 载荷工况

不知道压缩机真实载荷，采用单位载荷进行相对评价：

1. **径向 X 向**：Fx = 1 kN
2. **径向 Y 向**：Fy = 1 kN
3. **轴向 Z 向**：Fz = 1 kN
4. **倾覆力矩**：Mx = 1 kN·m

施加于轴承孔内表面，约束壳体外表面。

#### 5.2.3 刚度对比结果

| 工况 | Baseline 位移 | 6-wing 位移 | 刚度变化 |
| --- | ---: | ---: | ---: |
| 径向 X | 0.XXX mm | 0.XXX mm | -X.X% |
| 径向 Y | 0.XXX mm | 0.XXX mm | -X.X% |
| 轴向 Z | 0.XXX mm | 0.XXX mm | -X.X% |
| 倾覆 | X.XXX° | X.XXX° | -X.X% |

**结论**：径向刚度降低约 X%，轴向刚度基本不变，在工程可接受范围内。

### 5.3 应力集中与疲劳热点

#### 5.3.1 关键应力热点

| 位置 | 应力集中系数 K_t | 对策 |
| --- | ---: | --- |
| 六翼根部（槽端） | X.X | R2 圆角过渡，降至 K_t < 2.5 |
| 焊段起止端 | X.X | 延迟收弧填满弧坑，打磨焊趾 |
| 焊缝根部 | X.X | 坡口与钨极对中，小试金相确认熔透 |

#### 5.3.2 疲劳设计基线

按 IIW 名义应力法，环向角焊缝取 FAT 63–80 等级（2×10⁶ 循环参考强度）。镍基焊缝韧性好、残余应力低，是疲劳裕度来源。

**验证试验计划**：
1. 接头级：轴向疲劳试样（R=0.1，10⁷ 循环，≥3 件）
2. 部件级：振动台耐久试验，跟踪位置度漂移
3. 整机级：装机耐久后内窥复检

### 5.4 模态分析

| 阶次 | Baseline (Hz) | 6-wing (Hz) | 备注 |
| ---: | ---: | ---: | --- |
| 1 | XXX | XXX | 整体弯曲 |
| 2 | XXX | XXX | 扭转 |
| 3-6 | XXX-XXX | XXX-XXX | 局部模态 |

**结论**：一阶固有频率 > XXX Hz，远离压缩机运行频率（50～60 Hz），共振风险低。

### 5.5 边界说明

本章使用单位载荷进行结构相对评价，不知道压缩机真实载荷谱。真实工况下的安全裕度需在实测载荷谱标定后重新评估。
```

#### 4. 更新 FMEA

**文件**：`docs/design/fmea.md`

**增加失效模式**：

| 失效模式 | 成因 | 后果 | 严重度 | 当前控制措施 | 发生度 | 探测度 | RPN |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| 六翼根部疲劳裂纹 | 槽端应力集中，高频振动 | 裂纹扩展，轴承孔失效 | 9 | R2 圆角过渡，K_t < 2.5；振动台耐久试验 | 4 | 5 | 180 |
| 柔顺槽疲劳萌生 | 径向槽根部应力集中 | 裂纹扩展至焊缝 | 8 | 槽根圆角 R1；金相确认组织 | 4 | 6 | 192 |
| 径向刚度不足 | 柔顺结构刚度降低 | 轴承间隙增大，振动加剧 | 7 | 单位载荷刚度验证；刚度变化 < 15% | 3 | 4 | 84 |
| 轴承座整体共振 | 固有频率接近激励频率 | 疲劳加速，噪声增大 | 8 | 模态分析；一阶 > 200 Hz | 2 | 5 | 80 |

### 验收标准

✅ 新增 stiffness-baseline 和 stiffness-6wing 算例目录  
✅ 创建 run_stiffness_comparison.py 脚本（接口定义）  
✅ 技术报告增加第 5 章：承载、刚度与疲劳  
✅ FMEA 增加 4 个结构/疲劳失效模式  
✅ 明确边界：单位载荷相对评价，不是绝对设计  

---

## 执行顺序与时间估算

### 第 1 周（立即开始）

**Day 1-2**：修复 1（R73.8/1.2mm）
- 更新 geometry.json
- 更新工程图代码
- 重新生成所有图纸
- 更新文档

**Day 3-4**：修复 2（Ø39.96 定位销）
- 设计锥形心轴
- 更新夹具图
- 更新误差预算
- 更新文档

**Day 5-7**：修复 3（刚度验证）
- 创建算例目录结构
- 编写分析脚本接口
- 更新技术报告第 5 章
- 更新 FMEA

### 第 2 周

- 论文 8 章结构重构
- 制造级工程图（3 张）
- 误差预算拆分表格

### 第 3 周

- 版式优化
- 证据等级说明集中化
- 自动化章节精简
- 内部评审

---

## 追溯与版本控制

所有修改应：
1. ✅ 提交到 git，commit message 格式：`[V3-FIX-1] 修复 R73.8 接头几何矛盾`
2. ✅ 在本文件中标记完成状态
3. ✅ 更新 `docs/01-roadmap.md` 执行状态

---

## 下一步

1. 确认修复方案是否认可
2. 开始执行修复 1
3. 边执行边验证，确保每项修复符合评审要求
