"""Preserve supplementary NTS geometry as explicitly labelled process illustrations."""
from pathlib import Path
import json
import fitz
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'cad/generated/engineering-drawings/pdf-paper'
OUT=ROOT/'cad/generated/final-entry-drawings'
FONT=ROOT/'assets/fonts/NotoSansSC-Regular.ttf'

def main():
    manifest=json.loads((SOURCE/'pdf-exports.json').read_text(encoding='utf8'))
    doc=fitz.open();items=[]
    for entry in manifest['sheets']:
        if entry['number'] in [1,2,3,4,8]:continue
        number=len(items)+1;title=entry['title'].replace('微珩','孔成形')
        with fitz.open(SOURCE/Path(entry['pdf']).name) as src:
            page=src[0];replacement=[]
            for block in page.get_text('dict')['blocks']:
                for ln in block.get('lines',[]):
                    for span in ln['spans']:
                        if '微珩' in span['text']:
                            replacement.append((fitz.Rect(span['bbox']),span['text'].replace('微珩','孔成形'),span['size']))
            # Rewrite terminology in the exported appendix only; keep all original SVG/PDF sources.
            for box,_,_ in replacement:page.add_redact_annot(box,fill=(1,1,1))
            if replacement:
                page.apply_redactions(graphics=0);page.insert_font(fontname='CN',fontfile=str(FONT))
                for box,text,size in replacement:
                    page.insert_text((box.x0,box.y1-2),text,fontname='CN',fontsize=min(size,box.width/max(len(text),1)),color=(0,0,0))
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
