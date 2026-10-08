"""Integrate the completed P2 bending check with the retained full P1 audit."""
from pathlib import Path
from copy import deepcopy
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CASES=("radial","axial","overturning","combined")
FIG=HERE/"figures"
from geometry_audit import audit_unwelded_gap


def main():
    dirs=[HERE/"results"/f"p2-linear-{level}" for level in ("coarse","medium")]
    data=[json.loads((p/"result.json").read_text()) for p in dirs]
    samples=[json.loads((p/"virtual-bore-summary.json").read_text()) for p in dirs]
    from run_quadratic_check import cache_inputs, current_publication_identity
    version=current_publication_identity()["process_version"]
    gap_audits = {}
    for level,folder,raw,sample in zip(("coarse","medium"),dirs,data,samples):
        expected=cache_inputs(level)
        if raw.get("process_version")!=version:
            raise RuntimeError(f"{folder.name}: actual raw result process version differs from current design")
        meta=json.loads((folder/"mesh-summary.json").read_text())
        for supplied in (raw.get("input_identity"),meta.get("input_identity"),sample.get("source_input_identity")):
            if json.dumps(supplied,sort_keys=True)!=json.dumps(expected,sort_keys=True):
                raise RuntimeError(f"{folder.name}: raw/mesh/sample geometry or load identity differs; rebuild or resample the actual requested case")
        if sample.get("source_process_version") != raw.get("process_version"):
            raise RuntimeError(f"{folder.name}: bore sample source process version differs from actual raw result")
        gap_audits[folder.name] = audit_unwelded_gap(dict(np.load(folder/"mesh.npz")), reject=True)
        (folder/"geometry-audit.json").write_text(json.dumps(gap_audits[folder.name],indent=2))
    p1=[json.loads((HERE/"results"/lv/"result.json").read_text()) for lv in ("coarse","medium","fine")]
    p1comparison={case:{key:{"previous":p1[1]["cases"][case][key],"selected":p1[2]["cases"][case][key],
        "absolute_change":abs(p1[1]["cases"][case][key]-p1[2]["cases"][case][key]),
        "relative_change":abs(p1[1]["cases"][case][key]-p1[2]["cases"][case][key])/max(abs(p1[2]["cases"][case][key]),1e-12)}
        for key in ("axis_diameter_envelope_um","elastic_strain_energy_N_mm")}
        for case in CASES}
    comparison={}
    for case in CASES:
        comparison[case]={}
        for key in ("axis_diameter_envelope_um","mean_bore_diameter_change_um","cylindrical_radial_peak_to_valley_um","elastic_strain_energy_N_mm"):
            if key=="elastic_strain_energy_N_mm":a,b=[d["cases"][case][key] for d in data]
            else:a,b=[d["cases"][case][key] for d in samples]
            comparison[case][key]={"coarse":a,"medium":b,"absolute_change":abs(a-b),
                "relative_change":abs(a-b)/max(abs(b),1e-12),
                "is_symmetry_zero":case=="axial" and key=="axis_diameter_envelope_um" or
                    case in ("radial","overturning") and key=="mean_bore_diameter_change_um"}
    converged=all(v["relative_change"]<=.05 for values in comparison.values() for key,v in values.items()
                  if key in ("axis_diameter_envelope_um","elastic_strain_energy_N_mm") and not v["is_symmetry_zero"])
    shape_converged=all(v["relative_change"]<=.05 for values in comparison.values() for key,v in values.items()
                        if key in ("mean_bore_diameter_change_um","cylindrical_radial_peak_to_valley_um") and not v["is_symmetry_zero"])
    combined_shape_converged=all(comparison["combined"][key]["relative_change"]<=.05 for key in ("mean_bore_diameter_change_um","cylindrical_radial_peak_to_valley_um"))
    # Build a fresh record each time.  Historical P1 diagnostics have no current
    # process identity and cannot serve as the newly versioned primary result.
    assessment={"process_version":data[1]["process_version"],
        "input_identity":deepcopy(data[1]["input_identity"]),
        "verified_identity_sources":[f"simulation/ring-baseline-structure/results/p2-linear-medium/{name}"
            for name in ("result.json","mesh-summary.json","virtual-bore-summary.json")],
        "model":"complete-ring-R20-74.98-t15-z100-115-shell-R75-80-h200",
        "evidence_kind":"simulation","method":data[1]["method"],
        "joint":{"segment_count":8,"effective_segment_length_mm":18.,"minimum_leg_mm":3.5,
            "qualification_condition":"continuous effective QT/first-Ni/second-Ni/NiFe55/shell interfaces at modeled material shared faces"},
        "material_inputs":data[1]["input_identity"]["material_inputs"],
        "boundary":"complete shell bottom z=0 fixed; unwelded gap free; exact quarter symmetry of the specified full-ring reference loads",
        "loads":{"radial_N":5000,"axial_N":5000,"overturning_My_N_mm":250000,
            "scope":"self-selected reference envelope, not an official operating load or compressor duty-cycle specification"},
        "initial_state":"cold unstressed ideal qualified joint; no precoat or welding residual stresses transferred",
        "actual_joint_fusion_verified_by_this_model":False,
        "P1_convergence_audit":{"status":"historical same-nominal-geometry diagnostics; raw process identity absent, not current qualification evidence",
            "coarse_geometry_status":"shell facet edges intrude into nominal R74.98 ring envelope (minimum R74.96455); excluded from accepted geometry qualification",
            "stiffness_quantities_within_5_percent":False,"previous_mesh":"medium","selected_mesh":"fine","comparison":p1comparison},
        "P1_selected_response":p1[2]["cases"]["combined"],
        "all_mesh_response_summary":{lv:{"nodes":raw["mesh"]["nodes"],"tetrahedra":raw["mesh"]["tetrahedra"],
            "combined_axis_um":raw["cases"]["combined"]["axis_diameter_envelope_um"],
            "combined_energy_N_mm":raw["cases"]["combined"]["elastic_strain_energy_N_mm"],
            "combined_raw_weld_von_mises_max_MPa":raw["cases"]["combined"]["raw_element_stress_by_material"]["5"]["von_mises_max_MPa"]}
            for lv,raw in zip(("coarse","medium","fine"),p1)},
        "figures":[f"simulation/ring-baseline-structure/figures/{name}.png" for name in ("ring-cold-response","ring-joint-raw-stress","ring-mesh-comparison")]}
    selected={case:{**data[1]["cases"][case],**samples[1]["cases"][case]} for case in CASES}
    selected["combined"]["raw_quadrature_stress_by_material"]=data[1]["combined_raw_quadrature_stress_by_material"]
    assessment.update({"selected_mesh":"p2-linear-medium",
        "method":data[1]["method"],"combined":selected["combined"],"cases":selected,"mesh":data[1]["mesh"],
        "actual_faceted_gap_audit":gap_audits,
        "convergence_selected":{"stiffness_quantities_within_5_percent":converged,"bore_shape_quantities_within_5_percent":shape_converged,
            "combined_bore_shape_quantities_within_5_percent":combined_shape_converged,
            "previous_mesh":"p2-linear-coarse","selected_mesh":"p2-linear-medium","comparison":comparison,
            "criteria":"axis envelopes and full-ring elastic strain energy <=5%; shape metrics assessed separately on common 128x11 virtual inspection grid; exact symmetry-zero quantities listed by absolute values"},
        "quadratic_bending_check":{"comparison":comparison,"reference_envelope_only":True,
            "quarter_symmetry":"y=0 symmetric; x=0 symmetric for axial, antisymmetric for radial and My",
            "P2_displacement_order":2,"P2_geometry_order":1,"coarse":data[0],"medium":data[1],
            "common_bore_sampling":samples[1]["sampling"],
            "diagnosis":"P1 constant-strain tetrahedra remained too stiff in bending; P2 is checked independently at two resolutions, using the same effective-joint geometry and load conditions"},
        "strength_verified":False,"postweld_position_verified":False,
        "scope":"P2 cold service stiffness and hole-shape response under qualified effective-joint assumptions. Sharp toe/root stress is retained and is not a capacity/fatigue rating; no manufacturing residual field is transferred."})
    (HERE/"results/assessment.json").write_text(json.dumps(assessment,ensure_ascii=False,indent=2))
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"svg.fonttype":"none","pdf.fonttype":42})
    mesh=dict(np.load(dirs[1]/"mesh.npz"));p=mesh["points"];tri=mesh["triangles6"]
    q=p[tri];r=np.linalg.norm(q[:,:,:2],axis=2)
    top=tri[np.all(abs(q[:,:,2]-115.)<1e-5,axis=1)&np.all(r<74.99,axis=1)]
    micro=np.concatenate([top[:,ix] for ix in ((0,3,5),(3,1,4),(5,4,2),(3,4,5))])
    fields={name:np.load(dirs[1]/f"{name}-quarter-displacement.npz")["displacement_mm"] for name in ("radial","axial","overturning")}
    fullp=[];fullu=[];fulltri=[]
    for i,(sx,sy) in enumerate([(1,1),(-1,1),(-1,-1),(1,-1)]):
        R=np.array([sx,sy,1.]);fullp.append(p*R)
        fullu.append((fields["axial"]+sx*(fields["radial"]+fields["overturning"]))*R)
        fulltri.append(micro+i*len(p))
    pp=np.concatenate(fullp);uu=np.concatenate(fullu);tt=np.concatenate(fulltri)
    fig,axes=plt.subplots(1,2,figsize=(10,4.3),layout="constrained")
    for a,component,label in zip(axes,(0,2),("Lateral displacement ux","Axial bending uz")):
        artist=a.tripcolor(mtri.Triangulation(pp[:,0],pp[:,1],tt),1000*uu[:,component],shading="gouraud",cmap="viridis",rasterized=True)
        fig.colorbar(artist,ax=a,label="um",shrink=.8);a.set_aspect("equal")
        a.set(xlim=(-80,80),ylim=(-80,80),xlabel="x (mm)",ylabel="y (mm)",title=label)
    fig.suptitle("Complete ring / minimum effective joints / quadratic FE / combined reference load",fontsize=10)
    for ext in ("png","pdf","svg"):fig.savefig(FIG/f"ring-cold-response.{ext}",dpi=220)
    plt.close(fig)
    # Show the P1 bias and the separate P2 convergence family in one compact figure.
    fig,axes=plt.subplots(1,2,figsize=(9,3.8),layout="constrained")
    p1axis=[json.loads((HERE/"results"/lv/"virtual-bore-summary.json").read_text())["cases"]["combined"]["axis_diameter_envelope_um"] for lv in ("coarse","medium","fine")]
    p2axis=[s["cases"]["combined"]["axis_diameter_envelope_um"] for s in samples]
    for a,vs,ys,label in [(axes[0],p1axis,p2axis,"Combined loaded axis envelope (um)"),
                           (axes[1],[d["cases"]["combined"]["elastic_strain_energy_N_mm"] for d in p1],
                            [d["cases"]["combined"]["elastic_strain_energy_N_mm"] for d in data],"Full-ring elastic strain energy (N mm)")]:
        a.plot([1,2],vs[1:],"o-",color="#557a95",label="P1 full model")
        a.plot([0],[vs[0]],"x",color="#999999",label="P1 coarse: gap approximation rejected")
        a.plot([3,4],ys,"o-",color="#b56837",label="P2 quarter symmetry")
        a.set_xticks(range(5),["P1 coarse","P1 medium","P1 fine","P2 coarse","P2 medium"],rotation=20,fontsize=8)
        a.set_ylabel(label);a.grid(axis="y",alpha=.2);a.spines[["top","right"]].set_visible(False)
    axes[0].legend(frameon=False,fontsize=8)
    for ext in ("png","pdf","svg"):fig.savefig(FIG/f"ring-mesh-comparison.{ext}",dpi=220)
    plt.close(fig)
    rows=[]
    for case in CASES:
        d=selected[case]
        rows.append(f"| {case} | {d['axis_diameter_envelope_um']:.3f} | {d['mean_bore_diameter_change_um']:.3f} | {d['cylindrical_radial_peak_to_valley_um']:.3f} | {d['elastic_strain_energy_N_mm']:.3f} |")
    stress=data[1]["combined_raw_quadrature_stress_by_material"]
    stressrows=[f"| {prop['name']} | {stress[str(mid)]['von_mises_max_MPa']:.2f} | {stress[str(mid)]['maximum_principal_max_MPa']:.2f} |" for mid,prop in assessment["material_inputs"].items()]
    report=f"""# 完整圆环冷态承载结果

本计算以QT450-10完整圆环、5 mm Q235B壳体、两种保留镍层和八个18 mm有效焊段为实体模型，采用3.5 mm最小焊脚。未焊圆周保持0.02 mm分离间隙。壳体下端环面固定，参考荷载为径向5000 N、轴向5000 N和倾覆250 kN·mm。荷载是本设计参考包络，题面未规定整机工作载荷。

三档全模型P1常应变四面体在倾覆/轴向弯曲中持续偏硬，细档组合孔轴直径包络28.908 μm、能量238.728 N·mm，尚不能据其百万级单元数认定精度。随后用同几何和有效接头的四分之一P2二次位移实体复核，径向/倾覆采用x=0反对称，轴向双对称，分别求解再按荷载奇偶性还原全环。

最初P1首档的壳内曲面三角片边侵入名义间隙，最小半径74.96455 mm，虽然没有把座体直接绑到壳体，仍不能将该档列为合格几何模型。它仅保留历史故障和离散诊断记录；中/细档通过实际面片边界检查。当前两档P2对每片壳内三角面裁剪到z100～115 mm并计算整个多边形边的最低半径，分别为74.984410和74.992357 mm，均大于座体最大外半径74.98 mm，座体/壳直接共享节点均为0。该检查避免仅看节点或面心误判0.02 mm间隙。

两档P2为51,286/88,586四面体、86,811/146,223节点。中档实际求解438,669自由度，所有元素minDetJac为正。使用直边CAD面片逼近及二次位移插值；首档成功曲边P2给出的组合包络31.028 μm作为几何逼近敏感性记录，不与直边族混判收敛。曲边中档的优化失败保留在计算记录中，没有用于承载结果。

## 同一虚拟孔面采样的P2结果

每档以128个等角度、11个等高截面采样孔面位移；通过实际面片径向射线交点及二次形函数插值，避免网格节点分布改变拟合权重。

| 工况 | 受载轴线直径包络 / μm | 平均孔径变化 / μm | 圆柱径向峰谷 / μm | 全环应变能 / N·mm |
|---|---:|---:|---:|---:|
"""+"\n".join(rows)+f"""

两档P2的受载轴线及全环应变能{'均达到' if converged else '未全部达到'}5%工程复核要求；组合工况平均孔径和径向峰谷{'达到' if combined_shape_converged else '未达到'}5%。倾覆单项的圆柱径向峰谷为0.466→0.511 μm，绝对差0.044 μm、相对差8.69%，单独列为细小孔形残差尚未达到5%的量，不将其隐藏为零。比较原数见assessment.json。轴向单项的横向轴位移、径向/倾覆的平均孔径变化为对称性零量，保留绝对值。荷载/反力和力矩平衡另行记录。

## 组合工况原始积分点应力

| 材料区 | 最大Mises / MPa | 最大第一主应力 / MPa |
|---|---:|---:|
"""+"\n".join(stressrows)+"""

P1细档原始焊缝峰926.890 MPa仍保留；上述P2值同样不进行节点平均或削峰。尖锐焊趾、根部及材料分界的局部应力对离散敏感，整体刚度收敛不构成局部强度收敛。实际趾根轮廓、连续有效面积及接头材料容量应对应到局部弹塑性和疲劳核对，不以任意许用值签署完整强度通过。

## 设计结论的边界

该冷态模型的前提是QT—首层—第二层—最终焊缝—壳体所建有效面具有连续接头。模型没有把几何共享面赋予实际熔合证据，也未传递预制和最终组焊的残余场。它给出了本完整圆环在指定参考荷载和支承下可复核的弹性孔区响应与受力热点。strength_verified=false、postweld_position_verified=false明确保留；受载轴线变化不能替代焊后完全卸夹的位置度。
"""
    (HERE/"results/cold-structure-report.md").write_text(report)
    print(json.dumps({"P2_converged":converged,"combined_axis_um":selected["combined"]["axis_diameter_envelope_um"],"comparison":comparison},indent=2))


if __name__=="__main__":main()
