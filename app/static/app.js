const $ = (id) => document.getElementById(id);
const base = window.location.origin;
const stationId = document.body.dataset.stationId || "localradio";
$("m3uUrl").textContent = `${base}/playlist.m3u`;
$("streamUrl").textContent = `${base}/stream/${stationId}.mp3`;

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
}
function fmtDate(iso) {
  if (!iso) return "Never";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

async function refresh() {
  try {
    const r = await fetch('/api/status', {cache:'no-store'});
    const s = await r.json();
    const up = !!s.playout.running;
    const pill = $('statusPill');
    pill.textContent = up ? '● Broadcasting' : '○ Offline';
    pill.className = `pill ${up ? 'online' : 'offline'}`;

    $('tracks').textContent = s.library.tracks.toLocaleString();
    $('artists').textContent = s.library.artists.toLocaleString();
    $('albums').textContent = s.library.albums.toLocaleString();
    $('listeners').textContent = s.playout.listeners.toLocaleString();
    $('bitrate').textContent = `${s.station.bitrate_kbps} kbps MP3`;
    $('artistRepeat').textContent = `${s.station.artist_repeat_minutes} min`;
    $('songRepeat').textContent = `${s.station.song_repeat_hours} hr`;
    $('lastScan').textContent = fmtDate(s.scan.last_scan);
    $('scanState').textContent = s.scan.running ? 'Scanning music library…' : '';
    $('scanButton').disabled = !!s.scan.running;

    const cur = s.playout.current;
    if (cur) {
      $('nowTitle').textContent = cur.title || 'Unknown Title';
      $('nowArtist').textContent = cur.artist || 'Unknown Artist';
      const parts = [cur.album, cur.year, cur.genre].filter(Boolean);
      $('nowMeta').textContent = parts.join(' · ');
    } else {
      $('nowTitle').textContent = s.library.tracks ? 'Preparing broadcast…' : 'No playable tracks yet';
      $('nowArtist').textContent = s.library.tracks ? 'The first track will begin shortly.' : 'Mount /music and scan the library.';
      $('nowMeta').textContent = '';
    }

    const history = $('history');
    if (!s.recent.length) {
      history.className = 'history empty';
      history.textContent = 'No plays recorded yet.';
    } else {
      history.className = 'history';
      history.innerHTML = s.recent.map((h) => `
        <div class="history-row">
          <div><div class="history-title">${esc(h.title || 'Unknown Title')}</div><div class="history-sub">${esc(h.artist || 'Unknown Artist')}${h.album ? ' · ' + esc(h.album) : ''}</div></div>
          <div class="history-time">${esc(fmtTime(h.started_at))}</div>
        </div>`).join('');
    }

    const err = s.playout.last_error;
    $('errorCard').hidden = !err;
    $('errorText').textContent = err || '';
  } catch (e) {
    $('statusPill').textContent = '○ API unavailable';
    $('statusPill').className = 'pill offline';
  }
}

$('scanButton').addEventListener('click', async () => {
  $('scanButton').disabled = true;
  try { await fetch('/api/scan', {method:'POST'}); } finally { setTimeout(refresh, 500); }
});

refresh();
setInterval(refresh, 3000);
