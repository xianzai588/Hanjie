"""Cold Ni-layer constitutive diagnosis; no joint qualification is inferred.

3-D associated J2 return mapping retains hydrostatic stress. Both free lateral
stress and restrained lateral strain are evaluated. Wrought Ni200 data provide
comparison parameters, not diluted Ni99 deposit or QT-PMZ strength allowables.
"""
from pathlib import Path
import argparse,csv,json
import numpy as np

PV=np.outer([1.,1.,1.,0.,0.,0.],[1.,1.,1.,0.,0.,0.])/3
PD=np.eye(6)-PV


def response(strain,plastic,eqp,E,nu,Y,H):
    G=E/(2*(1+nu));K=E/(3*(1-2*nu))
    elastic=strain-plastic;dev=PD@elastic;s=2*G*dev
    q=np.sqrt(1.5*np.dot(s,s));dl=max(0.,(q-Y-H*eqp)/(3*G+H))
    direction=1.5*s/max(q,1e-20);beta=1-3*G*dl/max(q,1e-20)
    stress=beta*s+3*K*(PV@elastic)
    tangent=3*K*PV+2*G*beta*PD
    if dl>0:tangent-=4*G*G*(1/(3*G+H)-dl/max(q,1e-20))*np.outer(direction,direction)
    return stress,tangent,plastic+dl*direction,eqp+dl


def principal(stress):
    xx,yy,zz,yz,xz,xy=stress
    tensor=np.array([[xx,xy/np.sqrt(2),xz/np.sqrt(2)],
        [xy/np.sqrt(2),yy,yz/np.sqrt(2)],[xz/np.sqrt(2),yz/np.sqrt(2),zz]])
    return np.linalg.eigvalsh(tensor)


def run_path(constraint,Y,H,E=205000.,nu=.29,thickness=1.2):
    # Diagnostic jump history in mm; independent of unavailable whole-part fields.
    load=np.r_[np.linspace(0,1,121),np.linspace(1,0,121)[1:]]
    plastic=np.zeros(6);eqp=0.;rows=[];max_transverse_residual=0.
    for step,scale in enumerate(load):
        strain=np.zeros(6);strain[2]=.03*scale/thickness
        strain[3]=.01*scale/thickness/np.sqrt(2)
        if constraint=='free_lateral_stress':
            strain[:2]=rows[-1]['strain'][:2] if rows else 0.
            for iteration in range(40):
                stress,D,pnew,enew=response(strain,plastic,eqp,E,nu,Y,H)
                if np.linalg.norm(stress[:2])<1e-8:break
                strain[:2]-=np.linalg.solve(D[:2,:2],stress[:2])
            else:raise RuntimeError('local plane-stress reduction failed')
            max_transverse_residual=max(max_transverse_residual,float(np.linalg.norm(stress[:2])))
        stress,D,pnew,enew=response(strain,plastic,eqp,E,nu,Y,H)
        q=float(np.sqrt(1.5*np.dot(PD@stress,PD@stress)))
        rows.append(dict(step=step,scale=scale,normal_jump_mm=.03*scale,shear_jump_mm=.01*scale,
            strain=strain.copy(),stress=stress.copy(),plastic=pnew.copy(),eqp=enew,
            VM_MPa=q,maximum_principal_MPa=float(principal(stress).max()),
            mean_stress_MPa=float(stress[:3].mean()),delta_eqp=enew-eqp,
            yield_consistency_error_MPa=max(0.,q-Y-H*enew)))
        plastic,eqp=pnew,enew
    return rows,max_transverse_residual


def evaluate(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cases=[];all_rows=[];E=205000.;nu=.29;t=1.2;G=E/(2*(1+nu));K=E/(3*(1-2*nu))
    for constraint in ('free_lateral_stress','restrained_lateral_strain'):
        for Y in (85.,105.,210.):
            for factor in (0.,.005,.02):
                H=factor*E;rows,residual=run_path(constraint,Y,H)
                name=f'{constraint}-Y{Y:g}-H{factor:g}'
                np.savez_compressed(output/f'{name}.npz',
                    strain=np.array([r['strain'] for r in rows]),
                    stress_Mandel_MPa=np.array([r['stress'] for r in rows]),
                    plastic_Mandel=np.array([r['plastic'] for r in rows]),
                    eqp=np.array([r['eqp'] for r in rows]),
                    normal_jump_mm=np.array([r['normal_jump_mm'] for r in rows]),
                    shear_jump_mm=np.array([r['shear_jump_mm'] for r in rows]))
                cases.append(dict(name=name,constraint=constraint,yield_MPa=Y,hardening_MPa=H,
                    peak_VM_MPa=max(r['VM_MPa'] for r in rows),
                    peak_principal_MPa=max(r['maximum_principal_MPa'] for r in rows),
                    maximum_eqp=max(r['eqp'] for r in rows),
                    maximum_yield_consistency_error_MPa=max(r['yield_consistency_error_MPa'] for r in rows),
                    maximum_free_lateral_stress_residual_MPa=residual,
                    zero_jump_return_stress_Mandel_MPa=rows[-1]['stress'].tolist()))
                for r in rows:
                    all_rows.append(dict(case=name,**{k:v for k,v in r.items() if k not in ('strain','stress','plastic')},
                        normal_traction_MPa=r['stress'][2],shear_traction_MPa=r['stress'][3]/np.sqrt(2)))
    # Independent consistent-tangent check at a mixed plastic state.
    eps=np.array([-.0003,-.0002,.005,.002,.001,0.]);zero=np.zeros(6)
    stress,D,_,_=response(eps,zero,0,E,nu,105,.005*E)
    h=1e-8;finite=np.column_stack([(response(eps+h*np.eye(6)[i],zero,0,E,nu,105,.005*E)[0]-
        response(eps-h*np.eye(6)[i],zero,0,E,nu,105,.005*E)[0])/(2*h) for i in range(6)])
    tangent_error=float(np.linalg.norm(D-finite)/np.linalg.norm(finite))
    report=dict(scope='cold material-point constitutive comparison, not actual weld/service load or failure qualification',
        thickness_mm=t,E_MPa=E,nu=nu,
        normal_free_lateral_stiffness_N_mm3=E/t,
        normal_restrained_lateral_stiffness_N_mm3=(K+4*G/3)/t,
        shear_stiffness_N_mm3=G/t,legacy_scalar_stiffness_N_mm3=62500.,
        source=dict(url='https://www.specialmetals.com/documents/technical-bulletins/nickel-200.pdf',
            elastic='Table4, annealed wrought Ni200, 26C E205GPa/nu0.29',
            yield_basis='Table5 annealed tubing85..210MPa and rod/bar105..210MPa; comparison only',
            applicability='wrought material differs from first-layer79.71..89.66%Ni,0.374..0.738%C weld deposit'),
        hardening_basis='0,0.005E,0.02E explicit engineering sensitivity; not measured or supplier-qualified',
        imposed_jump_history=dict(normal_max_mm=.03,shear_max_mm=.01,
            return_condition='prescribed jumps return to zero; this is not unloading to zero traction'),
        tangent_relative_error=tangent_error,
        constitutive_implementation_pass=tangent_error<1e-6 and all(c['maximum_yield_consistency_error_MPa']<1e-7 for c in cases),
        cases=cases,connection_strength_pass=False,global_stiffness_feedback_complete=False,
        missing=['same-process diluted Ni99 temperature-dependent plastic law',
            'first QT/Ni PMZ geometry and tensile/fracture properties',
            'root Ni99 remelting and both-side fused geometry',
            'local model driven by actual manufacturing-state boundary displacements',
            'global re-equilibration of the revised nonlinear connection law'])
    (output/'diagnostic.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    with (output/'paths.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(all_rows[0]));writer.writeheader();writer.writerows(all_rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
    for constraint,color in [('free_lateral_stress','#167c80'),('restrained_lateral_strain','#ba5038')]:
        rows,_=run_path(constraint,105,.005*E)
        axes[0].plot([r['normal_jump_mm']*1000 for r in rows],[r['stress'][2] for r in rows],color=color,label=constraint.replace('_',' '))
        axes[1].plot([r['eqp']*100 for r in rows],[r['maximum_principal_MPa'] for r in rows],color=color)
    axes[0].plot([0,30],[0,62500*.03],'--',color='#64748b',label='legacy scalar elastic tie')
    axes[0].set(xlabel='Normal jump (micrometre)',ylabel='Normal traction (MPa)',title='Ni200 comparison parameters; Y=105 MPa')
    axes[0].legend(fontsize=8)
    axes[1].set(xlabel='Accumulated equivalent plastic strain (%)',ylabel='Maximum principal stress (MPa)',title='Lateral restraint retains hydrostatic tension')
    for ax in axes:ax.grid(alpha=.2)
    fig.savefig(output/'layer-response.png',dpi=180);plt.close(fig)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    r=evaluate(p.parse_args().output)
    print(json.dumps({k:r[k] for k in ('constitutive_implementation_pass','tangent_relative_error','normal_free_lateral_stiffness_N_mm3','normal_restrained_lateral_stiffness_N_mm3','shear_stiffness_N_mm3','connection_strength_pass')},indent=2))
