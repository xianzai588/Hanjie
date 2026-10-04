"""Seat candidate: real R2 merged junctions, uniform thickness selected by service verification."""
from pathlib import Path
import json,math
import gmsh
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"simulation/structural-v4"))
from generate_seat_geometry import BearingSeatGenerator,UnifiedParameters
from OCP.STEPControl import STEPControl_Reader,STEPControl_Writer,STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepTools import BRepTools
OUT=Path(__file__).parent/'geometry'
def main(thickness=15.):
 OUT.mkdir(exist_ok=True)
 generator= BearingSeatGenerator(UnifiedParameters(seat_thickness=thickness))
 original=generator._build_shape(8,'FAIR_B',18.)
 writer=STEPControl_Writer();writer.Transfer(original,STEPControl_AsIs)
 if writer.Write(str(OUT/f'8P-t{thickness:g}-base.step'))!=IFSelect_RetDone:raise RuntimeError('base STEP write failed')
 gmsh.initialize()
 try:
  gmsh.option.setNumber('General.Terminal',0);gmsh.model.add(f'seat-R2-t{thickness:g}');o=gmsh.model.occ
  o.importShapes(str(OUT/f'8P-t{thickness:g}-base.step'));o.synchronize()
  edges=[]
  for dim,tag in gmsh.model.getEntities(1):
   bounds=gmsh.model.getBoundingBox(dim,tag);x0,y0,z0,x1,y1,z1=bounds
   if x1-x0<1e-4 and y1-y0<1e-4 and z1-z0>thickness-.01 and abs(math.hypot((x0+x1)/2,(y0+y1)/2)-41)<.01:edges.append(tag)
  if len(edges)!=32:raise RuntimeError(f'actual merged junction count {len(edges)}')
  o.fillet([v for _,v in gmsh.model.getEntities(3)],edges,[2.],removeVolume=True);o.synchronize()
  if len(gmsh.model.getEntities(3))!=1:raise RuntimeError('single solid required')
  volume=o.getMass(*gmsh.model.getEntities(3)[0]);gmsh.write(str(OUT/f'8P-R2-t{thickness:g}.step'))
  (OUT/f'revised-seat-t{thickness:g}-candidate.json').write_text(json.dumps(dict(scope='requires service and welding verification',
   model_id=f'8P-R2-t{thickness:g}',slot_width_mm=4,slot_end_radius_mm=2,merged_core_root_radius_mm=2,
   core_diameter_mm=82,slot_deepest_radius_mm=39,thickness_mm=thickness,
   actual_core_junctions_rounded=32,volume_mm3=volume,mass_kg=volume*7.2e-6),indent=2),encoding='utf8')
  print('candidate mass kg',volume*7.2e-6)
 finally:gmsh.finalize()
 reader=STEPControl_Reader()
 if reader.ReadFile(str(OUT/f'8P-R2-t{thickness:g}.step'))!=IFSelect_RetDone:raise RuntimeError('STEP reread failed')
 reader.TransferRoots();shape=reader.OneShape()
 generator=BearingSeatGenerator(UnifiedParameters(seat_thickness=thickness))
 manifest=generator._manifest(8,'FAIR_B','8P',f'8P-R2-t{thickness:g}',18.,shape)
 manifest.seat['merged_core_transition_radius_mm']=2.
 manifest.generation['basis']='original 8P cylindrical interface; 32 post-union vertical corners rounded R2; axial thickness changed; historical P1A geometry remains intact'
 manifest.generation['step_file']=f'8P-R2-t{thickness:g}.step';manifest.generation['brep_file']=f'8P-R2-t{thickness:g}.brep'
 if not manifest.geometry['brep_valid'] or not manifest.geometry['single_solid'] or not manifest.geometry['shell_interference_free']:raise RuntimeError('seat geometry validation failed')
 if abs(manifest.seat['effective_total_width_mm']-144)>1e-5:raise RuntimeError('weld interface length changed')
 if not BRepTools.Write_s(shape,str(OUT/f'8P-R2-t{thickness:g}.brep')):raise RuntimeError('BREP write failed')
 manifest.to_json(OUT/f'8P-R2-t{thickness:g}-manifest.json')
 print('OCC validation: single valid solid, no shell interference; actual total weld interface',manifest.seat['effective_total_width_mm'])
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--thickness',type=float,default=15.);args=parser.parse_args();main(args.thickness)
