"""Explicit two-layer Ni99/local-parent, cylindrical 3-D enthalpy finite volumes.

Design verification: no measured fields or assigned PMZ strength. A local domain
test must precede use as a full-assembly boundary condition. r,z,s use mm; s=R*theta.
New metal is introduced at 20 C; the specified net arc power includes its melting.
"""
from pathlib import Path
import argparse, json, time
import numpy as np
import yaml
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import cg, LinearOperator
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[2]

def edges(points, step):
    return np.concatenate([np.linspace(a,b,max(1,int(np.ceil((b-a)/h)))+1)[:-1]
                           for a,b,h in zip(points[:-1],points[1:],step)]+[[points[-1]]])

def build(h, pocket, first, second, extent):
    floor=115-pocket; top1=floor+first; top2=top1+second
    re=edges([75-extent,69,72.2,74.97,75,77.5], [2*h,h,h/2,h/2,h/2])
    ze=edges([100,110,floor-1,floor,top1,115,top2,117.8,119,115+extent],
             [2*h,h,h/3,h/4,h/4,h/4,h/2,h/2,h])
    se=edges([-extent,-9,9,extent],[h,h/2,h])
    # top2 must exceed 115: deposition overfill is a real geometric constraint.
    if not np.all(np.diff(ze)>0): raise ValueError('deposition does not overfill finished surface')
    r,z,s=np.meshgrid((re[:-1]+re[1:])/2,(ze[:-1]+ze[1:])/2,(se[:-1]+se[1:])/2,indexing='ij')
    dr,dz,ds=np.meshgrid(np.diff(re),np.diff(ze),np.diff(se),indexing='ij')
    v=r/75*dr*dz*ds
    shape=r.shape; ids=np.arange(r.size).reshape(shape)
    # Material 0 steel, 1 QT, 2 NiFe, 3 first Ni99, 4 second Ni99; -1 void.
    mat=np.full(shape,-1,np.int8)
    mat[(r<74.97)&(z<115)]=1
    patch=(r>=69)&(r<74.97)&(abs(s)<=9)
    mat[patch&(z>=floor)&(z<top1)]=3
    mat[patch&(z>=top1)&(z<top2)]=4
    mat[(r>=75)&(r<77.5)]=0
    fillet=(r<75)&(r>=71)&(z>=115)&(z-115<=r-71)&(abs(s)<=9)
    # Overfill is removed before final welding, not covered by fictitious QT.
    final=mat.copy();final[(mat==3)|(mat==4)]=np.where(z[(mat==3)|(mat==4)]<115,mat[(mat==3)|(mat==4)],-1)
    final[fillet]=2
    pair=[];area=[];dist=[];axes=[];exterior=np.zeros(shape)
    for ax in range(3):
        lo=[slice(None)]*3;hi=lo.copy();lo[ax]=slice(None,-1);hi[ax]=slice(1,None)
        lo=tuple(lo);hi=tuple(hi)
        if ax==0:
            ar=re[1:-1,None,None]/75*dz[lo]*ds[lo];dl=dr[lo]/2;dh=dr[hi]/2
        elif ax==1:
            ar=r[lo]/75*dr[lo]*ds[lo];dl=dz[lo]/2;dh=dz[hi]/2
        else:
            ar=dr[lo]*dz[lo];dl=r[lo]/75*ds[lo]/2;dh=r[hi]/75*ds[hi]/2
        pair.append(np.stack([ids[lo].ravel(),ids[hi].ravel()],axis=1))
        area.append(np.broadcast_to(ar,ids[lo].shape).ravel())
        dist.append(np.stack([dl.ravel(),dh.ravel()],axis=1));axes.extend([ax]*ids[lo].size)
    return dict(r=r.ravel(),z=z.ravel(),s=s.ravel(),v=v.ravel(),mat=mat.ravel(),final=final.ravel(),
                pair=np.vstack(pair),area=np.concatenate(area),dist=np.vstack(dist),face_axis=np.asarray(axes),shape=shape,
                re=re,ze=ze,se=se,floor=floor,top1=top1,top2=top2)

def tables(ni1_solidus, ni_k_scale):
    mats=yaml.safe_load((ROOT/'project/materials.yaml').read_text(encoding='utf8'))['materials']
    out=[mats[k] for k in ['q235b','qt450_10','ernife_ci']]
    out[2]['temperature_dependent']=dict(temperatures_c=[20,200,400,600,800,1000,1400],
             thermal_conductivity_w_mk=[22,24,26,28,30,32,35],specific_heat_j_kgk=[480,520,570,630,710,760,800])
    # Thermophysical sensitivity only. Wrought Nickel 200/201 conductivity is
    # a high-Ni end member, never a strength assignment for diluted first layer.
    for j in [3,4]:
        out.append(dict(name='Ni99 first, diluted' if j==3 else 'Ni99 second',
            nominal_properties_20c=dict(density_kg_m3=1/(.8/8890+.2/7200) if j==3 else 1/(.97/8890+.03/7200)),
            temperature_dependent=dict(temperatures_c=[20,100,200,300,400,500,600,700,800,900,1000,1446],
              thermal_conductivity_w_mk=(ni_k_scale*np.array([70.3,66.5,61.6,56.8,55.4,57.6,59.7,61.8,64,66.1,68.2,68.2])).tolist(),
              specific_heat_j_kgk=[456,480,510,550,570,590,610,630,650,670,690,750]),
            fusion_enthalpy=dict(solidus_C=ni1_solidus if j==3 else 1435,
              liquidus_C=1446,latent_heat_J_kg=297000),
            basis='k: Special Metals Nickel 200 Table3, scaled sensitivity; cp(T) and latent engineering inputs; first-layer solidus parameter, not CALPHAD or observed PMZ'))
    return out

def solve(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    g=build(args.h,args.pocket,args.first,args.second,args.extent)
    tab=tables(args.ni1_solidus,args.ni_k_scale)
    r,z,s,v=g['r'],g['z'],g['s'],g['v'];n=len(r);a,b=g['pair'].T
    rho=np.array([t['nominal_properties_20c']['density_kg_m3'] for t in tab])*1e-9
    inp=vars(args)|dict(materials=tab,cells=n,coordinates='cylindrical r,z,s=75theta',
      remote_boundary='adiabatic truncations, free faces convection15 W/m2K plus radiation0.7; domain check required',
      power_policy='net power is partitioned into entering filler enthalpy and Gaussian parent/pool heating; total power conserved',
      mechanical_or_failure_capacity_assigned=False)
    (out/'input.json').write_text(json.dumps(inp,ensure_ascii=False,indent=2),encoding='utf8')
    T=np.full(n,20.);stage_peaks=[];stage_face_peaks=[];stage_ends=[];history=[];fields=[];time0=time.perf_counter()
    def props(q,mat,key):
        val=np.zeros(n)
        for j,t in enumerate(tab):
            ix=mat==j;tb=t['temperature_dependent'];val[ix]=np.interp(q[ix],tb['temperatures_c'],tb[key])
        return val
    def enthalpy(q,mat):
        H=np.zeros(n);dH=np.ones(n)
        for j,t in enumerate(tab):
            ix=mat==j;tb=t['temperature_dependent'];x=np.asarray(tb['temperatures_c']);y=np.asarray(tb['specific_heat_j_kgk'])
            prefix=np.r_[0,np.cumsum(np.diff(x)*(y[1:]+y[:-1])/2)]
            def integral(u):
                p=np.clip(np.searchsorted(x,u,side='right')-1,0,len(x)-2);dx=np.minimum(u,x[-1])-x[p]
                return prefix[p]+y[p]*dx+.5*(y[p+1]-y[p])/np.diff(x)[p]*dx**2+np.maximum(u-x[-1],0)*y[-1]
            f=t['fusion_enthalpy'];ts=f['solidus_C'];tl=f['liquidus_C'];L=f['latent_heat_J_kg']
            H[ix]=rho[j]*v[ix]*(integral(q[ix])-integral(np.full(ix.sum(),20.))+L*np.clip((q[ix]-ts)/(tl-ts),0,1))
            dH[ix]=rho[j]*v[ix]*(np.interp(q[ix],x,y)+L/(tl-ts)*((q[ix]>ts)&(q[ix]<tl)))
        return H,dH
    stages=[dict(name='precoat1',power=args.precoat_power,speed=2.,mat=g['mat'],born=3,top=g['top1'],sr=args.precoat_width,sd=args.precoat_depth,source_r=args.precoat_r,cool_to=90.),
            dict(name='precoat2',power=args.precoat_power,speed=2.,mat=g['mat'],born=4,top=g['top2'],sr=args.precoat_width,sd=args.precoat_depth,source_r=args.precoat_r,cool_to=20.5),
            dict(name='final_root',power=470.25*1.05,speed=1.65,mat=g['final'],born=2,top=116.2,sr=1.270170592,sd=.923760431,source_r=74.8,cool_to=90.),
            dict(name='final_cap',power=470.25*1.05,speed=1.65,mat=g['final'],born=2,top=117.,sr=1.270170592,sd=.923760431,source_r=74.8,cool_to=20.5)]
    if args.precoat_tracks==2:
        strips=[]
        for st in stages[:2]:
            for strip,rad in enumerate([70.5,73.5]):
                row=st.copy();row.update(name=st['name']+f'_strip{strip+1}',source_r=rad,strip=strip,
                  cool_to=90. if strip==0 or st['born']==3 else 20.5)
                strips.append(row)
        stages=strips+stages[2:]
    previous_active=None
    for stidx,st in enumerate(stages[:args.stages]):
        mat=st['mat'].copy();local=0.;dur=18/st['speed'];peak=T.copy();face_peak=np.full(len(a),20.);inputJ=0.;lossJ=0.;balance_max=0.;iterations=0;depositionJ=0.
        is_precoat=st['born'] in (3,4)
        if is_precoat:active=(mat==1) if previous_active is None else previous_active.copy()
        elif st['name']=='final_root':
            active=(mat>=0)&(mat!=2);T[mat==0]=20.;T[~active]=20.
        else:active=mat>=0
        if is_precoat:
            mat[mat==0]=-1;mat[mat==2]=-1
            if st['born']==3:mat[mat==4]=-1
        root=(mat==2)&(75-r+z-115<2.8)
        born=mat==st['born']
        if st['name']=='final_root':born &= root
        if st['name']=='final_cap':born &= ~root;active[born]=False
        if args.precoat_tracks==2 and is_precoat:born &= (r<72.) if st['strip']==0 else (r>=72.)
        near=(r>69)&(abs(s)<10)&(z>112)
        # Faces between occupied and void cells are true exposed surfaces.
        while local<args.max_stage_time:
            dt=args.dt if local<dur+3 else min(1.,args.dt*10)
            if local<dur-1e-9:dt=min(dt,dur-local)
            elif abs(local-dur)<1e-9:local=dur
            nt=local+dt;oldactive=active.copy()
            active |= born & (s+9<=min(nt*st['speed'],18)+1e-9)
            born_now=active&~oldactive
            T[born_now]=20.
            if st['name']=='final_cap':active[root]=True
            kk=mat.copy();kk[~active]=-1
            expose=np.bincount(a,weights=g['area']*(active[a]&~active[b]),minlength=n)+np.bincount(b,weights=g['area']*(active[b]&~active[a]),minlength=n)
            # Adiabatic outer computational faces are intentionally excluded.
            oldH,_=enthalpy(T,kk);q=np.zeros(n)
            incoming_T=T.copy();incoming_T[born_now]=args.deposition_temperature
            incoming_H,_=enthalpy(incoming_T,kk)
            fillerJ=float((incoming_H-oldH).sum())
            depositionJ+=fillerJ;T=incoming_T
            if local<dur-1e-10:
                centre=-9+st['speed']*(local+dt/2)
                if is_precoat:
                    weight=np.exp(-((r-st['source_r'])**2+(s-centre)**2)/st['sr']**2-(z-(st['top']-.15))**2/st['sd']**2)*v*active
                else:
                    weight=np.exp(-((r-st['source_r'])**2+(s-centre)**2)/st['sr']**2-(z-st['top'])**2/st['sd']**2)*v*active
                if weight.sum()==0:raise RuntimeError('empty physical heat source')
                available=st['power']-fillerJ/dt
                if available<0:raise RuntimeError('cellwise hot-filler birth enthalpy exceeds arc energy; refine the longitudinal birth grid')
                q=available*weight/weight.sum();inputJ+=st['power']*dt
            elif fillerJ>0:raise RuntimeError('new deposition occurred with the arc off')
            # The incoming enthalpy is a source independent of the spatial arc;
            # do not double count it as old stored energy or additional power.
            filler_source=np.zeros(n);filler_source[born_now]=(incoming_H-oldH)[born_now]/dt
            q+=filler_source
            guess=T.copy();resnorm=1.
            for it in range(80):
                k=props(guess,kk,'thermal_conductivity_w_mk')/1000
                live=active[a]&active[b];cond=np.zeros(len(a));cond[live]=g['area'][live]/(g['dist'][live,0]/k[a[live]]+g['dist'][live,1]/k[b[live]])
                flux=cond*(guess[a]-guess[b])
                H,dh=enthalpy(guess,kk)
                loss=expose*(15e-6*(guess-20)+.7*5.670374419e-14*((guess+273.15)**4-293.15**4))
                dl=expose*(15e-6+4*.7*5.670374419e-14*(guess+273.15)**3)
                residual=(H-oldH)/dt+np.bincount(a,weights=flux,minlength=n)-np.bincount(b,weights=flux,minlength=n)+loss-q
                residual[~active]=0
                resnorm=float(np.max(abs(residual)))
                if resnorm<2e-6:break
                diag=dh/dt+dl+np.bincount(a,weights=cond,minlength=n)+np.bincount(b,weights=cond,minlength=n);diag[~active]=1.
                A=coo_matrix((np.r_[diag,-cond,-cond],(np.r_[np.arange(n),a,b],np.r_[np.arange(n),b,a])),shape=(n,n)).tocsr()
                d,info=cg(A,-residual,rtol=1e-9,atol=1e-10,M=LinearOperator((n,n),matvec=lambda x:x/diag),maxiter=1500)
                if info:raise RuntimeError(f'linear solve did not converge: {info}')
                # Safeguard across the steep apparent heat capacity at fusion.
                alpha=min(1.,100/max(np.max(abs(d)),1.))
                guess+=alpha*d
            else:raise RuntimeError(f'enthalpy step not converged: {st["name"]} t{nt} residual{resnorm}')
            T=guess;iterations+=it+1;peak=np.maximum(peak,np.where(active,np.maximum(T,incoming_T),20.));lossJ+=float(loss.sum()*dt)
            kface=props(T,kk,'thermal_conductivity_w_mk')/1000
            face_temp=np.full(len(a),20.)
            da=g['dist'][live,0]/kface[a[live]];db=g['dist'][live,1]/kface[b[live]]
            face_temp[live]=(db*T[a[live]]+da*T[b[live]])/(da+db)
            face_peak=np.maximum(face_peak,face_temp)
            eb=float((H-oldH).sum()+loss.sum()*dt-q.sum()*dt);balance_max=max(balance_max,abs(eb))
            history.append([stidx,nt,float(T[active].max()),float(T[active&near].max()),float(T[active].min()),resnorm,eb,int(it+1)])
            local=dur if abs(nt-dur)<1e-9 else nt
            if len(history)%50==0:
                np.savetxt(out/'thermal-history-partial.csv',history,delimiter=',',header='stage,t_s,max_C,near_max_C,min_C,max_residual_W,energy_error_J,iterations',comments='')
                (out/'progress.json').write_text(json.dumps(dict(stage=st['name'],stage_time_s=local,peak_C=float(peak.max()),current_max_C=float(T.max()),elapsed_s=time.perf_counter()-time0)),encoding='utf8')
                print(st['name'],round(local,3),round(float(T.max()),2),round(float(peak.max()),2),flush=True)
            if local>=dur and T[active&near].max()<=st['cool_to']:break
            if args.arc_only and local>=dur+args.cool_after_arc-1e-9:break
        stage_peaks.append(peak.copy());stage_face_peaks.append(face_peak.copy());stage_ends.append(T.copy());fields.append(dict(stage=st['name'],time_s=local,input_J=inputJ,loss_J=lossJ,filler_enthalpy_share_J=depositionJ,
          maximum_step_energy_error_J=balance_max,nonlinear_iterations=iterations,cooled_to_target=bool(T[active&near].max()<=st['cool_to']),
          QT_peak_C=float(peak[mat==1].max()),first_layer_peak_C=float(peak[mat==3].max()),second_layer_peak_C=float(peak[mat==4].max()) if np.any(mat==4) else None))
        np.savez_compressed(out/'checkpoint.npz',T=T,stage_peaks=np.array(stage_peaks),stage_face_peaks=np.array(stage_face_peaks),stage_ends=np.array(stage_ends),stage_completed=stidx,**g)
        (out/'stage-results.json').write_text(json.dumps(fields,ensure_ascii=False,indent=2),encoding='utf8')
        previous_active=active.copy()
        if not args.arc_only and not fields[-1]['cooled_to_target']:
            raise RuntimeError('local domain did not reach the specified interpass/cold temperature')
    np.savetxt(out/'thermal-history.csv',history,delimiter=',',header='stage,t_s,max_C,near_max_C,min_C,max_residual_W,energy_error_J,iterations',comments='')
    (out/'result.json').write_text(json.dumps(dict(stages=fields,elapsed_s=time.perf_counter()-time0,completed=True,
      full_assembly_verification=False,material_state_strength_verified=False),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(fields),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--h',type=float,default=1.)
    p.add_argument('--dt',type=float,default=.1);p.add_argument('--pocket',type=float,default=1.5)
    p.add_argument('--first',type=float,default=.656);p.add_argument('--second',type=float,default=1.002)
    p.add_argument('--extent',type=float,default=15.);p.add_argument('--precoat-width',type=float,default=2.2)
    p.add_argument('--precoat-power',type=float,default=616.)
    p.add_argument('--precoat-r',type=float,default=72.)
    p.add_argument('--precoat-tracks',type=int,choices=[1,2],default=1)
    p.add_argument('--deposition-temperature',type=float,default=20.)
    p.add_argument('--precoat-depth',type=float,default=.8);p.add_argument('--ni1-solidus',type=float,default=1300.)
    p.add_argument('--ni-k-scale',type=float,default=.75);p.add_argument('--stages',type=int,default=4)
    p.add_argument('--max-stage-time',type=float,default=1800.);p.add_argument('--arc-only',action='store_true')
    p.add_argument('--cool-after-arc',type=float,default=0.)
    args=p.parse_args()
    try:
        with threadpool_limits(limits=1):solve(args)
    except Exception as exc:
        Path(args.output).mkdir(parents=True,exist_ok=True)
        (Path(args.output)/'failure.json').write_text(json.dumps(dict(error=str(exc),completed=False)),encoding='utf8')
        raise
