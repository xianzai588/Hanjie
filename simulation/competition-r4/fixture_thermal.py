"""Finite-volume thermal network of the actual fixed cone and slotted sleeve.

Six angular sectors retain opposed-head imbalance. Axial cells follow the
machined sections; integrated free thermal expansion changes the mandrel gap.
This reduced fixture model uses declared engineering properties and contact
conductance, whose sensitivity is checked independently of the part mesh.
Units mm/s/J/K. No measured temperature or conductance is claimed.
"""
import math
import numpy as np
from scipy.sparse import coo_matrix,diags


class FixtureThermal:
    def __init__(self,x,bore,area,h_contact=2000.,refinement=1,pads=None):
        self.h=float(h_contact);self.refinement=int(refinement)
        self.sectors=6*self.refinement;self.cells=[];self.connections=[]
        self.alpha_core=12.5e-6;self.alpha_sleeve=11.7e-6
        self.cone_slope=math.tan(math.radians(10))
        def section(chain,z0,z1,r0,r1=None,inside=0.,count=1,slot=False,material='core'):
            if r1 is None:r1=r0
            for j in range(count*self.refinement):
                a=z0+(z1-z0)*j/(count*self.refinement)
                b=z0+(z1-z0)*(j+1)/(count*self.refinement)
                ra=r0+(r1-r0)*(a-z0)/(z1-z0)
                rb=r0+(r1-r0)*(b-z0)/(z1-z0)
                for sector in range(self.sectors):
                    volume=math.pi*(ra*ra+ra*rb+rb*rb-3*inside*inside)/3*(b-a)/self.sectors
                    if slot:volume*=.9
                    self.cells.append(dict(chain=chain,sector=sector,z0=a,z1=b,z=(a+b)/2,
                        r=(ra+rb)/2,inside=inside,volume=volume,
                        axial_area=volume/(b-a),slot=slot,material=material))
        section('core',-160,-20,220,count=2)
        section('core',-20,80,72,count=10)
        section('core',80,94,36,count=2)
        section('core',94,99.8,30)
        section('core',99.8,115.2,19.1449047,16.4294692,count=4)
        # Four axial slices of the band; cone bore varies through each slice.
        for j in range(4*self.refinement):
            a=100.2+14.6*j/(4*self.refinement);b=100.2+14.6*(j+1)/(4*self.refinement)
            ri=16.5+(114.8-(a+b)/2)*self.cone_slope
            # section() already multiplies its axial count by refinement.
            before=self.refinement;self.refinement=1
            section('sleeve',a,b,20.004,inside=ri,slot=True,material='sleeve')
            self.refinement=before
        section('sleeve',114.8,115.4,20.1,inside=19.3,slot=True,material='sleeve')
        section('sleeve',115.4,145.4,20.1,inside=19.3,count=3,slot=True,material='sleeve')
        section('sleeve',145.4,155.4,23,inside=19.3,material='sleeve')
        section('sleeve',155.4,400,35,inside=12,count=12,material='sleeve')
        self.pad_ids=[];self.pads=pads
        if pads is not None:
            for sector in (0,2*self.refinement,4*self.refinement):
                self.pad_ids.append(len(self.cells))
                self.cells.append(dict(chain='pad',sector=sector,z0=94.,z1=100.,z=97.,r=4.,inside=0.,
                    volume=math.pi*4**2*6,axial_area=math.pi*4**2,slot=False,material='core'))
        N=len(self.cells);self.temperature=np.full(N,20.)
        # Declared low-temperature engineering properties, checked by sensitivity.
        self.capacity=np.array([c['volume']*(7.80e-6 if c['material']=='core' else 7.81e-6)*460 for c in self.cells])
        self.k=np.array([.040 if c['material']=='core' else .0178 for c in self.cells])
        def connect(i,j,g):self.connections.append((i,j,float(g)))
        for chain in ('core','sleeve'):
            for sector in range(self.sectors):
                ids=[i for i,c in enumerate(self.cells) if c['chain']==chain and c['sector']==sector]
                for i,j in zip(ids,ids[1:]):
                    a,b=self.cells[i],self.cells[j]
                    resistance=(a['z1']-a['z0'])/2/(self.k[i]*a['axial_area'])+(b['z1']-b['z0'])/2/(self.k[j]*b['axial_area'])
                    connect(i,j,1/resistance)
        # Neighboring sectors conduct circumferentially in integral steel rings.
        for i,c in enumerate(self.cells):
            if c['chain']=='pad':continue
            sector=(c['sector']+1)%self.sectors
            # A refined mesh subdivides each real finger; conduction stays
            # inside that finger and cannot cross the six machined slots.
            if c['slot'] and sector//self.refinement!=c['sector']//self.refinement:continue
            j=next(j for j,b in enumerate(self.cells) if b['chain']==c['chain'] and b['sector']==sector and b['z']==c['z'])
            radial=max(c['r']-c['inside'],.1)
            path=max((c['r']+c['inside'])/2,1)*2*math.pi/self.sectors
            if c['slot']:path*=.9
            connect(i,j,self.k[i]*radial*(c['z1']-c['z0'])/path)
        band_ids=[i for i,c in enumerate(self.cells) if c['chain']=='sleeve' and c['z1']<=114.8+1e-8]
        for i in band_ids:
            c=self.cells[i]
            j=min((j for j,b in enumerate(self.cells) if b['chain']=='core' and b['sector']==c['sector'] and b['z']>=99.8),key=lambda j:abs(self.cells[j]['z']-c['z']))
            interface=.9*2*math.pi*c['inside']*(c['z1']-c['z0'])/self.sectors/math.cos(math.radians(10))
            # Cone contact plus radial conduction through the sleeve wall.
            thickness=c['r']-c['inside']
            connect(i,j,interface/(1/(self.h*1e-6)+thickness/2/self.k[i]+self.cells[j]['r']/4/self.k[j]))
        for i in self.pad_ids:
            c=self.cells[i]
            for sector in range(c['sector'],c['sector']+self.refinement):
                j=max((j for j,b in enumerate(self.cells) if b['chain']=='core' and b['sector']==sector and b['z1']<=94.),key=lambda j:self.cells[j]['z'])
                connect(i,j,.040*c['axial_area']/self.refinement/(3+(self.cells[j]['z1']-self.cells[j]['z0'])/2))
        row=[];col=[];values=[]
        for i,j,g in self.connections:
            row.extend((i,j,i,j));col.extend((i,j,j,i));values.extend((g,g,-g,-g))
        self.conduction=coo_matrix((values,(row,col)),shape=(N,N)).tocsr()
        self.external=np.zeros(N)
        for i,c in enumerate(self.cells):
            if c['chain']=='core' and c['z0']==-160:
                self.external[i]+=self.k[i]*c['axial_area']/((c['z1']-c['z0'])/2)
            if c['chain']=='sleeve' and c['z1']==400:
                self.external[i]+=self.k[i]*c['axial_area']/((c['z1']-c['z0'])/2)
            # Ambient loss from exposed sections, excluding the fitted band.
            if c['chain']!='pad' and not (c['chain']=='core' and c['z0']>=99.8) and not i in band_ids:
                self.external[i]+=15e-6*2*math.pi*c['r']*(c['z1']-c['z0'])/self.sectors
        self.bore=bore;self.area=area
        self.boundary_nodes=np.unique(np.r_[bore,pads.nodes.ravel() if pads is not None else np.array([],int)])
        phi=np.arctan2(x[bore,1],x[bore,0])%(2*math.pi)
        sectors=np.floor((phi+math.pi/6)%(2*math.pi)/(2*math.pi/self.sectors)).astype(int)
        self.mapping=np.array([min((i for i in band_ids if self.cells[i]['sector']==s),key=lambda i:abs(self.cells[i]['z']-z)) for s,z in zip(sectors,x[bore,2])])
        self.core_mapping=np.array([min((i for i,c in enumerate(self.cells) if c['chain']=='core' and c['sector']==s and c['z']>=99.8),key=lambda i:abs(self.cells[i]['z']-z)) for s,z in zip(sectors,x[bore,2])])
        # Radial shell expansion plus change of axial cone engagement.
        self.growth=np.zeros((len(bore),N))
        for row,(s,z,core,band) in enumerate(zip(sectors,x[bore,2],self.core_mapping,self.mapping)):
            self.growth[row,core]+=self.alpha_core*self.cells[core]['r']
            self.growth[row,band]+=self.alpha_sleeve*(20.004-self.cells[band]['inside'])
            for j,c in enumerate(self.cells):
                if c['sector']!=s:continue
                if c['chain']=='core':length=max(0.,min(z,c['z1'])-c['z0']);alpha=self.alpha_core
                elif c['chain']=='sleeve':length=max(0.,c['z1']-max(z,c['z0']));alpha=self.alpha_sleeve
                else:continue
                self.growth[row,j]+=self.cone_slope*alpha*length
        self.pad_expansion=np.zeros((3,N))
        for row,i in enumerate(self.pad_ids):
            sector=self.cells[i]['sector'];self.pad_expansion[row,i]=6*self.alpha_core
            for j,c in enumerate(self.cells):
                if c['chain']=='core' and sector<=c['sector']<sector+self.refinement:
                    self.pad_expansion[row,j]=max(0,min(94.,c['z1'])-c['z0'])*self.alpha_core/self.refinement
        self.audit=dict(model='six-sector axial finite volumes; thermal radius and cone engagement from integrated expansion',
            contact_conductance_W_m2K=self.h,argon_gap_conductivity_table=dict(T_K=[200,300,400],k_W_mK=[.0124,.0177,.0224]),
            core_properties=dict(rho_kg_m3=7800,Cp_J_kgK=460,k_W_mK=40,alpha_per_K=self.alpha_core,basis='Ovako C45 typical low-temperature data; alpha12.5e-6 engineering upper envelope for45 steel'),
            sleeve_properties=dict(rho_kg_m3=7810,Cp_J_kgK=460,k_W_mK=17.8,alpha_per_K=self.alpha_sleeve,basis='ATI H900 density/k and mean alpha upper-envelope; ARMCO heat capacity'),
            cells=self.cells,axial_refinement=self.refinement,angular_sectors=self.sectors,
            support_heat_model='three Ø8×6 finite-capacity steel pads; QT/contact/pad/core conduction; integrated support thermal height' if pads is not None else None,
            base_boundary_C=20,upper_stop_boundary_C=20,
            scope='machined fixture thermal network; base and massive upper portal treated as ambient thermal sinks; conductance is a qualification/design input')

    def offset(self):return self.growth@(self.temperature-20)

    def pad_offset(self):return self.pad_expansion@(self.temperature-20)

    def coupling(self,nn,gap,released,u=None,part_temperature=None):
        # The small argon gap is a series resistance, not instantaneous insulation.
        gas_k=np.full(len(self.bore),.0177e-3)
        if part_temperature is not None:
            mean_K=(part_temperature[self.bore]+self.temperature[self.mapping])/2+273.15
            gas_k=np.interp(mean_K,[200,300,400],[.0124,.0177,.0224])*1e-3
        conductance=np.zeros(len(self.bore)) if released else self.area/(1/(self.h*1e-6)+np.maximum(gap,0)/gas_k)
        M=coo_matrix((conductance,(self.bore,self.mapping)),shape=(nn,len(self.cells))).tocsr()
        if self.pads is not None and not released:
            p=self.pads
            vertical=np.zeros(len(p.area)) if u is None else np.sum(u[p.dof]*p.weights,axis=1)-self.pad_offset()[p.pad]
            mean_K=np.full(len(p.area),293.15)
            if part_temperature is not None:
                mean_K=(np.sum(part_temperature[p.nodes]*p.weights,axis=1)+self.temperature[np.array(self.pad_ids)[p.pad]])/2+273.15
            k_pad=np.interp(mean_K,[200,300,400],[.0124,.0177,.0224])*1e-3
            contact=p.area/(1/(self.h*1e-6)+np.maximum(vertical,0)/k_pad)
            ids=np.array(self.pad_ids)[p.pad]
            M+=coo_matrix(((contact[:,None]*p.weights).ravel(),(p.nodes.ravel(),np.repeat(ids,3))),shape=M.shape).tocsr()
        return M,np.asarray(M.sum(axis=1)).ravel(),np.asarray(M.sum(axis=0)).ravel()
