"""Preserve supplementary NTS geometry as explicitly labelled process illustrations."""
from pathlib import Path
import json
import fitz
import re
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'cad/generated/engineering-drawings/pdf-paper'
OUT=ROOT/'cad/generated/final-entry-drawings'
FONT=ROOT/'assets/fonts/NotoSansSC-Regular.ttf'

def display_text(text):
    text=text.replace('微珩','孔成形').replace('2026-10-08','2026-10-11')
    text=text.replace('退位另须温度<55℃、颗粒检查合格；枪丝先升150，再副环升150。',
        '退位：<55℃且颗粒合格；枪丝升40、避让至150，再副环升150。')
    text=text.replace('段间枪丝升150后转位：全工具z≥265.2～370，越工作臂顶245。',
        '枪丝先升40周向避让，再升至150转位；角度及许可见HJ-C-03。')
    text=text.replace('89.415','89.41')  # Display the unrounded result already tabulated in HJ-W-00E.
    text=text.replace('0.075～0.07875 L/min','75.00～78.75 mL/min')
    text=text.replace('外圆同轴≤0.003','外圆同轴≤3.0 μm')
    text=text.replace('制造端面极差≤0.0025；含热差≤0.003','制造端面极差≤2.5 μm；含热差≤3.0 μm')
    text=text.replace('4. 本图为加工公差实体；带残余应力的实际去料/重平衡须接续有效冷态制造状态。',
        '4. 本图用于预制层修整；最终孔在装夹态一次成形，孔轴及卸夹回弹按首件计划校准。')
    # Numerical readouts only. Preserve fit/tolerance windows and all geometry.
    values={'19.074':2,'0.942':1,'86.394':2,'20.957':2,'18.803':2,
        '13.203':1,'2.155':2,'154.510':1,'151.703':1,'176.157710':2,
        '1.566042':2,'0.164543':2,'0.009813':2,'0.9156':2,
        '0.324':2,'0.510':2,'2.374':2,'0.095':2}
    # The nine-row volume table is displayed at the same precision as its card.
    values.update({v:2 for v in ('163.441','84.755','78.686','153.124','78.478','74.646',
        '150.657','77.390','73.267','89.415','63.709','88.159','62.498','176.158',
        '80.985','95.173','173.674','79.909','93.766','92.308','83.850','91.066','82.608')})
    text=text.replace('0.095','0.09')  # Round the minimum installation clearance downward.
    return re.sub(r'\d+\.\d+',lambda m:f'{float(m[0]):.{values[m[0]]}f}' if m[0] in values else m[0],text)

def main():
    manifest=json.loads((SOURCE/'pdf-exports.json').read_text(encoding='utf8'))
    doc=fitz.open();items=[];annotation_font=fitz.Font(fontfile=str(FONT))
    for entry in manifest['sheets']:
        if entry['number'] in [1,2,3,4,8]:continue
        number=len(items)+1;title=entry['title'].replace('微珩','孔成形')
        with fitz.open(SOURCE/Path(entry['pdf']).name) as src:
            page=src[0];replacement=[]
            for block in page.get_text('dict')['blocks']:
                for ln in block.get('lines',[]):
                    for span in ln['spans']:
                        revised=display_text(span['text'])
                        if revised!=span['text']:
                            replacement.append((fitz.Rect(span['bbox']),revised,span['size'],span['origin']))
            # Rewrite exported annotations only; preserve original geometry and sources.
            for box,_,_,_ in replacement:page.add_redact_annot(box,fill=(1,1,1))
            if replacement:
                page.apply_redactions(graphics=0);page.insert_font(fontname='CN',fontfile=str(FONT))
                for box,text,size,origin in replacement:
                    width=annotation_font.text_length(text,fontsize=size)
                    fitted_size=size*min(1,box.width/max(width,1))
                    page.insert_text(origin,text,fontname='CN',fontsize=fitted_size,color=(0,0,0))
            dest=doc.new_page(width=420*72/25.4,height=297*72/25.4)
            dest.insert_font(fontname='CN',fontfile=str(FONT))
            dest.insert_text((35,31),f'附图 I{number:02}  {title}',fontname='CN',fontsize=13)
            dest.insert_text((35,50),'用途：工序、结构接口及操作功能示意（NTS）；制造尺寸以HJ-F01～05及现行工艺卡为准。',fontname='CN',fontsize=9)
            dest.show_pdf_page(fitz.Rect(26,65,dest.rect.width-26,dest.rect.height-26),src,0)
            items.append(dict(number=number,title=title,source=entry['pdf'],purpose='Process/interface illustration, NTS'))
    doc.set_metadata({'title':'附录C 工艺与工装功能示意（18张NTS附图）','author':''})
    doc.save(OUT/'process-illustrations.pdf',garbage=4,deflate=True);doc.close()
    (OUT/'illustrations.json').write_text(json.dumps(dict(count=len(items),items=items),ensure_ascii=False,indent=2),encoding='utf8')
    print('NTS process illustrations:',len(items))
if __name__=='__main__':main()
