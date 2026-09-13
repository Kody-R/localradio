const $ = (id) => document.getElementById(id);
const base = window.location.origin;
let latest = null;
let previewObjectUrl = null;

function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmtTime(iso){if(!iso)return"";const d=new Date(iso);return Number.isNaN(d.getTime())?iso:d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});}
function fmtDate(iso){if(!iso)return"Never";const d=new Date(iso);return Number.isNaN(d.getTime())?iso:d.toLocaleString();}
function initials(name){return String(name||'LR').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();}
function filterText(s){const parts=[];if(s.min_year||s.max_year)parts.push(`Years ${s.min_year||'any'}–${s.max_year||'any'}`);if(s.genres_include)parts.push(`Genres: ${s.genres_include}`);if(s.genres_exclude)parts.push(`Exclude genres: ${s.genres_exclude}`);if(s.artists_include)parts.push(`Artists: ${s.artists_include}`);if(s.artists_exclude)parts.push(`Exclude artists: ${s.artists_exclude}`);return parts.join(' · ')||'All library tracks';}
function aiText(s){if(!s.dj_enabled)return'DJ breaks off';if(!s.ai_dj_enabled)return'Deterministic DJ templates';return`AI DJ · ${s.ai_model||latest?.ollama?.default_model||'default model'}`;}

function onAirContent(s,p){
  const cur=p.current;
  if(p.segment_type==='dj') return {label:'ON AIR · DJ BREAK',title:s.ai_dj_enabled?'AI DJ':'LocalRadio DJ',sub:p.announcement_text||`DJ break on ${s.name}`};
  if(p.segment_type==='station-id') return {label:'ON AIR · STATION ID',title:s.name,sub:p.announcement_text||'Prerecorded station imaging'};
  if(cur) return {label:'NOW PLAYING',title:cur.title||'Unknown Title',sub:cur.artist||'Unknown Artist'};
  return {label:'ON AIR',title:s.enabled?'Preparing broadcast…':'Station disabled',sub:p.last_error||''};
}

function stationCard(item){
  const s=item.station,p=item.playout,onAir=onAirContent(s,p),sch=p.schedule||{};
  const state=!s.enabled?'Disabled':p.running?'Broadcasting':'Offline';
  const stateClass=!s.enabled?'disabled':p.running?'online':'offline';
  const logo=s.logo_url?`<img class="station-logo" src="${esc(s.logo_url)}" alt="">`:`<div class="station-logo placeholder">${esc(initials(s.name))}</div>`;
  const next=p.next?`<div class="next-line">Next: ${esc(p.next.artist||'Unknown Artist')} — ${esc(p.next.title||'Unknown Title')}</div>`:'';
  const target=Number(sch.target_hours||latest?.schedule?.target_hours||24);
  const hours=Number(sch.hours||0);
  const schedState=sch.building?'building':hours>=Number(sch.minimum_hours||6)?'ready':'low';
  return `<article class="card station-card ${s.enabled?'':'disabled'}">
    <div class="station-accent"></div><div class="station-body">
      <div class="station-top"><div class="station-ident">${logo}<div><div class="station-name">${esc(s.name)}</div><div class="station-sub">Channel ${esc(s.channel_number||'—')} · /${esc(s.id)}</div></div></div><span class="pill ${stateClass}">${state}</span></div>
      <div class="now"><div class="now-label">${esc(onAir.label)}</div><div class="now-title">${esc(onAir.title)}</div><div class="now-artist">${esc(onAir.sub)}</div>${next}</div>
      <div class="station-metrics"><div class="mini"><span>Listeners</span><strong>${p.listeners}</strong></div><div class="mini"><span>Eligible</span><strong>${Number(p.eligible_tracks||0).toLocaleString()}</strong></div><div class="mini"><span>Schedule</span><strong>${hours.toFixed(1)}h</strong></div><div class="mini"><span>AI Queue</span><strong>${Number(sch.dj_entries||0)}</strong></div></div>
      <div class="schedule-bar"><div style="width:${Math.min(100,target?hours/target*100:0)}%"></div></div>
      <div class="filter-line">${esc(filterText(s))}</div>
      <div class="filter-line">${esc(aiText(s))} · ${esc(s.dj_voice||'auto TTS')} · schedule ${schedState}${sch.prepared_through?' through '+fmtTime(sch.prepared_through):''}</div>
      <div class="station-actions"><a class="button" href="/stream/${encodeURIComponent(s.id)}.mp3">Listen</a><button class="button" data-edit="${esc(s.id)}">Edit</button><button class="button" data-rebuild="${esc(s.id)}">Rebuild Schedule</button><span class="spacer"></span><button class="button" data-toggle="${esc(s.id)}" data-enabled="${s.enabled?'1':'0'}">${s.enabled?'Disable':'Enable'}</button></div>
    </div></article>`;
}

function renderTtsStatus(tts){
  if(!tts){$('ttsStatus').textContent='Unknown';return;}
  if(tts.piper_available && (tts.piper_voices||[]).length){$('ttsStatus').textContent=`Piper (${tts.piper_voices.length})`;return;}
  if(tts.espeak_available){$('ttsStatus').textContent='eSpeak NG';return;}
  $('ttsStatus').textContent='Offline';
}
function renderOllamaStatus(o){
  if(!o){$('ollamaStatus').textContent='Unknown';return;}
  $('ollamaStatus').textContent=o.online?`Online · ${o.default_model}`:(o.circuit_open?'Circuit open':'Offline');
  $('aiInfo').textContent=`Ollama: ${o.url} · Default model: ${o.default_model}${o.last_error&&!o.online?' · '+o.last_error:''}`;
}

async function refresh(){
  try{
    const r=await fetch('/api/status',{cache:'no-store'});latest=await r.json();
    $('tracks').textContent=latest.library.tracks.toLocaleString();
    $('artists').textContent=latest.library.artists.toLocaleString();
    $('stationCount').textContent=latest.stations.length.toLocaleString();
    $('listeners').textContent=latest.stations.reduce((n,x)=>n+(x.playout.listeners||0),0).toLocaleString();
    renderTtsStatus(latest.tts);renderOllamaStatus(latest.ollama);
    $('scanInfo').textContent=latest.scan.running?'Scanning music library…':`Last scan: ${fmtDate(latest.scan.last_scan)} · ${latest.library.albums.toLocaleString()} albums · schedule target ${latest.schedule.target_hours}h`;
    $('scanButton').disabled=!!latest.scan.running;
    $('m3uUrl').textContent=`${base}/playlist.m3u`;
    $('stations').innerHTML=latest.stations.length?latest.stations.map(stationCard).join(''):'<article class="card empty-network">No stations yet. Create your first station.</article>';
    bindStationActions();renderHistory(latest.recent);
  }catch(e){$('scanInfo').textContent='API unavailable';$('ttsStatus').textContent='Unknown';$('ollamaStatus').textContent='Unknown';}
}

function renderHistory(rows){const el=$('history');if(!rows.length){el.className='history empty';el.textContent='No plays recorded yet.';return;}el.className='history';el.innerHTML=rows.map(h=>`<div class="history-row"><div><div class="history-title">${esc(h.title||'Unknown Title')}<span class="station-tag">${esc(h.station_id||'legacy')}</span></div><div class="history-sub">${esc(h.artist||'Unknown Artist')}${h.album?' · '+esc(h.album):''}</div></div><div class="history-time">${esc(fmtTime(h.started_at))}</div></div>`).join('');}

function bindStationActions(){
  document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEditor(b.dataset.edit));
  document.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=()=>toggleStation(b.dataset.toggle,b.dataset.enabled==='1'));
  document.querySelectorAll('[data-rebuild]').forEach(b=>b.onclick=()=>rebuildSchedule(b.dataset.rebuild,b));
}
async function toggleStation(id,enabled){const item=latest?.stations.find(x=>x.station.id===id);if(!item)return;await fetch(`/api/stations/${encodeURIComponent(id)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...item.station,enabled:!enabled})});await refresh();}
async function rebuildSchedule(id,button){button.disabled=true;button.textContent='Rebuilding…';try{await fetch(`/api/stations/${encodeURIComponent(id)}/schedule/rebuild`,{method:'POST'});}finally{setTimeout(refresh,700);}}

function updateImagingPath(){const id=$('editId').value||$('stationId').value.trim()||'STATION-ID';$('imagingPath').textContent=`Save WAV/MP3/OGG files in /config/imaging/${id}/`;}
function clearForm(){
  $('editId').value='';$('name').value='';$('stationId').value='';$('stationId').disabled=false;$('channelNumber').value='';$('enabled').checked=true;
  $('minYear').value='0';$('maxYear').value='0';$('genresInclude').value='';$('genresExclude').value='';$('artistsInclude').value='';$('artistsExclude').value='';
  $('artistRepeat').value='90';$('songRepeat').value='12';$('logoUrl').value='';
  $('aiDjEnabled').checked=true;$('aiModel').value='';$('aiMaxWords').value='40';$('aiPersonality').value='Friendly, concise local radio DJ. Natural and upbeat without sounding exaggerated.';
  $('djEnabled').checked=true;$('djMinSongs').value='3';$('djMaxSongs').value='5';$('djVoice').value='';$('djSpeed').value='165';$('stationSlogan').value='';
  $('stationIdEnabled').checked=true;$('stationIdEverySongs').value='8';$('stationLiners').value='';
  $('deleteStation').hidden=true;$('formMessage').hidden=true;$('previewAudio').hidden=true;updateImagingPath();
}
function openNew(){clearForm();$('dialogTitle').textContent='New Station';$('stationDialog').showModal();}
async function openEditor(id){
  const r=await fetch(`/api/stations/${encodeURIComponent(id)}`);if(!r.ok)return;const {station:s}=await r.json();clearForm();
  $('dialogTitle').textContent=`Edit ${s.name}`;$('editId').value=s.id;$('name').value=s.name;$('stationId').value=s.id;$('stationId').disabled=true;$('channelNumber').value=s.channel_number;$('enabled').checked=s.enabled;
  $('minYear').value=s.min_year;$('maxYear').value=s.max_year;$('genresInclude').value=s.genres_include;$('genresExclude').value=s.genres_exclude;$('artistsInclude').value=s.artists_include;$('artistsExclude').value=s.artists_exclude;
  $('artistRepeat').value=s.artist_repeat_minutes;$('songRepeat').value=s.song_repeat_hours;$('logoUrl').value=s.logo_url;
  $('aiDjEnabled').checked=s.ai_dj_enabled;$('aiModel').value=s.ai_model||'';$('aiMaxWords').value=s.ai_max_words||40;$('aiPersonality').value=s.ai_personality||'';
  $('djEnabled').checked=s.dj_enabled;$('djMinSongs').value=s.dj_min_songs;$('djMaxSongs').value=s.dj_max_songs;$('djVoice').value=s.dj_voice||'';$('djSpeed').value=s.dj_speed_wpm;$('stationSlogan').value=s.station_slogan||'';
  $('stationIdEnabled').checked=s.station_id_enabled;$('stationIdEverySongs').value=s.station_id_every_songs;$('stationLiners').value=s.station_liners||'';
  $('deleteStation').hidden=false;updateImagingPath();$('stationDialog').showModal();
}
function payload(){return {
  id:$('stationId').value.trim(),name:$('name').value.trim(),channel_number:$('channelNumber').value.trim(),enabled:$('enabled').checked,
  min_year:Number($('minYear').value||0),max_year:Number($('maxYear').value||0),genres_include:$('genresInclude').value.trim(),genres_exclude:$('genresExclude').value.trim(),artists_include:$('artistsInclude').value.trim(),artists_exclude:$('artistsExclude').value.trim(),
  artist_repeat_minutes:Number($('artistRepeat').value||0),song_repeat_hours:Number($('songRepeat').value||0),logo_url:$('logoUrl').value.trim(),
  ai_dj_enabled:$('aiDjEnabled').checked,ai_model:$('aiModel').value.trim(),ai_max_words:Number($('aiMaxWords').value||40),ai_personality:$('aiPersonality').value.trim(),
  dj_enabled:$('djEnabled').checked,dj_min_songs:Number($('djMinSongs').value||3),dj_max_songs:Number($('djMaxSongs').value||5),dj_voice:$('djVoice').value.trim(),dj_speed_wpm:Number($('djSpeed').value||165),station_slogan:$('stationSlogan').value.trim(),
  station_id_enabled:$('stationIdEnabled').checked,station_id_every_songs:Number($('stationIdEverySongs').value||8),station_liners:$('stationLiners').value.trim()
};}

async function previewVoice(){
  const button=$('previewVoice');button.disabled=true;$('formMessage').hidden=true;
  const name=$('name').value.trim()||'LocalRadio';const slogan=$('stationSlogan').value.trim();
  const text=`You're listening to ${name}.${slogan?' '+slogan+'.':''} More music is coming up next.`;
  try{
    const r=await fetch('/api/tts/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,voice:$('djVoice').value.trim(),speed_wpm:Number($('djSpeed').value||165)})});
    if(!r.ok)throw new Error('TTS preview could not be generated.');
    const blob=await r.blob();if(previewObjectUrl)URL.revokeObjectURL(previewObjectUrl);previewObjectUrl=URL.createObjectURL(blob);
    $('previewAudio').src=previewObjectUrl;$('previewAudio').hidden=false;await $('previewAudio').play();
  }catch(e){showFormMessage(e.message||'Could not play voice preview.');}finally{button.disabled=false;}
}
function showFormMessage(msg,ok=false){$('formMessage').hidden=false;$('formMessage').textContent=msg;$('formMessage').classList.toggle('ok',ok);}
async function testOllama(model,button){button.disabled=true;const old=button.textContent;button.textContent='Testing…';try{const r=await fetch('/api/ollama/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:model||''})});const d=await r.json();if(!r.ok)throw new Error(d.status?.last_error||'Ollama test failed');if(button.id==='testStationOllama')showFormMessage(`${d.model}: ${d.text}`,true);else alert(`${d.model}: ${d.text}`);}catch(e){if(button.id==='testStationOllama')showFormMessage(e.message||'Ollama test failed');else alert(e.message||'Ollama test failed');}finally{button.disabled=false;button.textContent=old;refresh();}}

$('stationForm').addEventListener('submit',async e=>{e.preventDefault();const edit=$('editId').value;const url=edit?`/api/stations/${encodeURIComponent(edit)}`:'/api/stations';const data=payload();if(data.dj_max_songs<data.dj_min_songs)data.dj_max_songs=data.dj_min_songs;const r=await fetch(url,{method:edit?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(!r.ok){showFormMessage('Could not save the station.');return;}$('stationDialog').close();await refresh();});
$('deleteStation').addEventListener('click',async()=>{const id=$('editId').value;if(!id||!confirm('Delete this station? Its historical play records will remain in the database.'))return;const r=await fetch(`/api/stations/${encodeURIComponent(id)}`,{method:'DELETE'});if(r.ok){$('stationDialog').close();await refresh();}});
$('scanButton').addEventListener('click',async()=>{$('scanButton').disabled=true;try{await fetch('/api/scan',{method:'POST'});}finally{setTimeout(refresh,500);}});
$('testOllama').onclick=()=>testOllama('', $('testOllama'));
$('testStationOllama').onclick=()=>testOllama($('aiModel').value.trim(),$('testStationOllama'));
$('newStation').onclick=openNew;$('closeDialog').onclick=()=>$('stationDialog').close();$('cancelDialog').onclick=()=>$('stationDialog').close();$('previewVoice').onclick=previewVoice;$('stationId').addEventListener('input',updateImagingPath);

async function loadOptions(){
  try{
    const [libR,ttsR,ollamaR]=await Promise.all([fetch('/api/library/options'),fetch('/api/tts'),fetch('/api/ollama')]);
    const d=await libR.json(),t=await ttsR.json(),o=await ollamaR.json();
    $('genreOptions').innerHTML=d.genres.slice(0,200).map(x=>`<option value="${esc(x.genre)}">`).join('');
    $('artistOptions').innerHTML=d.artists.slice(0,500).map(x=>`<option value="${esc(x.artist)}">`).join('');
    const voices=[...(t.piper_voices||[]),'en-us','en','en-gb'];$('voiceOptions').innerHTML=[...new Set(voices)].map(v=>`<option value="${esc(v)}">`).join('');
    const models=[o.default_model,...(o.models||[])].filter(Boolean);$('modelOptions').innerHTML=[...new Set(models)].map(v=>`<option value="${esc(v)}">`).join('');
  }catch(e){}
}
loadOptions();refresh();setInterval(refresh,5000);
