"""Actualiza solo los bloques de respaldo del comparador a partir del JSON."""
import json,re
from html import escape
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent

def main():
    data=json.loads((ROOT/'tasas-datos.json').read_text())
    if data.get('version')!=1 or not isinstance(data.get('lineas'),list):raise ValueError('Esquema no válido')
    ids=[x['id'] for x in data['lineas']]
    if len(ids)!=len(set(ids)):raise ValueError('Identificadores repetidos')
    if any(x['entidad']=='CFI' for x in data['lineas']):raise ValueError('CFI excluido del alcance')
    now=datetime.now(timezone.utc)
    ready=[]
    for x in data['lineas']:
        expiry=datetime.fromisoformat(x['vence']+'T23:59:59-03:00') if x.get('vence') else None
        fresh=(now-datetime.fromisoformat(x['consultado'])).total_seconds()<=7*86400
        if x.get('tasa_completa') and x['estado']=='Vigencia confirmada' and fresh and (not expiry or expiry>=now):ready.append(x)
    cards=[]
    for x in ready:
        if not x['fuente'].startswith('https://'):raise ValueError('Enlace inseguro')
        cards.append('<article class="card"><div class="bank">'+escape(x['entidad'])+' · '+escape(x['region'])+'</div><h3>'+escape(x['linea'])+'</h3><span class="badge">'+escape(x.get('destino',''))+'</span><p class="rate">'+escape(x['tasa'])+'</p><p>'+escape(x['condiciones'])+'</p><small>'+escape(x['vigencia'])+'</small><a href="'+escape(x['fuente'],quote=True)+'" target="_blank" rel="noopener noreferrer">Fuente oficial ↗</a></article>')
    h=(ROOT/'tasas.html').read_text()
    def replace(pattern,value):
        nonlocal h
        h,n=re.subn(pattern,lambda m:value,h,count=1,flags=re.S)
        if n!=1:raise ValueError('Bloque de respaldo no encontrado: '+pattern)
    replace(r'<!-- BEGIN SAVED ROWS -->.*?<!-- END SAVED ROWS -->','<!-- BEGIN SAVED ROWS -->'+(''.join(cards) or '<p class="empty">Sin condiciones completas verificadas. Consultá Pendientes.</p>')+'<!-- END SAVED ROWS -->')
    replace(r'<script id="saved-report" type="application/json">.*?</script>','<script id="saved-report" type="application/json">'+json.dumps(data,ensure_ascii=False).replace('<','\\u003c')+'</script>')
    for key,value in [('total',len(data['lineas'])),('ready',len(ready)),('pendingCount',len(data['lineas'])-len(ready)),('banks',len(set(x['entidad'] for x in data['lineas'])))]:replace(r'<b id="'+key+r'">.*?</b>','<b id="'+key+'">'+str(value)+'</b>')
    for key,value in [('summary',data['resumen']),('coverage',data['cobertura'])]:replace(r'<p id="'+key+r'">.*?</p>','<p id="'+key+'">'+escape(value)+'</p>')
    (ROOT/'tasas.html').write_text(h)

if __name__=='__main__':main()
