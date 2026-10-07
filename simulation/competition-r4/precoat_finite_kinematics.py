"""Finite Hencky kinematics for the existing precoat manufacturing replay.

E=log(C)/2, P=F*Dlog(C)[T]. T is the work-conjugate Hencky stress,
not an unrotated Cauchy stress. The consistent tangent includes both the
material return-map tangent and the second derivative of log(C).
Basis: Lewandowski et al., CMAME414(2023)116101, sections2--3.
The integral representation avoids divided differences at repeated stretches.
"""
import numpy as np
from numpy.polynomial.legendre import leggauss


KELVIN=np.zeros((6,3,3))
KELVIN[:3,range(3),range(3)]=np.eye(3)
for k,(i,j) in enumerate([(1,2),(0,2),(0,1)],3):
    KELVIN[k,i,j]=KELVIN[k,j,i]=1/np.sqrt(2)
PV=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3
PD=np.eye(6)-PV


def tensor(values):return np.einsum('...k,kij->...ij',values,KELVIN)
def kelvin(values):return np.einsum('...ij,kij->...k',values,KELVIN)


def logarithmic_strain(F):
    C=np.einsum('eki,ekj->eij',F,F)
    eigen,Q=np.linalg.eigh(C)
    if np.any(eigen<=0):raise ValueError('Finite material configuration has a singular stretch')
    E=np.einsum('eia,ea,eja->eij',Q,.5*np.log(eigen),Q)
    return kelvin(E),eigen,Q


def isotropic_elastic_response(F,g,eigen,Q,G,bulk,reference_scalar,expansion):
    """Exact spectral tangent for the unplastified isotropic-reference cells.

    This is the same finite energy, not a small-strain submodel. It avoids
    numerical log Hessian integration over the cold, elastic bulk of the seat.
    """
    strain=.5*np.log(eigen)-reference_scalar[:,None]-expansion[:,None]
    lame=bulk-2*G/3
    T=2*G[:,None]*strain+lame[:,None]*strain.sum(axis=1)[:,None]
    Se=T/eigen
    S=np.einsum('eia,ea,eja->eij',Q,Se,Q)
    P=np.einsum('eij,ejk->eik',F,S)
    force=np.einsum('eij,enj->eni',P,g).reshape(len(F),12)
    Cauchy=np.einsum('eij,ekj->eik',P,F)/np.linalg.det(F)[:,None,None]
    r=np.einsum('eij,ejk->eik',F,Q)
    s=np.einsum('eni,eij->enj',g,Q)
    DC=(np.einsum('eni,eaj->enaij',s,r)+np.einsum('eai,enj->enaij',r,s)).reshape(len(F),12,3,3)
    a=eigen[:,:,None];b=eigen[:,None,:];z=(a-b)/b
    divided=np.divide(np.log1p(z),z,out=np.ones_like(z),where=z!=0)/b
    off=G[:,None,None]*divided/a-T[:,None,:]/(a*b)
    off=.5*(off+off.transpose(0,2,1))
    diagonal=(G[:,None,None]*np.eye(3)+lame[:,None,None]/2)/(a*b)
    diagonal[:,range(3),range(3)]-=T/eigen**2
    dS=off[:,None]*DC
    dS[:,:,range(3),range(3)]=np.einsum('eij,enj->eni',diagonal,np.diagonal(DC,axis1=2,axis2=3))
    K=np.einsum('eik,emkl,enl->enim',r,dS,s).reshape(len(F),12,12)
    first=np.einsum('eni,eij,emj->enm',g,S,g)
    K+=(first[:,:,None,:,None]*np.eye(3)[None,None,:,None,:]).reshape(len(F),12,12)
    return force,K,kelvin(Cauchy)


def response(F,g,reference,plastic,eqp,expansion,G,bulk,Y,H,tangent=True,quadrature_order=0,elastic_shortcut=True):
    """Return local nodal force, exact tangent, Cauchy stress and plastic flow.

    All tensors and g are in the original material reference. The caller
    multiplies nodal forces/tangents by the actual coherent reference volume.
    """
    J=np.linalg.det(F)
    if np.any(J<=0):raise ValueError('Occupied coherent material has nonpositive detF')
    E,eigen,Q=logarithmic_strain(F)
    elastic=E-reference-plastic
    elastic[:,:3]-=expansion[:,None]
    dev=elastic@PD;shear=2*G[:,None]*dev
    equivalent=np.sqrt(1.5*np.sum(shear*shear,axis=1))
    excess=np.maximum(0.,equivalent-Y-H*eqp)
    dl=excess/(3*G+H)
    direction=1.5*shear/np.maximum(equivalent[:,None],1e-30)
    beta=1-3*G*dl/np.maximum(equivalent,1e-30)
    stress_H=shear*beta[:,None]+3*bulk[:,None]*(elastic@PV)
    stress_tensor=tensor(stress_H)
    if tangent and elastic_shortcut:
        isotropic=np.all(reference[:,:3]==reference[:,:1],axis=1)&np.all(reference[:,3:]==0,axis=1)
        shortcut=isotropic&np.all(plastic==0,axis=1)&(dl==0)
        if shortcut.any():
            force=np.zeros((len(F),12));local_tangent=np.zeros((len(F),12,12));cauchy=np.zeros((len(F),6))
            force[shortcut],local_tangent[shortcut],cauchy[shortcut]=isotropic_elastic_response(
                F[shortcut],g[shortcut],eigen[shortcut],Q[shortcut],G[shortcut],bulk[shortcut],reference[shortcut,0],expansion[shortcut])
            remaining=~shortcut
            if remaining.any():
                other=response(F[remaining],g[remaining],reference[remaining],plastic[remaining],eqp[remaining],expansion[remaining],
                    G[remaining],bulk[remaining],Y[remaining],H[remaining],tangent,quadrature_order,False)
                force[remaining],local_tangent[remaining],cauchy[remaining]=other[:3]
            potential=G*np.sum(dev*dev,axis=1)+.5*bulk*np.sum(elastic[:,:3],axis=1)**2-excess**2/(2*(3*G+H))
            return force,local_tangent,cauchy,dl,direction,potential,stress_H
    # Exact first log derivative, including equal/repeated stretches. log1p
    # retains precision when the two eigenvalues differ only by roundoff.
    a=eigen[:,:,None];b=eigen[:,None,:];z=(a-b)/b
    divided=np.divide(np.log1p(z),z,out=np.ones_like(z),where=z!=0)/b
    basis=np.einsum('eia,kij,ejb->ekab',Q,KELVIN,Q)
    L=np.einsum('ekij,eij,elij->ekl',basis,divided,basis)
    S=tensor(np.einsum('eij,ej->ei',L,stress_H))
    if tangent:
        DC=np.empty((len(F),12,3,3))
        for node in range(4):
            for component in range(3):
                a=np.einsum('ei,ej->eij',g[:,node],F[:,component])
                DC[:,3*node+component]=a+a.transpose(0,2,1)
        geometric=np.zeros((len(F),12,12))
    if tangent:
        if quadrature_order:
            groups=[(np.ones(len(F),bool),quadrature_order)]
        else:
            near=(eigen.min(axis=1)>=.8)&(eigen.max(axis=1)<=1.25)
            # The actual7.75s failed trial reached squared stretches0.0015
            # and656. Its16-point Hessian differs from the resolved integral;
            #128/256-point comparison closes that local derivative. Resolve
            # the log integral there without changing its force, material,
            # thermal path or accepting the distorted trial as manufacturing.
            extreme=(eigen.min(axis=1)<.05)|(eigen.max(axis=1)>20)
            broad=((eigen.min(axis=1)<.2)|(eigen.max(axis=1)>5))&~extreme
            groups=[(near,4),(~near&~broad&~extreme,16),(broad,64),(extreme,128)]
        for selected,order in groups:
            if not np.any(selected):continue
            points,weights=leggauss(order);second_sum=np.zeros((selected.sum(),12,12))
            for s,w in zip((points+1)/2,weights/2):
                A=np.einsum('eia,ea,eja->eij',Q[selected],1/((1-s)*eigen[selected]+s),Q[selected])
                ATA=np.einsum('eij,ejk,ekl->eil',A,stress_tensor[selected],A)
                a=np.einsum('eij,enjk,ekl->enil',ATA,DC[selected],A)
                second=np.einsum('enij,emji->enm',a,DC[selected])
                second_sum-=.5*w*(1-s)*(second+second.transpose(0,2,1))
            geometric[selected]=second_sum
    P=np.einsum('eij,ejk->eik',F,S)
    force=np.einsum('eij,enj->eni',P,g).reshape(len(F),12)
    cauchy=np.einsum('eij,ekj->eik',P,F)/J[:,None,None]
    if not tangent:local_tangent=None
    else:
        dE=.5*np.einsum('eij,enj->ein',L,kelvin(DC))
        yielded=dl>0
        material=(2*G[:,None,None]*beta[:,None,None]*PD+3*bulk[:,None,None]*PV)
        coefficient=np.zeros(len(F))
        coefficient[yielded]=4*G[yielded]**2*(dl[yielded]/np.maximum(equivalent[yielded],1e-30)-1/(3*G[yielded]+H[yielded]))
        material+=coefficient[:,None,None]*np.einsum('ei,ej->eij',direction,direction)
        # The spectral log Hessian above supplies the nonlinear geometric term.
        a=np.einsum('eni,eij,emj->enm',g,S,g)
        geometric+=(a[:,:,None,:,None]*np.eye(3)[None,None,:,None,:]).reshape(len(F),12,12)
        local_tangent=np.einsum('ein,eij,ejm->enm',dE,material,dE)+geometric
    potential=G*np.sum(dev*dev,axis=1)+.5*bulk*np.sum(elastic[:,:3],axis=1)**2-excess**2/(2*(3*G+H))
    return force,local_tangent,kelvin(cauchy),dl,direction,potential,stress_H
