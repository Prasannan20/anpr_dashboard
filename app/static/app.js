function colorPill(isAuth){
  return `<span class="pill ${isAuth?'green':'red'}">${isAuth?'🟢':'🔴'}</span>`;
}
const isAdmin = document.body.dataset.role === 'admin';
let loadInFlight = false;
let loadQueued = false;

const metricRefs = {
  fps: document.getElementById('metricFps'),
  frameMs: document.getElementById('metricFrameMs'),
  detectMs: document.getElementById('metricDetectMs'),
  ocrMs: document.getElementById('metricOcrMs'),
  eventsPerMin: document.getElementById('metricEventsPerMin'),
  ocrSuccess: document.getElementById('metricOcrSuccess'),
  totalFrames: document.getElementById('metricTotalFrames'),
  totalEvents: document.getElementById('metricTotalEvents'),
  updatedAt: document.getElementById('metricUpdatedAt'),
};

function getCsrfToken(){
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function fetchWithCsrf(url, options = {}){
  const opts = { ...options };
  const headers = new Headers(opts.headers || {});
  const token = getCsrfToken();
  if (token) {
    headers.set('X-CSRFToken', token);
  }
  opts.headers = headers;
  return fetch(url, opts);
}

function handleHttpError(res){
  if (!res.ok) {
    console.error(`Request failed: ${res.status}`);
    alert('Action failed. Please try again.');
  }
  return res;
}

function rowHtml(serial, r, vanMode=false){
  const authText = r.authorized_as;
  const alertText = r.alert_sent ? '⚠ Alert Sent' : 'No';
  // Fix time display - handle UTC timestamps correctly
  let timeStr = r.time_stamp;
  if (timeStr && !timeStr.includes('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
    // If no timezone info, assume UTC and convert to local
    timeStr = timeStr + 'Z';
  }
  const dateObj = new Date(timeStr);
  // Format as DD/MM/YYYY HH:MM:SS
  const day = String(dateObj.getDate()).padStart(2, '0');
  const month = String(dateObj.getMonth() + 1).padStart(2, '0');
  const year = dateObj.getFullYear();
  const hours = String(dateObj.getHours()).padStart(2, '0');
  const minutes = String(dateObj.getMinutes()).padStart(2, '0');
  const seconds = String(dateObj.getSeconds()).padStart(2, '0');
  const time = `${day}/${month}/${year} ${hours}:${minutes}:${seconds}`;
  const actions = isAdmin ? `<button class="btn-delete" data-id="${r.id}">Delete</button>` : '';
  return `<tr data-id="${r.id}" data-snap="${r.snapshot_path||''}">
    <td>${serial}</td>
    <td>${r.vehicle_number}</td>
    <td>${r.vehicle_type || '-'}</td>
    <td>${time}</td>
    <td>${r.status}</td>
    <td>${vanMode ? 'Van' : authText}</td>
    <td>${colorPill(r.is_authorized)}</td>
    <td>${r.confidence}%</td>
    <td>${alertText}</td>
    <td>${actions}</td>
  </tr>`;
}
async function loadAll(){
  if(loadInFlight){
    loadQueued = true;
    return;
  }
  loadInFlight = true;
  const v = document.getElementById('filterVehicle').value.trim();
  const s = document.getElementById('filterStatus').value;
  const a = document.getElementById('filterAuth').value;
  const role = document.getElementById('filterRole').value;
  const vehicleType = document.getElementById('filterVehicleType').value;
  const df = document.getElementById('dateFrom').value;
  const dt = document.getElementById('dateTo').value;
  const params = {};
  if (v) params.vehicle = v;
  if (s) params.status = s;
  if (a) params.authorized = a;
  if (role) params.role = role;
  if (vehicleType) params.vehicle_type = vehicleType;
  if (df) params.date_from = new Date(df).toISOString();
  if (dt) params.date_to = new Date(dt).toISOString();
  try{
    const qs = new URLSearchParams(params).toString();
    const mainRes = await fetch(`/api/events?${qs}`);
    const mainData = await mainRes.json();
    const total = mainData.length;
    const totalEl = document.getElementById('totalVehicles');
    if (totalEl) totalEl.textContent = total;
    document.querySelector("#tbl-main tbody").innerHTML = mainData.map((r,i)=>rowHtml(total - i,r,false)).join("");
    const vansParams = Object.assign({}, params, { authorized: 'true' });
    delete vansParams.role;
    const vansRes = await fetch(`/api/events?${new URLSearchParams(vansParams).toString()}`);
    const vansData = await vansRes.json();
    const vans = vansData.filter(r=>r.authorized_as==='Van');
    const vansTotal = vans.length;
    document.querySelector("#tbl-vans tbody").innerHTML = vans.map((r,i)=>rowHtml(vansTotal - i,r,true)).join("");
  }catch(err){
    console.error('Failed to load events', err);
  }finally{
    loadInFlight = false;
    if(loadQueued){
      loadQueued = false;
      loadAll();
    }
  }
}
document.addEventListener('input', (e)=>{
  if(['filterVehicle','dateFrom','dateTo'].includes(e.target.id)){ loadAll(); }
});
document.addEventListener('change', (e)=>{
  if(['filterStatus','filterAuth','filterRole','filterVehicleType'].includes(e.target.id)){ loadAll(); }
});
const btnCsv = document.getElementById('exportCsv');
if(btnCsv){ btnCsv.onclick = ()=> window.location = '/api/events/export.csv'; }
const btnPdf = document.getElementById('exportPdf');
if(btnPdf){ 
  btnPdf.onclick = ()=> {
    const v = document.getElementById('filterVehicle').value.trim();
    const s = document.getElementById('filterStatus').value;
    const a = document.getElementById('filterAuth').value;
    const role = document.getElementById('filterRole').value;
    const vehicleType = document.getElementById('filterVehicleType').value;
    const df = document.getElementById('dateFrom').value;
    const dt = document.getElementById('dateTo').value;
    const params = {};
    if (v) params.vehicle = v;
    if (s) params.status = s;
    if (a) params.authorized = a;
    if (role) params.role = role;
    if (vehicleType) params.vehicle_type = vehicleType;
    if (df) params.date_from = new Date(df).toISOString();
    if (dt) params.date_to = new Date(dt).toISOString();
    window.location = `/api/events/export.pdf?${new URLSearchParams(params).toString()}`;
  }
}
const btnVansPdf = document.getElementById('exportVansPdf');
if(btnVansPdf){ 
  btnVansPdf.onclick = ()=> {
    const v = document.getElementById('filterVehicle').value.trim();
    const s = document.getElementById('filterStatus').value;
    const a = document.getElementById('filterAuth').value;
    const df = document.getElementById('dateFrom').value;
    const dt = document.getElementById('dateTo').value;
    const params = {};
    if (v) params.vehicle = v;
    if (s) params.status = s;
    if (a) params.authorized = a;
    if (df) params.date_from = new Date(df).toISOString();
    if (dt) params.date_to = new Date(dt).toISOString();
    window.location = `/api/events/export_vans.pdf?${new URLSearchParams(params).toString()}`;
  }
}
function connectSocket(){
  if (typeof io === 'undefined') { setTimeout(connectSocket, 500); return; }
  const socket = io('/ws/live');
  socket.on('vehicle_event', ()=> loadAll());
}
connectSocket();
// Modal handling
const modal = document.getElementById('modal');
const modalImg = document.getElementById('modalImg');
const modalClose = document.getElementById('modalClose');

function closeModal() {
  if (modal) {
    modal.classList.add('hidden');
    // Clear image src to free memory
    if (modalImg) modalImg.src = '';
  }
}

function openModal(imagePath) {
  if (modal && modalImg) {
    modalImg.src = '/' + imagePath;
    modal.classList.remove('hidden');
  }
}

// Close modal on close button click
if (modalClose) {
  modalClose.onclick = (e) => {
    e.stopPropagation();
    closeModal();
  };
}

// Close modal when clicking outside the image
if (modal) {
  modal.addEventListener('click', (e) => {
    // Only close if clicking the modal background, not the image or modal body
    if (e.target === modal) {
      closeModal();
    }
  });
}

// Prevent modal body clicks from closing modal
if (modal) {
  const modalBody = modal.querySelector('.modal-body');
  if (modalBody) {
    modalBody.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }
}

// Close modal on ESC key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
    closeModal();
  }
});

// Table row click handling
document.addEventListener('click', (e)=>{
  const tr = e.target.closest('tr[data-id]');
  if(!tr) return;
  if(e.target.classList.contains('btn-delete')){
    const id = e.target.getAttribute('data-id');
    const serial = tr.querySelector('td:nth-child(1)')?.textContent?.trim() || 'N/A';
    const vehicleType = tr.querySelector('td:nth-child(3)')?.textContent?.trim() || '-';
    const time = tr.querySelector('td:nth-child(4)')?.textContent?.trim() || '-';
    const confirmMsg = `Delete this vehicle event?\nS.No: ${serial}\nVehicle: ${vehicleType}\nTime: ${time}`;
    if(id && confirm(confirmMsg)){
      fetchWithCsrf(`/api/events/${id}`, {method:'DELETE'}).then(res=>{
        if(res.ok){ 
          loadAll(); 
        } else {
          handleHttpError(res);
        }
      }).catch(err=>{
        console.error('Failed to delete event', err);
        alert('Could not delete this event. Please try again.');
      });
    }
    return;
  }
  const snap = tr.getAttribute('data-snap');
  if(!snap) return;
  openModal(snap);
});
const sim = document.getElementById('simForm');
if(sim){
  sim.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const form = new FormData(sim);
    const payload = Object.fromEntries(form.entries());
    payload.confidence = parseInt(payload.confidence||'90',10);
    const res = await fetchWithCsrf('/api/events/simulate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if(res.ok){ sim.reset(); loadAll(); }
  });
}
/* Camera controls */
async function postJson(url, body){ 
  const res = await fetchWithCsrf(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body||{})});
  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    // Ignore JSON parse errors for endpoints that don't return bodies
  }
  if(!res.ok){
    const msg = (data && (data.error || data.message)) || 'Request failed';
    throw new Error(msg);
  }
  return data || { ok: true };
}
window.addEventListener('DOMContentLoaded', ()=>{
  const img = document.getElementById('camStream');
  const start = document.getElementById('btnCamStart');
  const stopb = document.getElementById('btnCamStop');
  if(start){ 
    start.onclick = async ()=>{
      try {
        await postJson('/camera/start', {});
        img.src = '/video_feed?ts='+Date.now();
      } catch(err){
        alert(err.message || 'Failed to start camera/video.');
      }
    } 
  }
  if(stopb){ 
    stopb.onclick = async ()=>{
      try{
        await postJson('/camera/stop', {});
        img.src='';
      }catch(err){
        alert(err.message || 'Failed to stop camera/video.');
      }
    } 
  }
  // Set default date to today (start of day)
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dateFromInput = document.getElementById('dateFrom');
  const dateToInput = document.getElementById('dateTo');
  if (dateFromInput && !dateFromInput.value) {
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    dateFromInput.value = `${year}-${month}-${day}T00:00`;
  }
  if (dateToInput && !dateToInput.value) {
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    dateToInput.value = `${year}-${month}-${day}T23:59`;
  }
  // Load data after setting default dates
  loadAll();
  loadMetrics();
});

// Auto-refresh every 2 seconds for quicker updates
setInterval(loadAll, 2000);
setInterval(loadMetrics, 3000);

function fmtMetric(value, digits = 2, suffix = '') {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return `--${suffix}`;
  }
  return `${value.toFixed(digits)}${suffix}`;
}

async function loadMetrics() {
  if (!metricRefs.fps) {
    return;
  }
  try {
    const res = await fetch('/api/metrics/performance');
    if (!res.ok) {
      return;
    }
    const data = await res.json();
    const recent = data.recent || {};
    const totals = data.totals || {};
    if (metricRefs.fps) metricRefs.fps.textContent = fmtMetric(recent.fps, 2, '');
    if (metricRefs.frameMs) metricRefs.frameMs.textContent = fmtMetric(recent.frame_ms, 1, ' ms');
    if (metricRefs.detectMs) metricRefs.detectMs.textContent = fmtMetric(recent.detect_ms, 1, ' ms');
    if (metricRefs.ocrMs) metricRefs.ocrMs.textContent = fmtMetric(recent.ocr_ms, 1, ' ms');
    if (metricRefs.eventsPerMin) metricRefs.eventsPerMin.textContent = fmtMetric(recent.events_per_min, 2, '');
    if (metricRefs.ocrSuccess) metricRefs.ocrSuccess.textContent = fmtMetric(recent.ocr_success_rate, 1, '%');
    if (metricRefs.totalFrames) metricRefs.totalFrames.textContent = (totals.frames || 0).toString();
    if (metricRefs.totalEvents) metricRefs.totalEvents.textContent = (totals.events || 0).toString();
    if (metricRefs.updatedAt) {
      metricRefs.updatedAt.textContent = `Updated ${new Date(data.updated_at || Date.now()).toLocaleTimeString()}`;
    }
  } catch (err) {
    console.warn('Failed to load metrics', err);
  }
}
