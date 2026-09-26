"""Consulta fuentes públicas, compara huellas y conserva fallos sin borrar la base.
No interpreta una modificación de contenido como un cambio confirmado de tasa.
"""
import concurrent.futures
import hashlib
import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMIT = 8 * 1024 * 1024

class PublicText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=[]
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style','nav','footer','header','noscript'}: self.skip.append(tag)
        if tag in {'p','li','tr','h1','h2','h3','h4','br','div'} and not self.skip:self.parts.append('\n')
    def handle_endtag(self, tag):
        if self.skip and tag==self.skip[-1]:self.skip.pop()
    def handle_data(self, data):
        if not self.skip:self.parts.append(data)

def extract(body, content_type):
    if body.startswith(b'%PDF'):
        from pypdf import PdfReader
        return '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(body)).pages)
    if 'html' not in content_type:raise ValueError('Formato de documento no reconocido')
    parser=PublicText();parser.feed(body.decode('utf-8',errors='replace'))
    return ''.join(parser.parts)

def fingerprint(text):
    lines=[' '.join(x.split()) for x in text.splitlines() if x.strip()]
    relevant=[x for x in lines if re.search(r'tasa|tna|tea|cft|plazo|gracia|monto|garant|millones|inversi|capital|leasing|vigencia|bonific',x,re.I)]
    if len(relevant)<3 or len(text)<150:raise ValueError('Contenido insuficiente; puede requerir revisión manual')
    normalized='\n'.join(relevant)
    return hashlib.sha256(normalized.encode()).hexdigest(),len(relevant)

def fetch_source(source):
    req=urllib.request.Request(source['url'],headers={'User-Agent':'FP2026-FinanceMonitor/1.0 (daily public-source review)'})
    with urllib.request.urlopen(req,timeout=22) as response:
        body=response.read(LIMIT+1)
        if len(body)>LIMIT:raise ValueError('Documento supera el límite de lectura')
        text=extract(body,response.headers.get_content_type())
        lower=text.lower()
        if any(x in lower for x in ('verify you are human','checking your browser','captcha challenge')):raise ValueError('Fuente solicita verificación de acceso')
        return fingerprint(text)

def transition(source, previous, now, result=None, error=None):
    row={**previous,**source,'ultimo_intento':now}
    if error:
        row.update(estado='error',error=error)
        return row
    digest,count=result
    changed=bool(previous.get('huella') and previous['huella']!=digest)
    row.update(estado='ok',error=None,ultima_consulta_correcta=now,huella=digest,bloques_relevantes=count)
    if changed:row.update(cambio_pendiente=True,ultimo_cambio_detectado=now,huella_anterior=previous['huella'])
    else:row.setdefault('cambio_pendiente',False)
    row.setdefault('primera_consulta',now)
    return row

def main():
    sources=json.loads((ROOT/'tasas-fuentes.json').read_text())
    path=ROOT/'monitor-fuentes.json'
    old=json.loads(path.read_text()) if path.exists() else {'fuentes':[],'historial':[]}
    previous={s['id']:s for s in old.get('fuentes',[])}
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    def check(s):
        try:return transition(s,previous.get(s['id'],{}),now,result=fetch_source(s))
        except Exception as e:
            message=f'HTTP {e.code}' if hasattr(e,'code') else str(e)[:180]
            return transition(s,previous.get(s['id'],{}),now,error=message)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(check,sources))
    history=old.get('historial',[])
    history.append({'fecha':now,'correctas':sum(r['estado']=='ok' for r in rows),'total':len(rows),'cambios_detectados':[r['id'] for r in rows if r.get('ultimo_cambio_detectado')==now],'fallidas':[r['id'] for r in rows if r['estado']=='error']})
    result={'version':1,'actualizado':now,'fuentes':rows,'historial':history}
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
    print(json.dumps(history[-1],ensure_ascii=False))

if __name__=='__main__':main()
