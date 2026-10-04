"""Recover interface demand from saved service displacements, without a new solve.

The area-scaled springs define stiffness, not strength. Report the actual
traction demand and transfer equilibrium; no NiFe/QT allowable is assigned
to the QT/Ni99 interface or to the pure-Ni transition metal.
"""
from pathlib import Path
import argparse,json
import numpy as np

OUT=Path(__file__).parent/'results'


def evaluate(case):
    folder=OUT/case
    with np.load(folder/'mesh.npz') as mesh:
        x=mesh['x'];e=mesh['e'];material=mesh['material'];bd=mesh['boundary']
        nodes=mesh['link_nodes'];weights=mesh['link_weights']
    with np.load(folder/'service-area-fields.npz') as fields:u=fields['u_combined']
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    service=json.loads((folder/'service-area-result.json').read_text(encoding='utf8'))
    weld_nodes=np.unique(e[material==2]);cast_nodes=np.unique(e[material==1])
    top=float(x[weld_nodes,2].min())
    faces=bd[np.isin(bd[:,0],weld_nodes)]
    area=np.linalg.norm(np.cross(x[faces[:,1]]-x[faces[:,0]],x[faces[:,2]]-x[faces[:,0]]),axis=1)/2
    radii=np.linalg.norm(x[faces,:2],axis=2)
    selections=[np.all(abs(radii-75)<1e-4,axis=1),np.all(abs(x[faces,2]-top)<1e-4,axis=1)]
    nodal_area=[np.bincount(faces.ravel(),weights=np.repeat(area*mask/3,3),minlength=len(x)) for mask in selections]
    cast=np.isin(nodes[:,1],cast_nodes)
    link_area=np.where(cast,nodal_area[1][nodes[:,0]],nodal_area[0][nodes[:,0]])
    density=np.where(cast,75000/1.2,160000/inp['h_mm'])
    jump=np.sum(weights[:,:,None]*u[nodes],axis=1)
    traction=density[:,None]*jump
    force=link_area[:,None]*traction
    xyz=x[nodes[:,0]]
    # Saved weights reproduce coordinates. Thus force couples of each
    # interpolation patch conserve moment as well as resultant force.
    coordinate_residual=np.sum(weights[:,:,None]*x[nodes],axis=1)
    patch_error=float(np.linalg.norm(coordinate_residual,axis=1).max())
    outputs={}
    for name,mask in [('QT_Ni99_transition',cast),('Q235_NiFe',~cast)]:
        mask=mask&(link_area>0)
        normal=np.tile([0.,0.,1.],(int(mask.sum()),1)) if name.startswith('QT') else xyz[mask].copy()
        if not name.startswith('QT'):
            normal[:,2]=0;normal/=np.linalg.norm(normal,axis=1)[:,None]
        t=traction[mask];normal_value=np.sum(t*normal,axis=1)
        shear=np.linalg.norm(t-normal_value[:,None]*normal,axis=1)
        resultant=np.linalg.norm(t,axis=1);indices=np.flatnonzero(mask)
        peak=int(indices[np.argmax(resultant)])
        outputs[name]=dict(area_mm2=float(link_area[mask].sum()),
            maximum_absolute_normal_traction_MPa=float(abs(normal_value).max()),
            maximum_tangential_traction_MPa=float(shear.max()),
            maximum_resultant_traction_MPa=float(resultant.max()),
            required_normal_capacity_with_SF1_5_MPa=float(1.5*abs(normal_value).max()),
            required_shear_capacity_with_SF1_5_MPa=float(1.5*shear.max()),
            hotspot_xyz_mm=xyz[peak].tolist(),hotspot_traction_vector_MPa=traction[peak].tolist(),
            force_on_weld_N=(-force[mask].sum(axis=0)).tolist(),
            moment_on_weld_about_origin_N_mm=(-np.cross(xyz[mask],force[mask]).sum(axis=0)).tolist())
    # QT has only the hole load and the QT-side weld connection in this
    # unloaded service model. Its balancing spring resultant is the most
    # direct independent check on the recovered interface load.
    radius=inp['initial_bore_diameter_mm']/2
    bore_faces=bd[np.all(abs(np.linalg.norm(x[bd,:2],axis=2)-radius)<1e-4,axis=1)]
    ba=np.linalg.norm(np.cross(x[bore_faces[:,1]]-x[bore_faces[:,0]],x[bore_faces[:,2]]-x[bore_faces[:,0]]),axis=1)/2
    mass=np.bincount(bore_faces.ravel(),weights=np.repeat(ba/3,3),minlength=len(x));mass/=mass.sum()
    centre=mass@x
    load=service['load_conditions'];applied_force=np.array([load['Fr_N'],0.,load['Fa_N']])
    # service_check applies its Mx-labelled scalar as a z-force couple
    # proportional to y: the actual moment vector is about global x.
    xy=x[:,:2]-centre[:2]
    forces=np.zeros_like(x);forces[:,0]=load['Fr_N']*mass
    # Reproduce saved legacy load definitions. New solves explicitly declare
    # normalization of both moment components.
    if service.get('pure_couple_components_normalized'):
        couple=np.c_[xy[:,1],-xy[:,0]]
        coefficient=np.linalg.solve(couple.T@(mass[:,None]*couple),[load['Mx_Nmm'],0.])
        forces[:,2]=load['Fa_N']*mass+mass*(couple@coefficient)
    else:
        yy=xy[:,1]
        forces[:,2]=load['Fa_N']*mass+load['Mx_Nmm']*mass*yy/np.dot(mass,yy**2)
    applied_moment=np.cross(x,forces).sum(axis=0)
    cast_force=force[cast].sum(axis=0)
    cast_moment=np.cross(xyz[cast],force[cast]).sum(axis=0)
    force_residual=float(np.linalg.norm(cast_force+applied_force))
    moment_residual=float(np.linalg.norm(cast_moment+applied_moment))
    result=dict(case=case,initial_bore_diameter_mm=2*radius,interfaces=outputs,
        applied_hole_force_N=applied_force.tolist(),applied_hole_moment_about_origin_N_mm=applied_moment.tolist(),
        applied_pure_couple_about_weighted_hole_centre_N_mm=(applied_moment-np.cross(centre,applied_force)).tolist(),
        QT_force_balance_residual_N=force_residual,QT_moment_balance_residual_N_mm=moment_residual,
        interpolation_coordinate_residual_mm=patch_error,
        recovered_transfer_equilibrium_pass=bool(force_residual<=.01 and moment_residual<=1 and patch_error<=1e-7),
        scope='current saved combined linear-elastic service increment; area-scaled isotropic interface spring demand, not interface strength or inherited-residual verification',
        strength_interaction='normal/shear demands require a qualified mixed-mode criterion and QT/PMZ/transition metallurgy; separate SF1.5 demands do not certify their simultaneous interaction')
    (folder/'interface-service-demand.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    np.savez_compressed(folder/'interface-service-demand.npz',xyz=xyz,area_mm2=link_area,
        traction_MPa=traction,force_N=force,is_QT_interface=cast)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True)
    args=parser.parse_args();print(json.dumps(evaluate(args.case),ensure_ascii=False,indent=2))
