# 成分核算、相图适用范围与QT侧冶金连接

当前计算入口为 `studies/SCHAEFFLER-MAP/run.py`，当前工程解释见 `deliverables/report/technical-report-v4-unified.md` §2。本文件替代旧四道、直接QT稀释及Ms外推说明。

Schaeffler/DeLong是钢焊缝组织/铁素体估算工具。Kobelco《Specific 4th edition》3-7页Fig.2.3给出Schaeffler原图，Cr_eq约0～40、Ni_eq约0～30。QT450-10名义高碳点、Ni99和NiFe-55及最终高镍配混点超出该图域，仅报告成分/当量坐标，不读外推相区。母材点也不用于判定来料基体组织；不采用从假定石墨体积分数扣除碳的方法获得“基体点”。

两层Ni99逐层质量配混必须保留QT碳输入。第一层QT稀释10%～20%、第二层重熔首层10%～15%、最终Ni层占10%～20%/钢侧占5%～10%均是设计窗口。其成分计算可复算，但窗口是否实现要由真实熔合、重熔深度与局部热循环验证。

Alizadeh-Sh等2024年研究的EN-GJS-500-14/GMAW-MCAW、纯Ni与45%Ni丝显示纯Ni焊缝有石墨、NiFe焊缝可有渗碳体，两者HAZ均可形成马氏体。该材料与方法不同于本件QT450-10/GTAW/NiFe55，引用其机理，不移植PMZ厚度、强度或“无裂纹”结论。参考：https://link.springer.com/article/10.1007/s11661-024-07399-4 。

TWI/Kobelco支持短道、镍过渡与适度热态轻击的工艺方向。400～500℃、≤200N、压痕≤0.05mm是本项目的待核验轻击设计窗口，不据E乘塑性应变推断整条QT侧熔合线已转为压应力。热态覆盖与局部应力改变分别评价。

Ni99根层不能简单采用纯镍轧材的抗拉/屈服数据。当前首层配混具有0.374%～0.738%C、79.71%～89.66%Ni；轧材Ni200只用于本构对照。QT侧首次PMZ、Ni99/NiFe及钢侧熔合边界均需显式几何、塑性状态及适用失效参数。

工程核验顺序：独立Ni99预制首/第二层热循环→QT首次PMZ/HAZ与重熔并集→最终根道/盖面双侧熔合→局部塑性传力与最大主拉应力→整件刚度和残余孔形反馈→同残余状态承载加载/卸载。宏观截面、金相、HV0.3与PT作为后续试制证据；当前不填造实测结果。

原始来源：
- Kobelco手册：https://www.kobelco-welding.jp/images/education-center/pdf/Specific_4Ed.pdf
- TWI铸铁指南：https://www.twi-global.com/technical-knowledge/job-knowledge/weldability-of-materials-cast-irons-025
- NiFe55供方：https://certilas.com/en/product/nife-55-tig
- Ni200轧材数据：https://www.specialmetals.com/documents/technical-bulletins/nickel-200.pdf
