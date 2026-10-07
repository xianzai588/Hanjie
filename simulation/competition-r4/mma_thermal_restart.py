"""Replay an accepted first-track prefix for a bounded endpoint time check."""
import json
import numpy as np


def accepted_prefix(folder,at_s,x,e,m):
    manifest=json.loads((folder/'nodal-thermal-history/manifest.json').read_text(encoding='utf8'))
    with np.load(folder/'mesh.npz') as mesh:
        if not all(np.array_equal(mesh[key],value) for key,value in [('x',x),('e',e),('material',m)]):
            raise ValueError('endpoint restart requires identical mesh and material indices')
    traces=[]
    for row in manifest['chunks']:
        if row['first_s']>at_s+1e-9:continue
        with np.load(folder/'nodal-thermal-history'/row['file']) as data:
            for i in np.flatnonzero(data['time_s']<=at_s+1e-9):
                traces.append((float(data['time_s'][i]),data['temperature_C'][i].copy(),data['deposit_fraction'][i].copy(),float(data['front_level_rad'][i])))
    if not traces or abs(traces[-1][0]-at_s)>1e-9:raise ValueError('restart time is not an accepted recorded increment')
    if any(t.max()>=2800 or t.min()<20.-1e-4 for _,t,_,_ in traces):
        raise ValueError('restart prefix is outside the thermal model domain')
    rows={}
    for key,filename in [('history','thermal-history.csv'),('source_history','source-partition-history.csv'),
                         ('birth_history','deposition-history.csv'),('source_path','source-path-history.csv')]:
        data=np.loadtxt(folder/filename,delimiter=',',skiprows=1,ndmin=2)
        rows[key]=data[data[:,0]<=at_s+1e-9].tolist()
    if len(rows['history'])!=len(traces):raise ValueError('thermal history and trace prefix lengths differ')
    return traces,rows
