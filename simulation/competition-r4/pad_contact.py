"""Compression-only Ø8 support pads on the actual planar QT surface mesh."""
import numpy as np
from scipy.sparse import coo_matrix
from matplotlib.tri import Triangulation


class PadContact:
    def __init__(self,x,boundary,radius=4.,radial_count=12,angular_count=64):
        faces=boundary[np.all(abs(x[boundary,2]-100)<1e-7,axis=1)]
        lower=np.unique(faces)
        tri=np.searchsorted(lower,faces)
        xy=x[lower,:2]
        sign=np.cross(xy[tri[:,1]]-xy[tri[:,0]],xy[tri[:,2]]-xy[tri[:,0]])
        tri[sign<0]=tri[sign<0][:,[0,2,1]]
        finder=Triangulation(xy[:,0],xy[:,1],tri).get_trifinder()
        gx,gw=np.polynomial.legendre.leggauss(radial_count)
        r=radius*(gx+1)/2;rw=radius*gw/2
        theta=2*np.pi*(np.arange(angular_count)+.5)/angular_count
        local=np.c_[np.repeat(r,angular_count)*np.tile(np.cos(theta),radial_count),
            np.repeat(r,angular_count)*np.tile(np.sin(theta),radial_count)]
        area=np.repeat(r*rw,angular_count)*2*np.pi/angular_count
        centres=np.array([[30*np.cos(a),30*np.sin(a)] for a in (0,2*np.pi/3,4*np.pi/3)])
        query=np.concatenate([local+c for c in centres])
        picked=finder(query[:,0],query[:,1])
        if np.any(picked<0):raise RuntimeError('support contact quadrature outside actual QT lower face')
        self.nodes=lower[tri[picked]]
        hosts=x[self.nodes,:2]
        matrix=np.stack((hosts[:,0]-hosts[:,2],hosts[:,1]-hosts[:,2]),axis=2)
        w=np.linalg.solve(matrix,(query-hosts[:,2])[:,:,None])[:,:,0]
        self.weights=np.c_[w,1-w.sum(axis=1)]
        self.area=np.tile(area,3);self.pad=np.repeat(np.arange(3),len(area));self.xy=query
        self.dof=3*self.nodes+2
        self.density=200000./6. # steel pad E / actual 6 mm height, N/mm³
        self.k=self.density*self.area
        mismatch=float(np.linalg.norm(np.einsum('ij,ijk->ik',self.weights,hosts)-query,axis=1).max())
        if mismatch>1e-7 or self.weights.min()<-1e-7:raise RuntimeError('pad interpolation patch failed')
        expected_area=np.pi*radius**2
        area_error=float(np.max(abs(np.bincount(self.pad,weights=self.area)-expected_area)))
        # Closed-form disk tests: rigid compression, lift, and half-contact tilt.
        compression=np.zeros(3*len(x));compression[2::3]=-.0001
        _,_,reaction,_,_=self.apply(compression,False)
        relative_compression=float(np.max(abs(reaction-self.density*expected_area*.0001))/(self.density*expected_area*.0001))
        lift=-compression
        _,_,lift_reaction,_,_=self.apply(lift,False)
        tilt=np.zeros_like(compression);tilt[2::3]=1e-4*(x[:,0]-centres[0,0])
        _,_,tilt_reaction,_,_=self.apply(tilt,False)
        exact_tilt=self.density*1e-4*2*radius**3/3
        relative_tilt=abs(tilt_reaction[0]-exact_tilt)/exact_tilt
        passed=bool(mismatch<1e-7 and area_error<1e-8 and relative_compression<1e-10 and lift_reaction.max()==0 and relative_tilt<.005)
        if not passed:raise RuntimeError('support disk contact analytic checks failed')
        self.audit=dict(model='unilateral distributed normal contact; circular Ø8 pads at R30/z100, 0/120/240 degrees',
            centres_mm=np.c_[centres,np.full(3,100.)].tolist(),area_per_pad_mm2=expected_area,
            spring_density_N_mm3=self.density,steel_modulus_MPa=200000.,pad_height_mm=6.,
            quadrature=[radial_count,angular_count],maximum_affine_coordinate_error_mm=mismatch,
            area_error_mm2=area_error,uniform_compression_relative_error=relative_compression,
            half_contact_tilt_relative_error=float(relative_tilt),analytic_geometry_contact_checks_pass=passed)

    def apply(self,u,tangent=True,growth=None):
        gap=np.sum(u[self.dof]*self.weights,axis=1)
        if growth is not None:gap-=np.asarray(growth)[self.pad]
        active=gap<=0
        upward=-self.k*np.minimum(gap,0)
        force=np.bincount(self.dof.ravel(),weights=(-upward[:,None]*self.weights).ravel(),minlength=len(u))
        matrix=None
        if tangent:
            ids=self.dof[active];w=self.weights[active]
            data=self.k[active,None,None]*w[:,:,None]*w[:,None,:]
            matrix=coo_matrix((data.ravel(),(np.repeat(ids,3,axis=1).ravel(),np.tile(ids,(1,3)).ravel())),shape=(len(u),len(u))).tocsr()
        reaction=np.bincount(self.pad,weights=upward,minlength=3)
        active_area=np.bincount(self.pad,weights=self.area*active,minlength=3)
        moment=np.array([np.dot(self.xy[:,1],upward),-np.dot(self.xy[:,0],upward)])
        metrics=dict(maximum_pressure_MPa=float(self.density*np.maximum(-gap,0).max()),
            maximum_lift_gap_mm=float(np.maximum(gap,0).max()),moment_N_mm=moment)
        return force,matrix,reaction,active_area,metrics
