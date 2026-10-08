"""Publish independent P1 diagnostics without overwriting the current P2 result."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FIG=HERE/"figures"/"p1-diagnostic"
CASES=("radial","axial","overturning","combined")
METRICS=("axis_diameter_envelope_um","elastic_strain_energy_N_mm",
         "mean_bore_diameter_change_um","cylindrical_radial_peak_to_valley_um")


def changes(a,b):
    # For near-zero symmetry residuals, relative error is not a useful accuracy
    # measure.  Also report the absolute change so a vanishing denominator never
    # hides an unresolved result.
    out={}
    for case in CASES:
        out[case]={}
        for metric in METRICS:
            av,bv=a["cases"][case][metric],b["cases"][case][metric]
            out[case][metric]={"previous":av,"selected":bv,"absolute_change":abs(av-bv),
                               "relative_change":abs(av-bv)/max(abs(bv),1e-12)}
    return out


def element_face_owner(t, mids, tri, npoints, allowed):
    ix=np.flatnonzero(np.isin(mids,allowed))
    faces=np.concatenate([t[ix][:,f] for f in ((0,1,2),(0,1,3),(0,2,3),(1,2,3))])
    owners=np.tile(ix,4)
    sf=np.sort(faces,axis=1)
    code=(sf[:,0].astype(np.int64)*npoints+sf[:,1])*npoints+sf[:,2]
    order=np.argsort(code);code=code[order];owners=owners[order]
    st=np.sort(tri,axis=1)
    query=(st[:,0].astype(np.int64)*npoints+st[:,1])*npoints+st[:,2]
    loc=np.searchsorted(code,query)
    loc=np.minimum(loc,len(code)-1)
    found=code[loc]==query
    return found,owners[loc]


def save(fig,name):
    for ext in ("png","pdf","svg"):
        fig.savefig(FIG/f"{name}.{ext}",dpi=220)
    plt.close(fig)


def main():
    FIG.mkdir(parents=True,exist_ok=True)
    levels=[name for name in ("coarse","medium","fine") if (HERE/f"results/{name}/result.json").exists()]
    data={name:json.loads((HERE/f"results/{name}/result.json").read_text()) for name in levels}
    # A summary must not stamp today's version on an unidentified old result.
    from run_ring_structure import analysis_inputs
    for name,raw in data.items():
        expected=analysis_inputs(name,float(raw["mesh"]["fillet_leg_mm"]))
        if json.dumps(raw.get("analysis_inputs"),sort_keys=True)!=json.dumps(expected,sort_keys=True):
            raise RuntimeError(f"{name} raw result lacks/mismatches current process/geometry inputs; rerun run_ring_structure.py --rebuild before this P1 summary")
    if len(levels)<2:raise RuntimeError("Need at least two completed meshes")
    earlier,selected=levels[-2:]
    comp=changes(data[earlier],data[selected])
    # Stiffness quantities are evaluated separately from tiny asymmetry-driven
    # diameter/roundness residuals and raw re-entrant-corner stress peaks.
    controlled={case:{k:v for k,v in comp[case].items() if k in
                        ("axis_diameter_envelope_um","elastic_strain_energy_N_mm")}
                for case in CASES}
    stiffness_ok=all(v["relative_change"]<=.05 for c in controlled.values() for k,v in c.items()
                     if not (k=="axis_diameter_envelope_um" and abs(v["selected"])<1.))
    axes=data[selected]["cases"]
    raw_stress_changes={str(mid):{
        "previous_von_mises_max_MPa":data[earlier]["cases"]["combined"]["raw_element_stress_by_material"][str(mid)]["von_mises_max_MPa"],
        "selected_von_mises_max_MPa":axes["combined"]["raw_element_stress_by_material"][str(mid)]["von_mises_max_MPa"]}
        for mid in range(1,6)}
    version=data[selected]["analysis_inputs"]["process_version"]
    assessment={"process_version":version,"model":"complete-ring-R20-74.98-t15-z100-115-shell-R75-80-h200",
        "method":"actual five-material 3D linear tetrahedral FE; conforming bonded effective-joint interfaces; open unwelded gap; AMG-preconditioned conjugate gradient",
        "evidence_kind":"simulation", "selected_mesh":selected,
        "joint":{"segment_count":8,"effective_segment_length_mm":18.,"minimum_leg_mm":3.5,
                 "qualification_condition":"continuous effective QT/first-Ni/second-Ni/NiFe55/shell interfaces at modeled material shared faces"},
        "material_inputs":data[selected]["material_inputs"],
        "boundary":data[selected]["boundary"],"loads":{"radial_N":5000,"axial_N":5000,"overturning_My_N_mm":250000,
            "scope":"self-selected reference envelope, not an official operating load or compressor duty-cycle specification"},
        "convergence_selected":{"stiffness_quantities_within_5_percent":bool(stiffness_ok),
            "previous_mesh":earlier,"selected_mesh":selected,
            "comparison":comp,"raw_stress_peaks":raw_stress_changes,
            "criteria":"axis envelope and strain energy <=5%; axis envelopes <1um use absolute change because they are symmetry residuals; shape residuals listed separately"},
        "combined":axes["combined"],"cases":axes,"mesh":data[selected]["mesh"],
        "all_mesh_response_summary":{lv:{"nodes":data[lv]["mesh"]["nodes"],"tetrahedra":data[lv]["mesh"]["tetrahedra"],
            "combined_axis_um":data[lv]["cases"]["combined"]["axis_diameter_envelope_um"],
            "combined_energy_N_mm":data[lv]["cases"]["combined"]["elastic_strain_energy_N_mm"],
            "combined_raw_weld_von_mises_max_MPa":data[lv]["cases"]["combined"]["raw_element_stress_by_material"]["5"]["von_mises_max_MPa"]} for lv in levels},
        "strength_verified":False,"postweld_position_verified":False,"actual_joint_fusion_verified_by_this_model":False,
        "initial_state":data[selected]["initial_state"],
        "scope":"cold conditional service stiffness; raw local stresses retained. Manufacturing residual field, nonlinear local weld/HAZ response, actual interface capacity and fatigue are not assigned by this calculation.",
        "figures":[str((FIG/name).relative_to(ROOT)) for name in
                   ("ring-cold-response.png","ring-joint-raw-stress.png","ring-mesh-comparison.png")]}
    (HERE/"results/assessment-p1.json").write_text(json.dumps(assessment,ensure_ascii=False,indent=2))
    mesh=dict(np.load(HERE/f"results/{selected}/mesh.npz"));p=mesh["points"];t=mesh["tetrahedra"];tri=mesh["triangles"];mids=mesh["material_ids"]
    field=dict(np.load(HERE/f"results/{selected}/combined-field.npz"));u=field["displacement_mm"]
    q=p[tri];r=np.linalg.norm(q[:,:,:2],axis=2)
    top=tri[np.all(abs(q[:,:,2]-115.)<1e-5,axis=1)&np.all(r<74.99,axis=1)]
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"svg.fonttype":"none","pdf.fonttype":42})
    fig,ax=plt.subplots(1,2,figsize=(10,4.3),layout="constrained")
    triang=mtri.Triangulation(p[:,0],p[:,1],triangles=top)
    for a,component,title in zip(ax,(0,2),("Bore-seat lateral displacement","Bore-seat axial bending")):
        artist=a.tripcolor(triang,1000*u[:,component],shading="gouraud",cmap="viridis")
        fig.colorbar(artist,ax=a,label=f"u{'xz'[component//2]} (um)",shrink=.8)
        a.set_aspect("equal");a.set(xlim=(-80,80),ylim=(-80,80),xlabel="x (mm)",ylabel="y (mm)",title=title)
    fig.suptitle(f"Complete ring / qualified effective joints / combined reference load / {selected} mesh",fontsize=10)
    save(fig,"ring-cold-response")
    found,owner=element_face_owner(t,mids,tri,len(p),[5]);wtri=tri[found];values=field["element_von_mises_MPa"][owner[found]]
    # Pick one actual high-stress segment; all triangle values come directly from
    # one adjacent final-weld tetrahedron.  No nodal averaging or stress clipping.
    peak=axes["combined"]["raw_element_stress_by_material"]["5"]["peak_centroid_mm"]
    phi=np.arctan2(peak[1],peak[0]);cent=p[wtri].mean(axis=1);angle=np.arctan2(cent[:,1],cent[:,0])
    pick=abs(np.angle(np.exp(1j*(angle-phi))))<.23
    v=wtri[pick];stress=values[pick];xyz=p[v].copy()
    cs,sn=np.cos(phi),np.sin(phi)
    xy=xyz[:,:,:2].copy();xyz[:,:,0]=cs*xy[:,:,0]+sn*xy[:,:,1];xyz[:,:,1]=-sn*xy[:,:,0]+cs*xy[:,:,1]
    fig=plt.figure(figsize=(8,4.5),layout="constrained");a=fig.add_subplot(111,projection="3d")
    cmap=plt.get_cmap("magma");norm=plt.Normalize(0,field["element_von_mises_MPa"][mids==5].max())
    collection=Poly3DCollection(xyz,facecolors=cmap(norm(stress)),edgecolor="none",linewidth=0.)
    a.add_collection3d(collection);a.set(xlim=(70.8,75.2),ylim=(-10,10),zlim=(114.8,118.6),xlabel="Radial coordinate (mm)",ylabel="Tangential coordinate (mm)",zlabel="z (mm)")
    a.set_box_aspect((4,15,4));a.view_init(elev=25,azim=-135)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),ax=a,shrink=.65,label="Raw element von Mises (MPa)",pad=.12)
    a.set_title("Local effective fillet: unsmoothed element stress\nSharp toe/root; peak retained, strength not rated",fontsize=10)
    save(fig,"ring-joint-raw-stress")
    fig,axs=plt.subplots(1,2,figsize=(8,3.5),layout="constrained")
    x=np.arange(4);labels=["Radial","Axial","Moment","Combined"]
    for level,color in zip(levels,("#557a95","#b56837","#537849")):
        axs[0].plot(x,[data[level]["cases"][c]["axis_diameter_envelope_um"] for c in CASES],"o-",color=color,label=f"{level}: {data[level]['mesh']['tetrahedra']:,} tet")
        axs[1].plot(x,[data[level]["cases"][c]["elastic_strain_energy_N_mm"] for c in CASES],"o-",color=color)
    for a in axs:a.set_xticks(x,labels);a.grid(axis="y",alpha=.2);a.spines[["top","right"]].set_visible(False)
    axs[0].set_ylabel("Loaded axis diameter envelope (um)");axs[1].set_ylabel("Elastic strain energy (N mm)")
    axs[0].legend(frameon=False,fontsize=8)
    save(fig,"ring-mesh-comparison")
    rows=[]
    for case in CASES:
        v=axes[case]
        rows.append(f"| {case} | {v['axis_diameter_envelope_um']:.3f} | {v['mean_bore_diameter_change_um']:.4f} | {v['cylindrical_radial_peak_to_valley_um']:.4f} | {v['elastic_strain_energy_N_mm']:.3f} |")
    peaks=[]
    for mid,prop in data[selected]["material_inputs"].items():
        c=raw_stress_changes[mid]
        peaks.append(f"| {prop['name']} | {c['previous_von_mises_max_MPa']:.2f} | {c['selected_von_mises_max_MPa']:.2f} |")
    report="""# 完整圆环冷态承载结果

本结果来自完整圆环、17个保留材料实体、5 mm壳体及八个18 mm有效连接区的实际三维实体有限元。焊脚采用3.5 mm最小值，未焊圆周的0.02 mm间隙保持分离。壳体下端环面固定，参考包络为径向5000 N、轴向5000 N和倾覆250 kN·mm，计算单项与同向叠加。

## 受载孔区响应

| 工况 | 受载轴线直径包络 / μm | 平均孔径变化 / μm | 圆柱径向峰谷 / μm | 应变能 / N·mm |
|---|---:|---:|---:|---:|
"""+"\n".join(rows)+f"""

{selected}网格采用{data[selected]['mesh']['nodes']:,}节点、{data[selected]['mesh']['tetrahedra']:,}四面体。较前一档的孔轴包络和应变能{'达到' if stiffness_ok else '尚未全部达到'}5%工程复核要求。轴向单项的横向孔轴与孔径微小变化主要为非完全对称离散残差，原始值及绝对差保留在assessment.json。它们不作为相对误差接近零时的达标依据。孔形峰谷指标单独列出，不据几乎为零的响应扩大精度结论。

## 材料与连接区原始应力

| 材料区 | 前一档最大Mises / MPa | 本档最大Mises / MPa |
|---|---:|---:|
"""+"\n".join(peaks)+"""

表内为各实体的原始单元应力峰值，未做节点平均或削峰。最终焊缝的最大值位于有效段的焊趾/根部及起止端附近，尖角几何使局部应力对离散敏感；当前线弹性峰值须用于定位真实趾根轮廓和局部承载核对，不能直接签署完整强度、界面容量或疲劳合格。冷态整体刚度证据与局部强度证据分别判定。

## 结论的适用范围

该计算的连接前提是：所建有效面已经取得连续接头，QT—首层—第二层—最终焊缝—壳体的力流成立。它说明这个完整圆环几何在指定参考支承和荷载下的弹性刚度与应力分布，不给几何实体赋予熔合试验结果。来料和熔敷层的批次弹性/强度参数、实际压缩机荷载与支承可用相同输入重算。

初始场为冷态、无制造残余应力的有效接头。受载轴线位移不得与焊后完全卸夹的位置度相加替代制造结果；预制及最终组焊残余场、界面有效面积和局部弹塑性仍应由对应制造/连接验证给出。当前文件明确strength_verified=false、postweld_position_verified=false，保留可直接追算的输入、网格、原始场和收敛比较。
"""
    (HERE/"results/cold-structure-report-p1.md").write_text(report)
    print(json.dumps({"assessment":str(HERE/"results/assessment-p1.json"),"stiffness_convergence":stiffness_ok,"combined_axis_um":axes["combined"]["axis_diameter_envelope_um"]}))


if __name__=="__main__":main()
