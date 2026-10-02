"""Current full assembly: implicit heat conduction and incremental J2 tetrahedral FE.

Units mm, N, s, C, MPa. This is an engineering model, not measured data.
All arrays, input choices and equilibrium/convergence records are saved.
"""
from pathlib import Path
import argparse, json, time, sys
import numpy as np
import gmsh, yaml
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import spsolve
from threadpoolctl import threadpool_limits

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

def mesh(n,h):
    """Independent solid meshes avoid facets crossing the real 0.02 mm fit gap.
    Weld interfaces use explicit interpolation constraints, never join bare wing sides.
    """
    from scipy.spatial import cKDTree
    allx=[];alle=[];allm=[];allbd=[]; offsets=[]
    for part in range(3):
        gmsh.initialize()
        try:
            gmsh.option.setNumber('General.Terminal',0);gmsh.model.add('part')
            occ=gmsh.model.occ
            if part==0:occ.importShapes(str(ROOT/'simulation/structural-v4/common/shell.step'))
            elif part==1:
                seat=occ.importShapes(str(ROOT/f'simulation/structural-v4/models/{n}p-fair-b/{n}P-FAIR_B.step'))
                occ.translate(seat,0,0,100)
            else:
                roots=[];covers=[]
                for j in range(n):
                    current=[]
                    for leg in (2.8,4.):
                        pts=[occ.addPoint(r,0,z) for r,z in ((75-leg,112),(75,112),(75,112+leg))]
                        ls=[occ.addLine(pts[k],pts[(k+1)%3]) for k in range(3)]
                        surf=occ.addPlaneSurface([occ.addCurveLoop(ls)])
                        angle=18/74.98;occ.rotate([(2,surf)],0,0,0,0,0,1,j*2*np.pi/n-angle/2)
                        current.append([d for d in occ.revolve([(2,surf)],0,0,0,0,0,1,angle) if d[0]==3][0])
                    roots.append(current[0]);covers.append(current[1])
                occ.fragment(roots,covers)
            occ.synchronize()
            gmsh.option.setNumber('Mesh.MeshSizeMin',h*.75)
            gmsh.option.setNumber('Mesh.MeshSizeMax',h*(3 if part==0 else 2 if part==1 else 1))
            gmsh.option.setNumber('Mesh.Algorithm3D',1)
            if part<2:
                surfaces=[]
                for d,tag in gmsh.model.getEntities(2):
                    xx,yy,zz=occ.getCenterOfMass(d,tag)
                    if (part==0 and 108<zz<118) or (part==1 and np.hypot(xx,yy)>65):surfaces.append(tag)
                if surfaces:
                    field=gmsh.model.mesh.field.add('Distance');gmsh.model.mesh.field.setNumbers(field,'FacesList',surfaces)
                    f=gmsh.model.mesh.field.add('Threshold')
                    for key,val in {'InField':field,'SizeMin':h,'SizeMax':h*(3 if part==0 else 2),'DistMin':4,'DistMax':15}.items():gmsh.model.mesh.field.setNumber(f,key,val)
                    gmsh.model.mesh.field.setAsBackgroundMesh(f)
            gmsh.model.mesh.generate(3)
            tags,xx,_=gmsh.model.mesh.getNodes();ix={int(v):i for i,v in enumerate(tags)}
            coords=np.array(xx).reshape(-1,3);_,conn=gmsh.model.mesh.getElementsByType(4)
            elems=np.array([ix[int(z)] for z in conn]).reshape(-1,4)
            offset=sum(len(v) for v in allx);offsets.append(offset)
            faces=np.sort(np.vstack([elems[:,[0,1,2]],elems[:,[0,1,3]],elems[:,[0,2,3]],elems[:,[1,2,3]]]),axis=1)
            uf,cnt=np.unique(faces,axis=0,return_counts=True)
            allx.append(coords);alle.append(elems+offset);allm.extend([part]*len(elems));allbd.append(uf[cnt==1]+offset)
        finally:gmsh.finalize()
    x=np.vstack(allx);e=np.vstack(alle);m=np.array(allm);bd=np.vstack(allbd)
    links=[]
    for part in (0,1):
        nodes=np.unique(allbd[part]);rr=np.linalg.norm(x[nodes,:2],axis=1)
        if part==0:target=nodes[(rr<75.05)&(x[nodes,2]>105)&(x[nodes,2]<122)]
        else:target=nodes[abs(x[nodes,2]-112)<1e-5]
        tree=cKDTree(x[target]);weldnodes=np.unique(allbd[2]);wr=np.linalg.norm(x[weldnodes,:2],axis=1)
        pick=weldnodes[(abs(wr-75)<1e-5) if part==0 else (abs(x[weldnodes,2]-112)<1e-5)]
        for node in pick:
            distances,idx=tree.query(x[node],k=4);weights=1/np.maximum(distances,1e-8)**2;weights/=weights.sum()
            links.append((int(node),target[idx].tolist(),weights.tolist()))
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

def run(n,h,dt,output,imbalance=0.,preheat=20.):
    output.mkdir(parents=True,exist_ok=True)
    clock=time.perf_counter(); x,e,m,bd,links=mesh(n,h)
    print('mesh',n,h,len(x),len(e),flush=True)
    g,vol,b,dof=operators(x,e); c=x[e].mean(axis=1)
    radius=np.linalg.norm(c[:,:2],axis=1); theta=np.arctan2(c[:,1],c[:,0])%(2*np.pi)
    segment=np.round(theta/(2*np.pi/n)).astype(int)%n
    local=(theta-segment*2*np.pi/n+np.pi)%(2*np.pi)-np.pi
    along=local*74.98+9
    layer=np.where(75.01-c[:,0]*np.cos(theta)-c[:,1]*np.sin(theta)+c[:,2]-112<2.8,0,1)
    order=list(range(0,n,2))+list(range(1,n,2))
    if n==6: order=[0,3,2,5,1,4]
    if n==8: order=[0,4,2,6,1,5,3,7]
    seq=[(p,j) for p in range(2) for j in order]
    v=1.65; duration=18/v; idle=18.; interval=duration+idle
    starts=np.array([seq.index((int(layer[k]),int(segment[k])))*interval if m[k]==2 else -1e6 for k in range(len(e))])
    birth=starts+np.clip(along/v,0,duration)
    # Physical surface areas supply convection, radiation and fixture cooling.
    area=np.linalg.norm(np.cross(x[bd[:,1]]-x[bd[:,0]],x[bd[:,2]]-x[bd[:,0]]),axis=1)/2
    surface=np.bincount(bd.ravel(),weights=np.repeat(area/3,3),minlength=len(x))
    bx=x[bd].mean(axis=1); br=np.linalg.norm(bx[:,:2],axis=1)
    copper=(abs(br-75)<.5)&(bx[:,2]>=94)&(bx[:,2]<=100)
    copper_area=np.bincount(bd[copper].ravel(),weights=np.repeat(area[copper]/3,3),minlength=len(x))
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
    nn=len(x); nd=3*nn; u=np.zeros(nd); plastic=np.zeros((len(e),6)); eqp=np.zeros(len(e)); ref=np.zeros((len(e),6)
    )
    temp=np.full(nn,preheat);active=m!=2;thermal_active=active.copy(); history=[];struct=[]; saved_t=[];saved_u=[];energy=0.; loss_total=0.;input_total=0.
    pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3; pd=np.eye(6)-pv
    rn=np.linalg.norm(x[:,:2],axis=1)
    # Three-point shell base: sufficient to remove rigid motion, without a fully clamped rim.
    bottom=np.flatnonzero(x[:,2]<1e-5)
    anchors=[bottom[np.argmin(np.linalg.norm(x[bottom,:2]-[77.5*np.cos(a),77.5*np.sin(a)],axis=1))] for a in (0,2*np.pi/3,4*np.pi/3)]
    fixed={3*int(k)+2:0 for k in bottom}
    for ax in (0,1): fixed[3*int(anchors[0])+ax]=0.
    fixed[3*int(anchors[1])+1]=0.
    bore=np.flatnonzero((abs(rn-20)<1e-4)&(x[:,2]>=100-1e-4)&(x[:,2]<=112+1e-4))
    a_pts=bottom
    b_pts=np.flatnonzero((abs(rn-75)<1e-4)&((x[:,2]<35)|(x[:,2]>165)))
    if len(bore)<10 or len(b_pts)<6: raise RuntimeError('measurement surfaces missing')
    normals=x[bore,:2]/rn[bore,None]
    # Mandrel acts in compression only, locks contracting bore, allows outward thermal expansion.
    contact_k=5e4
    endarc=len(seq)*interval-idle
    end=endarc+1800
    peak=np.zeros(len(e));peaknode=np.zeros(nn);newton_max=0;max_res=0.;max_contact=0.;rel=False
    last_struct_t=0
    t=0.
    lnodes=np.array([[z[0],*z[1]] for z in links]);lweights=np.array([[1.,*[-v for v in z[2]]] for z in links])
    while t<end-1e-8:
        stepdt=dt if t<endarc+120 else min(15.,dt*5)
        t+=stepdt
        newactive=(m!=2)|(t>=birth)
        te=temp[e].mean(axis=1)
        k=prop(te,'thermal_conductivity_w_mk')/1000
        thermal_factor=np.where(newactive,1.,1e-6)
        ke=np.einsum('eik,ejk,e->eij',g,g,k*vol*thermal_factor)
        conductivity=coo_matrix((ke.ravel(),(rr,cc)),shape=(nn,nn)).tocsr()
        occupied=np.unique(e[newactive]);linkactive=np.isin(lnodes[:,0],occupied)
        lt=lnodes[linkactive];lw=lweights[linkactive]
        lk=10*np.einsum('li,lj->lij',lw,lw)
        conductivity+=coo_matrix((lk.ravel(),(np.repeat(lt,5,axis=1).ravel(),np.tile(lt,(1,5)).ravel())),shape=(nn,nn)).tocsr()
        mass_e=rho*vol*thermal_factor
        hrad=.7*5.670374419e-14*((np.maximum(temp,20)+273.15)**2+293.15**2)*(np.maximum(temp,20)+566.3)
        cool=(15e-6+hrad)*surface+.002*copper_area
        q=np.zeros(len(e)); st=int((t-stepdt/2)//interval)
        on=st<len(seq) and 0<=(t-stepdt/2-st*interval)<duration
        if on:
            p,j=seq[st]; ang=(j*2*np.pi/n+(v*(t-stepdt/2-st*interval)-9)/74.98)
            source=np.array([73.8*np.cos(ang),73.8*np.sin(ang),113.2 if p==0 else 114.0])
            d=c-source; norm=np.exp(-((d[:,0]**2+d[:,1]**2)/2.2**2+(d[:,2]/1.6)**2))
            norm*=vol*newactive
            q=norm/max(norm.sum(),1e-30)*495*(1+imbalance if j==0 else 1)
        nodal_q=np.bincount(e.ravel(),weights=np.repeat(q/4,4),minlength=nn)
        old=temp.copy()
        def enthalpy_nodes(tv):
            local=tv[e]
            hh=integrated(local,'specific_heat_j_kgk')+250000*np.clip((local-1100)/300,0,1)
            cap=prop(local,'specific_heat_j_kgk')+250000/300*((local>1100)&(local<1400))
            H=np.bincount(e.ravel(),weights=(mass_e[:,None]*hh/4).ravel(),minlength=nn)
            C=np.bincount(e.ravel(),weights=(mass_e[:,None]*cap/4).ravel(),minlength=nn)
            return H,C
        # New cold filler enters at 20 C. Its enthalpy is zero before deposition.
        old_H,_=enthalpy_nodes(old)
        born=(m==2)&newactive&~thermal_active
        if np.any(born):
            bh=integrated(old[e],'specific_heat_j_kgk')+250000*np.clip((old[e]-1100)/300,0,1)
            old_H-=np.bincount(e[born].ravel(),weights=(mass_e[born,None]*bh[born]/4).ravel(),minlength=nn)
        for thermal_iteration in range(35):
            H,C=enthalpy_nodes(temp)
            residual=H-old_H+stepdt*(conductivity@temp+cool*(temp-20)-nodal_q)
            if np.linalg.norm(residual)<1e-5:break
            increment=spsolve(diags(C+stepdt*cool)+stepdt*conductivity,-residual)
            norm=np.linalg.norm(residual)
            for power in range(12):
                candidate=temp+increment*.5**power
                ch,_=enthalpy_nodes(candidate)
                cr=ch-old_H+stepdt*(conductivity@candidate+cool*(candidate-20)-nodal_q)
                if np.linalg.norm(cr)<norm:temp=candidate;break
            else:raise RuntimeError('enthalpy Newton stagnation')
        else:raise RuntimeError('enthalpy Newton failure')
        thermal_active=newactive.copy()
        if not np.all(np.isfinite(temp)) or temp.max()>5000:raise RuntimeError('invalid thermal state')
        delta_H=float((H-old_H).sum())
        balance=delta_H+stepdt*np.dot(cool,temp-20)-stepdt*q.sum()
        energy+=delta_H;loss_total+=stepdt*np.dot(cool,temp-20);input_total+=stepdt*q.sum()
        te=temp[e].mean(axis=1);peak=np.maximum(peak,te);peaknode=np.maximum(peaknode,temp)
        history.append([t,float(temp.max()),float(te[m==1].max()),input_total,loss_total,energy,float(balance)])
        # Solve frequently through every heated segment; all thermal increments retained.
        if t-last_struct_t>=max(20.,dt)-1e-8 or (t>=end):
            E=prop(te,'elastic_modulus_gpa')*1000; Y=prop(te,'yield_strength_mpa'); al=integrated(te,'alpha_per_k')
            G=E/(2*(1+nu));K=E/(3*(1-2*nu));H=.005*E
            newly=newactive&~active
            strains=np.einsum('eij,ej->ei',b,u[dof])
            # New deposition / material above annealing temperature is stress free.
            reset=newly|(te>1200)
            ref[reset]=strains[reset];ref[reset,:3]-=al[reset,None]
            plastic[reset]=0.;eqp[reset]=0.
            active=newactive.copy()
            scale=np.where(active,1.,1e-8)
            constraints=dict(fixed)
            occupied=np.unique(e[active]); unoccupied=np.setdiff1d(np.arange(nn),occupied)
            for z in (3*unoccupied[:,None]+np.arange(3)).ravel():constraints[int(z)]=0.
            if not rel and t>endarc+120 and float(te[(m==2)|(radius>70)].max())<55:rel=True
            fix=np.array(sorted(constraints));free=np.setdiff1d(np.arange(nd),fix)
            trial=u.copy();trial[fix]=[constraints[int(d)] for d in fix]
            lr=[];lc=[];lv=[]
            for ax in range(3):
                ld=3*lt+ax;lr.extend(np.repeat(ld,5,axis=1).ravel());lc.extend(np.tile(ld,(1,5)).ravel());lv.extend((1e6*np.einsum('li,lj->lij',lw,lw)).ravel())
            tie=coo_matrix((lv,(lr,lc)),shape=(nd,nd)).tocsr()
            def assemble(uv,tangent=True):
                strain=np.einsum('eij,ej->ei',b,uv[dof])-ref-plastic
                strain[:,:3]-=al[:,None]
                dev=strain-strain@pv; s=2*G[:,None]*dev
                qv=np.sqrt(1.5*np.sum(s*s,axis=1)); dl=np.maximum(0,(qv-Y-H*eqp)/(3*G+H))
                direction=1.5*s/np.maximum(qv[:,None],1e-20)
                beta=1-3*G*dl/np.maximum(qv,1e-20)
                stress=s*beta[:,None]+3*K[:,None]*(strain@pv)
                stress*=scale[:,None]
                fi=np.einsum('eji,ej,e->ei',b,stress,vol)
                force=np.bincount(dof.ravel(),weights=fi.ravel(),minlength=nd)
                force+=tie@uv
                if tangent:
                    D=3*K[:,None,None]*pv+2*G[:,None,None]*beta[:,None,None]*pd
                    corr=1/(3*G+H)-dl/np.maximum(qv,1e-20)
                    D-=np.where(dl>0,4*G*G*corr,0)[:,None,None]*direction[:,:,None]*direction[:,None,:]
                    ke=np.einsum('eji,ejk,ekl,e->eil',b,D,b,vol*scale,optimize=True)
                    matrix=coo_matrix((ke.ravel(),(srr,scc)),shape=(nd,nd)).tocsr()
                    matrix+=tie
                else:matrix=None
                reaction=0.
                if not rel:
                    bu=uv.reshape(-1,3)[bore,:2];gap=(bu*normals).sum(axis=1)
                    ids=np.flatnonzero(gap<0)
                    cf=-contact_k*gap[ids,None]*normals[ids]
                    np.add.at(force,3*bore[ids],-cf[:,0]);np.add.at(force,3*bore[ids]+1,-cf[:,1])
                    reaction=float(np.linalg.norm(cf,axis=1).sum())
                    if tangent and len(ids):
                        cd=3*bore[ids,None]+np.arange(2)
                        blocks=contact_k*normals[ids,:,None]*normals[ids,None,:]
                        matrix+=coo_matrix((blocks.ravel(),(np.repeat(cd,2,axis=1).ravel(),np.tile(cd,(1,2)).ravel())),shape=(nd,nd)).tocsr()
                return force,matrix,stress,dl,direction,reaction
            converged=False
            for it in range(35):
                force,matrix,stress,dl,direction,reaction=assemble(trial)
                res=np.linalg.norm(force[free])
                if res<.05:
                    converged=True;break
                du=spsolve(matrix[free][:,free],-force[free])
                accepted=False
                for power in range(9):
                    candidate=trial.copy();candidate[free]+=du*(.5**power)
                    ff,*_=assemble(candidate,False)
                    if np.linalg.norm(ff[free])<res:trial=candidate;accepted=True;break
                if not accepted:raise RuntimeError(f'Newton stagnation t={t} residual={res}')
            if not converged:raise RuntimeError(f'Newton failed t={t} residual={res}')
            u=trial;plastic+=dl[:,None]*direction;eqp+=dl
            newton_max=max(newton_max,it);max_res=max(max_res,float(res));max_contact=max(max_contact,reaction)
            struct.append([t,it,float(res),reaction,int(rel),float(np.max(np.linalg.norm(u.reshape(-1,3),axis=1)))])
            if len(struct)%20==0:print('step',n,h,round(t,2),round(temp.max(),1),'peak',round(peaknode.max(),1),it,round(time.perf_counter()-clock,1),flush=True)
            last_struct_t=t
            if len(struct)%10==0:saved_t.append(te.astype(np.float32));saved_u.append(u.astype(np.float32))
        if rel and temp.max()<20.5:break
    # Final return to reference temperature, then release is evaluated explicitly.
    # Continue cooling rather than asserting ambient at a finite hot step.
    np.savez_compressed(output/'fields.npz',x=x,e=e,material=m,boundary=bd,u=u.reshape(-1,3),stress=stress,plastic=plastic,
        eqp=eqp,temperature=temp,peak_temperature=peak,peak_nodal_temperature=peaknode,temperature_snapshots=saved_t,displacement_snapshots=saved_u)
    np.savetxt(output/'thermal-history.csv',history,delimiter=',',header='t_s,max_C,seat_max_C,input_J,loss_J,stored_J,balance_J',comments='')
    np.savetxt(output/'equilibrium-history.csv',struct,delimiter=',',header='t_s,iterations,residual_N,mandrel_reaction_N,released,max_u_mm',comments='')
    if not rel:raise RuntimeError('not yet released; extend cooling duration')
    deformed=x+u.reshape(-1,3)
    fitted=fit_position_diameter(deformed[a_pts],deformed[b_pts],deformed[bore])
    result={'layout':n,'h_mm':h,'dt_s':dt,'nodes':nn,'tetrahedra':len(e),'peak_C':float(peak.max()),
        'final_max_C':float(temp.max()),'released':rel,'max_newton_iterations':newton_max,'max_equilibrium_residual_N':max_res,
        'max_mandrel_reaction_N':max_contact,'input_J':input_total,'loss_J':loss_total,'stored_J':energy,
        'energy_balance_relative':float((input_total-loss_total-energy)/max(input_total,1)),
        'elapsed_s':time.perf_counter()-clock,'fit':fitted,'imbalance_fraction':imbalance,'preheat_C':preheat,
        'method':'full-part tetrahedral implicit thermal + incremental temperature-dependent J2; nonconforming interpolated weld ties; compression-only mandrel; deposition birth and thermal annealing',
        'material_basis':'project temperature curves are engineering estimates; temperature-dependent NiFe extrapolation recorded in inputs',
        'peak_nodal_C':float(peaknode.max()),'filler_volume_above_1200C_mm3':float(vol[(m==2)&(peak>1200)].sum()),
        'max_von_mises_MPa':float(np.sqrt(1.5*np.sum((stress-stress@pv)**2,axis=1)).max())}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (output/'input.json').write_text(json.dumps({'materials':tables,'sequence':seq,'travel_mm_s':v,'net_W':495,'leg_mm':4,
        'root_leg_mm':2.8,'idle_s':idle,'h_air_W_m2K':15,'emissivity':.7,'copper_contact_W_m2K':2000,
        'mandrel_penalty_N_mm_per_node':contact_k,'annealing_C':1200,'latent_heat_J_kg':250000,
        'source_radius_mm':2.2,'source_depth_mm':1.6},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--n',type=int,default=6);p.add_argument('--h',type=float,default=2.0)
    p.add_argument('--dt',type=float,default=2);p.add_argument('--imbalance',type=float,default=.05);p.add_argument('--preheat',type=float,default=20)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with threadpool_limits(limits=1):run(a.n,a.h,a.dt,a.output,a.imbalance,a.preheat)
