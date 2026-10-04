# Schaeffler图域与逐层稀释计算

运行 `python studies/SCHAEFFLER-MAP/run.py`，生成成分表、相图及冷焊热容量比较图。

Q235B、QT450-10及NiFe-55的名义成分统一读取 `project/materials.yaml`；Ni99采用Weldwire WWNA99供方典型成分。来料和焊材批次分析替换名义输入。

Schaeffler当量按 Cr+Mo+1.5Si+0.5Nb 与 Ni+30C+0.5Mn计算。Kobelco手册原图范围为Cr_eq 0～40、Ni_eq 0～30；高镍和高碳点在图外，不能外推单相组织或相分数。当前计算不使用旧版的Ms外推、减除石墨碳或虚构的水平组织边界。

保留14组直接QT稀释算例，另按质量守恒计算27组两层Ni99及最终NiFe熔池的配混，其中12组属于设计窗口。最终组焊只重熔第二层：第二层加工后≥0.50 mm、最终熔深≤0.40 mm，总剩余镍层≥0.80 mm。首次QT/Ni99界面的PMZ及HAZ仍须独立检查。

奥氏体主枝晶、枝晶间碳化物和HAZ马氏体机理参照Alizadeh-Sh等2024的原始研究，材料和方法移植边界写入输出JSON及说明书。自由热胀图只表达均匀温度下的半径变化，不等于孔轴偏移或焊后残余位置度。

旧 `run-r2-historical.py` 是历史对照，不能生成现行交付结论。
