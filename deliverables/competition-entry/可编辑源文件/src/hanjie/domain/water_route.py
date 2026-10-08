"""Dimensioned, constant-length PFA movement bends for the four Cu sectors.

These curves define installation envelopes, not a hose elasticity simulation.
Metal inlet elbows and compression unions move rigidly with their Cu sector.
"""
import math
import numpy as np
from scipy.integrate import simpson
from scipy.optimize import brentq

_rad = np.array([math.cos(math.radians(3)), math.sin(math.radians(3))])
_tan = np.array([-_rad[1], _rad[0]])
_rot = np.array([[2**-.5, -2**-.5], [2**-.5, 2**-.5]])
_layers = ((66.8, 58., 92., 13.68, 8.745, -.23),
           (56.8, 52., 94., 10.856, 6.218, -1.366))


def _curve(layer, stroke, a, b, count=501):
    radius, end_radius, z, *_ = _layers[layer]
    p0 = radius*_rad + 9*_tan - stroke*_rot[:, 0]
    p3 = _rot @ np.array([end_radius, -8.])
    p1, p2 = p0+a*_tan, p3-b*_rot[:, 1]
    u = np.linspace(0, 1, count)[:, None]
    p = (1-u)**3*p0 + 3*(1-u)**2*u*p1 + 3*(1-u)*u*u*p2 + u**3*p3
    d = 3*(1-u)**2*(p1-p0)+6*(1-u)*u*(p2-p1)+3*u*u*(p3-p2)
    dd = 6*(1-u)*(p2-2*p1+p0)+6*u*(p3-2*p2+p1)
    curvature_radius = np.linalg.norm(d, axis=1)**3 / np.maximum(
        np.abs(d[:, 0]*dd[:, 1]-d[:, 1]*dd[:, 0]), 1e-15)
    length = simpson(np.linalg.norm(d, axis=1), x=u[:, 0])
    return np.column_stack((p, np.full(count, z))), length, curvature_radius


def bends(stroke=0., count=501):
    """16 hose centrelines; paired blocks rotate at 45+90*i degrees."""
    curves, radii, lengths = [], [], []
    for layer, (_, _, _, a0, b0, slope) in enumerate(_layers):
        nominal_length = _curve(layer, 0, a0, b0)[1]
        a = a0+slope*stroke
        b = brentq(lambda b: _curve(layer, stroke, a, b)[1]-nominal_length, .1, 30)
        p, length, radius = _curve(layer, stroke, a, b, count)
        # Reflection about the sector bisector gives the opposite supply/return.
        mirror = p.copy(); mirror[:, :2] = p[:, [1, 0]]
        for quarter in range(4):
            angle = quarter*math.pi/2
            rotation = np.array([[math.cos(angle), -math.sin(angle)],
                                 [math.sin(angle), math.cos(angle)]])
            for branch in (p, mirror):
                q = branch.copy(); q[:, :2] = branch[:, :2]@rotation.T
                curves.append(q); radii.append(float(radius.min())); lengths.append(float(length))
    return curves, radii, lengths


def moving_union_envelopes(stroke=0.):
    """OD5 x8 rigid compression unions at the sixteen moving hose exits."""
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    curves,_,_=bends(stroke,count=3)
    bodies=[]
    for i,c in enumerate(curves):
        quarter=(i%8)//2;direction=_tan.copy()
        if i%2:direction=direction[::-1]
        angle=quarter*math.pi/2
        direction=np.array([[math.cos(angle),-math.sin(angle)],
                            [math.sin(angle),math.cos(angle)]])@direction
        tail=c[0]-np.array([8*direction[0],8*direction[1],0])
        axis=gp_Ax2(gp_Pnt(*tail),gp_Dir(direction[0],direction[1],0))
        bodies.append(BRepPrimAPI_MakeCylinder(axis,2.5,8).Shape())
    return bodies


def moving_elbow_envelopes(stroke=0.):
    """Machined Cu 5x5x5 L-port blocks, with integral M4 outlet nipples.

    Cross-drilled waterways remove the need for a tightly cold-bent microtube.
    The nipple lies inside the matching compression union envelope.
    """
    from OCP.gp import gp_Pnt
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from hanjie.domain.copper_sectors import moved
    bodies=[]
    for radius,_,z,*_ in _layers:
        for quarter in range(4):
            angle=quarter*math.pi/2
            shift=-stroke*np.array([math.cos(angle+math.pi/4),math.sin(angle+math.pi/4)])
            for mirror in (False,True):
                centre=radius*_rad+3*_tan
                if mirror:
                    centre=centre[::-1];orientation=math.pi/2-math.radians(3)
                else:orientation=math.radians(3)
                block=BRepPrimAPI_MakeBox(gp_Pnt(-2.5,-2.5,z-2.5),5,5,5).Shape()
                block=moved(block,angle=orientation)
                block=moved(block,dx=centre[0],dy=centre[1])
                if quarter:block=moved(block,angle=angle)
                bodies.append(moved(block,dx=shift[0],dy=shift[1]))
    return bodies
