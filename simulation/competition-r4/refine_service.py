"""Refine the cold full-assembly load check independently of the welding history."""
from pathlib import Path
import json,sys
import numpy as np
from threadpoolctl import threadpool_limits
from run_verified import mesh
from service_check import run

def main(h,candidate=False,pad=False,revised=False,root_h=None,thickness=14.,bore_diameter=40.014):
    if not 39.98<=bore_diameter<=40.04:raise ValueError('服役孔径超出本设计参数化范围')
    bore_tag=f'bore{bore_diameter:g}-' if bore_diameter!=40.014 else ''
    out=Path(__file__).parent/'results'/f'service-{f"t{thickness:g}-affine-" if revised else "pad-" if pad else "rounded-" if candidate else ""}{bore_tag}h{h:g}{f'-rootlocal{root_h:g}' if root_h else ''}'
    out.mkdir(parents=True,exist_ok=True)
    seat=Path(__file__).parent/f'geometry/8P-R2-t{thickness:g}.step' if revised else Path(__file__).parent/'geometry/8P-R2-central-pad13.step' if pad else Path(__file__).parent/'geometry/8P-root-transition-R2.step' if candidate else None
    x,e,m,bd,links=mesh(8,h,1.,seat,root_h)
    from affine_interface import audit
    patch=audit(x,links)
    print(patch,flush=True)
    radius=np.linalg.norm(x[:,:2],axis=1);bore=abs(radius-20)<1e-4
    x[bore,:2]*=(bore_diameter/2)/20
    np.savez_compressed(out/'mesh.npz',x=x,e=e,material=m,boundary=bd,
        link_nodes=np.array([[z[0],*z[1]] for z in links]),
        link_weights=np.array([[1.,*[-v for v in z[2]]] for z in links]))
    (out/'input.json').write_text(json.dumps(dict(h_mm=h,weld_mesh_mm=1,
        scope='cold static service model only; no welding history calculated',
        interface_patch=patch,initial_bore_diameter_mm=bore_diameter,geometry_candidate=bool(candidate or pad or revised),central_pad=bool(pad),revised_geometry=bool(revised),seat_geometry=str(seat) if seat else 'original 8P-FAIR_B',geometry_representation='parametric solid with cylindrical faces and post-union R2 fillets' if revised else 'original',root_mesh_mm=root_h,seat_thickness_mm=thickness if revised else 12.),ensure_ascii=False,indent=2),encoding='utf8')
    run(out)

if __name__=='__main__':
    with threadpool_limits(limits=1):main(float(sys.argv[1]),'--rounded' in sys.argv,'--pad' in sys.argv,'--revised' in sys.argv,float(sys.argv[sys.argv.index('--root-h')+1]) if '--root-h' in sys.argv else None,float(sys.argv[sys.argv.index('--thickness')+1]) if '--thickness' in sys.argv else 14.,float(sys.argv[sys.argv.index('--bore')+1]) if '--bore' in sys.argv else 40.014)
