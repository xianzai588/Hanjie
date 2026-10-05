"""Resolve observed interface quadrature fusion along each actual welded arc.

Each point's peak came from actual converged steps with both adjacent solids
active. Area is three-point quadrature, not a filled-face or bond-strength claim.
"""
from pathlib import Path
import argparse,csv,json
import numpy as np


def audit(case):
    with np.load(case/'material-interface-thermal.npz',allow_pickle=False) as data:
        xyz=data['quadrature_xyz_mm'];pairs=data['material_pairs'];segment=data['segment']
        area=data['face_area_mm2'];peak=data['peak_quadrature_C'];wet=data['thermally_active']
        ts=data['solidus_C'];tl=data['liquidus_C']
    rows=[];summary={}
    for pair,name in [([2,4],'Ni99_NiFe'),([0,2],'steel_NiFe')]:
        selected=np.all(pairs==pair,axis=1)&wet
        solidus=float(ts[pair].max());liquidus=float(tl[pair].max())
        summary[name]={}
        for j in [0,4]:
            select=selected&(segment==j)
            points=xyz[select].reshape(-1,3);temperature=peak[select].ravel()
            weight=np.repeat(area[select]/3,3)
            if not len(points):continue
            angle=np.arctan2(points[:,1],points[:,0])-j*np.pi/4
            angle=np.arctan2(np.sin(angle),np.cos(angle));arc=74.98*angle
            bins=np.clip(np.floor(arc+9).astype(int),0,17)
            per=[]
            for b in range(18):
                k=bins==b;physical=float(weight[k].sum())
                fused=float(weight[k&(temperature>=solidus)].sum())
                liquid=float(weight[k&(temperature>=liquidus)].sum())
                row=dict(interface=name,segment=j+1,arc_begin_mm=b-9,arc_end_mm=b-8,
                    observed_active_area_mm2=physical,both_solidus_area_mm2=fused,
                    both_liquidus_area_mm2=liquid,solidus_fraction=fused/physical if physical else None,
                    maximum_quadrature_C=float(temperature[k].max()) if k.any() else None)
                rows.append(row);per.append(row)
            summary[name][str(j+1)]=dict(observed_active_area_mm2=float(weight.sum()),
                both_solidus_area_mm2=float(weight[temperature>=solidus].sum()),
                bins_without_observed_fusion=[row['arc_begin_mm'] for row in per if not row['both_solidus_area_mm2']],
                bin_width_mm=1.)
    with (case/'fusion-footprint-by-arc.csv').open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result=dict(interfaces=summary,
        scope='actual fixed face quadrature points; temporal union at each point; 1mm arc bins and three-point area integration',
        spatial_time_convergence_verified=False,metallurgical_bond_capacity_verified=False)
    (case/'fusion-footprint-by-arc.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',type=Path,required=True)
    print(json.dumps(audit(parser.parse_args().case),indent=2))
