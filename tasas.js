'use strict';
let report;
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const date = value => value && Number.isFinite(Date.parse(value)) ? new Date(value.length === 10 ? value + 'T12:00:00-03:00' : value).toLocaleString('es-AR',{timeZone:'America/Argentina/Cordoba'}) : 'Sin fecha';
const link = url => {try {const u=new URL(url);return u.protocol==='https:' ? `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">Fuente oficial ↗</a>` : '';} catch {return '';}};
function rows(){
 const q=$('query').value.toLocaleLowerCase('es').trim();
 const items=report.lineas.filter(x=>(!$('entity').value||x.entidad===$('entity').value)&&(!$('state').value||x.estado===$('state').value)&&(!q||JSON.stringify(x).toLocaleLowerCase('es').includes(q)));
 $('count').textContent=`${items.length} de ${report.lineas.length} líneas relevadas`;
 $('rows').innerHTML=items.map(x=>`<tr><td><strong>${esc(x.entidad)}</strong><p>${esc(x.linea)}</p><small>${esc(x.region)}</small></td><td><strong>${esc(x.tasa)}</strong><small>TEA: ${esc(x.tea||'No informada')} · CFT: ${esc(x.cft||'No informado')}</small><p>${esc(x.modalidad)}</p></td><td>${esc(x.condiciones)}<p><small>Garantías: ${esc(x.garantias)}</small></p></td><td><span class="badge">${esc(x.estado)}</span><small>Consultado: ${date(x.consultado)}</small><small>Vigencia: ${esc(x.vigencia||'No explicitada')}</small>${link(x.fuente)}<p class="warning">${esc(x.observacion)}</p></td></tr>`).join('');
 $('empty').hidden=items.length>0;
}
async function load(){
 $('reload').disabled=true;
 try{
  const response=await fetch('./tasas-datos.json?v='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);
  const data=await response.json();if(data.version!==1||!Array.isArray(data.lineas)||!Array.isArray(data.historial)||!Array.isArray(data.novedades))throw Error('Formato inválido');report=data;
  $('status').textContent='Última consulta: '+date(report.actualizado);
  $('summary').textContent=report.resumen;$('coverage').textContent=report.cobertura;
  $('stale').hidden=Number.isFinite(Date.parse(report.actualizado))&&Date.now()-Date.parse(report.actualizado)<48*3600000;
  const selected=$('entity').value;$('entity').innerHTML='<option value="">Todas las entidades</option>'+[...new Set(report.lineas.map(x=>x.entidad))].sort().map(x=>`<option>${esc(x)}</option>`).join('');if([...$('entity').options].some(x=>x.value===selected))$('entity').value=selected;
  rows();
  $('news').innerHTML=report.novedades.length?report.novedades.map(x=>`<article><small>${esc(x.tipo)} · ${date(x.fecha)}</small><h3>${esc(x.titulo)}</h3><p>${esc(x.detalle)}</p><p><strong>Revisar:</strong> ${esc(x.impacto)}</p>${link(x.fuente)}</article>`).join(''):'<p class="empty">Sin novedades verificadas en esta revisión.</p>';
  $('history').innerHTML=report.historial.slice().reverse().map(x=>`<details><summary>${date(x.fecha)} · ${esc(x.resumen)}</summary><p>${esc(x.detalle)}</p>${(x.lineas||[]).map(l=>`<p><strong>${esc(l.entidad)} — ${esc(l.linea)}:</strong> ${esc(l.tasa)}. ${esc(l.condiciones)} ${link(l.fuente)}</p>`).join('')}</details>`).join('')||'<p>Sin revisiones anteriores.</p>';
 }catch(error){$('status').textContent='No se pudo cargar la revisión. '+(report?'Se mantienen los datos anteriores; pueden estar desactualizados.':'Probá recargar en unos minutos.');$('status').classList.add('warning');}finally{$('reload').disabled=false;}
}
['query','entity','state'].forEach(id=>$(id).addEventListener(id==='query'?'input':'change',()=>{if(report)rows();}));$('reload').addEventListener('click',load);load();
