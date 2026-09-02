# 自动化数字样机（WP6）

当前版本不连接真实焊机，先验证数据链路和控制逻辑：

1. `vision/`：生成带已知偏移/转角的数字样本，并用颜色分割与外轮廓拟合恢复中心。
2. `path-planning/`：根据 4/6/8 点布局和 S1/S2/S3 顺序生成焊接段点位。
3. `anomaly-detection/`：生成带注入异常的仿真 I/U/v/T 信号，按工艺窗口聚合异常。
4. `traceability/`：把一件一码、信号来源和异常事件写入 SQLite。
5. `app/`：运行一次端到端 Demo。

## 已执行数字基准

- 常规视觉：`python automation/vision/run_benchmark.py --count 1000`；
- 困难视觉：`python automation/vision/run_benchmark.py --difficult --count-per-condition 100`；结果见 `vision/results/difficult-summary.md`；
- 异常检测：`python automation/anomaly-detection/run_benchmark.py --normal-count 100 --injected-count 100`；结果见 `anomaly-detection/results/benchmark/summary.md`。

困难视觉条件覆盖噪声、模糊、光照梯度、约 10–30° 透视近似、遮挡、缺失边缘、低对比度、畸变和 ±5 mm 偏移。异常检测基准按事件级输出 TP/FP/FN、precision、recall、FPR 和延迟。

所有结果必须区分 `simulated` 与未来的 `physical`；数字样本测试不能表述为真实相机/焊机采集。
