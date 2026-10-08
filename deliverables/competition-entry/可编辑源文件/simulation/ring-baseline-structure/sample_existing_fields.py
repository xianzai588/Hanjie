"""Export a common 128-angle x 11-height virtual FE bore inspection grid."""
import csv
import argparse
import json
from pathlib import Path
import numpy as np
import run_ring_structure as base
from bore_sampling import sample_surface,sample_quarter

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels",nargs="+",choices=("coarse","medium","fine","p2-linear-coarse","p2-linear-medium"),
                        default=("p2-linear-coarse","p2-linear-medium"),
                        help="Explicit completed field snapshots to sample; defaults to the current P2 family")
    args=parser.parse_args()
    theta=np.linspace(-np.pi,np.pi,128,endpoint=False);z=np.linspace(100.,115.,11)
    for level in args.levels:
        folder=HERE/"results"/level
        if not (folder/"result.json").exists() or not (folder/"mesh.npz").exists():
            raise RuntimeError(f"{level}: requested raw result/mesh is missing; rerun its FE calculation before sampling")
        mesh=dict(np.load(folder/"mesh.npz"));p=mesh["points"]
        p2=folder.name.startswith("p2-")
        if not p2:
            tri=mesh["triangles"];r=np.linalg.norm(p[tri][:,:,:2],axis=2);bore=tri[np.all(abs(r-20.)<1e-5,axis=1)]
        else:bore=mesh["bore_triangles6"]
        values={};metrics={}
        for name in ("radial","axial","overturning") if p2 else ("radial","axial","overturning","combined"):
            source=folder/(f"{name}-quarter-displacement.npz" if p2 else f"{name}-field.npz")
            u=np.load(source)["displacement_mm"]
            q,v=sample_quarter(p,bore,u,theta,z,name) if p2 else sample_surface(p,bore,u,theta,z,1)
            values[name]=v
        if p2:values["combined"]=sum(values.values())
        with (folder/"bore-uniform-virtual-displacement.csv").open("w") as stream:
            writer=csv.writer(stream);writer.writerow(["case","theta_deg","z_mm","x_mm","y_mm","ux_um","uy_um","uz_um","evidence_kind"])
            for name,v in values.items():
                metrics[name]=base.bore_metrics(q,v,np.arange(len(q)))
                writer.writerows([[name,float(np.rad2deg(np.arctan2(a[1],a[0]))),a[2],a[0],a[1],*b,"simulation_virtual_sample"] for a,b in zip(q,1000*v)])
        raw=json.loads((folder/"result.json").read_text())
        record={"source_input_identity":raw.get("input_identity",raw.get("analysis_inputs")),
                "source_process_version":raw.get("process_version",raw.get("analysis_inputs",{}).get("process_version")),
                "sampling":"128 equally spaced angles x 11 equally spaced heights; ray intersection of actual P1/P2 FE bore faces; same sample grid at every resolution",
                "sample_count":len(q),"interpolation_order":2 if p2 else 1,"cases":metrics,
                "coordinate_reference":"nominal R20 cylinder directions; displacement interpolated on the actual faceted FE bore surface"}
        (folder/"virtual-bore-summary.json").write_text(json.dumps(record,indent=2))
        print(folder.name,metrics["combined"]["axis_diameter_envelope_um"],metrics["combined"]["cylindrical_radial_peak_to_valley_um"])


if __name__=="__main__":main()
