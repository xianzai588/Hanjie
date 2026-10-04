"""Current full assembly: implicit heat conduction and incremental J2 tetrahedral FE.

Units mm, N, s, C, MPa. This is an engineering model, not measured data.
All arrays, input choices and equilibrium/convergence records are saved.
"""
from pathlib import Path
import argparse, json, time, sys
import numpy as np
import gmsh, yaml
from scipy.sparse import coo_matrix, diags, bmat
from scipy.sparse.linalg import spsolve,cg,LinearOperator
from threadpoolctl import threadpool_limits

DIRECT_SOLVER_NAME="SciPy SuperLU"
SOLVER_THREADS=1
thermal_spsolve=spsolve
structural_spsolve=spsolve

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from hanjie.simulation.structural_prep import fit_position_diameter

def mesh_conforming_attempt(n, h):
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0)
        gmsh.model.add('full-part')
        occ=gmsh.model.occ
        seat=occ.importShapes(str(ROOT/f'simulation/structural-v4/models/{n}p-fair-b/{n}P-FAIR_B.step'))
        occ.translate(seat,0,0,100)
        shell=occ.importShapes(str(ROOT/'simulation/structural-v4/common/shell.step'))
        beads=[]
        for i in range(n):
            for leg in (2.8,4.):
                ps=[occ.addPoint(r,0,z) for r,z in ((74.96-leg,112),(75.01,112),(75.01,112+leg))]
                ls=[occ.addLine(ps[j],ps[(j+1)%3]) for j in range(3)]
                surf=occ.addPlaneSurface([occ.addCurveLoop(ls)])
                angle=18/74.98
                occ.rotate([(2,surf)],0,0,0,0,0,1,i*2*np.pi/n-angle/2)
                swept=occ.revolve([(2,surf)],0,0,0,0,0,1,angle)
                beads.append([d for d in swept if d[0]==3][0])
        entities, maps=occ.fragment(seat+shell,beads)
        occ.synchronize()
        seatids={x[1] for x in maps[0] if x[0]==3}
        shellids={x[1] for x in maps[len(seat)] if x[0]==3}
        beadids={x[1] for m in maps[len(seat)+len(shell):] for x in m if x[0]==3}-seatids-shellids
        gmsh.option.setNumber('Mesh.MeshSizeMin',h)
        gmsh.option.setNumber('Mesh.MeshSizeMax',h*5)
        # Distance refinement includes real weld and slot-root surfaces.
        near=[]
        for dim,tag in entities:
            if dim==3 and tag in beadids:
                near.extend(t for d,t in gmsh.model.getBoundary([(dim,tag)],False,False) if d==2)
        fld=gmsh.model.mesh.field.add('Distance')
        gmsh.model.mesh.field.setNumbers(fld,'FacesList',list(set(near)))
        gmsh.model.mesh.field.setNumber(fld,'Sampling',40)
        th=gmsh.model.mesh.field.add('Threshold')
        for k,v in {'InField':fld,'SizeMin':h,'SizeMax':h*5,'DistMin':3,'DistMax':18}.items():
            gmsh.model.mesh.field.setNumber(th,k,v)
        gmsh.model.mesh.field.setAsBackgroundMesh(th)
        gmsh.option.setNumber('Mesh.MinimumCirclePoints',200)
        gmsh.option.setNumber('Mesh.Algorithm3D',1)
        gmsh.model.mesh.generate(3)
        tags,xyz,_=gmsh.model.mesh.getNodes()
        ix={int(v):i for i,v in enumerate(tags)}
        x=np.array(xyz).reshape(-1,3)
        ee=[]; mm=[]
        for dim,tag in entities:
            if dim!=3: continue
            _,conn=gmsh.model.mesh.getElementsByType(4,tag)
            ee.extend(np.array([ix[int(v)] for v in conn]).reshape(-1,4))
            mat=0 if tag in shellids else 1 if tag in seatids else 2
            mm.extend([mat]*(len(conn)//4))
        e=np.array(ee); m=np.array(mm)
        # Use only exterior faces; internal conforming faces cancel.
        faces=np.sort(np.vstack([e[:,[0,1,2]],e[:,[0,1,3]],e[:,[0,2,3]],e[:,[1,2,3]]]),axis=1)
        uniq,count=np.unique(faces,axis=0,return_counts=True)
        bd=uniq[count==1]
        if not all(np.any(m==j) for j in range(3)): raise RuntimeError('missing material region')
        return x,e,m,bd
    finally: gmsh.finalize()

def mesh(n,h,weld_h=1.,seat_path=None,root_h=None):
    """Independent solid meshes avoid facets crossing the real 0.02 mm fit gap.
    Weld interfaces use explicit interpolation constraints, never join bare wing sides.
    """
    from scipy.spatial import cKDTree
    # Measure the actual outer interface height, including candidate geometries.
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0);gmsh.model.add('interface-height')
        gmsh.model.occ.importShapes(str(seat_path or ROOT/f'simulation/structural-v4/models/{n}p-fair-b/{n}P-FAIR_B.step'))
        gmsh.model.occ.synchronize();outer_z=[]
        for dim,tag in gmsh.model.getEntities(0):
            point=gmsh.model.getValue(dim,tag,[])
            if np.hypot(point[0],point[1])>74.9:outer_z.append(point[2])
        if not outer_z:raise RuntimeError('outer seat interface vertices missing')
        seat_top=100+round(max(outer_z),6)
    finally:gmsh.finalize()
    allx=[];alle=[];allm=[];allbd=[]; offsets=[]
    for part in range(3):
        gmsh.initialize()
        try:
            gmsh.option.setNumber('General.Terminal',0);gmsh.model.add('part')
            occ=gmsh.model.occ
            if part==0:occ.importShapes(str(ROOT/'simulation/structural-v4/common/shell.step'))
            elif part==1:
                seat=occ.importShapes(str(seat_path or ROOT/f'simulation/structural-v4/models/{n}p-fair-b/{n}P-FAIR_B.step'))
                occ.translate(seat,0,0,100)
            else:
                roots=[];covers=[]
                for j in range(n):
                    current=[]
                    for leg in (2.8,4.):
                        pts=[occ.addPoint(r,0,z) for r,z in ((75-leg,seat_top),(75,seat_top),(75,seat_top+leg))]
                        ls=[occ.addLine(pts[k],pts[(k+1)%3]) for k in range(3)]
                        surf=occ.addPlaneSurface([occ.addCurveLoop(ls)])
                        angle=18/74.98;occ.rotate([(2,surf)],0,0,0,0,0,1,j*2*np.pi/n-angle/2)
                        current.append([d for d in occ.revolve([(2,surf)],0,0,0,0,0,1,angle) if d[0]==3][0])
                    roots.append(current[0]);covers.append(current[1])
                occ.fragment(roots,covers)
            occ.synchronize()
            gmsh.option.setNumber('Mesh.MeshSizeMin',.75*min(h,weld_h,root_h if root_h else h))
            gmsh.option.setNumber('Mesh.MeshSizeMax',h*(3 if part==0 else 2) if part<2 else weld_h)
            gmsh.option.setNumber('Mesh.Algorithm3D',1)
            if part<2:
                # Cylindrical faces have centroid z=100, so a centroid-z filter
                # misses the entire weld band. Distance to the eight real arcs
                # refines both parent solids around the heat source instead.
                curves=[]
                for jj in range(n):
                    angle=jj*2*np.pi/n
                    curves.append(occ.addCircle(0,0,seat_top,75,angle1=angle-9/75,angle2=angle+9/75))
                occ.synchronize()
                field=gmsh.model.mesh.field.add('Distance')
                gmsh.model.mesh.field.setNumbers(field,'CurvesList',curves)
                gmsh.model.mesh.field.setNumber(field,'Sampling',60)
                f=gmsh.model.mesh.field.add('Threshold')
                for key,val in {'InField':field,'SizeMin':weld_h,'SizeMax':h*(3 if part==0 else 2),'DistMin':2,'DistMax':12}.items():gmsh.model.mesh.field.setNumber(f,key,val)
                if part==1 and root_h is not None:
                    root_faces=[]
                    for dim,tag in gmsh.model.getEntities(2):
                        centre=occ.getCenterOfMass(dim,tag);bounds=gmsh.model.getBoundingBox(dim,tag)
                        if 35<np.hypot(centre[0],centre[1])<47 and bounds[5]-bounds[2]>seat_top-100-.01:root_faces.append(tag)
                    if not root_faces:raise RuntimeError('physical root faces missing')
                    root_distance=gmsh.model.mesh.field.add('Distance')
                    gmsh.model.mesh.field.setNumbers(root_distance,'FacesList',root_faces)
                    gmsh.model.mesh.field.setNumber(root_distance,'Sampling',60)
                    root_field=gmsh.model.mesh.field.add('Threshold')
                    for key,val in {'InField':root_distance,'SizeMin':root_h,'SizeMax':h*2,'DistMin':.7,'DistMax':3.}.items():gmsh.model.mesh.field.setNumber(root_field,key,val)
                    combined=gmsh.model.mesh.field.add('Min')
                    gmsh.model.mesh.field.setNumbers(combined,'FieldsList',[f,root_field])
                    gmsh.model.mesh.field.setAsBackgroundMesh(combined)
                else:gmsh.model.mesh.field.setAsBackgroundMesh(f)
            gmsh.model.mesh.generate(3)
            tags,xx,_=gmsh.model.mesh.getNodes();ix={int(v):i for i,v in enumerate(tags)}
            coords=np.array(xx).reshape(-1,3);_,conn=gmsh.model.mesh.getElementsByType(4)
            elems=np.array([ix[int(z)] for z in conn]).reshape(-1,4)
            # Refinement-only curves carry nodes outside the solid FE closure.
            used=np.unique(elems); remap=np.full(len(coords),-1,int);remap[used]=np.arange(len(used))
            coords=coords[used];elems=remap[elems]
            offset=sum(len(v) for v in allx);offsets.append(offset)
            faces=np.sort(np.vstack([elems[:,[0,1,2]],elems[:,[0,1,3]],elems[:,[0,2,3]],elems[:,[1,2,3]]]),axis=1)
            uf,cnt=np.unique(faces,axis=0,return_counts=True)
            allx.append(coords);alle.append(elems+offset);allm.extend([part]*len(elems));allbd.append(uf[cnt==1]+offset)
        finally:gmsh.finalize()
    x=np.vstack(allx);e=np.vstack(alle);m=np.array(allm);bd=np.vstack(allbd)
    links=[]
    for part in (0,1):
        nodes=np.unique(allbd[part]);rr=np.linalg.norm(x[nodes,:2],axis=1)
        if part==0:target=nodes[(rr<75.05)&(x[nodes,2]>seat_top-7)&(x[nodes,2]<seat_top+10)]
        else:target=nodes[abs(x[nodes,2]-seat_top)<1e-5]
        if len(target)<4:raise RuntimeError("actual weld interface has fewer than four host nodes")
        tree=cKDTree(x[target]);weldnodes=np.unique(allbd[2]);wr=np.linalg.norm(x[weldnodes,:2],axis=1)
        pick=weldnodes[(abs(wr-75)<1e-5) if part==0 else (abs(x[weldnodes,2]-seat_top)<1e-5)]
        if len(pick)==0:raise RuntimeError(f'material {part} has no physical weld interface')
        from affine_interface import interface_links
        links.extend(interface_links(x,target,pick,planar=part==1))
    return x,e,m,bd,links

def operators(x,e):
    xe=x[e]
    a=np.concatenate((np.ones((len(e),4,1)),xe),axis=2)
    g=np.linalg.inv(a)[:,1:,:].transpose(0,2,1)
    vol=np.abs(np.linalg.det((xe[:,1:]-xe[:,:1]).transpose(0,2,1)))/6
    b=np.zeros((len(e),6,12))
    for j in range(4):
        gx,gy,gz=g[:,j,:].T; k=3*j
        b[:,0,k]=gx;b[:,1,k+1]=gy;b[:,2,k+2]=gz
        b[:,3,k+1]=gz/np.sqrt(2);b[:,3,k+2]=gy/np.sqrt(2)
        b[:,4,k]=gz/np.sqrt(2);b[:,4,k+2]=gx/np.sqrt(2)
        b[:,5,k]=gy/np.sqrt(2);b[:,5,k+1]=gx/np.sqrt(2)
    dof=(3*e[:,:,None]+np.arange(3)).reshape(-1,12)
    return g,vol,b,dof

def run(n,h,dt,output,imbalance=0.,preheat=20.,stop_time=None,thermal_only=False,struct_dt=5.,contact_density=2000.,copper_h=50.,source_radius=2.2,source_depth=1.6,weld_h=1.,source_r=73.8,use_amg=False,cold_struct_dt=None,seat_path=None,root_h=None,peening_trace=False,peening_all=False,thermal_observer=None,event_dT=None,paired=False,unilateral_pads=False,material_enthalpy=False,initial_bore_diameter=40.014,resume=False,checkpoint=False,fixture_contact_h=None,fixture_refinement=1):
    output.mkdir(parents=True,exist_ok=True)
    clock=time.perf_counter(); x,e,m,bd,links=mesh(n,h,weld_h,seat_path,root_h)
    # Morph the nominal CAD bore to the declared manufacturing verification point.
    # Reassemble geometry, thermal capacity/conductivity and contact for that point.
    bore_radius=initial_bore_diameter/2
    radii=np.linalg.norm(x[:,:2],axis=1); bore_geom=np.abs(radii-20)<1e-4
    x[bore_geom,:2]*=bore_radius/20
    np.savez_compressed(output/'mesh.npz',x=x,e=e,material=m,boundary=bd,link_nodes=np.array([[z[0],*z[1]] for z in links]),link_weights=np.array([[1.,*[-v for v in z[2]]] for z in links]))
    from affine_interface import audit as interface_audit
    interface_patch=interface_audit(x,links)
    print('mesh',n,h,len(x),len(e),interface_patch,flush=True)
    g,vol,b,dof=operators(x,e); c=x[e].mean(axis=1)
    weld_top=float(np.min(x[np.unique(e[m==2]),2]))
    radius=np.linalg.norm(c[:,:2],axis=1); theta=np.arctan2(c[:,1],c[:,0])%(2*np.pi)
    segment=np.round(theta/(2*np.pi/n)).astype(int)%n
    local=(theta-segment*2*np.pi/n+np.pi)%(2*np.pi)-np.pi
    along=local*74.98+9
    layer=np.where(75.01-c[:,0]*np.cos(theta)-c[:,1]*np.sin(theta)+c[:,2]-weld_top<2.8,0,1)
    order=list(range(0,n,2))+list(range(1,n,2))
    if n==6: order=[0,3,2,5,1,4]
    if n==8: order=[0,4,2,6,1,5,3,7]
    seq=[(p,j) for p in range(2) for j in order]
    stages=[seq[i:i+2] for i in range(0,len(seq),2)] if paired else [[item] for item in seq]
    if paired and any(len(stage)!=2 or stage[0][0]!=stage[1][0] or (stage[1][1]-stage[0][1])%n!=n//2 for stage in stages):
        raise ValueError('paired stages must contain diametrically opposed segments of one pass')
    stage_index={tuple(item):i for i,stage in enumerate(stages) for item in stage}
    v=1.65; duration=18/v; idle=18.; interval=duration+idle
    starts=np.array([stage_index[(int(layer[k]),int(segment[k]))]*interval if m[k]==2 else -1e6 for k in range(len(e))])
    birth=starts+np.clip(along/v,0,duration)
    # Physical surface areas supply convection, radiation and fixture cooling.
    area=np.linalg.norm(np.cross(x[bd[:,1]]-x[bd[:,0]],x[bd[:,2]]-x[bd[:,0]]),axis=1)/2
    surface=np.bincount(bd.ravel(),weights=np.repeat(area/3,3),minlength=len(x))
    bx=x[bd].mean(axis=1); br=np.linalg.norm(bx[:,:2],axis=1)
    sys.path.insert(0,str(ROOT/'studies/COMPETITION-DESIGN'))
    from seal_design import evaluate as seal_evaluate
    seal=seal_evaluate()
    if not seal['checks_pass']:raise RuntimeError('seal geometry envelope failed')
    copper=(abs(br-75)<.5)&(bx[:,2]>=seal['copper_bottom_z_mm'])&(bx[:,2]<=seal['copper_top_z_mm'])
    copper_area=np.bincount(bd[copper].ravel(),weights=np.repeat(area[copper]/3,3),minlength=len(x))
    if copper_area.sum()<=0:raise RuntimeError('copper heat-transfer surface missing')
    copper_area*=seal['copper_effective_area_mm2']/copper_area.sum()
    copper_capacity=seal['copper_heat_capacity_J_K'];water_h=seal['water_lumped_design_W_K'];water_inlet=22.
    copper_temp=water_inlet;max_copper_temp=copper_temp;max_seal_band_temp=preheat
    # Seal radial preload is an upper design load, removed together with the fixture.
    shell_copper_nodes=np.flatnonzero(copper_area>0)
    shell_copper_normal=x[shell_copper_nodes,:2]/np.linalg.norm(x[shell_copper_nodes,:2],axis=1)[:,None]
    seal_force=seal['seal_radial_force_design_limit_N']*copper_area[shell_copper_nodes]/copper_area.sum()
    mat=yaml.safe_load((ROOT/'project/materials.yaml').read_text(encoding='utf8'))['materials']
    tables=[mat['q235b'],mat['qt450_10'],mat['ernife_ci']]
    # NiFe temperature dependence is explicitly a design interpolation, not a certificate.
    ni=tables[2]['nominal_properties_20c']
    tables[2]['temperature_dependent']={'temperatures_c':[20,200,400,600,800,1000,1400],
        'thermal_conductivity_w_mk':[22,24,26,28,30,32,35],
        'specific_heat_j_kgk':[480,520,570,630,710,760,800],
        'elastic_modulus_gpa':[160,150,130,90,50,15,2],
        'yield_strength_mpa':[290,260,210,150,70,15,2],
        'alpha_per_k':[1.1e-5]*7}
    rho=np.array([t['nominal_properties_20c']['density_kg_m3'] for t in tables])[m]*1e-9
    nu=np.array([t['nominal_properties_20c']['poisson_ratio'] for t in tables])[m]
    fusion=[t['fusion_enthalpy'] for t in tables] if material_enthalpy else [dict(solidus_C=1100.,liquidus_C=1400.,latent_heat_J_kg=250000.,basis='superseded common broad melting interval') for t in tables]
    solidus=np.array([t['solidus_C'] for t in fusion])[m,None]
    liquidus=np.array([t['liquidus_C'] for t in fusion])[m,None]
    latent=np.array([t['latent_heat_J_kg'] for t in fusion])[m,None]
    if np.any(liquidus<=solidus) or np.any(latent<=0):raise ValueError('invalid material fusion enthalpy data')
    def latent_enthalpy(local):return latent*np.clip((local-solidus)/(liquidus-solidus),0,1)
    def prop(te,key):
        out=np.empty_like(te,dtype=float)
        for j,t in enumerate(tables):
            tab=t['temperature_dependent'];out[m==j]=np.interp(te[m==j],tab['temperatures_c'],tab[key])
        return out
    def integrated(te,key):
        out=np.empty_like(te,dtype=float)
        for j,tb in enumerate(tables):
            knots=np.array(tb['temperature_dependent']['temperatures_c'],float)
            vals=np.array(tb['temperature_dependent'][key],float)
            prefix=np.r_[0,np.cumsum(np.diff(knots)*(vals[1:]+vals[:-1])/2)]
            query=te[m==j];pos=np.clip(np.searchsorted(knots,query,side='right')-1,0,len(knots)-2)
            clipped=np.minimum(query,knots[-1]);dx=clipped-knots[pos]
            val=prefix[pos]+vals[pos]*dx+.5*(vals[pos+1]-vals[pos])/np.diff(knots)[pos]*dx**2
            val+=np.maximum(query-knots[-1],0)*vals[-1]
            out[m==j]=val
        return out
    rr=np.repeat(e,4,axis=1).ravel(); cc=np.tile(e,(1,4)).ravel()
    srr=np.repeat(dof,12,axis=1).ravel(); scc=np.tile(dof,(1,12)).ravel()
    nn=len(x); nd=3*nn; u=np.zeros(nd); plastic=np.zeros((len(e),6)); eqp=np.zeros(len(e)); ref=np.zeros((len(e),6))
    temp=np.full(nn,preheat);active=m!=2;thermal_active=active.copy(); history=[];struct=[]; saved_t=[];saved_u=[];energy=0.; loss_total=0.;input_total=0.
    pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3; pd=np.eye(6)-pv
    rn=np.linalg.norm(x[:,:2],axis=1)
    # Annular axial shell support, with one locating pin and one tangential stop.
    bottom=np.flatnonzero(x[:,2]<1e-5)
    anchors=[bottom[np.argmin(np.linalg.norm(x[bottom,:2]-[77.5*np.cos(a),77.5*np.sin(a)],axis=1))] for a in (0,2*np.pi/3,4*np.pi/3)]
    fixed={3*int(k)+2:0 for k in bottom}
    for ax in (0,1): fixed[3*int(anchors[0])+ax]=0.
    fixed[3*int(anchors[1])+1]=0.
    bore=np.flatnonzero((abs(rn-bore_radius)<1e-4)&(x[:,2]>=100-1e-4)&(x[:,2]<=weld_top+1e-4))
    a_pts=bottom
    b_pts=np.flatnonzero((abs(rn-75)<1e-4)&((x[:,2]<35)|(x[:,2]>165)))
    if len(bore)<10 or len(b_pts)<6: raise RuntimeError('measurement surfaces missing')
    normals=x[bore,:2]/rn[bore,None]
    # Mandrel acts in compression only, locks contracting bore, allows outward thermal expansion.
    bore_face=np.all(abs(np.linalg.norm(x[bd,:2],axis=2)-bore_radius)<1e-4,axis=1)
    bore_area=np.bincount(bd.ravel(),weights=np.repeat(area*bore_face/3,3),minlength=nn)[bore]
    if bore_area.sum()<=0:raise RuntimeError('mandrel contact surface missing')
    # Full-hole equivalent of six fingers over seat thickness minus 0.4 mm, 90% coverage.
    bore_area*=2*np.pi*bore_radius*(weld_top-100-.4)*.9/bore_area.sum()
    contact_k=contact_density*bore_area
    # The existing 100 N setting preload acts before the first bead is deposited.
    mandrel_intrusion=100./contact_k.sum()
    tool=None;tool_history=[];tool_boundary_trace=[]
    seat_nodes=np.unique(e[m==1]); lower=seat_nodes[abs(x[seat_nodes,2]-100)<1e-4]
    support_nodes=[lower[np.argmin(np.linalg.norm(x[lower,:2]-[30*np.cos(a),30*np.sin(a)],axis=1))] for a in (0,2*np.pi/3,4*np.pi/3)]
    pads=None
    if unilateral_pads:
        from pad_contact import PadContact
        pads=PadContact(x,bd)
    if fixture_contact_h is not None:
        from fixture_thermal import FixtureThermal
        tool=FixtureThermal(x,bore,bore_area,fixture_contact_h,fixture_refinement,pads)
    pad_history=[];max_pad_pressure=0.;max_pad_moment=0.;max_pad_total=0.
    mandrel_history=[];mandrel_state={}
    press_top=float(x[seat_nodes[rn[seat_nodes]<35],2].max())
    press_nodes=seat_nodes[(abs(x[seat_nodes,2]-press_top)<1e-4)&(rn[seat_nodes]<35)]
    if len(press_nodes)==0:raise RuntimeError('pressure ring seat missing')
    endarc=len(stages)*interval-idle
    end=endarc+12000 if stop_time is None else stop_time
    peak=np.zeros(len(e));peaknode=np.zeros(nn);newton_max=0;max_res=0.;max_contact=0.;rel=False
    peak_active=np.full(len(e),preheat)
    last_struct_t=0
    last_mechanical_temperature=np.full(len(e),preheat)
    observed_hot=np.zeros(len(e),dtype=bool);sampled_hot=np.zeros(len(e),dtype=bool)
    event_counts=dict(birth=0,annealing=0,temperature_jump=0,arc_boundary=0)
    amg_cache=None;amg_free=None;linear_fallbacks=0
    modes=np.zeros((nd,6));modes.reshape(nn,3,6)[:,:,:3]=np.eye(3)[None,:,:]
    centred=(x-x.mean(axis=0))/160
    for axis in range(3):modes[:,axis+3]=np.cross(np.eye(3)[axis],centred).ravel()
    # Non-invasive process-temperature record at actual segment start events.
    from scipy.interpolate import LinearNDInterpolator
    qt_top=seat_nodes[abs(x[seat_nodes,2]-weld_top)<1e-5]
    marker_points={j:np.c_[61*np.cos(j*2*np.pi/n+np.array([-9/74.98,0,9/74.98])),61*np.sin(j*2*np.pi/n+np.array([-9/74.98,0,9/74.98]))] for j in range(n)}
    root_nodes={j:np.unique(e[(m==2)&(layer==0)&(segment==j)]) for j in range(n)}
    process_starts=[];recorded_starts=set()
    t=0.
    peening_rows=[]
    # Final coupled runs record every bead surface without changing the solve.
    # This lets the same actual temperature field support the peening check.
    if tool is not None and not thermal_only:
        peening_trace=True
        peening_all=True
    if peening_trace:
        from scipy.spatial import Delaunay
        weld_nodes=np.unique(e[m==2]);surface_interpolators=[]
        peening_sites=np.arange(.5,17.5001,.25)
        trace_meta=[]
        for leg,contact_radius in ((2.8,73.6),(4.,73.0)):
            for sector in (range(n) if peening_all else [0]):
                nodes=weld_nodes[abs(x[weld_nodes,2]-np.linalg.norm(x[weld_nodes,:2],axis=1)-weld_top+75-leg)<1e-5]
                relative=np.arctan2(np.sin(np.arctan2(x[nodes,1],x[nodes,0])-sector*2*np.pi/n),np.cos(np.arctan2(x[nodes,1],x[nodes,0])-sector*2*np.pi/n))
                selected=abs(relative)<.14;nodes=nodes[selected];relative=relative[selected]
                coordinates=np.c_[74.98*relative+9,np.linalg.norm(x[nodes,:2],axis=1)]
                triangulation=Delaunay(coordinates)
                query=np.c_[peening_sites,np.full(len(peening_sites),contact_radius)]
                simplex=triangulation.find_simplex(query)
                if np.any(simplex<0):raise RuntimeError('peening surface points outside actual bead surface')
                transform=triangulation.transform[simplex]
                bary=np.einsum('nij,nj->ni',transform[:,:2,:],query-transform[:,2,:])
                weights=np.c_[bary,1-bary.sum(axis=1)]
                surface_interpolators.append((nodes[triangulation.simplices[simplex]],weights))
                pass_index=0 if leg==2.8 else 1
                trace_meta.append(dict(pass_index=pass_index,segment=sector+1,leg_mm=leg,contact_radius_mm=contact_radius,start_s=stage_index[(pass_index,sector)]*interval))
        (output/'peening-trace-sites.json').write_text(json.dumps(dict(interface_arc_coordinate_mm=peening_sites.tolist(),traces=trace_meta,root_contact_radius_mm=73.6,cover_contact_radius_mm=73.0,root_start_s=0.,cover_start_s=stage_index[(1,order[0])]*interval,travel_mm_s=v,measurement='interpolated nodal temperature on actual root/cover conical free surfaces'),indent=2),encoding='utf8')
    lnodes=np.array([[z[0],*z[1]] for z in links]);lweights=np.array([[1.,*[-v for v in z[2]]] for z in links])
    # Area-scaled interface: QT-side 1.2 mm Ni layer is a thin-layer Robin path.
    weld_faces=bd[np.isin(bd[:,0],np.unique(e[m==2]))]
    weld_face_area=np.linalg.norm(np.cross(x[weld_faces[:,1]]-x[weld_faces[:,0]],x[weld_faces[:,2]]-x[weld_faces[:,0]]),axis=1)/2
    wr=np.linalg.norm(x[weld_faces,:2],axis=2)
    i_face=[np.all(abs(wr-75)<1e-4,axis=1),np.all(abs(x[weld_faces,2]-weld_top)<1e-4,axis=1)]
    ia=[np.bincount(weld_faces.ravel(),weights=np.repeat(weld_face_area*pick/3,3),minlength=nn) for pick in i_face]
    link_reference=np.zeros((len(lnodes),3));mechanical_link_active=np.zeros(len(lnodes),dtype=bool)
    birth_audits=[]
    link_cast=np.isin(lnodes[:,1],np.unique(e[m==1]))
    link_area=np.where(link_cast,ia[1][lnodes[:,0]],ia[0][lnodes[:,0]])
    if np.any(link_area<=0):raise RuntimeError('empty interface tributary area')
    thermal_link_density=np.where(link_cast,.040/1.2,10.)
    mechanical_link_density=np.where(link_cast,75000/1.2,160000/h)
    (output/'input.json').write_text(json.dumps({'materials':tables,'interface_patch':interface_patch,'linear_direct_solver':DIRECT_SOLVER_NAME,'solver_threads':SOLVER_THREADS,'sequence':seq,'travel_mm_s':v,'net_W':495,'leg_mm':4,
        'weld_base_z_mm':weld_top,'seat_thickness_mm':weld_top-100,'root_leg_mm':2.8,'root_mesh_mm':root_h,'idle_s':idle,'h_air_W_m2K':15,'emissivity':.7,'copper_contact_W_m2K':copper_h,'copper_water_model':seal,'copper_water_inlet_C':water_inlet,'fixture_cooling_removed_on_release':True,
        'mandrel_penalty_N_mm3':contact_density,'contact_area_mm2':float(bore_area.sum()),'initial_bore_diameter_mm':initial_bore_diameter,'structural_step_s':struct_dt,'weld_mesh_mm':weld_h,'h_mm':h,'dt_s':dt,'annealing_C':1200,'latent_heat_J_kg':[t['latent_heat_J_kg'] for t in fusion] if material_enthalpy else 250000,
        'source_radius_mm':source_radius,'source_depth_mm':source_depth,'source_r_mm':source_r,'Ni99_thin_layer_mm':1.2,'Ni99_conductivity_W_mK':40,'mechanical_interface_N_mm3':'Ni side 62500, steel side 160000/h','cold_structural_step_s':cold_struct_dt,'seat_geometry':str(seat_path) if seat_path else 'original 8P-FAIR_B','initial_radial_preload_N':100,'stress_free_interface_birth':True,'stress_free_birth':'distance-weighted complete affine continuation; adaptive 16/32/64/128 hosts, exact coordinate patch and L1 <=4, no inverse-distance fallback; cold fixture preload equilibrated before arc','support':('shell annular axial seat; QT three unilateral distributed Ø8 steel pads at R30, E200 GPa/H6 mm; separate 500 N pressure ring over R20.007..35; pads and pressure released with mandrel' if unilateral_pads else 'shell annular axial seat; QT three pads at R30; separate 500 N pressure ring; pads and pressure released with mandrel'),
        'unilateral_pads':unilateral_pads,'pad_contact':pads.audit if pads is not None else None,
        'material_specific_fusion_enthalpy':material_enthalpy,'fusion_enthalpy_model':fusion,
        'mechanical_event_policy':'mandatory birth, every observed >1200 C state, arc on/off boundaries and active temperature jump' if event_dT is not None else 'fixed mechanical cadence',
        'mechanical_event_temperature_increment_C':event_dT,'paired_opposed_sources':paired,'stage_sequence':stages,
        'maximum_simultaneous_heads':2 if paired else 1,'net_W_per_head':495,'arc_end_s':endarc},ensure_ascii=False,indent=2),encoding='utf8')
    if tool is not None:
        inputs=json.loads((output/'input.json').read_text(encoding='utf8'))
        inputs['fixture_thermal']=tool.audit
        inputs['fixture_thermal_coupling_policy']='previous converged displacement and gap; current implicit part temperature' if not thermal_only else 'continuous initial setting contact thermal diagnostic'
        (output/'input.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf8')
    checkpoint_path=output/'continuation-checkpoint.npz'
    if resume:
        if not checkpoint_path.exists():raise ValueError('no continuation checkpoint exists')
        cp=np.load(checkpoint_path,allow_pickle=False)
        meta=json.loads(str(cp['metadata']))
        if meta['version']!=1 or meta['inputs']!=json.loads((output/'input.json').read_text(encoding='utf8')):
            raise ValueError('checkpoint physics/parameters do not match the current run')
        if not np.array_equal(cp['x'],x) or not np.array_equal(cp['e'],e):
            raise ValueError('checkpoint mesh differs')
        u=cp['u'].copy()
        plastic=cp['plastic'].copy()
        eqp=cp['eqp'].copy()
        ref=cp['ref'].copy()
        temp=cp['temp'].copy()
        active=cp['active'].copy()
        thermal_active=cp['thermal_active'].copy()
        peak=cp['peak'].copy()
        peak_active=cp['peak_active'].copy()
        peaknode=cp['peaknode'].copy()
        last_mechanical_temperature=cp['last_mechanical_temperature'].copy()
        observed_hot=cp['observed_hot'].copy()
        sampled_hot=cp['sampled_hot'].copy()
        link_reference=cp['link_reference'].copy()
        mechanical_link_active=cp['mechanical_link_active'].copy()
        stress=cp['stress'].copy()
        copper_temp=meta['copper_temp']
        max_copper_temp=meta['max_copper_temp']
        max_seal_band_temp=meta['max_seal_band_temp']
        energy=meta['energy']
        loss_total=meta['loss_total']
        input_total=meta['input_total']
        last_struct_t=meta['last_struct_t']
        newton_max=meta['newton_max']
        max_res=meta['max_res']
        max_contact=meta['max_contact']
        rel=meta['rel']
        t=meta['t']
        linear_fallbacks=meta['linear_fallbacks']
        max_pad_pressure=meta['max_pad_pressure']
        max_pad_moment=meta['max_pad_moment']
        max_pad_total=meta['max_pad_total']
        history=meta['history']
        struct=meta['struct']
        process_starts=meta['process_starts']
        peening_rows=meta['peening_rows']
        birth_audits=meta['birth_audits']
        pad_history=meta['pad_history']
        mandrel_history=meta.get('mandrel_history',[])
        event_counts=meta['event_counts']
        recorded_starts=set(meta['recorded_starts'])
        saved_t=list(cp['saved_t']);saved_u=list(cp['saved_u'])
        if tool is not None:
            tool.temperature=cp['tool_temperature'].copy();tool_history=meta['tool_history']
            tool_boundary_trace=list(cp['tool_boundary_trace'])
        clock-=meta['elapsed_s']
        print('resumed converged state',t,flush=True)
        cp.close()
    def save_continuation(state):
        if not checkpoint or thermal_only:return
        meta=dict(version=1,inputs=json.loads((output/'input.json').read_text(encoding='utf8')),
                  recorded_starts=sorted(recorded_starts),elapsed_s=time.perf_counter()-clock)
        for key in ['copper_temp', 'max_copper_temp', 'max_seal_band_temp', 'energy', 'loss_total', 'input_total', 'last_struct_t', 'newton_max', 'max_res', 'max_contact', 'rel', 't', 'linear_fallbacks', 'max_pad_pressure', 'max_pad_moment', 'max_pad_total', 'history', 'struct', 'process_starts', 'peening_rows', 'birth_audits', 'pad_history', 'event_counts']:meta[key]=state[key]
        meta['mandrel_history']=mandrel_history
        data={key:state[key] for key in ['u', 'plastic', 'eqp', 'ref', 'temp', 'active', 'thermal_active', 'peak', 'peak_active', 'peaknode', 'last_mechanical_temperature', 'observed_hot', 'sampled_hot', 'link_reference', 'mechanical_link_active', 'stress']}
        data.update(x=x,e=e,saved_t=np.array(saved_t),saved_u=np.array(saved_u),
                    metadata=np.array(json.dumps(meta,ensure_ascii=False)))
        if tool is not None:
            meta['tool_history']=tool_history
            data['tool_temperature']=tool.temperature.copy()
            data['tool_boundary_trace']=np.asarray(tool_boundary_trace)
            data['metadata']=np.array(json.dumps(meta,ensure_ascii=False))
        temporary=checkpoint_path.with_name('continuation-next.npz')
        np.savez_compressed(temporary,**data);temporary.replace(checkpoint_path)
    while t<end-1e-8:
        initial_step=not thermal_only and not history
        stepdt=0. if initial_step else (dt if t<endarc+120 else min(10.,cold_struct_dt if cold_struct_dt is not None else dt*20))
        # Integrate the real on/off duration; never straddle an arc boundary.
        event_times=np.r_[np.arange(len(stages))*interval,np.arange(len(stages))*interval+duration,end]
        future=event_times[event_times>t+1e-8]
        stepdt=min(stepdt,float(future.min()-t),end-t)
        t+=stepdt
        newactive=(m!=2)|(t>=birth)
        te=temp[e].mean(axis=1)
        k=prop(te,'thermal_conductivity_w_mk')/1000
        thermal_factor=np.where(newactive,1.,1e-6)
        ke=np.einsum('eik,ejk,e->eij',g,g,k*vol*thermal_factor)
        conductivity=coo_matrix((ke.ravel(),(rr,cc)),shape=(nn,nn)).tocsr()
        occupied=np.unique(e[newactive]);linkactive=np.isin(lnodes[:,0],occupied)
        lt=lnodes[linkactive];lw=lweights[linkactive]
        lk=np.einsum('li,lj,l->lij',lw,lw,(thermal_link_density*link_area)[linkactive])
        conductivity+=coo_matrix((lk.ravel(),(np.repeat(lt,lnodes.shape[1],axis=1).ravel(),np.tile(lt,(1,lnodes.shape[1])).ravel())),shape=(nn,nn)).tocsr()
        mass_e=rho*vol*thermal_factor
        hrad=.7*5.670374419e-14*((np.maximum(temp,20)+273.15)**2+293.15**2)*(np.maximum(temp,20)+566.3)
        cool=(15e-6+hrad)*surface
        copper_k=np.zeros(nn) if rel else copper_h*1e-6*copper_area
        q=np.zeros(len(e)); st=int((t-stepdt/2)//interval)
        on=st<len(stages) and 0<=(t-stepdt/2-st*interval)<duration
        if on:
            for p,j in stages[st]:
                ang=(j*2*np.pi/n+(v*(t-stepdt/2-st*interval)-9)/74.98)
                source=np.array([source_r*np.cos(ang),source_r*np.sin(ang),weld_top+1.2 if p==0 else weld_top+2.0])
                d=c-source; norm=np.exp(-((d[:,0]**2+d[:,1]**2)/source_radius**2+(d[:,2]/source_depth)**2))
                norm*=vol*newactive
                q+=norm/max(norm.sum(),1e-30)*495*(1+imbalance if j==0 else 1)
        nodal_q=np.bincount(e.ravel(),weights=np.repeat(q/4,4),minlength=nn)
        old=temp.copy();old_copper_temp=copper_temp
        if tool is not None:
            old_tool=tool.temperature.copy()
            previous_gap=(u.reshape(-1,3)[bore,:2]*normals).sum(axis=1)-mandrel_intrusion-tool.offset()
            tool_link,tool_part_diagonal,tool_diagonal=tool.coupling(nn,previous_gap,rel,u,temp)
        at_start=int(round((t-stepdt)/interval))
        if at_start<len(stages) and at_start not in recorded_starts and abs((t-stepdt)-at_start*interval)<1e-8:
            for pass_index,segment_index in stages[at_start]:
                marker_temp=LinearNDInterpolator(x[qt_top,:2],old[qt_top])(marker_points[segment_index])
                if not np.all(np.isfinite(marker_temp)):raise RuntimeError('QT process markers outside actual top-face mesh')
                previous_root=float(old[root_nodes[segment_index]].max()) if pass_index else None
                start_max=max(float(marker_temp.max()),previous_root if previous_root is not None else -np.inf)
                process_starts.append(dict(t_s=t-stepdt,pass_index=pass_index,segment_number=segment_index+1,QT_marker_radius_mm=61,QT_marker_temperatures_C=marker_temp.tolist(),previous_root_max_C=previous_root,start_max_C=start_max,temperature_limit_C=35 if at_start==0 else 100,process_temperature_pass=bool(start_max<=(35 if at_start==0 else 100))))
            recorded_starts.add(at_start)
            (output/'process-start-temperatures.json').write_text(json.dumps(process_starts,ensure_ascii=False,indent=2),encoding='utf8')
        def enthalpy_nodes(tv):
            local=tv[e]
            hh=integrated(local,'specific_heat_j_kgk')+latent_enthalpy(local)
            cap=prop(local,'specific_heat_j_kgk')+latent/(liquidus-solidus)*((local>solidus)&(local<liquidus))
            H=np.bincount(e.ravel(),weights=(mass_e[:,None]*hh/4).ravel(),minlength=nn)
            C=np.bincount(e.ravel(),weights=(mass_e[:,None]*cap/4).ravel(),minlength=nn)
            return H,C
        # New cold filler enters at 20 C. Its enthalpy is zero before deposition.
        old_H,_=enthalpy_nodes(old)
        born=(m==2)&newactive&~thermal_active
        if np.any(born):
            bh=integrated(old[e],'specific_heat_j_kgk')+latent_enthalpy(old[e])
            old_H-=np.bincount(e[born].ravel(),weights=(mass_e[born,None]*bh[born]/4).ravel(),minlength=nn)
        def coupled_residual(tv,tc,hv):
            part=hv-old_H+stepdt*(conductivity@tv+cool*(tv-20)+copper_k*(tv-tc)-nodal_q)
            ring=copper_capacity*(tc-old_copper_temp)+stepdt*(np.dot(copper_k,tc-tv)+water_h*(tc-water_inlet))
            if tool is not None:
                tt=tool.temperature
                part+=stepdt*(tool_part_diagonal*tv-tool_link@tt)
                fixture=tool.capacity*(tt-old_tool)+stepdt*(tool.conduction@tt+tool.external*(tt-20)+tool_diagonal*tt-tool_link.T@tv)
                return np.r_[part,ring,fixture]
            return np.r_[part,ring]
        for thermal_iteration in range(35):
            H,C=enthalpy_nodes(temp)
            residual=coupled_residual(temp,copper_temp,H)
            if np.linalg.norm(residual)<1e-5:break
            off=coo_matrix((-stepdt*copper_k,(np.arange(nn),np.zeros(nn,dtype=int))),shape=(nn,1)).tocsr()
            jacobian=bmat([[diags(C+stepdt*(cool+copper_k))+stepdt*conductivity,off],
                           [off.T,coo_matrix([[copper_capacity+stepdt*(copper_k.sum()+water_h)]])]],format='csr')
            if tool is not None:
                jacobian=bmat([[jacobian, bmat([[-stepdt*tool_link],[coo_matrix((1,len(tool.cells)))]],format='csr')],
                    [bmat([[-stepdt*tool_link.T,coo_matrix((len(tool.cells),1))]],format='csr'),
                     diags(tool.capacity+stepdt*(tool.external+tool_diagonal))+stepdt*tool.conduction]],format='csr')
                jacobian+=diags(np.r_[stepdt*tool_part_diagonal,0,np.zeros(len(tool.cells))])
            increment=thermal_spsolve(jacobian,-residual)
            norm=np.linalg.norm(residual)
            for power in range(12):
                candidate=temp+increment[:nn]*.5**power
                candidate_copper=copper_temp+increment[nn]*.5**power
                if tool is not None:
                    current_tool=tool.temperature.copy()
                    tool.temperature=current_tool+increment[nn+1:]*.5**power
                ch,_=enthalpy_nodes(candidate)
                cr=coupled_residual(candidate,candidate_copper,ch)
                if np.linalg.norm(cr)<norm:temp=candidate;copper_temp=candidate_copper;break
                if tool is not None:tool.temperature=current_tool
            else:raise RuntimeError('enthalpy Newton stagnation')
        else:raise RuntimeError('enthalpy Newton failure')
        thermal_active=newactive.copy()
        if not np.all(np.isfinite(temp)) or temp.max()>5000:raise RuntimeError('invalid thermal state')
        if peening_trace:
            values=[np.sum(temp[nodes]*weights,axis=1) for nodes,weights in surface_interpolators]
            peening_rows.append([t,*np.concatenate(values)])
        delta_H=float((H-old_H).sum())+copper_capacity*(copper_temp-old_copper_temp)
        external_loss=float(np.dot(cool,temp-20)+water_h*(copper_temp-water_inlet))
        if tool is not None:
            delta_H+=float(tool.capacity@(tool.temperature-old_tool))
            external_loss+=float(tool.external@(tool.temperature-20))
            tool_history.append([t,float(tool.temperature.max()),float(tool.offset().min()),float(tool.offset().max()),*tool.temperature.tolist()])
            tool_boundary_trace.append(np.r_[t,stepdt,int(rel),old[tool.boundary_nodes],temp[tool.boundary_nodes],
                u.reshape(-1,3)[tool.boundary_nodes,2],(u.reshape(-1,3)[bore,:2]*normals).sum(axis=1)])
        balance=delta_H+stepdt*external_loss-stepdt*q.sum()
        energy+=delta_H;loss_total+=stepdt*external_loss;input_total+=stepdt*q.sum()
        te=temp[e].mean(axis=1);peak=np.maximum(peak,te);peaknode=np.maximum(peaknode,temp)
        peak_active=np.maximum(peak_active,np.where(newactive,te,preheat))
        if thermal_observer is not None:
            thermal_observer(t,te,newactive,m,vol)
        band_temp=float(temp[shell_copper_nodes].max())
        if not rel:
            max_copper_temp=max(max_copper_temp,float(copper_temp));max_seal_band_temp=max(max_seal_band_temp,band_temp)
        history.append([t,float(temp.max()),float(te[m==1].max()),input_total,loss_total,energy,float(balance),float(copper_temp),band_temp])
        observed_hot |= newactive & (te>1200)
        # Solve frequently through every heated segment; all thermal increments retained.
        mechanical_step=struct_dt if t<=endarc+120 or cold_struct_dt is None else cold_struct_dt
        event_flags={}
        if event_dT is not None:
            event_flags=dict(birth=bool(np.any(newactive & ~active)),annealing=bool(np.any(newactive & (te>1200))),
                temperature_jump=bool(np.max(abs(te[newactive]-last_mechanical_temperature[newactive]))>=event_dT),
                arc_boundary=bool(np.min(abs(event_times-t))<1e-8))
        if not thermal_only and (initial_step or t-last_struct_t>=mechanical_step-1e-8 or t>=end or any(event_flags.values())):
            for key, value in event_flags.items():event_counts[key]+=int(value)
            E=prop(te,'elastic_modulus_gpa')*1000; Y=prop(te,'yield_strength_mpa'); al=integrated(te,'alpha_per_k')
            G=E/(2*(1+nu));K=E/(3*(1-2*nu));H=.005*E
            newly=newactive&~active
            # Inactive nodes held at zero must not impose a fictitious strain on a
            # newly born tetrahedron. Extend the existing material displacement
            # affinely to newly occupied nodes before defining stress-free birth.
            old_occupied=np.unique(e[active])
            added_nodes=np.setdiff1d(np.unique(e[newactive]),old_occupied)
            if len(added_nodes):
                from affine_interface import birth_continuation
                rows,birth_audit=birth_continuation(x,old_occupied,added_nodes)
                birth_audits.append(dict(t_s=t,**birth_audit))
                for node,(host,weights) in zip(added_nodes,rows):
                    u.reshape(-1,3)[node]=weights@u.reshape(-1,3)[host]
            new_links=linkactive&~mechanical_link_active
            link_reference[new_links]=np.einsum('ij,ijk->ik',lweights[new_links],u.reshape(-1,3)[lnodes[new_links]])
            mechanical_link_active=linkactive.copy()
            strains=np.einsum('eij,ej->ei',b,u[dof])
            # New deposition / material above annealing temperature is stress free.
            reset=newly|(te>1200)
            sampled_hot |= newactive & (te>1200)
            ref[reset]=strains[reset];ref[reset,:3]-=al[reset,None]
            plastic[reset]=0.;eqp[reset]=0.
            active=newactive.copy()
            scale=np.where(active,1.,1e-8)
            constraints=dict(fixed)
            occupied=np.unique(e[active]); unoccupied=np.setdiff1d(np.arange(nn),occupied)
            for z in (3*unoccupied[:,None]+np.arange(3)).ravel():constraints[int(z)]=0.
            if not rel and t>endarc+120 and float(temp.max())<55:rel=True
            if not rel and pads is None:
                for node in support_nodes:constraints[3*int(node)+2]=0.
            if initial_step:
                # A coordinate gauge fixes the unloaded seat's rigid rotation;
                # it is removed as soon as the first physical weld is activated.
                constraints[3*int(support_nodes[0])+1]=0.
            fix=np.array(sorted(constraints));free=np.setdiff1d(np.arange(nd),fix)
            trial=u.copy();trial[fix]=[constraints[int(d)] for d in fix]
            lr=[];lc=[];lv=[]
            for ax in range(3):
                ld=3*lt+ax;lr.extend(np.repeat(ld,lnodes.shape[1],axis=1).ravel());lc.extend(np.tile(ld,(1,lnodes.shape[1])).ravel());lv.extend((np.einsum('li,lj,l->lij',lw,lw,(mechanical_link_density*link_area)[linkactive])).ravel())
            tie=coo_matrix((lv,(lr,lc)),shape=(nd,nd)).tocsr()
            tie_reference_force=np.zeros(nd)
            density=(mechanical_link_density*link_area)[linkactive]
            for ax in range(3):
                np.add.at(tie_reference_force,3*lt.ravel()+ax,(lw*(density*link_reference[linkactive,ax])[:,None]).ravel())
            pad_state={}
            def assemble(uv,tangent=True):
                strain=np.einsum('eij,ej->ei',b,uv[dof])-ref-plastic
                strain[:,:3]-=al[:,None]
                dev=strain-strain@pv; s=2*G[:,None]*dev
                qv=np.sqrt(1.5*np.sum(s*s,axis=1)); dl=np.where(active,np.maximum(0,(qv-Y-H*eqp)/(3*G+H)),0.)
                direction=1.5*s/np.maximum(qv[:,None],1e-20)
                beta=1-3*G*dl/np.maximum(qv,1e-20)
                stress=s*beta[:,None]+3*K[:,None]*(strain@pv)
                stress*=scale[:,None]
                fi=np.einsum('eji,ej,e->ei',b,stress,vol)
                force=np.bincount(dof.ravel(),weights=fi.ravel(),minlength=nd)
                force+=tie@uv-tie_reference_force
                if not rel:
                    force[3*press_nodes+2]+=500/len(press_nodes)
                    np.add.at(force,3*shell_copper_nodes,-seal_force*shell_copper_normal[:,0])
                    np.add.at(force,3*shell_copper_nodes+1,-seal_force*shell_copper_normal[:,1])
                if tangent:
                    D=3*K[:,None,None]*pv+2*G[:,None,None]*beta[:,None,None]*pd
                    corr=1/(3*G+H)-dl/np.maximum(qv,1e-20)
                    D-=np.where(dl>0,4*G*G*corr,0)[:,None,None]*direction[:,:,None]*direction[:,None,:]
                    ke=np.einsum('eji,ejk,ekl,e->eil',b,D,b,vol*scale,optimize=True)
                    matrix=coo_matrix((ke.ravel(),(srr,scc)),shape=(nd,nd)).tocsr()
                    matrix+=tie
                else:matrix=None
                if pads is not None:
                    if not rel:
                        pf,pm,pr,pa,metrics=pads.apply(uv,tangent,growth=tool.pad_offset() if tool is not None else None)
                        force+=pf
                        if tangent:matrix+=pm
                    else:
                        pr=np.zeros(3);pa=np.zeros(3)
                        metrics=dict(maximum_pressure_MPa=0.,maximum_lift_gap_mm=0.,moment_N_mm=np.zeros(2))
                    pad_state.update(reaction=pr,area=pa,**metrics)
                reaction=0.;mandrel_state['vector']=np.zeros(2)
                if not rel:
                    bu=uv.reshape(-1,3)[bore,:2];gap=(bu*normals).sum(axis=1)-mandrel_intrusion
                    if tool is not None:gap-=tool.offset()
                    ids=np.flatnonzero(gap<0)
                    cf=-contact_k[ids,None]*gap[ids,None]*normals[ids]
                    np.add.at(force,3*bore[ids],-cf[:,0]);np.add.at(force,3*bore[ids]+1,-cf[:,1])
                    reaction=float(np.linalg.norm(cf,axis=1).sum())
                    mandrel_state['vector']=cf.sum(axis=0)
                    if tangent and len(ids):
                        cd=3*bore[ids,None]+np.arange(2)
                        blocks=contact_k[ids,None,None]*normals[ids,:,None]*normals[ids,None,:]
                        matrix+=coo_matrix((blocks.ravel(),(np.repeat(cd,2,axis=1).ravel(),np.tile(cd,(1,2)).ravel())),shape=(nd,nd)).tocsr()
                return force,matrix,stress,dl,direction,reaction
            converged=False
            for it in range(35):
                force,matrix,stress,dl,direction,reaction=assemble(trial)
                res=np.linalg.norm(force[free])
                if res<.05:
                    converged=True;break
                A=matrix[free][:,free].tocsr();rhs=-force[free]
                if use_amg:
                    import pyamg
                    # Retain the hierarchy while a few deposition nodes enter.
                    # The enlarged inverse is SPD block diagonal; linear residual
                    # checks and direct fallback remain the acceptance criteria.
                    rebuild=amg_cache is None or not np.all(np.isin(amg_free,free)) or len(free)-len(amg_free)>256
                    if rebuild:
                        amg_cache=pyamg.smoothed_aggregation_solver(A,B=modes[free],symmetry='symmetric',max_coarse=300,coarse_solver='splu')
                        amg_free=free.copy()
                    original=amg_cache.aspreconditioner()
                    if np.array_equal(amg_free,free):preconditioner=original
                    else:
                        indices=np.searchsorted(free,amg_free);added=np.ones(len(free),dtype=bool);added[indices]=False
                        diagonal=A.diagonal()[added]
                        if np.any(diagonal<=0):raise RuntimeError('invalid deposition tangent diagonal')
                        def enlarged(vector):
                            out=np.zeros_like(vector);out[indices]=original@vector[indices];out[added]=vector[added]/diagonal
                            return out
                        preconditioner=LinearOperator(A.shape,matvec=enlarged,dtype=float)
                    du,info=cg(A,rhs,M=preconditioner,rtol=1e-9,atol=.0005,maxiter=180)
                    if info or np.linalg.norm(A@du-rhs)>.001:
                        du=structural_spsolve(A,rhs);amg_cache=None;linear_fallbacks+=1
                else:du=structural_spsolve(A,rhs)
                accepted=False
                for power in range(9):
                    candidate=trial.copy();candidate[free]+=du*(.5**power)
                    ff,*_=assemble(candidate,False)
                    if np.linalg.norm(ff[free])<res:trial=candidate;accepted=True;break
                if not accepted:raise RuntimeError(f'Newton stagnation t={t} residual={res}')
            if not converged:raise RuntimeError(f'Newton failed t={t} residual={res}')
            u=trial;plastic+=dl[:,None]*direction;eqp+=dl
            newton_max=max(newton_max,it);max_res=max(max_res,float(res));max_contact=max(max_contact,reaction)
            if pads is not None:
                pr=pad_state['reaction'];pa=pad_state['area'];moment=pad_state['moment_N_mm']
                max_pad_pressure=max(max_pad_pressure,pad_state['maximum_pressure_MPa'])
                max_pad_moment=max(max_pad_moment,float(np.linalg.norm(moment)))
                max_pad_total=max(max_pad_total,float(pr.sum()))
                pad_history.append([t,int(rel),*pr,*pa,pad_state['maximum_pressure_MPa'],pad_state['maximum_lift_gap_mm'],*moment])
            struct.append([t,it,float(res),reaction,int(rel),float(np.max(np.linalg.norm(u.reshape(-1,3),axis=1)))])
            vector=mandrel_state['vector']
            mandrel_history.append([t,*vector,float(np.linalg.norm(vector)),reaction,int(rel)])
            if len(struct)%20==0:
                print('step',n,h,round(t,2),round(temp.max(),1),'peak',round(peaknode.max(),1),it,round(time.perf_counter()-clock,1),flush=True)
                (output/'progress.json').write_text(json.dumps(dict(t_s=t,arc_end_s=endarc,elapsed_s=time.perf_counter()-clock,max_C=float(temp.max()),copper_max_C=max_copper_temp,seal_band_max_C=max_seal_band_temp,released=rel,energy_balance_relative=(input_total-loss_total-energy)/max(input_total,1),max_equilibrium_residual_N=max_res,linear_fallbacks=linear_fallbacks)),encoding='utf8')
            last_struct_t=t
            last_mechanical_temperature=te.copy()
            if len(struct)%10==0:saved_t.append(te.astype(np.float32));saved_u.append(u.astype(np.float32))
            if len(struct)%20==0:save_continuation(locals())
        if rel and temp.max()<20.5:break
        if thermal_only and len(history)%50==0:print('thermal',round(t,2),round(temp.max(),1),round(peak.max(),1),flush=True)
    if not thermal_only:save_continuation(locals())
    if tool is not None:
        np.savez_compressed(output/'fixture-boundary-trace.npz',trace=np.asarray(tool_boundary_trace),
            boundary_nodes=tool.boundary_nodes,bore=bore,bore_area=bore_area,initial_intrusion_mm=mandrel_intrusion)
        np.savetxt(output/'fixture-thermal-history.csv',tool_history,delimiter=',',
            header='t_s,max_tool_C,min_radial_growth_mm,max_radial_growth_mm,'+','.join(f'cell{i}_C' for i in range(len(tool.cells))),comments='')
        data=np.asarray(tool_history)
        (output/'fixture-thermal-verification.json').write_text(json.dumps(dict(model=tool.audit,
            maximum_temperature_C=float(data[:,1].max()),maximum_radial_growth_mm=float(data[:,3].max()),
            final_tool_C=tool.temperature.tolist(),thermal_energy_balance_relative=(input_total-loss_total-energy)/max(input_total,1),
            scope='computed fixture thermal history; coupled to part heat conduction and compression gap'),ensure_ascii=False,indent=2),encoding='utf8')
    if peening_trace:
        np.savetxt(output/'peening-surface-history.csv',peening_rows,delimiter=',',header='t_s,'+','.join(f"p{row['pass_index']+1}_seg{row['segment']}_{p:g}" for row in trace_meta for p in peening_sites),comments='')
    if thermal_only:
        result=dict(h_mm=h,dt_s=dt,nodes=nn,tetrahedra=len(e),peak_nodal_C=float(peaknode.max()),peak_element_C=float(peak.max()),input_J=input_total,filler_volume_above_1200C_mm3=float(vol[(m==2)&(peak>1200)].sum()),thermal_only=True,end_s=t,elapsed_s=time.perf_counter()-clock,source_radius_mm=source_radius,source_depth_mm=source_depth,source_r_mm=source_r,copper_contact_W_m2K=copper_h)
        result['active_filler_volume_above_1200C_mm3']=float(vol[(m==2)&(peak_active>1200)].sum())
        result['active_peak_scope']='element-mean temperature observed only after deposition activation; 1200 C is the constitutive annealing threshold'
        np.savez_compressed(output/'thermal-fields.npz',x=x,e=e,material=m,peak_temperature=peak,peak_active_temperature=peak_active,peak_nodal_temperature=peaknode,temperature=temp)
        np.savetxt(output/'thermal-history.csv',history,delimiter=',',header='t_s,max_C,seat_max_C,input_J,loss_J,stored_part_and_copper_J,balance_J,copper_C,seal_band_max_C',comments='')
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result),flush=True);return
    (output/'mechanical-integration-audit.json').write_text(json.dumps(dict(event_temperature_increment_C=event_dT,
        event_trigger_counts=event_counts,mechanical_samples=len(struct),
        missed_above_annealing_mm3={str(i):float(vol[(m==i)&observed_hot&~sampled_hot].sum()) for i in range(3)}),indent=2),encoding='utf8')
    if pads is not None:
        np.savetxt(output/'pad-contact-history.csv',pad_history,delimiter=',',header='t_s,released,pad1_N,pad2_N,pad3_N,pad1_active_mm2,pad2_active_mm2,pad3_active_mm2,max_pressure_MPa,max_lift_mm,Mx_N_mm,My_N_mm',comments='')
        (output/'pad-contact-audit.json').write_text(json.dumps(dict(**pads.audit,
            maximum_pressure_MPa=max_pad_pressure,maximum_carrier_moment_N_mm=max_pad_moment,
            maximum_total_upward_reaction_N=max_pad_total,
            minimum_upward_reaction_N=float(np.asarray(pad_history)[:,2:5].min()),
            compression_only_reactions_pass=bool(np.asarray(pad_history)[:,2:5].min()>=0)),indent=2),encoding='utf8')
    # Final return to reference temperature, then release is evaluated explicitly.
    # Continue cooling rather than asserting ambient at a finite hot step.
    np.savez_compressed(output/'fields.npz',x=x,e=e,material=m,boundary=bd,u=u.reshape(-1,3),stress=stress,plastic=plastic,
        link_nodes=lnodes,link_weights=lweights,eqp=eqp,temperature=temp,peak_temperature=peak,peak_active_temperature=peak_active,peak_nodal_temperature=peaknode,temperature_snapshots=saved_t,displacement_snapshots=saved_u)
    np.savetxt(output/'thermal-history.csv',history,delimiter=',',header='t_s,max_C,seat_max_C,input_J,loss_J,stored_part_and_copper_J,balance_J,copper_C,seal_band_max_C',comments='')
    np.savetxt(output/'equilibrium-history.csv',struct,delimiter=',',header='t_s,iterations,residual_N,mandrel_reaction_N,released,max_u_mm',comments='')
    np.savetxt(output/'mandrel-vector-history.csv',mandrel_history,delimiter=',',header='t_s,Fx_N,Fy_N,resultant_N,compression_sum_N,released',comments='')
    (output/'birth-continuation-verification.json').write_text(json.dumps(dict(method='distance-weighted affine continuation; adaptive 16/32/64/128 host cloud, coordinate patch <1e-7 mm and host L1 <=4; no IDW fallback',records=birth_audits,rigid_motion_patch_pass=all(r['maximum_coordinate_error_mm']<1e-7 and r['maximum_host_weight_L1']<=4 for r in birth_audits)),indent=2),encoding='utf8')
    if not rel:
        if stop_time is not None:
            (output/'diagnostic.json').write_text(json.dumps(dict(status='partial mechanical diagnostic; not cold release',elapsed_s=time.perf_counter()-clock,linear_fallbacks=linear_fallbacks,use_amg=use_amg,max_equilibrium_residual_N=max_res)),encoding='utf8');return
        raise RuntimeError('not yet released; extend cooling duration')
    deformed=x+u.reshape(-1,3)
    fitted=fit_position_diameter(deformed[a_pts],deformed[b_pts],deformed[bore])
    result={'layout':n,'h_mm':h,'dt_s':dt,'nodes':nn,'tetrahedra':len(e),'peak_C':float(peak.max()),
        'final_max_C':float(temp.max()),'released':rel,'max_newton_iterations':newton_max,'max_equilibrium_residual_N':max_res,
        'max_mandrel_reaction_N':max_contact,'input_J':input_total,'loss_J':loss_total,'stored_J':energy,
        'energy_balance_relative':float((input_total-loss_total-energy)/max(input_total,1)),
        'copper_max_C':max_copper_temp,'seal_band_max_C':max_seal_band_temp,'seal_thermal_limits_pass':bool(max_copper_temp<=45 and max_seal_band_temp<=180),
        'elapsed_s':time.perf_counter()-clock,'linear_solver':'CG/AMG with checked sparse-direct fallback' if use_amg else DIRECT_SOLVER_NAME,'linear_solver_fallbacks':linear_fallbacks,'fit':fitted,'imbalance_fraction':imbalance,'preheat_C':preheat,
        'method':'full-part tetrahedral implicit thermal + incremental temperature-dependent J2; nonconforming interpolated weld ties; compression-only mandrel; deposition birth and thermal annealing',
        'material_basis':'project temperature curves are engineering estimates; temperature-dependent NiFe extrapolation recorded in inputs',
        'peak_nodal_C':float(peaknode.max()),'filler_volume_above_1200C_mm3':float(vol[(m==2)&(peak>1200)].sum()),
        'max_von_mises_MPa':float(np.sqrt(1.5*np.sum((stress-stress@pv)**2,axis=1)).max()),
        'active_filler_volume_above_1200C_mm3':float(vol[(m==2)&(peak_active>1200)].sum()),
        'active_peak_scope':'element-mean temperature observed only after deposition activation; 1200 C is the constitutive annealing threshold'}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')

    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--n',type=int,default=6);p.add_argument('--h',type=float,default=2.0)
    p.add_argument('--initial-bore',type=float,default=40.014)
    p.add_argument('--fixture-contact-h',type=float);p.add_argument('--fixture-refinement',type=int,default=1)
    p.add_argument('--dt',type=float,default=2);p.add_argument('--imbalance',type=float,default=.05);p.add_argument('--preheat',type=float,default=20)
    p.add_argument('--resume',action='store_true');p.add_argument('--checkpoint',action='store_true');p.add_argument('--pardiso-symmetric',action='store_true');p.add_argument('--pardiso',action='store_true');p.add_argument('--pardiso-pattern',action='store_true');p.add_argument('--event-dT',type=float);p.add_argument('--paired-opposed',action='store_true');p.add_argument('--unilateral-pads',action='store_true');p.add_argument('--material-enthalpy',action='store_true');p.add_argument('--threads',type=int,default=1)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--amg',action='store_true');p.add_argument('--source-r',type=float,default=73.8);p.add_argument('--weld-h',type=float,default=1.);p.add_argument('--stop-time',type=float);p.add_argument('--thermal-only',action='store_true');p.add_argument('--struct-dt',type=float,default=5.);p.add_argument('--cold-struct-dt',type=float);p.add_argument('--seat-path',type=Path);p.add_argument('--root-h',type=float);p.add_argument('--contact-density',type=float,default=2000.);p.add_argument('--copper-h',type=float,default=50.);p.add_argument('--source-radius',type=float,default=2.2);p.add_argument('--source-depth',type=float,default=1.6);p.add_argument('--peening-trace',action='store_true');p.add_argument('--peening-all',action='store_true');a=p.parse_args()
    if not 1<=a.threads<=8:p.error('--threads must be between 1 and 8')
    if not 39.98<=a.initial_bore<=40.04:p.error('--initial-bore must stay within the declared near-nominal design range')
    if a.fixture_contact_h is not None and (a.fixture_contact_h<=0 or a.fixture_refinement not in (1,2)):
        p.error('positive fixture conductance and refinement1/2 required')
    if a.event_dT is not None and a.event_dT<=0:p.error('--event-dT must be positive')
    if a.pardiso_pattern and (a.pardiso or a.pardiso_symmetric or a.amg):p.error('choose one direct solver mode')
    if (a.pardiso or a.pardiso_symmetric) and a.amg:p.error('choose --pardiso or --amg')
    if a.pardiso or a.pardiso_symmetric:
        import pypardiso
        if a.pardiso_symmetric:
            # Both enthalpy/conduction and associated J2 tangents are symmetric.
            # Intel documents mtype=2 with upper-triangular CSR input.
            from scipy.sparse import triu
            symmetric_solver=pypardiso.PyPardisoSolver(mtype=2)
            def symmetric_solve(matrix,rhs):
                difference=matrix-matrix.T
                if difference.nnz and np.max(abs(difference.data))>1e-10*max(abs(matrix.data).max(),1):
                    raise RuntimeError('PARDISO symmetric solve received an asymmetric tangent')
                answer=pypardiso.spsolve(triu(matrix,format='csr'),rhs,solver=symmetric_solver)
                if np.linalg.norm(matrix@answer-rhs)>.001:
                    raise RuntimeError('PARDISO direct linear residual exceeds 0.001')
                return answer
            spsolve=symmetric_solve
            DIRECT_SOLVER_NAME='Intel MKL PARDISO Cholesky mtype=2, upper-triangular CSR'
        else:
            spsolve=pypardiso.spsolve
            DIRECT_SOLVER_NAME='Intel MKL PARDISO via pypardiso'

    thermal_spsolve=spsolve;structural_spsolve=spsolve
    if a.pardiso_pattern:
        from pardiso_pattern import SymmetricPatternSolver
        thermal_spsolve=SymmetricPatternSolver();structural_spsolve=SymmetricPatternSolver()
        DIRECT_SOLVER_NAME='Intel MKL PARDISO Cholesky mtype=2; independent thermal/mechanical symbolic graphs, phases 13/23'
    SOLVER_THREADS=a.threads
    with threadpool_limits(limits=a.threads):run(a.n,a.h,a.dt,a.output,a.imbalance,a.preheat,a.stop_time,a.thermal_only,a.struct_dt,a.contact_density,a.copper_h,a.source_radius,a.source_depth,a.weld_h,a.source_r,a.amg,a.cold_struct_dt,a.seat_path,a.root_h,a.peening_trace,a.peening_all,event_dT=a.event_dT,paired=a.paired_opposed,unilateral_pads=a.unilateral_pads,material_enthalpy=a.material_enthalpy,initial_bore_diameter=a.initial_bore,resume=a.resume,checkpoint=a.checkpoint,fixture_contact_h=a.fixture_contact_h,fixture_refinement=a.fixture_refinement)
