# Run A 定稿状态

分支：`codex/final-entry-20261009`；基线：`86b3e6e`；技术冻结：2026-10-18。主方案8P-R2-t15；不push，不处理原有未跟踪文件，不删除simulation/output数据。

## 已完成步骤

- A1：`e719f32`，规则、stage-status与README转入定稿；28+2+0+20=50 μm，微珩为备用；PQR与首件验收集中入第9章。
- A2：`49e6ad3`，三个既有结果的Richardson/GCI已计算，三级网格准备完成。
- A3：`afd0eb3`，现有h1.125场生成三张300 dpi中文云图；焊趾邻域404.1 MPa、槽根邻域149.7 MPa；温度保存快照t=9.75 s、1492.0℃，全时程节点峰值1639.6℃。
- A4：`c125241`，容量脚本及对应JSON/参赛附件统一根3.42、盖3.78 mm/s；根298.4727、盖329.8909，合计628.3636 mm。
- A5：`4eeee12`，九章正文重写，概要一页、五项创新、方法明确排序、试制假设集中表16；第二层85 A/14 V、2.88 mm/s、11.52±0.29 mm/s同步到参数源及相关工艺卡；无微珩主线，备用3 μm径向微珩。三张云图和工艺路线图已入正文，失败首层算例与制造接口叙述已移出正文。
- A6：本文件完成汇总并独立提交；提交哈希由本文件git历史及本轮最终回复给出。

## PDF与定稿检查

- 正文PDF31页：封面/目录2页，概要及九章正文27页，参考文献2页；概要单独一页。
- 含工艺卡79页；合订本102页，包含既有23页八翼工程图，本轮保留图集。
- 按README的报告命令重建：`python -X utf8 deliverables/report/build_technical_report_pdf.py --competition-entry --with-drawings`。
- 已同步`deliverables/competition-entry/06-焊接工艺设计说明书-正文.pdf`与`01-焊接工艺设计说明书与工程图.pdf`。
- 渲染并检查概要、目录、温度/应力/孔位移云图、GCI表、试制表跨页、结论、参考文献及相关卡关键页；版面无截断/重叠。正文5位以上小数0处，指定内部术语0处，否定/免责类匹配2处。
- 核对原构建器的路径、热量、弧燃与分道耗丝守恒；YAML可读，PDF包含49.9/58.5 μm及39.9974 mm限制条件。仅作本次数字/排版检查，没有扩张测试。

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

## 仍需完成与边界

1. 主控在本轮退出后启动上述唯一三级算例。空间网格差16.6%，实测阶次仍待三级结果；当前双网格GCI安全系数采用3，不能将p=2点值49.9 μm写成数值误差上界也达标。
2. 现有孔径下界39.99745 mm，直接尺寸目标未满足；首件PQR/CMM/孔径测量与焊前补偿校准按第9章执行。本轮没有改孔径输入或开展新扫描。
3. 现有终焊FE采用对向同步双热源、等效1.20 mm薄镍层和预设初始残余状态；首批单头及现行两层预制的差异在正文模型和试制计划明确列出。没有将现有场重新命名为单头或完整现行制造链验证。
4. PQR、实物照片、检测、洁净与疲劳实测均在试制中取得。本轮交付的是工艺设计与条件计算结论，未填写虚构实测结果。
5. Run B：按比例工程图4～6张、其余NTS图转插图、内部审核附件清理、评委阅读说明、匿名复查及单一主PDF。本轮未执行Run B，参赛ZIP和材料清单仍为旧导出快照，需要Run B重打包。

本轮保存原未跟踪文件及simulation/output数据，没有push；新三级仅生成网格冒烟数据，没有启动完整求解。Run A到此停止。
