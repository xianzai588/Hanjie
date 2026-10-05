"""Review HJ-015/016 with a bounded return-line hydraulic design.

The orifice equation alone does not qualify a real hose, valve or UT gel.
Geometry is recomputed; leakage/particle qualification remains outstanding.
"""
from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studies/COMPETITION-DESIGN'))
sys.path.insert(0,str(ROOT/'cad/parametric'))
from postweld_isolation import evaluate
from competition_drawings import postweld_isolation_sheet,postweld_cartridge_sheet
from export_drawing_pdfs import register_fonts,parse_css,export_sheet
import xml.etree.ElementTree as ET
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4,landscape


def build():
    out=ROOT/'output/cloud-20261005';out.mkdir(parents=True,exist_ok=True)
    geometry=evaluate()
    diameter=.0039;length=1.;mu=.005;density=1000.;dp=2000.;minor_K=10.
    area=math.pi*diameter**2/4
    linear=128*mu*length/(math.pi*diameter**4)
    quadratic=minor_K*density/(2*area**2)
    flow=2*dp/(linear+math.sqrt(linear**2+4*quadratic*dp))
    reynolds=density*(flow/area)*diameter/mu
    assert reynolds<2000
    capacity=flow*60e6
    model=dict(diameter_lower_mm=diameter*1000,line_length_upper_m=length,
        dynamic_viscosity_upper_mPa_s=mu*1000,density_kg_m3=density,
        total_minor_loss_K_upper=minor_K,net_pressure_lower_Pa=dp,
        gravity_head_credit_Pa=0.,return_capacity_ml_min=capacity,Reynolds=reynolds,
        required_capacity_ml_min=120.,capacity_design_condition_pass=capacity>=120,
        equation='dp = 128 mu L Q/(pi D^4) + K rho (Q/A)^2/2',
        pressure_definition='actual differential from cup outlet to bottle inlet after measurement uncertainty; cup gauge vacuum alone is insufficient',
        fluid_scope='Newtonian low-viscosity microhoning liquid within declared bound; not non-Newtonian UT gel',
        physical_flow_qualification=False,leakage_particle_qualification=False)
    result=dict(geometry=geometry,hydraulic=model,
        PT_UT_policy='metered bolus <=5 mL; drain/dry before next application; no UT-gel drain-rate credit without rheology and actual line qualification',
        release_status='design review C1; no product cleanliness claim')
    (out/'protection-design.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    register_fonts()
    for number,builder in [('HJ-015',postweld_isolation_sheet),('HJ-016',postweld_cartridge_sheet)]:
        source='\n'.join(builder({},{}))
        source=source.replace('工艺设计图 / 修订5','云端审阅 C1 / 未放行')
        source=source.replace('试制检验按说明书执行','实流量/颗粒/泄漏待资格')
        source=source.replace('供液≤60 mL/min；Ø4下引排液；吸压−2～−5 kPa',
            '供液≤60 mL/min；排液ID≥3.90/L≤1 m；μ≤5 mPa·s')
        source=source.replace('失吸0.10 s停进给/供液；管内可回流量≤5 mL',
            '净排液压差≥2 kPa；失压0.10 s停液/进给；管存≤5 mL')
        if number=='HJ-015':
            source=source.replace('加厚圈扣占位后容量47.73 mL；Ø4密闭回液',
                '容量47.73 mL；PT/UT单次≤5 mL；下次施液前抽尽')
            source=source.replace('正常产品：过程记录＋干态内窥＋封存；过滤膜提取只用于退出产品流的牺牲件',
                '正常产品禁整腔恢复清洗；UT凝胶不借用水的流量；牺牲件核验泄漏/颗粒/实排液')
        svg=out/f'{number}-cloud-review.svg';svg.write_text(source,encoding='utf8')
        root=ET.parse(svg).getroot();css=root.find('{http://www.w3.org/2000/svg}style').text
        pdf=out/f'{number}-cloud-review.pdf'
        c=Canvas(str(pdf),pagesize=landscape(A4),author='',title=f'{number} 云端工程设计审阅C1')
        export_sheet(svg,c,*landscape(A4),parse_css(css));c.showPage();c.save()
    return model


if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
