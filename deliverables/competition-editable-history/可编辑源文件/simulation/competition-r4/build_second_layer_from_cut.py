"""Conforming second-layer envelope on the actual cold, re-equilibrated cut.

Split only cut CI parent tetrahedra. Both sides use identical edge nodes and
face diagonals. Surviving parent tensors are transferred into the actual cold
coordinate frame; changing coordinates does not remove residual stress.
"""
import argparse
import json
import numpy as np
import yaml
from scipy.optimize import brentq
from mma_conservative_birth import clipped_moments
from mma_literature_profile import ROOT
from run_candidate_solver import operators
from run_first_layer_machining import datum_frame


def normal_surface(x):
    r=np.linalg.norm(x[:,:2],axis=1)
    value=np.where(r>=70.48,x[:,2]-114.2,
        np.maximum(x[:,2]-115,.8-np.hypot(r-70.48,x[:,2]-115)))
    value[abs(value)<1e-9]=0.
    return value


def rotate_kelvin(v,basis):
    tensor=np.zeros((len(v),3,3));tensor[:,range(3),range(3)]=v[:,:3]
    for j,(a,b) in enumerate([(1,2),(0,2),(0,1)]):
        tensor[:,a,b]=tensor[:,b,a]=v[:,j+3]/np.sqrt(2)
    q=np.einsum('ia,eij,jb->eab',basis,tensor,basis)
    return np.column_stack([q[:,0,0],q[:,1,1],q[:,2,2],
        np.sqrt(2)*q[:,1,2],np.sqrt(2)*q[:,0,2],np.sqrt(2)*q[:,0,1]])


def split_mesh(x,e,m,signed,temperature=None):
    nodes=x.tolist();children=[];materials=[];parents=[];edge_nodes={}
    temperatures=None if temperature is None else temperature.tolist()
    def cross(a,b):
        if signed[a]==0:return int(a)
        if signed[b]==0:return int(b)
        key=tuple(sorted([int(a),int(b)]))
        if key not in edge_nodes:
            f=signed[a]/(signed[a]-signed[b])
            edge_nodes[key]=len(nodes);nodes.append(((1-f)*x[a]+f*x[b]).tolist())
            if temperatures is not None:temperatures.append(float((1-f)*temperature[a]+f*temperature[b]))
        return edge_nodes[key]
    def polygon(face,side):
        result=[]
        for a,b in zip(face,np.roll(face,-1)):
            inside=side*signed[a]<=0;next_inside=side*signed[b]<=0
            if inside:result.append(int(a))
            if inside!=next_inside:result.append(cross(a,b))
        return list(dict.fromkeys(result))
    def fan(ids):
        k=ids.index(min(ids));ids=ids[k:]+ids[:k]
        return [[ids[0],ids[j],ids[j+1]] for j in range(1,len(ids)-1)]
    for parent,tet in enumerate(e):
        v=signed[tet]
        if m[parent]!=3 or v.max()<=0 or v.min()>=0:
            children.append(tet.tolist());materials.append(int(m[parent] if m[parent]!=3 or v.max()<=0 else 4));parents.append(parent)
            continue
        cut=[]
        for a in range(4):
            if v[a]==0:cut.append(int(tet[a]))
            for b in range(a+1,4):
                if v[a]*v[b]<0:cut.append(cross(tet[a],tet[b]))
        cut=list(dict.fromkeys(cut));p=np.array(nodes)[cut]
        centre=p.mean(axis=0);_,_,axes=np.linalg.svd(p-centre,full_matrices=False)
        angles=np.arctan2((p-centre)@axes[1],(p-centre)@axes[0]);cut=np.array(cut)[np.argsort(angles)].tolist()
        for side,material in [(1,3),(-1,4)]:
            faces=[polygon(tet[q],side) for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]
            faces.append(cut);faces=[face for face in faces if len(face)>=3]
            used=np.unique(np.concatenate(faces));point=np.array(nodes)[used].mean(axis=0)
            centre_id=len(nodes);nodes.append(point.tolist())
            if temperatures is not None:temperatures.append(float(np.array(temperatures)[used].mean()))
            for face in faces:
                for triangle in fan(face):
                    children.append([centre_id,*triangle]);materials.append(material);parents.append(parent)
    result=(np.array(nodes),np.array(children,int),np.array(materials,np.int8),np.array(parents,int))
    return result if temperatures is None else (*result,np.array(temperatures))


def run(source,output,deposition_efficiency=.94):
    if output.exists():raise ValueError('Preserve existing second-layer geometry evidence')
    result=json.loads((source/'result.json').read_text())
    if not result.get('machining_demand_equilibrated') or result['partial']:
        raise ValueError('Second layer requires the completed actual cold cut and re-equilibration')
    card=yaml.safe_load((ROOT/'project/precoat-process-design.yaml').read_text(encoding='utf8'))['second']
    if not card['deposition_efficiency_range'][0]<=deposition_efficiency<=card['deposition_efficiency_range'][1]:
        raise ValueError('Deposition efficiency outside the frozen accounting range')
    with np.load(source/'fields.npz') as f:
        old={key:f[key].copy() for key in f.files}
    with np.load(source/'machining-cut.npz') as f:
        cut_coordinates=f['registered_cold_coordinates'].copy();expected=f['retained_P1_moments'].sum(axis=1)
    current,registration=datum_frame(old['x'],old['u'],old['e'],old['material'])
    representative=np.arange(len(current))
    for a,b in old['current_bond_pairs']:
        if np.linalg.norm(current[a]-current[b])>1e-7:raise ValueError('Qualified cold interface is geometrically open')
        representative[b]=a
    # Require all original interface vertices to belong to qualified cold bonds.
    required=np.unique(old['original_fusion_faces'])
    if not np.all(np.isin(required,old['current_bond_pairs'][:,0])):
        raise ValueError('Incomplete first-layer cold connection; do not merge an unqualified interface')
    e=representative[old['e']]
    x,children,m,parent,temperature=split_mesh(current,e,old['material'],normal_surface(cut_coordinates),old['temperature_C'])
    _,vol,_,_=operators(x,children,False)
    original_physical=abs(np.linalg.det((current[e[:,1:]]-current[e[:,:1]]).transpose(0,2,1)))/6
    retained=np.bincount(parent[m==3],weights=vol[m==3],minlength=len(e))
    # Geometric partition uses the same P1 contour as the actual cutting step.
    partition=np.bincount(parent,weights=vol,minlength=len(e))
    if np.max(abs(partition-original_physical))>1e-8 or np.max(abs(retained[old['material']==3]-original_physical[old['material']==3]*expected[old['material']==3]))>1e-8:
        raise RuntimeError('Actual cut tetrahedral partition does not close')
    required_volume=np.pi*(card['diameter_mm']/2)**2*card['feed_mm_s']*card['track_length_per_wing_mm']/card['travel_mm_s']*deposition_efficiency
    fill_volume=float(vol[m==4].sum());extra=required_volume-fill_volume
    if extra<=0:raise ValueError('Frozen feed cannot fill the actual removed envelope; revise the physical route')
    faces=np.sort(np.vstack([children[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    owners=np.tile(np.arange(len(children)),4);unique,first,count=np.unique(faces,axis=0,return_index=True,return_counts=True)
    roof=unique[(count==1)&(m[owners[first]]==4)]
    # The original envelope roof remains the substrate for additional feed.
    old_top=old['x'][np.unique(old['e'][old['material']==3]),2].max()
    original_roof=np.flatnonzero(abs(old['x'][:,2]-old_top)<1e-7)
    roof=roof[np.all(np.isin(roof,representative[original_roof]),axis=1)]
    xyz=x[roof];area_vector=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])/2
    projected=float(abs(area_vector[:,2]).sum())
    if projected<=0:raise ValueError('Actual original deposited roof not found')
    height=extra/projected;nodes=x.tolist();upper={};temperatures=temperature.tolist()
    for node in np.unique(roof):
        upper[int(node)]=len(nodes);nodes.append((x[node]+[0,0,height]).tolist());temperatures.append(20.)
    caps=[]
    for a,b,c in np.sort(roof,axis=1):
        A,B,C=upper[int(a)],upper[int(b)],upper[int(c)]
        caps.extend([[a,b,c,C],[a,b,B,C],[a,A,B,C]])
    x=np.array(nodes);children=np.vstack([children,np.array(caps,int)]);m=np.r_[m,np.full(len(caps),4,np.int8)]
    parent=np.r_[parent,np.full(len(caps),-1,int)]
    used=np.unique(children);remap=np.full(len(x),-1,int);remap[used]=np.arange(len(used));x=x[used];children=remap[children];temperature=np.array(temperatures)[used]
    _,vol,_,_=operators(x,children,False)
    if abs(vol[m==4].sum()-required_volume)>1e-8:raise RuntimeError('Actual Ni99 feed-envelope volume does not close')
    # The two real continuous arcs have slightly different lengths. Assign
    # their envelope domains by exact volume, so constant feed cannot create
    # a different mass/time history merely because a radial strip is wider.
    budget=json.loads((ROOT/'studies/COMPETITION-DESIGN/results/precoat-input-budget.json').read_text())
    tracks=budget['track_geometry']['wings'][0]['tracks']
    lengths=np.array([row['arc_length_mm'] for row in tracks])
    if abs(lengths.sum()-card['track_length_per_wing_mm'])>1e-8:raise ValueError('Actual CAD arcs and second-layer card differ')
    deposit=np.flatnonzero(m==4);radius=np.linalg.norm(x[:,:2],axis=1);local_r=radius[children[deposit]]
    inner_volume=required_volume*lengths[0]/lengths.sum()
    def domain_volume(boundary):
        return sum(vol[k]*clipped_moments(values,boundary).sum() for k,values in zip(deposit,local_r))
    radial_boundary=brentq(lambda value:domain_volume(value)-inner_volume,float(local_r.min()),float(local_r.max()),xtol=1e-11)
    temporary=np.where(m==4,3,np.where(m==3,2,1)).astype(np.int8)
    x,new_e,new_m,new_parent,temperature=split_mesh(x,children,temporary,radius-radial_boundary,temperature)
    m=np.where(new_m==2,3,np.where(new_m==3,4,np.where(new_m==4,5,1))).astype(np.int8)
    parent=parent[new_parent];children=new_e
    _,vol,_,_=operators(x,children,False)
    if abs(vol[m==4].sum()-inner_volume)>1e-8 or abs(vol[m==5].sum()-(required_volume-inner_volume))>1e-8:
        raise RuntimeError('Two-track envelope dose split does not close')
    _,_,old_B,old_dof=operators(old['x'],old['e'],True)
    strain=np.einsum('eij,ej->ei',old_B,old['u'].ravel()[old_dof])
    basis=np.array(registration['rotation_columns'])
    inherited=m<4;indices=parent[inherited]
    cut_input=json.loads((source/'input.json').read_text());mechanical_source=ROOT/cut_input['source']
    first_source=ROOT/json.loads((mechanical_source/'input.json').read_text())['source']
    first_tables=json.loads((first_source/'input.json').read_text())['materials']
    original_density=np.array([row['nominal_properties_20c']['density_kg_m3'] for row in first_tables])[old['material']]*1e-9
    parent_mass=old['material_mass_kg'] if 'material_mass_kg' in old else original_density*old['volume_mm3']
    material_mass=8890e-9*vol
    material_mass[inherited]=parent_mass[indices]*vol[inherited]/original_physical[indices]
    expected_surviving_mass=float(parent_mass@old['occupation'])
    if abs(material_mass[inherited].sum()-expected_surviving_mass)>max(1e-12,expected_surviving_mass*1e-9):
        raise RuntimeError('Surviving material mass changed during coordinate/tetrahedron update')
    plastic=np.zeros((len(children),6));reference=plastic.copy();stress=plastic.copy();eqp=np.zeros(len(children));remelted=np.zeros(len(children),bool)
    plastic[inherited]=rotate_kelvin(old['plastic'][indices],basis)
    reference[inherited]=rotate_kelvin((old['solid_reference_strain']-strain)[indices],basis)
    stress[inherited]=rotate_kelvin(old['stress'][indices],basis);eqp[inherited]=old['eqp'][indices];remelted[inherited]=old['remelted_QT'][indices]
    occupation=(m<4).astype(float);output.mkdir(parents=True)
    np.savez_compressed(output/'mesh.npz',x=x,e=children,material=m,parent_element=parent,volume_mm3=vol,material_mass_kg=material_mass)
    np.savez_compressed(output/'inherited-state.npz',x=x,e=children,material=m,volume_mm3=vol,
        u=np.zeros_like(x),plastic=plastic,eqp=eqp,solid_reference_strain=reference,stress=stress,
        solid_weight=occupation,occupation=occupation,remelted_QT=remelted,
        temperature_C=temperature,source_parent=parent,material_mass_kg=material_mass)
    audit=dict(source=str(source),registration=registration,nodes=len(x),tetrahedra=len(children),
        retained_first_actual_volume_mm3=float(vol[m==3].sum()),second_envelope_volume_mm3=float(vol[m>=4].sum()),
        prescribed_wire_volume_mm3=required_volume,deposition_efficiency_design_case=deposition_efficiency,
        continuous_track_geometry=tracks,radial_dose_boundary_mm=radial_boundary,
        track_deposit_volume_mm3=[float(vol[m==j].sum()) for j in (4,5)],
        actual_removed_envelope_mm3=fill_volume,additional_roof_height_mm=height,
        maximum_parent_partition_error_mm3=float(abs(partition-original_physical).max()),
        surviving_material_mass_kg=float(material_mass[inherited].sum()),source_surviving_mass_kg=expected_surviving_mass,
        mass_transfer_policy='advect each surviving reference material mass into actual child geometry; no mass replacement by nominal density times deformed volume',
        state_transfer='actual cold coordinate update; reference_new=rotate(reference_old-B_old*u_old), plastic/eqp/stress retained per surviving parent; new Ni99 unborn',
        first_layer_residual_stress_reset=False,second_layer_fusion_verified=False,full_manufacturing_verified=False)
    (output/'geometry-state-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True);p.add_argument('--deposition-efficiency',type=float,default=.94)
    a=p.parse_args();run(a.source,a.output,a.deposition_efficiency)
