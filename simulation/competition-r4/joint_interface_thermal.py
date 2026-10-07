"""Track material-interface quadrature peaks at actual converged time steps."""
from pathlib import Path
import csv,json
import numpy as np


class InterfaceThermalObserver:
    def __init__(self,mesh,output,tables):
        self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True);self.step=0
        with np.load(Path(mesh)/'mesh.npz',allow_pickle=False) as d:x,e,m=d['x'],d['e'],d['material']
        faces=np.sort(np.vstack([e[:,p] for p in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1).astype(np.int32)
        owners=np.tile(np.arange(len(e)),4);order=np.lexsort(faces.T[::-1]);faces=faces[order];owners=owners[order]
        bounds=np.flatnonzero(np.r_[True,np.any(np.diff(faces,axis=0)!=0,axis=1),True])
        two=bounds[:-1][np.diff(bounds)==2];adj=np.c_[owners[two],owners[two+1]]
        pairs=np.sort(m[adj],axis=1);keep=pairs[:,0]!=pairs[:,1]
        self.faces=faces[two][keep];self.adj=adj[keep];self.pairs=pairs[keep];self.material=m
        self.layer_elements=e[np.isin(m,[1,3,4])]
        self.layer_material=m[np.isin(m,[1,3,4])]
        self.layer_indices=np.flatnonzero(np.isin(m,[1,3,4]))
        self.layer_xyz=x[self.layer_elements]
        lc=self.layer_xyz.mean(axis=1)
        self.layer_segment=np.round(np.arctan2(lc[:,1],lc[:,0])/(np.pi/4)).astype(int)%8
        self.minimum_melt_z=np.full((5,8),np.inf)
        self.witness_path=self.output/'melting-depth-witness.csv'
        with self.witness_path.open('w',newline='',encoding='utf8') as stream:
            csv.writer(stream).writerow(['t_s','material','segment','element','solidus_C','minimum_melt_z_mm','T0_C','T1_C','T2_C','T3_C'])
        xyz=x[self.faces];self.area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
        self.xyz=xyz;self.bary=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
        self.peak=np.full((len(self.faces),3),20.);self.wet=np.zeros(len(self.faces),bool)
        self.nodal_fused=np.zeros((len(self.faces),3),bool)
        self.solidus=np.array([t['fusion_enthalpy']['solidus_C'] for t in tables])
        self.remelt_solidus=np.array([t['fusion_enthalpy'].get('remelt_solidus_C',t['fusion_enthalpy']['solidus_C']) for t in tables])
        self.liquidus=np.array([t['fusion_enthalpy']['liquidus_C'] for t in tables])
        centre=xyz.mean(axis=1);theta=np.arctan2(centre[:,1],centre[:,0])
        self.segment=np.round(theta/(np.pi/4)).astype(int)%8

    def __call__(self,t,T,active,front_values=None,front_level=None):
        live=np.all(active[self.adj],axis=1)
        current=T[self.faces]@self.bary.T
        present=live[:,None]
        nodal_present=live[:,None]
        if front_values is not None:
            self.cut_front_observed=True
            has_deposit=np.any(self.pairs==3,axis=1)
            present=present&(~has_deposit[:,None]|(front_values[self.faces]@self.bary.T<=front_level))
            nodal_present=nodal_present&(~has_deposit[:,None]|(front_values[self.faces]<=front_level))
        self.peak=np.maximum(self.peak,np.where(present,current,20.));self.wet |= np.any(present*np.ones_like(current,dtype=bool),axis=1)
        threshold=self.solidus[self.pairs].max(axis=1)
        self.nodal_fused |= nodal_present&(T[self.faces]>=threshold[:,None])
        # At a given step P1 temperature is affine on a tetrahedron. The
        # lowest molten point is a hot vertex or an isotherm/edge crossing.
        # This records actual instantaneous fields, not asynchronous maxima.
        lt=T[self.layer_elements];ts=self.remelt_solidus[self.layer_material]
        molten=active[self.layer_indices] & (lt.max(axis=1)>=ts)
        if front_values is not None:
            # Depth witnesses for partially occupied deposit cells would
            # extrapolate into unborn metal. Their interface quadrature is
            # retained above; volume-depth witnesses wait for a full cell.
            molten &= (self.layer_material!=3)|(front_values[self.layer_elements].max(axis=1)<=front_level)
        if molten.any():
            vv=lt[molten];zz=self.layer_xyz[molten,:,2];ss=ts[molten]
            low=np.where(vv>=ss[:,None],zz,np.inf).min(axis=1)
            for a,b in [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]:
                cross=(vv[:,a]<ss)&(vv[:,b]>=ss)|(vv[:,b]<ss)&(vv[:,a]>=ss)
                delta=vv[cross,b]-vv[cross,a]
                level=zz[cross,a]+(ss[cross]-vv[cross,a])/delta*(zz[cross,b]-zz[cross,a])
                low[cross]=np.minimum(low[cross],level)
            np.minimum.at(self.minimum_melt_z,(self.layer_material[molten],self.layer_segment[molten]),low)
            witnesses=[]
            lm=self.layer_material[molten];ls=self.layer_segment[molten];li=self.layer_indices[molten]
            for material in [1,3,4]:
                for segment in [0,4]:
                    ids=np.flatnonzero((lm==material)&(ls==segment))
                    if len(ids):
                        k=ids[np.argmin(low[ids])]
                        witnesses.append([t,material,segment+1,int(li[k]),float(ss[k]),float(low[k]),*vv[k].tolist()])
            with self.witness_path.open('a',newline='',encoding='utf8') as stream:csv.writer(stream).writerows(witnesses)
        self.step+=1;self.time=t
        if self.step%25==0:self.save(partial=True)

    def save(self,partial=False):
        np.savez_compressed(self.output/'material-interface-thermal.npz',face_nodes=self.faces,
           adjacent_elements=self.adj,material_pairs=self.pairs,face_area_mm2=self.area,
           quadrature_barycentric=self.bary,quadrature_xyz_mm=np.einsum('qj,fjk->fqk',self.bary,self.xyz),
           peak_quadrature_C=self.peak,thermally_active=self.wet,nodal_fusion_mask=self.nodal_fused,
           segment=self.segment,solidus_C=self.solidus,liquidus_C=self.liquidus)
        rows={}
        for ids,name in [((2,4),'Ni99_NiFe'),((0,2),'steel_NiFe'),((1,3),'QT_first_Ni99'),((3,4),'Ni99_layers'),((1,2),'bare_QT_NiFe')]:
            selected=np.all(self.pairs==ids,axis=1);ts=max(self.solidus[list(ids)]);tl=max(self.liquidus[list(ids)])
            rows[name]=dict(solidus_threshold_C=ts,liquidus_threshold_C=tl,
                physical_face_area_mm2=float(self.area[selected].sum()),
                maximum_observed_quadrature_C=float(self.peak[selected].max()) if selected.any() else None,
                area_above_both_solidus_mm2=float(np.sum(self.area[selected]*np.mean(self.peak[selected]>=ts,axis=1))),
                area_above_both_liquidus_mm2=float(np.sum(self.area[selected]*np.mean(self.peak[selected]>=tl,axis=1))),
                by_segment_above_solidus_mm2={str(j+1):float(np.sum(self.area[selected&(self.segment==j)]*np.mean(self.peak[selected&(self.segment==j)]>=ts,axis=1))) for j in [0,4]})
        result=dict(t_s=float(self.time),steps=self.step,partial=partial,interfaces=rows,
          actual_P1_melting_depth_below_z115_mm={str(i):{str(j+1):float(115-self.minimum_melt_z[i,j]) if np.isfinite(self.minimum_melt_z[i,j]) else None for j in [0,4]} for i in [1,3,4]},
          scope='actual per-time-step P1 face quadrature; only when both adjacent solids thermally active; union of melting events',
          spatial_time_convergence_verified=False,precoat_state_verified=False)
        if getattr(self,'cut_front_observed',False):
            result['cut_front_scope']='interface quadrature/nodes require actual front arrival; Ni volume-depth witnesses use fully occupied cells only'
        (self.output/'interface-thermal-history-summary.json').write_text(json.dumps(result,indent=2),encoding='utf8')
        (self.output/'progress.json').write_text(json.dumps(dict(t_s=float(self.time),thermal_steps=self.step,
           Ni99_interface_peak_C=rows['Ni99_NiFe']['maximum_observed_quadrature_C'],steel_interface_peak_C=rows['steel_NiFe']['maximum_observed_quadrature_C'])),encoding='utf8')
        return result
