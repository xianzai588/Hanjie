# Run A 定稿状态

分支：`codex/final-entry-20261009`；基线：`86b3e6e`；技术冻结：2026-10-18。主方案8P-R2-t15；不push，不处理原有未跟踪文件，不删除simulation/output数据。

## 已完成步骤

- A1：`e719f32`，规则、stage-status与README转入定稿；28+2+0+20=50 μm，微珩为备用；PQR与首件验收集中入第9章。
- A2：`49e6ad3`，三个既有结果的Richardson/GCI已计算，三级网格准备完成。
- A3：现有h1.125场生成三张300 dpi中文云图；焊趾邻域404.1 MPa、槽根邻域149.7 MPa；温度保存快照t=9.75 s、1492.0℃，全时程节点峰值1639.6℃。提交见本文件git历史。

## 位置度数字

三算例热残余直径13.0028／15.5839／13.7414 μm，主预算非热项30 μm。按名义h比4/3，p=1外推23.3274 μm，p=2外推18.9026 μm。dt0.25→0.125同时细化力学／温变触发，q=2的dt0.25校正+0.9848 μm；p=2、q=2可分离假设下预测19.8874 μm，总预算49.8874 μm。

两空间网格不能辨识实测阶次。采用NASA推荐双网格Fs=3，p=2空间GCI绝对带±9.9559 μm（细网格15.5839为中心，5.6281～25.5398 μm）。时间协议GCI追加±2.9544 μm，合并总预算带32.6737～58.4942 μm。GCI不是统计置信区间；点预测满足50 μm，数值误差上界未收口。三级完成前写条件预测及误差区间，不宣称网格收敛或稳健达标。

既有三场孔径最小值39.99796／39.99745／39.99762 mm，低于40.000 mm。无微珩是制造目标及首件验收条件，不能把现有孔径结果写成直接合格。首件CMM／孔径校准集中列入试制计划，预算不变。

计算来源：`studies/COMPETITION-DESIGN/results/final-entry-position-gci-20261009.json`。GCI参考：https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html 。

## 三级空间网格：由主控启动

- h=0.84375 mm（1.125×0.75），dt=0.25 s；其余worker设置相同，焊缝网格1.0 mm。
- 一次网格／接口冒烟完成：95,474节点，392,512四面体；仿射接口误差2.30×10⁻¹³ mm，通过。网格生成23.5 s；未运行完整三级求解或首层计算。
- 两级求解耗时4.57／7.40 h，单元数118,585／188,351；按T∝N^1.0424外推三级约15.9 h，计划11.9～23.9 h，受内存和主机负载影响。
- 完整一行PowerShell命令（后台、隐藏窗口、独立日志），本轮只保存命令，未启动：

```powershell
$job='E:\AI\bisai\Hanjie\simulation\competition-r4\results\8p-thermal-tool-bore008-h084375-dt025-s05'; New-Item -ItemType Directory -Path $job -Force | Out-Null; Start-Process -FilePath (Get-Command python.exe).Source -ArgumentList @('-X','utf8','simulation/competition-r4/run_bore_worker.py','--case','8p-thermal-tool-bore008-h084375-dt025-s05') -WorkingDirectory 'E:\AI\bisai\Hanjie' -WindowStyle Hidden -RedirectStandardOutput ($job+'\worker-final-entry.log') -RedirectStandardError ($job+'\worker-final-entry-errors.log') -PassThru
```

完整冷却及壳底卸夹由worker执行；已有续算检查点时自动resume。三级完成后读取measurement.json的position_diameter_mm，加入同一表判定实测阶次和GCI；不改预算、不扩扫描。

## 后续步骤

A3现有场云图；A4耗丝同步；A5正文、相关卡与PDF；A6汇总提交。Run B才重画按比例工程图、清理主包及重写评委阅读说明。
