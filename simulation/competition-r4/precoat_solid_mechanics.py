"""Solid-state manufacturing demand from the saved deposition/temperature path.

Existing solid reference and plastic strain are retained by solid volume. New
coherent material retains its current shear configuration; its specific-volume
reference follows the carried mass and cold density of the CAD envelope.
Liquid carries no shear in this free-surface model.
This is a material-reference demand calculation, not a PMZ capacity assignment.
"""
import json
import numpy as np
import yaml
from scipy.sparse import coo_matrix, bmat, csr_matrix, kron, eye, diags
from scipy.sparse.csgraph import connected_components
import pypardiso
from run_candidate_solver import operators
from mma_literature_profile import ROOT


class SolidMechanics:
    def __init__(self,x,e,material,volume,thermal_input,phase_method='exact_P1',interface_policy='chronological',kinematics='small_strain'):
        self.kinematics=kinematics
        self.interface_policy=interface_policy;self.source_nodes=len(x)
        self.deposition_material_ids=thermal_input.get('deposition_material_ids',[3])
        self.preexisting_material_ids=thermal_input.get('preexisting_material_ids',[1])
        self.birth_regions=[]
        if phase_method=='exact_P1':
            from mma_conservative_birth import ConservativeBirth
            sector=np.round(np.arctan2(x[e].mean(axis=1)[:,1],x[e].mean(axis=1)[:,0])/(np.pi/4)).astype(int)%8
            rho=np.array([row['nominal_properties_20c']['density_kg_m3'] for row in thermal_input['materials']])[material]*1e-9
            descriptions=thermal_input.get('deposition_regions')
            if descriptions is None:
                descriptions=[dict(material_id=3,wing=int(wing),radius_mm=71.98,
                    growth_rise_length_mm=thermal_input['growth_rise_length_mm'],angle_offset_rad=wing*np.pi/4)
                    for wing in np.unique(sector[material==3])]
            for description in descriptions:
                select=material==description['material_id']
                if 'wing' in description:select&=sector==description['wing']
                # The original eight-wing constructor has separated envelopes.
                # A second-layer track shares nodes with surviving CI and its
                # adjacent track; do not overwrite those front coordinates.
                birth_material=material if descriptions[0].get('wing') is not None else np.where(np.isin(material,self.preexisting_material_ids),1,0)
                region=ConservativeBirth(x,e,birth_material,volume,rho,radius=description['radius_mm'],
                    rise_length=description['growth_rise_length_mm'],deposit_mask=select,
                    angle_offset=description.get('angle_offset_rad',0.))
                self.birth_regions.append(region)
        self.thermal_origin=np.arange(len(x));self.current_bond_pairs=np.empty((0,2),int)
        if interface_policy=='chronological':
            source_faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
            owners=np.tile(np.arange(len(e)),4)
            faces,first,inverse,count=np.unique(source_faces,axis=0,return_index=True,return_inverse=True,return_counts=True)
            last=np.zeros(len(count),int);np.maximum.at(last,inverse,np.arange(len(source_faces)))
            adj=np.c_[owners[first],owners[last]]
            select=(count==2)&(material[adj[:,0]]!=material[adj[:,1]])&np.any(np.isin(material[adj],self.deposition_material_ids),axis=1)
            self.fusion_faces=faces[select];self.fusion_adj=adj[select]
            face_points=x[self.fusion_faces]
            self.fusion_face_area=np.linalg.norm(np.cross(face_points[:,1]-face_points[:,0],face_points[:,2]-face_points[:,0]),axis=1)/2
            self.fused_faces=np.zeros(len(self.fusion_faces),bool)
            self.bonded_faces=np.zeros(len(self.fusion_faces),bool)
            mappings={};original_x=x.copy();e=e.copy()
            for material_id in self.deposition_material_ids:
                local_faces=self.fusion_faces[np.any(material[self.fusion_adj]==material_id,axis=1)]
                common=np.unique(local_faces);copied=np.arange(len(x),len(x)+len(common))
                duplicate=np.arange(self.source_nodes);duplicate[common]=copied;mappings[material_id]=duplicate
                e[material==material_id]=duplicate[e[material==material_id]]
                x=np.vstack([x,original_x[common]]);self.thermal_origin=np.r_[self.thermal_origin,common]
            face_pairs=[]
            for side in range(2):
                values=self.fusion_faces.copy()
                for material_id,mapping in mappings.items():
                    rows=material[self.fusion_adj[:,side]]==material_id;values[rows]=mapping[values[rows]]
                face_pairs.append(values)
            self.fusion_vertex_pairs=np.stack(face_pairs,axis=2)
        self.x,self.e,self.m,self.volume=x,e,material,volume
        self.phase_method=phase_method
        self.g,_,self.B,self.dof=operators(x,e,True)
        self.n=len(x);self.nd=3*self.n
        self.QT_node_mask=np.zeros(self.n,bool);self.QT_node_mask[np.unique(e[material==1])]=True
        self.rows=np.repeat(self.dof,12,axis=1).ravel()
        self.cols=np.tile(self.dof,(1,12)).ravel()
        self.pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3
        self.pd=np.eye(6)-self.pv
        self.reference_input=yaml.safe_load((ROOT/'project/precoat-mechanical-reference.yaml').read_text(encoding='utf8'))
        fusion=thermal_input['materials']
        self.solidus=np.array([row['fusion_enthalpy']['solidus_C'] for row in fusion])[material]
        self.liquidus=np.array([row['fusion_enthalpy']['liquidus_C'] for row in fusion])[material]
        self.cold_density_kg_mm3=np.array([row['nominal_properties_20c']['density_kg_m3'] for row in fusion])[material]*1e-9
        self.material_mass_kg=self.cold_density_kg_mm3*volume
        self.fusion_threshold_C=np.max(self.liquidus[self.fusion_adj],axis=1) if interface_policy=='chronological' else None
        self.u=np.zeros(self.nd)
        self.plastic=np.zeros((len(e),6));self.eqp=np.zeros(len(e));self.reference=np.zeros((len(e),6))
        self.solid_weight=np.isin(material,self.preexisting_material_ids).astype(float)
        self.stress=np.zeros((len(e),6));self.remelted=np.zeros(len(e),bool)
        initial=float(thermal_input['cold_start_C'])
        expansion=self.thermal_strain(np.full(len(e),initial))
        # Uniform initial preheat of the unloaded QT seat is compatible with
        # a uniform thermal expansion; it does not create residual stress.
        self.u.reshape(-1,3)[:]=expansion[material==1][0]*(x-x[np.unique(e[material==1])].mean(axis=0))
        self.previous_temperature=np.full(len(e),initial)
        self.previous_actual_temperature=np.full(self.n,initial)
        self.previous_occupation=np.isin(material,self.preexisting_material_ids).astype(float)
        self.engine=pypardiso.PyPardisoSolver(mtype=11)
        self.history=[];self.birth_audits=[];self.maximum_residual=0.;self.total_iterations=0
        self.iteration_history=[];self.failed_iteration=None

    def strain_at(self,vector,active=None):
        if self.kinematics=='small_strain':return np.einsum('eij,ej->ei',self.B,vector[self.dof])
        from precoat_finite_kinematics import logarithmic_strain
        if active is None:active=self.solid_weight>1e-12
        result=np.zeros((len(self.e),6))
        F=np.eye(3)+np.einsum('eij,eik->ejk',vector.reshape(-1,3)[self.e[active]],self.g[active])
        if np.any(np.linalg.det(F)<=0):raise ValueError('Coherent material geometry has nonpositive detF')
        result[active]=logarithmic_strain(F)[0]
        return result

    def thermal_strain(self,temperatures):
        result=np.zeros_like(temperatures)
        qt=self.reference_input['QT_reference'];ni=self.reference_input['high_Ni_reference']
        for select,row in [(self.m==1,qt),(np.isin(self.m,[3,4,5]),ni)]:
            t=np.array(row['temperatures_C']);a=np.array(row['mean_alpha_20C_per_K'])
            q=temperatures[select]
            coefficient=np.interp(q,t,a)
            if row is ni:
                slope=(16.7e-6-a[-1])/100
                coefficient=np.where(q>900,a[-1]+slope*(q-900),coefficient)
            result[select]=coefficient*(q-20)
        return result

    def material_properties(self,temperatures):
        E=np.empty(len(self.e));Y=E.copy();nu=E.copy();H=np.zeros(len(self.e))
        qt=self.reference_input['QT_reference'];ni=self.reference_input['high_Ni_reference']
        for select,row in [(self.m==1,qt),(np.isin(self.m,[3,4,5]),ni)]:
            q=temperatures[select];knots=np.array(row['temperatures_C']);values=np.array(row['E_GPa'])
            modulus=np.interp(q,knots,values)
            if row is ni:
                modulus=np.where(q>knots[-1],values[-1]+(values[-1]-values[-2])/(knots[-1]-knots[-2])*(q-knots[-1]),modulus)
                yield_stress=np.interp(q,row['yield_temperatures_C'],row['yield_MPa'])
                # Table4b supplies Rp1.0-Rp0.2=25MPa at the saved points.
                # The0.8% offset interval implies a3125MPa plastic secant.
                hardening=np.full_like(q,3125.)
                scale=np.where(q>600,(self.liquidus[select]-q)/(self.liquidus[select]-600),1.)
                hardening*=scale
                yield_stress=np.where(q>600,40*scale,yield_stress)-.002*hardening
                H[select]=hardening
            else:
                yield_stress=np.interp(q,knots,row['source_yield_MPa'])*row['yield_grade_scale']
            if np.any(modulus<=0) or np.any(yield_stress < -1e-8):
                raise ValueError('Solid material reference queried beyond its physical temperature interval')
            E[select]=1000*modulus;Y[select]=yield_stress;nu[select]=row['poisson']
        return E,Y,nu,H

    def rigid_gauges(self,occupied,active):
        # Each disconnected solid body gets six rigid coordinate gauges.
        # The constraints add no contact stiffness or external process load.
        edges=[]
        for a,b in [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]:
            edges.append(self.e[active][:,[a,b]])
        pairs=np.vstack(edges)
        raw_graph=coo_matrix((np.ones(2*len(pairs)),(np.r_[pairs[:,0],pairs[:,1]],np.r_[pairs[:,1],pairs[:,0]])),shape=(self.n,self.n)).tocsr()
        _,support_labels=connected_components(raw_graph,directed=False)
        if len(self.current_bond_pairs):pairs=np.vstack([pairs,self.current_bond_pairs])
        graph=coo_matrix((np.ones(2*len(pairs)),(np.r_[pairs[:,0],pairs[:,1]],np.r_[pairs[:,1],pairs[:,0]])),shape=(self.n,self.n)).tocsr()
        _,labels=connected_components(graph,directed=False)
        row_ids=[];col_ids=[];values=[];row=0
        for label in np.unique(labels[occupied]):
            nodes=occupied[labels[occupied]==label]
            if len(nodes)<4:raise RuntimeError('Solid component lacks a tetrahedral support')
            positions=self.x if self.kinematics=='small_strain' else self.x+self.u.reshape(-1,3)
            p=positions[nodes]-positions[nodes].mean(axis=0)
            basis=np.zeros((3*len(nodes),6));basis.reshape(-1,3,6)[:,:,:3]=np.eye(3)
            for j in range(3):basis[:,j+3]=np.cross(np.eye(3)[j],p).ravel()
            Q,_=np.linalg.qr(basis)
            ids=(3*nodes[:,None]+np.arange(3)).ravel()
            for j in range(6):
                row_ids.extend([row]*len(ids));col_ids.extend(ids);values.extend(Q[:,j]);row+=1
        return coo_matrix((values,(row_ids,col_ids)),shape=(row,self.nd)).tocsr(),row//6,labels,support_labels

    def advance(self,time_s,temperature,occupation,fused_face_mask=None,geometry_cut_moments=None):
        if len(temperature)==self.source_nodes:temperature=temperature[self.thermal_origin]
        local=temperature[self.e]
        # Exact P1 solid cuts or constant-stress-cell phase fractions are
        # alternative discretizations of the saved temperature field. The
        # cell method uses its actual mean and keeps all non-liquid volume.
        # Neither method clips nodal temperatures to a constitutive interval.
        from mma_conservative_birth import clipped_moments,intersected_moments,multiple_cut_moments
        moments=np.zeros_like(local)
        cold=local.max(axis=1)<=self.solidus
        moments[cold]=.25
        crossing=np.flatnonzero((local.min(axis=1)<self.solidus)&~cold)
        for k in crossing:moments[k]=clipped_moments(local[k],self.solidus[k])
        if geometry_cut_moments is not None:
            if np.any(local.max(axis=1)>=self.solidus):raise ValueError('Cold machining moments require fully solid temperature fields')
            moments=np.array(geometry_cut_moments,copy=True)
        elif self.phase_method=='exact_P1':
            # Solid must be in metal that actually exists. Multiplying separate
            # birth and cold fractions includes cold unborn filler and creates
            # false solid islands. Intersect both affine cuts on the parent.
            for region in self.birth_regions:
                target=float(region.weights@occupation[region.indices])
                if target<=0:moments[region.indices]=0.;continue
                if target>=region.total_mass_kg*(1-1e-10):continue
                _,_,_,front=region.at_mass(target)
                for j,k in enumerate(region.indices):
                    if occupation[k]<=0 or local[k].min()>=self.solidus[k]:moments[k]=0.
                    elif occupation[k]<1-1e-10:moments[k]=intersected_moments(region.values[j],front,local[k],self.solidus[k])
        solid_fraction=moments.sum(axis=1)
        if self.phase_method=='cell_mean':
            mean=local.mean(axis=1)
            solid_fraction=1-np.clip((mean-self.solidus)/(self.liquidus-self.solidus),0,1)
        weight=solid_fraction if self.phase_method=='exact_P1' else occupation*solid_fraction
        self.remelted|=(self.m==1)&(local.max(axis=1)>=self.liquidus)
        active=weight>1e-12
        representative=np.arange(self.n)
        previous_representative=np.arange(self.n)
        previous_representative[self.current_bond_pairs[:,1]]=self.current_bond_pairs[:,0]
        previous_pairs=self.current_bond_pairs.copy()
        if self.interface_policy=='chronological':
            if fused_face_mask is not None:self.fused_faces|=fused_face_mask
            coherent_limit=np.min(self.solidus[self.fusion_adj],axis=1)
            # A discrete facet enters the strong solid-bond branch after its
            # entire recorded P1 face is coherent on both sides. This avoids
            # transmitting through its still-liquid vertices; the facet timing
            # remains a response to check with the retained-state mesh.
            coherent_face=temperature[self.fusion_faces].max(axis=1)<coherent_limit
            bonded=self.fused_faces&np.all(active[self.fusion_adj],axis=1)&coherent_face
            self.bonded_faces=bonded
            pairs=np.unique(self.fusion_vertex_pairs[bonded].reshape(-1,2),axis=0)
            def root(node):
                while representative[node]!=node:
                    representative[node]=representative[representative[node]];node=representative[node]
                return node
            for a,b in pairs:
                A,B=root(a),root(b)
                if A!=B:representative[max(A,B)]=min(A,B)
            for node in np.unique(pairs):representative[node]=root(node)
            copies=np.flatnonzero(representative!=np.arange(self.n))
            self.current_bond_pairs=np.c_[representative[copies],copies]
        old_active=self.solid_weight>1e-12
        retained_reference=self.reference.copy()
        retained_strain=self.strain_at(self.u,old_active)
        occupied=np.unique(self.e[active]);old_occupied=np.unique(self.e[old_active])
        gauges,components,solid_component,support_component=self.rigid_gauges(occupied,active)
        added=np.setdiff1d(occupied,old_occupied)
        if len(added):
            from affine_interface import birth_continuation
            for label in np.unique(support_component[added]):
                local_added=added[support_component[added]==label]
                local_hosts=old_occupied[support_component[old_occupied]==label]
                if len(local_hosts)<4:
                    # The prescribed liquid envelope may first become a free
                    # coherent Ni island. Its position comes from that retained
                    # envelope pose, not extrapolation from a separate QT body.
                    self.birth_audits.append(dict(time_s=time_s,kind='new coherent body retains prescribed liquid-envelope pose',
                        solid_component=int(label),new_nodes=len(local_added),old_same_body_hosts=len(local_hosts),
                        existing_material_state_reset=False))
                    continue
                try:interpolation,audit=birth_continuation(self.x,local_hosts,local_added)
                except RuntimeError as error:
                    self.birth_audits.append(dict(time_s=time_s,kind='new coherent nodes retain prescribed liquid-envelope pose',
                        solid_component=int(label),new_nodes=len(local_added),reason=str(error),
                        changed_extension_quality_limit=False,existing_material_state_reset=False))
                    continue
                for node,(hosts,weights) in zip(local_added,interpolation):
                    self.u.reshape(-1,3)[node]=weights@self.u.reshape(-1,3)[hosts]
                self.birth_audits.append(dict(time_s=time_s,kind='same-body coherent-node predictor',**audit))
        solid_T=np.sum(local*moments,axis=1)/np.maximum(solid_fraction,1e-30)
        if self.phase_method=='cell_mean':solid_T=local.mean(axis=1)
        solid_T=np.where(active,solid_T,20.)
        if self.phase_method=='exact_P1' and np.any(solid_T>self.solidus+1e-7):raise RuntimeError('Coherent solid temperature exceeds the cut solidus')
        expansion=self.thermal_strain(solid_T)
        if self.kinematics=='finite_Hencky':expansion=np.log1p(expansion)
        strain_now=self.strain_at(self.u,active)
        retained=np.minimum(weight,self.solid_weight)
        retained_moments=moments.copy()
        if self.phase_method=='exact_P1' and geometry_cut_moments is None:
            old_local=self.previous_actual_temperature[self.e]
            retained=np.zeros_like(weight);retained_moments=np.zeros_like(moments)
            survivors=(weight>1e-12)&(self.solid_weight>1e-12)
            old_full=old_local.max(axis=1)<=self.solidus
            new_full=local.max(axis=1)<=self.solidus
            existing=survivors&np.isin(self.m,self.preexisting_material_ids)
            retained_moments[existing&old_full]=moments[existing&old_full]
            for k in np.flatnonzero(existing&new_full&~old_full):
                retained_moments[k]=clipped_moments(old_local[k],self.solidus[k])
            for k in np.flatnonzero(existing&~old_full&~new_full):
                retained_moments[k]=multiple_cut_moments([old_local[k],local[k]],[self.solidus[k],self.solidus[k]])
            for region in self.birth_regions:
                old_mass=float(region.weights@self.previous_occupation[region.indices])
                if old_mass<=0:continue
                full_birth=old_mass>=region.total_mass_kg*(1-1e-10)
                old_front=None if full_birth else region.at_mass(old_mass)[3]
                for j,k in enumerate(region.indices):
                    if not survivors[k]:continue
                    if new_full[k]:
                        retained_moments[k]=clipped_moments(old_local[k],self.solidus[k]) if full_birth else intersected_moments(region.values[j],old_front,old_local[k],self.solidus[k])
                        continue
                    if full_birth and old_full[k]:retained_moments[k]=moments[k];continue
                    values=[old_local[k],local[k]];levels=[self.solidus[k],self.solidus[k]]
                    if not full_birth:values.insert(0,region.values[j]);levels.insert(0,old_front)
                    retained_moments[k]=multiple_cut_moments(values,levels)
            retained=retained_moments.sum(axis=1)
            upper=np.minimum(weight,self.solid_weight)
            if np.any(retained>upper+1e-9):raise RuntimeError('Actual surviving volume exceeds old/new material volume')
            self.birth_audits.append(dict(time_s=time_s,kind='actual surviving material intersection',
                additional_removed_volume_vs_scalar_min_mm3=float(self.volume@(upper-retained)),
                retained_volume_mm3=float(self.volume@retained),material_history_reset=False))
        # Two equal scalar volumes can exchange material across a moving
        # thermal front. Count actual new solid, not just a net volume rise.
        added_weight=np.maximum(weight-retained,0.)
        removed_weight=np.maximum(self.solid_weight-retained,0.)
        ratio=np.divide(retained,weight,out=np.ones_like(weight),where=active)
        added_moments=moments-retained_moments
        if self.phase_method=='exact_P1' and added_moments.min()<-1e-9:
            raise RuntimeError('New coherent-domain moments became negative')
        new_solid_T=solid_T.copy();new_solid=(added_weight>1e-12)&(self.phase_method=='exact_P1')
        new_solid_T[new_solid]=np.sum(local[new_solid]*added_moments[new_solid],axis=1)/added_weight[new_solid]
        moment_roundoff=128*np.finfo(float).eps*np.sum(abs(local[new_solid])*(abs(moments[new_solid])+abs(retained_moments[new_solid])),axis=1)/added_weight[new_solid]
        if np.any(new_solid_T[new_solid]>self.solidus[new_solid]+np.maximum(1e-7,moment_roundoff)):
            raise RuntimeError('New coherent-domain temperature exceeds its actual solidus beyond moment-subtraction roundoff')
        new_expansion=self.thermal_strain(new_solid_T)
        self.plastic[active]*=ratio[active,None];self.eqp[active]*=ratio[active]
        self.solid_weight=weight
        E,Y,nu,H=self.material_properties(solid_T)
        G=E/(2*(1+nu));bulk=E/(3*(1-2*nu))
        trial=self.u.copy()
        if self.interface_policy=='chronological':
            copies=self.current_bond_pairs[:,1]
            newly_joined=copies[representative[copies]!=previous_representative[copies]]
            if len(newly_joined):
                mismatch=self.u.reshape(-1,3)[newly_joined]-self.u.reshape(-1,3)[representative[newly_joined]]
                self.birth_audits.append(dict(time_s=time_s,kind='actual new coherent interface closure',
                    new_node_pairs=len(newly_joined),maximum_preclosure_pair_displacement_mm=float(np.linalg.norm(mismatch,axis=1).max()),
                    mean_preclosure_pair_displacement_mm=float(np.linalg.norm(mismatch,axis=1).mean()),surviving_material_state_reset=False))
                if self.kinematics=='finite_Hencky':
                    # An unrestrained coherent body can undergo a rigid motion
                    # into its new attachment. Use that objective motion as a
                    # Newton initial guess rather than straining only the
                    # duplicated face vertices. Already connected bodies are
                    # never repositioned; all non-rigid mismatch remains.
                    old_edges=np.vstack([self.e[old_active][:,[a,b]] for a,b in [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]])
                    if len(previous_pairs):old_edges=np.vstack([old_edges,previous_pairs])
                    old_graph=coo_matrix((np.ones(2*len(old_edges)),(np.r_[old_edges[:,0],old_edges[:,1]],np.r_[old_edges[:,1],old_edges[:,0]])),shape=(self.n,self.n)).tocsr()
                    _,old_labels=connected_components(old_graph,directed=False)
                    for label in np.unique(old_labels[newly_joined]):
                        contact=newly_joined[old_labels[newly_joined]==label]
                        target=representative[contact]
                        if np.any(old_labels[target]==label):continue
                        raw_labels=np.unique(support_component[contact])
                        body=occupied[np.isin(support_component[occupied],raw_labels)]
                        inherited=np.intersect1d(body,old_occupied)
                        if len(np.unique(old_labels[inherited]))!=1:continue
                        positions=self.x+trial.reshape(-1,3)
                        p=positions[contact];q=positions[target]
                        pc=p.mean(axis=0);qc=q.mean(axis=0)
                        U,_,Vt=np.linalg.svd((p-pc).T@(q-qc))
                        correction=np.eye(3);correction[-1,-1]=np.linalg.det(U@Vt)
                        rotation=U@correction@Vt
                        updated=(positions[body]-pc)@rotation+qc
                        trial.reshape(-1,3)[body]=updated-self.x[body]
                        self.birth_audits.append(dict(time_s=time_s,kind='objective free-body interface initial guess',
                            moved_nodes=len(body),new_contact_nodes=len(contact),old_component=int(label),
                            maximum_remaining_pair_mismatch_mm=float(np.linalg.norm(updated[np.searchsorted(body,contact)]-q,axis=1).max()),
                            reference_or_plastic_history_reset=False,nonrigid_mismatch_solved_by_equilibrium=True))
            trial.reshape(-1,3)[copies]=trial.reshape(-1,3)[representative[copies]]
        extension_coordinates=self.x if self.kinematics=='small_strain' else self.x+trial.reshape(-1,3)
        # Outside-coherent-solid vertex freedoms of cut cells are extended
        # affinely from actual solid nodes. This removes vanishing-support
        # freedoms while preserving translation, rotation and linear strain.
        node_limit=np.zeros(self.n)
        np.maximum.at(node_limit,self.e[active].ravel(),np.repeat(self.solidus[active],4))
        present=occupied[temperature[occupied]<node_limit[occupied]]
        if self.phase_method=='cell_mean':
            # Full solid cells provide stable hosts for partial deposition and
            # mushy cells. All partial volumes remain in stiffness/internal
            # force; aggregation restricts only unsupported shape freedoms.
            stable=(weight>=1-1e-10)
            present=np.unique(self.e[stable])
        if self.interface_policy=='chronological':
            # QT has no invented hardening. Unsupported outside-solid vertex
            # freedoms of its small cut cells are extended from its own cold
            # body. Ni keeps its physical freedoms and source-based hardening.
            present=occupied[(~self.QT_node_mask[occupied])|(temperature[occupied]<node_limit[occupied])]
            present=np.unique(representative[present])
        # Melting can separate a newly coherent island from the seat. Its
        # interpolation must stay in its own solid body. A body without a
        # fully solid tetrahedron keeps its own nodal freedoms; attaching it
        # to another body's hosts would create an artificial restraint.
        for label in np.unique(support_component[occupied]):
            local_occupied=occupied[(support_component[occupied]==label)&(representative[occupied]==occupied)]
            if len(local_occupied) and not np.any(support_component[present]==label):
                present=np.union1d(present,local_occupied)
        independent_occupied=occupied[representative[occupied]==occupied]
        ghost=np.setdiff1d(independent_occupied,present)
        extension_plans=[]
        if len(ghost):
            from affine_interface import birth_continuation
            for label in np.unique(support_component[ghost]):
                local_ghost=ghost[support_component[ghost]==label]
                local_hosts=present[support_component[present]==label]
                try:
                    rows,extension_audit=birth_continuation(extension_coordinates,local_hosts,local_ghost)
                except RuntimeError as error:
                    # A thin isolated body may have no bounded extrapolation
                    # from its few full cells. Keep that body's complete real
                    # FE freedoms instead of crossing a liquid gap or widening
                    # the affine-patch quality criterion. Matrix scaling below
                    # resolves the resulting different physical support sizes.
                    local_occupied=independent_occupied[support_component[independent_occupied]==label]
                    present=np.union1d(present,local_occupied)
                    self.birth_audits.append(dict(time_s=time_s,kind='full physical body freedoms',solid_component=int(label),
                        reason=str(error),promoted_node_count=len(local_ghost),added_material_or_stiffness=False))
                    continue
                extension_plans.append((local_ghost,rows))
                self.birth_audits.append(dict(time_s=time_s,kind='coherent-solid cut extension',solid_component=int(label),**extension_audit))
        ghost=np.setdiff1d(independent_occupied,present)
        if not len(present):raise RuntimeError('No coherent solid interpolation hosts')
        mapping=np.full(self.n,-1,int);mapping[present]=np.arange(len(present))
        if self.interface_policy=='chronological':
            rrows=list(present);rcols=list(np.arange(len(present)));rvalues=[1.]*len(present)
            bonded_copies=occupied[representative[occupied]!=occupied]
            rrows.extend(bonded_copies);rcols.extend(mapping[representative[bonded_copies]]);rvalues.extend([1.]*len(bonded_copies))
        else:rrows=list(present);rcols=list(np.arange(len(present)));rvalues=[1.]*len(present)
        for local_ghost,rows in extension_plans:
            for node,(hosts,weights) in zip(local_ghost,rows):
                rrows.extend([int(node)]*len(hosts));rcols.extend(mapping[hosts]);rvalues.extend(weights)
        scalar_extension=coo_matrix((rvalues,(rrows,rcols)),shape=(self.n,len(present))).tocsr()
        extension=kron(scalar_extension,eye(3,format='csr'),format='csr')
        free=(3*present[:,None]+np.arange(3)).ravel()
        if self.kinematics=='finite_Hencky':
            saved_u=self.u;self.u=trial
            gauges,components,solid_component,support_component=self.rigid_gauges(occupied,active)
            self.u=saved_u
        C=gauges@extension
        # Restrict displacement INCREMENTS to the current coherent cut space.
        # Projecting the total inherited displacement into a different space
        # moves surviving material. A compensating eigenstrain preserves its
        # stress but cannot preserve its physical volume or position. Retain
        # the accepted P1 material geometry and apply the new affine extension
        # only to Newton increments. Actual new interface closure is imposed
        # separately below and keeps its physical strain demand.
        # Fix only the undetermined rigid increment. When melting separates
        # a body, forcing its total displacement to zero would translate it
        # away from its inherited position and strain it upon reconnection.
        # The existing pose is retained through split/join events.
        coordinate_origin=trial[free].copy()
        mapped_strain=np.einsum('eij,ej->ei',self.B,trial[self.dof])
        # Mesh volumes are cold mass-equivalent references. A new coherent
        # region loses liquid shear memory, but its specific volume is fixed
        # by the SAME reference mass/density used to construct that envelope.
        # Treating cold CAD as hot stress-free geometry would count thermal
        # contraction twice and produce a stress-free cold density above the
        # prescribed material density. Bulk equilibrium supplies thermal
        # expansion; only the new region's shear configuration is initialized.
        density_reference_trace=np.log(self.material_mass_kg/(self.cold_density_kg_mm3*self.volume))
        # Form the new coherent material reference BEFORE imposing actual
        # interface closure. The trial snap of duplicated interface vertices
        # is a joining displacement, not a stress-free deposition shape.
        # Absorbing that local jump into newly coherent cells locks in a
        # spurious shear eigenstrain and prevents the free body's rigid
        # translation from relaxing it. Surviving material remains unchanged.
        new_reference=strain_now@self.pd
        new_reference[:,:3]+=density_reference_trace[:,None]/3
        self.reference[active]=ratio[active,None]*retained_reference[active]+(1-ratio[active,None])*new_reference[active]
        transfer_error=float(abs(retained_reference-self.reference)[old_active&active&(added_weight<=1e-12)].max()) if np.any(old_active&active&(added_weight<=1e-12)) else 0.
        if transfer_error>1e-10:raise RuntimeError('Surviving material reference changed without new coherent volume')
        self.birth_audits.append(dict(time_s=time_s,kind='cut-space material state transfer',
            maximum_surviving_reference_tensor_change_without_new_solid=transfer_error,
            displacement_space_policy='retain accepted P1 geometry; current cut-space constrains Newton increments only; actual new interface closure retained',
            representation_only_reference_increment=0.,
            new_material_specific_volume_reference='trace=log(reference_mass/(rho20*reference_volume)); coherent shear uses current configuration; existing tensors retained',
            maximum_new_material_density_reference_trace=float(abs(density_reference_trace[new_solid]).max()) if np.any(new_solid) else 0.))
        def assemble(vector,tangent=True):
            if self.kinematics=='finite_Hencky':
                from precoat_finite_kinematics import response
                F=np.eye(3)+np.einsum('eij,eik->ejk',vector.reshape(-1,3)[self.e[active]],self.g[active])
                local_force,local_tangent,local_stress,increment,flow,*_=response(F,self.g[active],self.reference[active],
                    self.plastic[active],self.eqp[active],expansion[active],G[active],bulk[active],Y[active],H[active],tangent)
                stress=np.zeros_like(self.stress);stress[active]=local_stress
                dl=np.zeros(len(self.e));dl[active]=increment
                direction=np.zeros_like(self.plastic);direction[active]=flow
                force=np.bincount(self.dof[active].ravel(),weights=(local_force*(self.volume*weight)[active,None]).ravel(),minlength=self.nd)
                K=None
                if tangent:
                    elements=np.zeros((len(self.e),12,12));elements[active]=local_tangent*(self.volume*weight)[active,None,None]
                    K=coo_matrix((elements.ravel(),(self.rows,self.cols)),shape=(self.nd,self.nd)).tocsr()
                return force,K,stress,dl,direction
            strain=np.einsum('eij,ej->ei',self.B,vector[self.dof])-self.reference-self.plastic
            strain[:,:3]-=expansion[:,None]
            dev=strain-strain@self.pv;shear=2*G[:,None]*dev
            equivalent=np.sqrt(1.5*np.sum(shear*shear,axis=1))
            dl=np.where(active,np.maximum(0.,(equivalent-Y-H*self.eqp)/(3*G+H)),0.)
            direction=1.5*shear/np.maximum(equivalent[:,None],1e-20)
            beta=1-3*G*dl/np.maximum(equivalent,1e-20)
            stress=shear*beta[:,None]+3*bulk[:,None]*(strain@self.pv)
            stress[~active]=0.
            forces=np.einsum('eji,ej,e->ei',self.B,stress,self.volume*weight)
            force=np.bincount(self.dof.ravel(),weights=forces.ravel(),minlength=self.nd)
            if not tangent:return force,None,stress,dl,direction
            D=3*bulk[:,None,None]*self.pv+2*G[:,None,None]*beta[:,None,None]*self.pd
            correction=1/(3*G+H)-dl/np.maximum(equivalent,1e-20)
            D-=np.where(dl>0,4*G*G*correction,0.)[:,None,None]*direction[:,:,None]*direction[:,None,:]
            elements=np.einsum('eji,ejk,ekl,e->eil',self.B,D,self.B,self.volume*weight,optimize=True)
            K=coo_matrix((elements.ravel(),(self.rows,self.cols)),shape=(self.nd,self.nd)).tocsr()
            return force,K,stress,dl,direction
        for iteration in range(40):
            force,K,stress,dl,direction=assemble(trial)
            projected_force=extension.T@force
            residual=float(np.linalg.norm(projected_force))
            if self.kinematics=='finite_Hencky' and time_s<=1 and iteration%5==0:
                print('finite equilibrium',round(time_s,6),iteration,residual,flush=True)
            self.iteration_history.append([time_s,iteration,residual,float(dl.max()),float(np.linalg.norm(trial))])
            if residual<.05:break
            gauge_error=C@(trial[free]-coordinate_origin)
            stiffness=(extension.T@K@extension).tocsr()
            # Exact diagonal congruence scaling handles small physical support
            # without adding stiffness, damping or artificial hardening.
            diagonal=stiffness.diagonal()
            if self.kinematics=='small_strain' and np.any(diagonal<=0):raise RuntimeError('Active physical stiffness has a non-positive diagonal')
            if np.any(diagonal==0):raise RuntimeError('Physical tangent has an unsupported zero diagonal')
            scale=1/np.sqrt(abs(diagonal));S=diags(scale)
            scaled_C=(C@S).tocsr();constraint_scale=1/np.sqrt(np.asarray(scaled_C.multiply(scaled_C).sum(axis=1)).ravel())
            L=diags(constraint_scale);scaled_C=L@scaled_C
            augmented=bmat([[S@stiffness@S,scaled_C.T],[scaled_C,csr_matrix((C.shape[0],C.shape[0]))]],format='csr')
            rhs=np.r_[-scale*projected_force,-constraint_scale*gauge_error]
            scaled_solution=pypardiso.spsolve(augmented,rhs,solver=self.engine)
            for refinement in range(2):
                step=scale*scaled_solution[:len(free)];multipliers=constraint_scale*scaled_solution[len(free):]
                force_defect=projected_force+stiffness@step+C.T@multipliers
                constraint_defect=gauge_error+C@step
                if np.linalg.norm(force_defect)<.001 and np.linalg.norm(constraint_defect)<1e-8:break
                defect=np.r_[-scale*force_defect,-constraint_scale*constraint_defect]
                scaled_solution+=pypardiso.spsolve(augmented,defect,solver=self.engine)
            solution=np.r_[scale*scaled_solution[:len(free)],constraint_scale*scaled_solution[len(free):]]
            linear_residual=float(np.linalg.norm(projected_force+stiffness@solution[:len(free)]+C.T@solution[len(free):]))
            if linear_residual>.001 or np.linalg.norm(gauge_error+C@solution[:len(free)])>1e-8:
                raise RuntimeError(f'Precoat solid linear residual {linear_residual} at{time_s}s; reference force{np.linalg.norm(rhs)}')
            for power in range(12):
                candidate=trial.copy();candidate+=extension@solution[:len(free)]*.5**power
                try:next_force,*_=assemble(candidate,False)
                except ValueError:
                    if self.kinematics=='finite_Hencky':continue
                    raise
                if np.linalg.norm(extension.T@next_force)<residual:
                    trial=candidate;break
            else:
                # Preserve the actual unconverged Newton iterate and check its
                # force derivative. This is diagnostic evidence, never an
                # accepted manufacturing state.
                rng=np.random.default_rng(731)
                perturbation=extension@rng.normal(size=len(free))
                perturbation*=1e-7/np.max(abs(perturbation))
                perturbed_force,*_=assemble(trial+perturbation,False)
                actual=extension.T@(perturbed_force-force)
                predicted=extension.T@(K@perturbation)
                rigid=np.zeros((self.nd,6));rigid.reshape(-1,3,6)[:,:,:3]=np.eye(3)
                for j in range(3):rigid[:,j+3]=np.cross(np.eye(3)[j],self.x-self.x.mean(axis=0)).ravel()
                root_rigid=rigid[free]
                self.failed_iteration=dict(time_s=time_s,iteration=iteration,residual_N=residual,
                    tangent_relative_direction_error=float(np.linalg.norm(actual-predicted)/max(np.linalg.norm(actual),1e-30)),
                    linear_residual_N=linear_residual,maximum_trial_plastic_increment=float(dl.max()),
                    maximum_solid_strain=float(np.linalg.norm(np.einsum('eij,ej->ei',self.B,trial[self.dof])-self.reference,axis=1)[active].max()),
                    rigid_gauge_reaction_norm_N=float(np.linalg.norm(C.T@solution[len(free):])),
                    force_norm_Newton_direction_derivative=float(projected_force@(stiffness@solution[:len(free)])/residual**2),
                    smallest_tested_step_force_N=float(np.linalg.norm(extension.T@next_force)),
                    resultant_force_N=force.reshape(-1,3).sum(axis=0).tolist(),
                    resultant_moment_Nmm=np.cross(self.x,force.reshape(-1,3)).sum(axis=0).tolist())
                self.failed_iteration.update(
                    maximum_rigid_extension_error=float(abs((extension@root_rigid)[3*occupied[:,None]+np.arange(3)]-rigid[3*occupied[:,None]+np.arange(3)]).max()),
                    reduced_rigid_force_projection=(root_rigid.T@projected_force).tolist(),
                    reduced_rigid_stiffness_norm=np.linalg.norm(stiffness@root_rigid,axis=0).tolist(),
                    gauge_rigid_singular_values=np.linalg.svd(C@root_rigid,compute_uv=False).tolist())
                self.failed_iteration.update(
                    gauge_multipliers=solution[len(free):].tolist(),
                    reduced_rigid_gauge_reaction=(root_rigid.T@(C.T@solution[len(free):])).tolist(),
                    Newton_step_norm_mm=float(np.linalg.norm(solution[:len(free)])),
                    linear_rhs_force_defect_N=float(np.linalg.norm(rhs[:len(free)]+scale*projected_force)))
                self.failed_trial_u=trial.copy()
                raise RuntimeError(f'Precoat solid Newton stagnated at{time_s}s residual{residual}N')
        else:
            force,K,stress,dl,direction=assemble(trial)
            projected_force=extension.T@force;stiffness=(extension.T@K@extension).tocsr()
            rigid=np.zeros((self.nd,6));rigid.reshape(-1,3,6)[:,:,:3]=np.eye(3)
            for j in range(3):rigid[:,j+3]=np.cross(np.eye(3)[j],self.x-self.x.mean(axis=0)).ravel()
            roots=rigid[free]
            rng=np.random.default_rng(731);perturbation=extension@rng.normal(size=len(free));perturbation*=1e-7/np.max(abs(perturbation))
            perturbed,*_=assemble(trial+perturbation,False);actual=extension.T@(perturbed-force);predicted=extension.T@(K@perturbation)
            self.failed_iteration=dict(time_s=time_s,iteration=40,residual_N=float(np.linalg.norm(projected_force)),
                components=components,rigid_gauge_reaction_norm_N=float(np.linalg.norm(C.T@solution[len(free):])),
                maximum_rigid_extension_error=float(abs((extension@roots)[3*occupied[:,None]+np.arange(3)]-rigid[3*occupied[:,None]+np.arange(3)]).max()),
                reduced_rigid_force_projection=(roots.T@projected_force).tolist(),
                reduced_rigid_stiffness_norm=np.linalg.norm(stiffness@roots,axis=0).tolist(),
                resultant_force_N=force.reshape(-1,3).sum(axis=0).tolist(),
                resultant_moment_Nmm=np.cross(self.x,force.reshape(-1,3)).sum(axis=0).tolist(),
                tangent_relative_direction_error=float(np.linalg.norm(actual-predicted)/max(np.linalg.norm(actual),1e-30)),
                maximum_trial_plastic_increment=float(dl.max()),maximum_trial_solid_strain=float(np.linalg.norm((np.einsum('eij,ej->ei',self.B,trial[self.dof])-self.reference)[active],axis=1).max()))
            self.failed_trial_u=trial.copy();self.failed_trial_stress=stress.copy()
            raise RuntimeError(f'Precoat solid Newton failed at{time_s}s residual{residual}N')
        self.u=trial;self.plastic+=dl[:,None]*direction;self.eqp+=dl;self.stress=stress
        self.maximum_residual=max(self.maximum_residual,residual);self.total_iterations+=iteration
        self.previous_temperature=solid_T;self.previous_occupation=occupation.copy()
        self.previous_actual_temperature=temperature.copy()
        row=[time_s,iteration,residual,int(np.sum(active)),components,float(self.eqp.max()),
            float(np.max(np.linalg.norm(self.u.reshape(-1,3),axis=1))),
            float(self.volume@added_weight),float(self.volume@removed_weight),
            float(np.max(np.linalg.norm(strain_now,axis=1)))]
        self.history.append(row)
        return row

    def save(self,folder,time_s,temperature,occupation,partial=True):
        folder.mkdir(parents=True,exist_ok=True)
        source_temperature=temperature.copy()
        if len(temperature)==self.source_nodes:temperature=temperature[self.thermal_origin]
        extra=dict(thermal_origin=self.thermal_origin,thermal_source_temperature_C=source_temperature,kinematics=self.kinematics)
        if self.interface_policy=='chronological':extra.update(fused_faces=self.fused_faces,bonded_faces=self.bonded_faces,current_bond_pairs=self.current_bond_pairs,original_fusion_faces=self.fusion_faces)
        np.savez_compressed(folder/'fields.npz',x=self.x,e=self.e,material=self.m,volume_mm3=self.volume,
            time_s=time_s,temperature_C=temperature,occupation=occupation,u=self.u.reshape(-1,3),
            stress=self.stress,plastic=self.plastic,eqp=self.eqp,solid_reference_strain=self.reference,
            solid_weight=self.solid_weight,remelted_QT=self.remelted,material_mass_kg=self.material_mass_kg,**extra)
        np.savetxt(folder/'equilibrium-history.csv',self.history,delimiter=',',comments='',
            header='t_s,iterations,residual_N,solid_elements,components,max_eqp,max_u_mm,added_solid_volume_mm3,removed_solid_volume_mm3,maximum_total_strain_norm')
        np.savetxt(folder/'Newton-history.csv',self.iteration_history,delimiter=',',comments='',
            header='t_s,iteration,residual_N,max_plastic_increment,displacement_norm_mm')
        if self.failed_iteration is not None:
            (folder/'Newton-failure-diagnostic.json').write_text(json.dumps(self.failed_iteration,indent=2),encoding='utf8')
            np.savez_compressed(folder/'Newton-failed-iterate.npz',u=self.failed_trial_u.reshape(-1,3))
        result=dict(partial=partial,time_s=time_s,mechanical_reference=self.reference_input,
            maximum_equilibrium_residual_N=self.maximum_residual,total_Newton_iterations=self.total_iterations,
            source_state_policy='actual nodal thermal/deposition history; actual previous/current solid-domain intersection retains reference/plasticity; newly coherent shear follows current configuration and specific volume follows carried mass/rho20/reference-volume',
            liquid_policy=self.phase_method+' material phase volume: existing solid-state tensors retained by solid volume; liquid carries no shear',
            volume_of_QT_cells_containing_remelt_mm3=float(self.volume[self.remelted].sum()),
            remelted_QT_constitutive_scope='cast-family reference in this demand case; region recorded separately, no pristine QT/PMZ fracture capacity assigned',
            maximum_equivalent_plastic_strain=float(self.eqp.max()),
            full_manufacturing_verified=False,PMZ_capacity_assigned=False)
        result.update(mechanical_interface_policy=self.interface_policy,
            bond_policy='separate newly connected material freedoms before recorded whole-face temperature exceeds both actual liquidus values; strong solid bond activates only when the complete P1 facet is below both solidus temperatures; surviving reference/plasticity retained through real closure' if self.interface_policy=='chronological' else 'conformal coupling sensitivity case',
            bonded_node_pairs=len(self.current_bond_pairs))
        if self.interface_policy=='chronological':result.update(
            qualified_fusion_reference_face_area_mm2=float(self.fusion_face_area[self.fused_faces].sum()),
            coherent_bonded_reference_face_area_mm2=float(self.fusion_face_area[self.bonded_faces].sum()),
            interface_facet_time_policy='strong full-facet coherent branch; its activation timing requires the retained-state mesh/time response check')
        full=self.solid_weight>=1-1e-10
        gradient=np.einsum('eij,eik->ejk',self.u.reshape(-1,3)[self.e],self.g)
        determinant=np.linalg.det(np.eye(3)+gradient)
        volume_error=abs(determinant-(1+np.trace(gradient,axis1=1,axis2=2)))/np.maximum(abs(determinant),1e-30)
        physical_strain=self.strain_at(self.u,full)
        result.update(full_solid_maximum_parent_kinematic_strain=float(np.linalg.norm(physical_strain[full],axis=1).max()),
            full_solid_maximum_material_reference_strain=float(np.linalg.norm((physical_strain-self.reference)[full],axis=1).max()),
            full_solid_minimum_det_F=float(determinant[full].min()),
            full_solid_maximum_finite_vs_linear_volume_difference=float(volume_error[full].max()),
            small_strain_geometry_volume_check_pass=bool(determinant[full].min()>0 and volume_error[full].max()<=.05),
            parent_extension_strain_scope='equilibrium-history maximum_total_strain_norm includes unborn/liquid parent extensions; use full-solid metrics for actual solid geometry',
            component_policy='affine interpolation independent for every connected solid body; six rigid-increment coordinate gauges retain its inherited pose through separation/reconnection; no cross-body support')
        result['kinematics']=self.kinematics
        result['finite_configuration_check_pass']=bool(self.kinematics=='finite_Hencky' and determinant[self.solid_weight>1e-12].min()>0)
        if self.kinematics=='finite_Hencky':
            result['stress_measure']='Cauchy stress from work-conjugate Hencky stress through the exact log-strain derivative; physical force uses first Piola stress'
            result['finite_kinematics_source']='https://doi.org/10.1016/j.cma.2023.116101; finite log-strain additive plasticity; existing reference-material demand curves'
        result['new_coherent_material_policy']='current shear configuration plus mass/density cold specific-volume reference; thermal bulk strain solved by equilibrium, no surviving material history reset'
        result['cut_space_displacement_policy']='accepted P1 geometry retained; current cut-space constrains Newton increments only; no representation-only reference shift'
        result['coherent_reference_initialization_order']='actual preclosure configuration; interface joining displacement is never initialized as stress-free new-material shear'
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        (folder/'birth-continuation-audit.json').write_text(json.dumps(self.birth_audits,indent=2),encoding='utf8')
        return result
