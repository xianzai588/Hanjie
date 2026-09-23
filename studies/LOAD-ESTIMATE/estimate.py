"""压缩机一阶载荷与倾覆力矩估算；参数为示例，需用实际机型数据替换。"""
from pathlib import Path
import json, math
ROOT=Path(__file__).resolve().parents[1]
m=0.8; r=0.02; speed_rpm=3000; lam=0.25; D=0.04; dp=1.5e6; eccentricity=0.07
omega=2*math.pi*speed_rpm/60
inertial=m*r*omega**2
gas=math.pi*D**2*dp/4
radial=inertial+gas
axial=gas
moment=radial*eccentricity
interaction=math.sqrt((radial/5000)**2+(axial/5000)**2+(moment/250)**2)
payload={"version":"LOAD-ESTIMATE-2","evidence_level":"parameterized_first_order_screening","inputs":{"reciprocating_mass_kg":m,"crank_radius_m":r,"speed_rpm":speed_rpm,"rod_ratio":lam,"bore_diameter_m":D,"pressure_difference_pa":dp,"force_line_to_weld_centroid_m":eccentricity},"formulas":{"omega":"2*pi*n/60","inertial_amplitude":"m*r*omega^2","gas_force":"pi*D^2*delta_p/4","overturning_moment":"(inertial+gas)*e","reference_interaction":"sqrt((Fr/5000)^2+(Fa/5000)^2+(M/250)^2)"},"results":{"inertial_force_n":inertial,"gas_force_n":gas,"radial_force_n":radial,"axial_force_n":axial,"overturning_moment_nm":moment,"reference_interaction_ratio":interaction,"reference_envelope_nm":250},"interpretation":"示例参数下径向约3.46 kN、轴向约1.88 kN、倾覆约0.24 kN·m；按三分量同时作用的平方和口径，交互比约1.46，不能宣称覆盖当前参考包络。须用实际机型载荷谱、相位和支承偏心更新后再做承载/疲劳判定。"}
out=Path(__file__).resolve().parent/'results/load-estimate.json';out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(out)
if __name__=='__main__': pass
