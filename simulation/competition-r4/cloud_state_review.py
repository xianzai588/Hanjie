"""Plot a committed checkpoint and compare its actual QT-side tie jumps.

The local paths are imposed monotonic displacement comparisons. They are not
the manufacturing history, a replacement equilibrium, or joint qualification.
"""
from pathlib import Path
import argparse,json
import numpy as np
from local_layer_diagnostic import response,principal,PD


def review(folder,output,checkpoint=None):
    folder,output=Path(folder),Path(output);output.mkdir(parents=True,exist_ok=True)
    with np.load(checkpoint or folder/'continuation-checkpoint.npz',allow_pickle=False) as cp:
        a={k:cp[k].copy() for k in cp.files}
    meta=json.loads(str(a['metadata']));t=meta['t']
    with np.load(folder/'mesh.npz',allow_pickle=False) as mesh:
        m=mesh['material'].copy();ln=mesh['link_nodes'].copy();lw=mesh['link_weights'].copy()
    assert np.array_equal(a['x'],np.load(folder/'mesh.npz')['x'])
    x,e=a['x'],a['e'];u=a['u'].reshape(-1,3);centres=x[e].mean(axis=1)
    cast=np.isin(ln[:,1],np.unique(e[m==1]));active=cast&a['mechanical_link_active']
    jump=np.einsum('ij,ijk->ik',lw,u[ln])-a['link_reference']
    ids=np.flatnonzero(active)
    if not len(ids):raise ValueError('no active QT-side links at this checkpoint')
    picks=np.unique([ids[np.argmax(np.linalg.norm(jump[ids],axis=1))],
        ids[np.argmax(jump[ids,2])],ids[np.argmin(jump[ids,2])],
        ids[np.argmax(np.linalg.norm(jump[ids,:2],axis=1))]])
    paths=[]
    for link in picks:
        for constraint in ('free_lateral_stress','restrained_lateral_strain'):
            plastic=np.zeros(6);eqp=0.;strain=np.zeros(6);rows=[]
            for scale in np.linspace(0,1,121):
                strain[2]=jump[link,2]*scale/1.2
                strain[3]=jump[link,1]*scale/(np.sqrt(2)*1.2)
                strain[4]=jump[link,0]*scale/(np.sqrt(2)*1.2)
                if constraint=='free_lateral_stress':
                    for iteration in range(40):
                        stress,D,pn,en=response(strain,plastic,eqp,205000.,.29,105.,1025.)
                        if np.linalg.norm(stress[:2])<1e-8:break
                        strain[:2]-=np.linalg.solve(D[:2,:2],stress[:2])
                    else:raise RuntimeError('local comparison reduction did not converge')
                stress,D,plastic,eqp=response(strain,plastic,eqp,205000.,.29,105.,1025.)
                q=float(np.sqrt(1.5*np.dot(PD@stress,PD@stress)))
                rows.append([scale,stress[2],stress[3]/np.sqrt(2),stress[4]/np.sqrt(2),q,float(principal(stress).max()),eqp])
            name=f'link-{link}-{constraint}'
            np.savez_compressed(output/f'{name}.npz',rows=np.array(rows),target_jump_mm=jump[link],birth_reference_mm=a['link_reference'][link])
            paths.append(dict(link=int(link),constraint=constraint,target_jump_mm=jump[link].tolist(),
                legacy_traction_MPa=(62500*jump[link]).tolist(),final_normal_traction_MPa=rows[-1][1],
                maximum_principal_MPa=max(row[5] for row in rows),final_eqp=eqp))
    report=dict(case=folder.name,checkpoint_t_s=t,released=bool(meta['rel']),complete_cold_release=False,
        maximum_temperature_C=float(a['temp'].max()),maximum_eqp=float(a['eqp'].max()),
        current_equilibrium_residual_N=float(meta['struct'][-1][2]),
        actual_QT_active_link_count=len(ids),maximum_actual_elastic_QT_traction_MPa=float(62500*np.linalg.norm(jump[ids],axis=1).max()),
        local_comparison=dict(material='wrought Ni200 comparison E205GPa nu.29 Y105MPa H1025MPa; not Ni99/PMZ properties',
            thickness_mm=1.2,loading='121 monotonic proportional jump steps to this current manufacturing state; no inherited local plastic state',
            sample_rule='maximum vector jump, maximum and minimum normal jump, maximum shear jump; not an exhaustive local FE search',paths=paths),
        connection_strength_pass=False,global_connection_feedback_complete=False,
        plot='top nodal values interpolated only on actual QT boundary triangles; QT midplane section uses constant saved element values; no fabricated measurements')
    (output/'state-review.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    np.savez_compressed(output/'committed-state.npz',**a)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.tri as tri
    from matplotlib.collections import PolyCollection
    fig,axes=plt.subplots(2,2,figsize=(11,9),layout='constrained')
    seat=np.unique(e[m==1]);zs=x[seat,2].max();surface=seat[abs(x[seat,2]-zs)<1e-5]
    if len(surface)<30:surface=seat[x[seat,2]>zs-1]
    with np.load(folder/'mesh.npz') as mesh:boundary=mesh['boundary'].copy()
    top=boundary[np.all(np.isin(boundary,surface),axis=1)]
    used=np.unique(top);lookup=np.full(len(x),-1);lookup[used]=np.arange(len(used))
    triangulation=tri.Triangulation(x[used,0],x[used,1],lookup[top])
    for ax,values,label in zip(axes.flat[:2],[a['temp'][used],np.linalg.norm(u[used],axis=1)*1000],
            ['QT top temperature (C)','QT top displacement norm (micrometre)']):
        artist=ax.tripcolor(triangulation,values,shading='gouraud',cmap='turbo',rasterized=True)
        fig.colorbar(artist,ax=ax,label=label);ax.set_aspect('equal');ax.set(xlabel='x (mm)',ylabel='y (mm)')
    stress=a['stress'];dev=stress.copy();dev[:,:3]-=stress[:,:3].mean(axis=1)[:,None]
    vm=np.sqrt(1.5*np.sum(dev*dev,axis=1));part=(m==1)&a['active']
    plane=(x[seat,2].min()+zs)/2;coords=x[e]
    intersect=np.flatnonzero(part&(coords[:,:,2].min(axis=1)<=plane)&(coords[:,:,2].max(axis=1)>=plane))
    polygons=[];cell_ids=[]
    for cell in intersect:
        points=[];tet=coords[cell]
        for i,j in ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3)):
            za,zb=tet[i,2]-plane,tet[j,2]-plane
            if za*zb<0:points.append((tet[i]+(-za/(zb-za))*(tet[j]-tet[i]))[:2])
            if abs(za)<1e-10:points.append(tet[i,:2])
            if abs(zb)<1e-10:points.append(tet[j,:2])
        points=np.unique(np.array(points),axis=0)
        if len(points)<3:continue
        centre=points.mean(axis=0);angle=np.arctan2(points[:,1]-centre[1],points[:,0]-centre[0])
        polygons.append(points[np.argsort(angle)]);cell_ids.append(cell)
    for ax,values,label in zip(axes.flat[2:],[vm[cell_ids],a['eqp'][cell_ids]*100],
            [f'QT section z={plane:g}: von Mises (MPa)',f'QT section z={plane:g}: equivalent plastic strain (%)']):
        artist=PolyCollection(polygons,array=values,cmap='turbo',edgecolors='none',rasterized=True)
        if np.max(values)==0:artist.set_clim(0,1)
        ax.add_collection(artist);ax.autoscale_view();ax.set_aspect('equal');ax.set(xlabel='x (mm)',ylabel='y (mm)')
        bar=fig.colorbar(artist,ax=ax,label=label)
        if np.max(values)==0:
            bar.set_ticks([0]);ax.set_title('Saved section values are all zero',fontsize=10)
    fig.suptitle(f'{folder.name}\nCommitted t={t:.6f} s; welding incomplete; no cold geometry qualification',fontsize=11)
    fig.savefig(output/'partial-state-cloud.png',dpi=180);plt.close(fig)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path)
    a=p.parse_args();r=review(a.case,a.output,a.checkpoint);print(json.dumps({k:r[k] for k in ('checkpoint_t_s','current_equilibrium_residual_N','maximum_actual_elastic_QT_traction_MPa','connection_strength_pass')}))
