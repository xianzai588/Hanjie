# 自动化焊接数字样机架构

```text
视觉图像 → 壳体/轴承座中心与姿态 → ΔX/ΔY/Δθ
                                  ↓
                         路径坐标变换与顺序
                                  ↓
                         机器人/变位机轨迹
                                  ↓
                 I / U / v / T 采集与工艺窗口判断
                                  ↓
                  异常事件 + 一件一码质量追溯
```

| 模块 | 当前实现 | 现场替换点 |
| --- | --- | --- |
| 视觉定位 | `automation/vision/`，1000 个有标签数字样本 | 工业相机、镜头、光源、标定板 |
| 路径规划 | `automation/path-planning/`，S1/S2/S3 | 机器人 TCP、坐标系和安全点 |
| 过程监测 | `automation/anomaly-detection/`，仿真 I/U/v/T | 焊机/传感器 SDK |
| 质量追溯 | `automation/traceability/`，SQLite | MES/数据库服务 |
| 展示入口 | `automation/app/run_demo.py` | 现场 PLC/机器人接口 |

当前 Demo 只证明数据链路和判定逻辑，不能证明现场焊接控制精度。

