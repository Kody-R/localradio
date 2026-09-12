const $ = (id) => document.getElementById(id);
const base = window.location.origin;
let latest = null;

function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmtTime(iso){if(!iso)return"";const d=new Date(iso);return Number.isNaN(d.getTime())?iso:d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});}
function fmtDate(iso){if(!iso)return"Never";const d=new Date(iso);return Number.isNaN(d.getTime())?iso:d.toLocaleString();}
function initials(name){return String(name||'LR').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();}
function filterText(s){const parts=[];if(s.min_year||s.max_year)parts.push(`Years ${s.min_year||'any'}–${s.max_year||'any'}`);if(s.genres_include)parts.push(`Genres: ${s.genres_include}`);if(s.genres_exclude)parts.push(`Exclude genres: ${s.genres_exclude}`);if(s.artists_include)parts.push(`Artists: ${s.artists_include}`);if(s.artists_exclude)parts.push(`Exclude artists: ${s.artists_exclude}`);return parts.join(' · ')||'All library tracks';}

function stationCard(item){
  const s=item.station,p=item.playout,cur=p.current;
  const state=!s.enabled?'Disabled':p.running?'Broadcasting':'Offline';
  const stateClass=!s.enabled?'disabled':p.running?'online':'offline';
  const logo=s.logo_url?`<img class="station-logo" src="${esc(s.logo_url)}" alt="">`:`<div class="station-logo placeholder">${esc(initials(s.name))}</div>`;
  return `<article class="card station-card ${s.enabled?'':'disabled'}">
    <div class="station-accent"></div><div class="station-body">
      <div class="station-top"><div class="station-ident">${logo}<div><div class="station-name">${esc(s.name)}</div><div class="station-sub">Channel ${esc(s.channel_number||'—')} · /${esc(s.id)}</div></div></div><span class="pill ${stateClass}">${state}</span></div>
      <div class="now"><div class="now-label">NOW PLAYING</div><div class="now-title">${esc(cur?.title||(s.enabled?'Preparing broadcast…':'Station disabled'))}</div><div class="now-artist">${esc(cur?.artist||(p.last_error||''))}</div></div>
      <div class="station-metrics"><div class="mini"><span>Listeners</span><strong>${p.listeners}</strong></div><div class="mini"><span>Eligible</span><strong>${Number(p.eligible_tracks||0).toLocaleString()}</strong></div><div class="mini"><span>Played</span><strong>${p.tracks_played_this_run}</strong></div></div>
      <div class="filter-line">${esc(filterText(s))}</div>
      <div class="station-actions"><a class="button" href="/stream/${encodeURIComponent(s.id)}.mp3">Listen</a><button class="button" data-edit="${esc(s.id)}">Edit</button><span class="spacer"></span><button class="button" data-toggle="${esc(s.id)}" data-enabled="${s.enabled?'1':'0'}">${s.enabled?'Disable':'Enable'}</button></div>
    </div></article>`;
}

async function refresh(){
  try{
    const r=await fetch('/api/status',{cache:'no-store'});latest=await r.json();
    $('tracks').textContent=latest.library.tracks.toLocaleString();
    $('artists').textContent=latest.library.artists.toLocaleString();
    $('stationCount').textContent=latest.stations.length.toLocaleString();
    $('listeners').textContent=latest.stations.reduce((n,x)=>n+(x.playout.listeners||0),0).toLocaleString();
    $('scanInfo').textContent=latest.scan.running?'Scanning music library…':`Last scan: ${fmtDate(latest.scan.last_scan)} · ${latest.library.albums.toLocaleString()} albums`;
    $('scanButton').disabled=!!latest.scan.running;
    $('m3uUrl').textContent=`${base}/playlist.m3u`;
    $('stations').innerHTML=latest.stations.length?latest.stations.map(stationCard).join(''):'<article class="card empty-network">No stations yet. Create your first station.</article>';
    bindStationActions();renderHistory(latest.recent);
  }catch(e){$('scanInfo').textContent='API unavailable';}
}

function renderHistory(rows){const el=$('history');if(!rows.length){el.className='history empty';el.textContent='No plays recorded yet.';return;}el.className='history';el.innerHTML=rows.map(h=>`<div class="history-row"><div><div class="history-title">${esc(h.title||'Unknown Title')}<span class="station-tag">${esc(h.station_id||'legacy')}</span></div><div class="history-sub">${esc(h.artist||'Unknown Artist')}${h.album?' · '+esc(h.album):''}</div></div><div class="history-time">${esc(fmtTime(h.started_at))}</div></div>`).join('');}

function bindStationActions(){
  document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEditor(b.dataset.edit));
  document.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=()=>toggleStation(b.dataset.toggle,b.dataset.enabled==='1'));
}

async function toggleStation(id,enabled){const item=latest?.stations.find(x=>x.station.id===id);if(!item)return;await fetch(`/api/stations/${encodeURIComponent(id)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...item.station,enabled:!enabled})});await refresh();}

function clearForm(){
  $('editId').value='';$('name').value='';$('stationId').value='';$('stationId').disabled=false;$('channelNumber').value='';$('enabled').checked=true;$('minYear').value='0';$('maxYear').value='0';$('genresInclude').value='';$('genresExclude').value='';$('artistsInclude').value='';$('artistsExclude').value='';$('artistRepeat').value='90';$('songRepeat').value='12';$('logoUrl').value='';$('deleteStation').hidden=true;$('formMessage').hidden=true;
}
function openNew(){clearForm();$('dialogTitle').textContent='New Station';$('stationDialog').showModal();}
async function openEditor(id){const r=await fetch(`/api/stations/${encodeURIComponent(id)}`);if(!r.ok)return;const {station:s}=await r.json();clearForm();$('dialogTitle').textContent=`Edit ${s.name}`;$('editId').value=s.id;$('name').value=s.name;$('stationId').value=s.id;$('stationId').disabled=true;$('channelNumber').value=s.channel_number;$('enabled').checked=s.enabled;$('minYear').value=s.min_year;$('maxYear').value=s.max_year;$('genresInclude').value=s.genres_include;$('genresExclude').value=s.genres_exclude;$('artistsInclude').value=s.artists_include;$('artistsExclude').value=s.artists_exclude;$('artistRepeat').value=s.artist_repeat_minutes;$('songRepeat').value=s.song_repeat_hours;$('logoUrl').value=s.logo_url;$('deleteStation').hidden=false;$('stationDialog').showModal();}
function payload(){return {id:$('stationId').value.trim(),name:$('name').value.trim(),channel_number:$('channelNumber').value.trim(),enabled:$('enabled').checked,min_year:Number($('minYear').value||0),max_year:Number($('maxYear').value||0),genres_include:$('genresInclude').value.trim(),genres_exclude:$('genresExclude').value.trim(),artists_include:$('artistsInclude').value.trim(),artists_exclude:$('artistsExclude').value.trim(),artist_repeat_minutes:Number($('artistRepeat').value||0),song_repeat_hours:Number($('songRepeat').value||0),logo_url:$('logoUrl').value.trim()};}

$('stationForm').addEventListener('submit',async e=>{e.preventDefault();const edit=$('editId').value;const url=edit?`/api/stations/${encodeURIComponent(edit)}`:'/api/stations';const r=await fetch(url,{method:edit?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});if(!r.ok){$('formMessage').hidden=false;$('formMessage').textContent='Could not save the station.';return;}$('stationDialog').close();await refresh();});
$('deleteStation').addEventListener('click',async()=>{const id=$('editId').value;if(!id||!confirm('Delete this station? Its historical play records will remain in the database.'))return;const r=await fetch(`/api/stations/${encodeURIComponent(id)}`,{method:'DELETE'});if(r.ok){$('stationDialog').close();await refresh();}});
$('scanButton').addEventListener('click',async()=>{$('scanButton').disabled=true;try{await fetch('/api/scan',{method:'POST'});}finally{setTimeout(refresh,500);}});
$('newStation').onclick=openNew;$('closeDialog').onclick=()=>$('stationDialog').close();$('cancelDialog').onclick=()=>$('stationDialog').close();

async function loadOptions(){try{const r=await fetch('/api/library/options');const d=await r.json();$('genreOptions').innerHTML=d.genres.slice(0,200).map(x=>`<option value="${esc(x.genre)}">`).join('');$('artistOptions').innerHTML=d.artists.slice(0,500).map(x=>`<option value="${esc(x.artist)}">`).join('');}catch(e){}}
loadOptions();refresh();setInterval(refresh,3000);
