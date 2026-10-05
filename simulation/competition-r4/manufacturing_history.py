"""Actual incremental constitutive/contact history, written in bounded chunks.

Thermal reset and plastic return are distinct events. Sparse records retain
float64 increments, not reconstructed differences of rounded snapshots.
"""
from pathlib import Path
import json
import numpy as np


class ManufacturingHistory:
    def __init__(self,folder,x,e,bore,pads,resume_time=None):
        self.folder=Path(folder)/'increment-history';self.folder.mkdir(exist_ok=True)
        self.rows=[];self.entries=[];self.chunk=0
        self.nn=len(x);self.ne=len(e);self.bore=np.asarray(bore)
        self.pad_nodes=np.unique(pads.nodes) if pads is not None else np.array([],int)
        self.pad_hosts=pads.nodes if pads is not None else np.empty((0,3),int)
        mapping=dict(bore_nodes=self.bore,pad_nodes=self.pad_nodes)
        if pads is not None:mapping.update(pad_hosts=pads.nodes,pad_weights=pads.weights,pad_area_mm2=pads.area,pad_number=pads.pad)
        np.savez_compressed(self.folder/'contact-mapping.npz',**mapping)
        old=sorted(self.folder.glob('chunk-*.npz'))
        if old:
            if resume_time is None:raise ValueError('increment history exists; use a new result folder')
            for path in old:
                with np.load(path,allow_pickle=False) as data:
                    times=data['time_s']
                    if times[-1]>resume_time+1e-8:raise ValueError('history extends beyond checkpoint; preserve it and select a consistent checkpoint')
                    self.entries.append(dict(file=path.name,count=len(times),first_s=float(times[0]),last_s=float(times[-1])))
            if abs(self.entries[-1]['last_s']-resume_time)>1e-8:raise ValueError('history does not end at the resumed checkpoint')
            self.chunk=len(old)
        elif resume_time is not None and resume_time>0:
            raise ValueError('cannot reconstruct missing pre-checkpoint incremental history')

    def append(self,t,release,reset,reset_reference,reset_temperature,plastic_increment,eqp_increment,bore_gap,pad_gap,residual):
        ids=np.flatnonzero(eqp_increment!=0)
        pids=np.flatnonzero(np.any(plastic_increment!=0,axis=1))
        rid=np.flatnonzero(reset)
        bm=(np.asarray(bore_gap)<0)&(not release)
        pm=(np.asarray(pad_gap)<=0)&(not release)
        nodal=np.zeros(len(self.pad_nodes),bool)
        if pm.size:
            active_nodes=np.unique(self.pad_hosts[pm])
            nodal[np.searchsorted(self.pad_nodes,active_nodes)]=True
        self.rows.append(dict(time_s=t,released=int(release),equilibrium_residual_N=residual,
          bore_mask=np.packbits(bm),bore_gap=np.asarray(bore_gap),pad_mask=np.packbits(pm),pad_gap=np.asarray(pad_gap),
          pad_node_mask=np.packbits(nodal),reset_ids=rid,reset_reference=reset_reference[rid],reset_temperature=reset_temperature[rid],
          plastic_ids=pids,plastic_increment=plastic_increment[pids],eqp_ids=ids,eqp_increment=eqp_increment[ids]))

    def flush(self):
        if not self.rows:return
        r=self.rows;data={key:np.asarray([z[key] for z in r]) for key in ['time_s','released','equilibrium_residual_N','bore_mask','bore_gap','pad_mask','pad_gap','pad_node_mask']}
        for prefix,keys in [('reset',['reset_reference','reset_temperature']),('plastic',['plastic_increment']),('eqp',['eqp_increment'])]:
            ids=[z[prefix+'_ids'] for z in r];data[prefix+'_offset']=np.r_[0,np.cumsum([len(v) for v in ids])]
            data[prefix+'_ids']=np.concatenate(ids)
            for key in keys:data[key]=np.concatenate([z[key] for z in r],axis=0)
        path=self.folder/f'chunk-{self.chunk:05d}.npz';tmp=self.folder/'chunk-next.npz'
        np.savez_compressed(tmp,**data);tmp.replace(path)
        self.entries.append(dict(file=path.name,count=len(r),first_s=float(r[0]['time_s']),last_s=float(r[-1]['time_s'])))
        self.chunk+=1;self.rows=[]
        manifest=dict(format_version=1,nodes=self.nn,elements=self.ne,bore_contact_points=len(self.bore),pad_surface_nodes=len(self.pad_nodes),
          scope='every converged mechanical increment; reset_reference and temperature recorded separately from return-map increments; no missing earlier steps reconstructed',
          chunks=self.entries)
        (self.folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
