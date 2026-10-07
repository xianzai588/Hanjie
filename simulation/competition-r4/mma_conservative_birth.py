"""Mass-controlled cut tetrahedra for the prescribed one-wing deposit envelope.

The front is a level set of the P1 nodal polar angle. Clipped volumes and the
integrals of all four parent shape functions are exact for that level set.
This is a conduction envelope model; it does not solve liquid transport.
"""
import numpy as np
import itertools
from scipy.optimize import brentq
from scipy.spatial import ConvexHull


def clipped_moments(values, threshold):
    """Return integral(N_i)/parent_volume over N.values <= threshold."""
    inside = values <= threshold
    count = int(inside.sum())
    if count == 0:
        return np.zeros(4)
    if count == 4:
        return np.full(4, .25)
    unit = np.eye(4)
    if count in (1, 3):
        select = inside if count == 1 else ~inside
        i = np.flatnonzero(select)[0]
        other = np.flatnonzero(~select)
        fraction = (threshold-values[i])/(values[other]-values[i])
        vertices = np.vstack([unit[i], unit[i]+fraction[:, None]*(unit[other]-unit[i])])
        moments = float(np.prod(fraction))*vertices.mean(axis=0)
        return moments if count == 1 else np.full(4, .25)-moments
    points = [unit[i] for i in np.flatnonzero(inside)]
    for i in np.flatnonzero(inside):
        for j in np.flatnonzero(~inside):
            f = (threshold-values[i])/(values[j]-values[i])
            points.append(unit[i]+f*(unit[j]-unit[i]))
    points = np.asarray(points)
    middle = points.mean(axis=0)
    hull = ConvexHull(points[:, 1:])
    moments = np.zeros(4)
    for tri in hull.simplices:
        tet = np.vstack([middle, points[tri]])
        ratio = abs(np.linalg.det(tet[1:, 1:]-tet[0, 1:]))
        moments += ratio*tet.mean(axis=0)
    return moments


def intersected_moments(first_values,first_level,second_values,second_level):
    """Exact P1 birth/solid intersection moments on one parent tetrahedron."""
    values=np.vstack([first_values,second_values]);levels=np.array([first_level,second_level])
    unit=np.eye(4);points=[]
    tolerance=16*np.finfo(float).eps*np.maximum(np.max(abs(values),axis=1),abs(levels))
    def append(point):
        if np.all(values@point<=levels+tolerance) and not any(np.max(abs(point-q))<1e-12 for q in points):points.append(point)
    for point in unit:append(point)
    for i in range(4):
        for j in range(i+1,4):
            for plane in range(2):
                delta=values[plane,j]-values[plane,i]
                if delta==0:continue
                fraction=(levels[plane]-values[plane,i])/delta
                if 0<=fraction<=1:append(unit[i]+fraction*(unit[j]-unit[i]))
    for omit in range(4):
        ids=[j for j in range(4) if j!=omit]
        matrix=np.vstack([np.ones(3),values[:,ids]])
        if abs(np.linalg.det(matrix))<1e-18:continue
        weights=np.linalg.solve(matrix,np.r_[1.,levels])
        if np.all(weights>=0) and np.all(weights<=1):
            point=np.zeros(4);point[ids]=weights;append(point)
    if len(points)<4:return np.zeros(4)
    points=np.array(points);singular=np.linalg.svd(points[1:,1:]-points[0,1:],compute_uv=False)
    if singular[-1]<=32*np.finfo(float).eps*singular[0]:return np.zeros(4)
    middle=points.mean(axis=0);hull=ConvexHull(points[:,1:]);moments=np.zeros(4)
    for tri in hull.simplices:
        tet=np.vstack([middle,points[tri]])
        ratio=abs(np.linalg.det(tet[1:,1:]-tet[0,1:]))
        moments+=ratio*tet.mean(axis=0)
    return moments


def multiple_cut_moments(values,levels):
    """P1 moments in up to three actual material-history halfspaces."""
    values=np.asarray(values);levels=np.asarray(levels);signed=values-levels[:,None]
    if np.any((signed.min(axis=1)>=0)&(signed.max(axis=1)>0)):return np.zeros(4)
    select=signed.max(axis=1)>0;values=values[select];levels=levels[select];signed=signed[select]
    if not len(values):return np.full(4,.25)
    if len(values)==1:return clipped_moments(values[0],levels[0])
    if len(values)==2:return intersected_moments(values[0],levels[0],values[1],levels[1])
    if len(values)!=3:raise ValueError('This manufacturing operation has at most three cuts')
    planes=np.vstack([-np.eye(4),signed/np.max(abs(signed),axis=1)[:,None]])
    combinations=np.array(list(itertools.combinations(range(7),3)))
    matrices=np.concatenate([np.ones((len(combinations),1,4)),planes[combinations]],axis=1)
    determinant=np.linalg.det(matrices);keep=abs(determinant)>1e-18
    rhs=np.tile([1.,0,0,0],(keep.sum(),1))
    candidates=np.linalg.solve(matrices[keep],rhs[...,None])[...,0]
    points=[]
    for point in candidates:
        if np.all(planes@point<=64*np.finfo(float).eps) and not any(np.max(abs(point-q))<1e-12 for q in points):points.append(point)
    if len(points)<4:return np.zeros(4)
    points=np.array(points);singular=np.linalg.svd(points[1:,1:]-points[0,1:],compute_uv=False)
    if singular[-1]<=32*np.finfo(float).eps*singular[0]:return np.zeros(4)
    middle=points.mean(axis=0);hull=ConvexHull(points[:,1:]);moments=np.zeros(4)
    for tri in hull.simplices:
        tet=np.vstack([middle,points[tri]])
        moments+=abs(np.linalg.det(tet[1:,1:]-tet[0,1:]))*tet.mean(axis=0)
    return moments


class ConservativeBirth:
    def __init__(self, x, e, material, volume, density_kg_mm3, radius=None, rise_length=None,
                 deposit_mask=None, initial_moments=None, angle_offset=0.):
        selected = material == 3 if deposit_mask is None else deposit_mask
        self.indices = np.flatnonzero(selected)
        self.nodal_values = (np.arctan2(x[:, 1], x[:, 0])-angle_offset+np.pi)%(2*np.pi)-np.pi
        deposit_nodes=np.unique(e[self.indices])
        self.floor=float(x[deposit_nodes,2].min());self.top=float(x[deposit_nodes,2].max())
        if rise_length is not None:
            self.nodal_values=self.nodal_values+rise_length/radius*(x[:,2]-self.floor)/(self.top-self.floor)
        self.values = self.nodal_values[e[self.indices]]
        self.lo = self.values.min(axis=1)
        self.hi = self.values.max(axis=1)
        self.weights = volume[self.indices]*density_kg_mm3[self.indices]
        self.total_mass_kg = float(self.weights.sum())
        self.material = material
        self.volume = volume
        self.xe = x[e]
        self.moments = np.zeros((len(e), 4))
        self.moments[material == 1] = .25
        if initial_moments is not None or deposit_mask is not None:
            if initial_moments is not None:self.moments = np.asarray(initial_moments).copy()
            if np.any(self.moments[selected]>1e-12):
                raise ValueError('current wing already has deposited metal')
            # Complete earlier wings and absent future wings share the same
            # geometry-aware area/front routines. They do not receive a new
            # temperature or enthalpy when the current deposition begins.
            other = (material == 3)&~selected
            old = other&(self.moments.sum(axis=1)>.999999)
            future = other&~old
            self.nodal_values[np.unique(e[old])] = -100.
            self.nodal_values[np.unique(e[future])] = 100.
            self.values = self.nodal_values[e[self.indices]]
            self.lo = self.values.min(axis=1)
            self.hi = self.values.max(axis=1)
        self.base_moments = self.moments.copy()

    def evaluate(self, threshold):
        q = np.zeros((len(self.indices), 4))
        q[self.hi <= threshold] = .25
        crossing = np.flatnonzero((self.lo < threshold)&(self.hi > threshold))
        for i in crossing:
            q[i] = clipped_moments(self.values[i], threshold)
        return q

    def at_mass(self, target_mass_kg):
        """Geometric state at an arbitrary time, without altering saved birth."""
        if not 0 < target_mass_kg <= self.total_mass_kg*(1+1e-8):
            raise ValueError('target deposited mass lies outside the CAD envelope')
        if target_mass_kg >= self.total_mass_kg*(1-1e-12):
            threshold = float(self.hi.max())
            q = np.full((len(self.indices), 4), .25)
        else:
            def residual(t):
                return float(self.evaluate(t).sum(axis=1)@self.weights-target_mass_kg)
            threshold = brentq(residual, float(self.lo.min()-1e-10), float(self.hi.max()+1e-10), xtol=1e-13)
            q = self.evaluate(threshold)
        moments=self.base_moments.copy()
        moments[self.indices]=q
        fraction=moments.sum(axis=1)
        cut_centre=self.xe.mean(axis=1)
        present=fraction>1e-14
        cut_centre[present]=np.einsum('ei,eij->ej',moments[present],self.xe[present])/fraction[present,None]
        return moments,fraction,cut_centre,threshold

    def advance(self, target_mass_kg):
        moments,fraction,cut_centre,threshold=self.at_mass(target_mass_kg)
        previous = self.moments.copy()
        self.moments=moments
        delta = self.moments-previous
        if delta.min() < -1e-10:
            raise ValueError('deposition front receded')
        return previous, self.moments.copy(), delta, fraction, cut_centre, threshold

    def surface(self, x, e, face, oa, ob, area, threshold):
        """P1 nodal area on real free facets plus the cut deposition front."""
        neighbour = np.maximum(ob, 0)
        exterior = ob < 0
        parent_external = exterior & (self.material[oa] == 1)
        interface = ~exterior & (self.material[oa] != self.material[neighbour])
        ni_external = exterior & (self.material[oa] == 3)
        nodal = np.bincount(face[parent_external | interface].ravel(),
            weights=np.repeat(area[parent_external | interface]/3, 3), minlength=len(x))
        angles = self.nodal_values
        for j in np.flatnonzero(interface | ni_external):
            nodes = face[j]
            values = angles[nodes]
            if values.min() >= threshold:
                continue
            if values.max() <= threshold:
                moment = np.full(3, area[j]/3)
            else:
                inside = values < threshold
                unit = np.eye(3)
                points = [unit[i] for i in np.flatnonzero(inside)]
                for i in np.flatnonzero(inside):
                    for k in np.flatnonzero(~inside):
                        f = (threshold-values[i])/(values[k]-values[i])
                        points.append(unit[i]+f*(unit[k]-unit[i]))
                points = np.asarray(points)
                xyz = points@x[nodes]
                centre = xyz.mean(axis=0)
                bcentre = points.mean(axis=0)
                # Order the convex polygon in the original triangle plane.
                u, _, _ = np.linalg.svd((xyz-centre).T, full_matrices=False)
                projected = (xyz-centre)@u[:, :2]
                order = np.argsort(np.arctan2(projected[:, 1], projected[:, 0]))
                moment = np.zeros(3)
                for i, k in zip(order, np.roll(order, -1)):
                    triangle_area = np.linalg.norm(np.cross(xyz[i]-centre, xyz[k]-centre))/2
                    moment += triangle_area*(bcentre+points[i]+points[k])/3
            nodal[nodes] += (-1 if interface[j] else 1)*moment
        crossing = np.flatnonzero((self.lo < threshold)&(self.hi > threshold))
        unit = np.eye(4)
        for local in crossing:
            j = self.indices[local]
            values = self.values[local]
            inside = values < threshold
            points = []
            for i in np.flatnonzero(inside):
                for k in np.flatnonzero(~inside):
                    f = (threshold-values[i])/(values[k]-values[i])
                    points.append(unit[i]+f*(unit[k]-unit[i]))
            points = np.asarray(points)
            xyz = points@x[e[j]]
            centre = xyz.mean(axis=0)
            bcentre = points.mean(axis=0)
            u, _, _ = np.linalg.svd((xyz-centre).T, full_matrices=False)
            projected = (xyz-centre)@u[:, :2]
            order = np.argsort(np.arctan2(projected[:, 1], projected[:, 0]))
            for i, k in zip(order, np.roll(order, -1)):
                triangle_area = np.linalg.norm(np.cross(xyz[i]-centre, xyz[k]-centre))/2
                nodal[e[j]] += triangle_area*(bcentre+points[i]+points[k])/3
        if nodal.min() < -1e-9:
            raise ValueError('negative exposed area')
        return nodal
