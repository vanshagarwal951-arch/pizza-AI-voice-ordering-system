const sessionInput = document.getElementById('session-input');
const cartContent = document.getElementById('cart-content');
const joinVoiceBtn = document.getElementById('join-voice');
const voiceStatus = document.getElementById('voice-status');
let ws = null;
let voiceRoom = null;
let voiceActive = false;
let adminToken = localStorage.getItem('adminToken') || '';

const TITLES = {
  overview: 'Overview', menu: 'Menu', order: 'Live Order', kitchen: 'Kitchen',
  analytics: 'Analytics', orders: 'Orders', chat: 'Text Chat', admin: 'Admin', calls: 'Call Logs'
};

// HTML escape function to prevent XSS (F04, F05 fix)
function escapeHtml(unsafe) {
  if (unsafe === null || unsafe === undefined) return '';
  return String(unsafe)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function fmtPrice(cents) {
  const n = cents / 100;
  return Number.isInteger(n) ? `₹${n}` : `₹${n.toFixed(2)}`;
}

function fmtTime(iso) {
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' });
}

// ----- Mobile sidebar -----
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
const mobileRefreshBtn = document.getElementById('mobile-refresh-btn');

function openSidebar() {
  sidebar.classList.add('open');
  sidebarOverlay.classList.add('open');
  mobileMenuToggle.setAttribute('aria-expanded', 'true');
}

function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('open');
  mobileMenuToggle.setAttribute('aria-expanded', 'false');
}

mobileMenuToggle.addEventListener('click', () => {
  if (sidebar.classList.contains('open')) closeSidebar();
  else openSidebar();
});

sidebarOverlay.addEventListener('click', closeSidebar);

if (mobileRefreshBtn) {
  mobileRefreshBtn.addEventListener('click', () => {
    loadOverview();
    loadMenu();
  });
}

// ----- Navigation -----
function switchPanel(panel) {
  document.querySelectorAll('.nav-item, .panel').forEach(x => x.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-panel="${panel}"]`);
  if (navItem) navItem.classList.add('active');
  navItem?.setAttribute('aria-current', 'page');
  document.querySelectorAll('.nav-item:not(.active)').forEach(el => el.removeAttribute('aria-current'));
  const panelEl = document.getElementById(panel);
  if (panelEl) panelEl.classList.add('active');
  const titleEl = document.getElementById('page-title');
  if (titleEl) titleEl.textContent = TITLES[panel] || panel;

  if (panel === 'kitchen') loadKds();
  if (panel === 'orders') loadOrders();
  if (panel === 'calls') loadCalls();
  if (panel === 'analytics') loadAnalytics();
  if (panel === 'admin') loadInventory();
}

document.querySelectorAll('.nav-item').forEach(el => {
  el.onclick = () => {
    switchPanel(el.dataset.panel);
    closeSidebar();
  };

  // Keyboard support for nav items
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      switchPanel(el.dataset.panel);
      closeSidebar();
    }
  });
});

document.getElementById('refresh-btn').onclick = () => {
  loadOverview();
  loadMenu();
};

// Hash-based panel switching (for links from landing page)
function handleHash() {
  const hash = location.hash.replace('#', '');
  if (hash && TITLES[hash]) {
    switchPanel(hash);
  }
}

window.addEventListener('hashchange', handleHash);

function renderCart(cart) {
  if (!cart?.item_count) {
    cartContent.innerHTML = '<p class="muted">Cart empty — order via voice or quick add</p>';
    return;
  }
  cartContent.innerHTML = cart.items.map(i =>
    `<div class="list-row"><strong>${escapeHtml(i.size_name)} ${escapeHtml(i.menu_item_name)}</strong> — ${fmtPrice(i.line_total_cents)}</div>`
  ).join('') + `<div class="total-line">Total: ${fmtPrice(cart.total_cents)}</div>`;
}

async function loadMenu() {
  const r = await fetch('/api/menu');
  const data = await r.json();
  const el = document.getElementById('menu-content');
  const cats = data.categories.length ? data.categories : Object.keys(data.items_by_category).map(id => ({ id, name: id }));
  el.innerHTML = cats.map(cat => {
    const items = data.items_by_category[cat.id] || [];
    if (!items.length) return '';
    return `<div class="cat-row"><div class="cat-label">${escapeHtml(cat.name).toUpperCase()}</div><div class="cat-line"></div></div>` +
      items.map(item => {
        const prices = item.sizes.map(s => `${escapeHtml(s.name)}: ${fmtPrice(s.price_cents)}`).join(' · ');
        return `<div class="menu-row"><div><div class="menu-name">${escapeHtml(item.name)}</div>${item.description ? `<div class="menu-desc">${escapeHtml(item.description)}</div>` : ''}</div><div class="menu-price">${prices}</div></div>`;
      }).join('');
  }).join('');
}

function setSessionBadge(online) {
  document.getElementById('ws-badge').textContent = online ? '● Live' : '○ Offline';
}

function setVoiceButton(connected) {
  joinVoiceBtn.textContent = connected ? 'Disconnect Microphone' : 'Connect Microphone';
  joinVoiceBtn.classList.toggle('btn-danger', connected);
  joinVoiceBtn.classList.toggle('btn-primary', !connected);
}

function connectWs() {
  return new Promise((resolve, reject) => {
    if (ws) ws.close();
    const id = sessionInput.value.trim();
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/sessions/${id}`);
    ws.onopen = () => {
      setSessionBadge(true);
      resolve();
    };
    ws.onclose = () => {
      setSessionBadge(false);
      if (voiceActive) disconnectVoice({ closeSession: false });
    };
    ws.onerror = () => reject(new Error('Session connection failed'));
    ws.onmessage = e => {
      const m = JSON.parse(e.data);
      if (m.type === 'cart_update') renderCart(m.cart);
    };
  });
}

async function disconnectVoice({ closeSession = true } = {}) {
  voiceActive = false;
  setVoiceButton(false);

  // Remove any attached audio elements from LiveKit tracks
  document.querySelectorAll('audio[data-livekit-track]').forEach(el => el.remove());

  if (voiceRoom) {
    try {
      await voiceRoom.localParticipant.setMicrophoneEnabled(false);
      await voiceRoom.disconnect();
    } catch (e) {
      console.warn('voice disconnect', e);
    }
    voiceRoom = null;
  }

  const room = sessionInput.value.trim();
  try {
    await fetch(`/api/livekit/voice-session?room=${encodeURIComponent(room)}`, { method: 'DELETE' });
  } catch (e) {
    console.warn('voice session cleanup', e);
  }

  if (closeSession && ws) {
    ws.close();
    ws = null;
  }

  voiceStatus.textContent = 'Disconnected — microphone and agent are off';
}

async function connectVoice() {
  const room = sessionInput.value.trim().replace(/\s+/g, '-');
  sessionInput.value = room;
  joinVoiceBtn.disabled = true;
  voiceStatus.textContent = 'Connecting session…';

  try {
    const start = await fetch(`/api/sessions/${encodeURIComponent(room)}/start`, { method: 'POST' });
    if (!start.ok) throw new Error('Could not start ordering session');
    await connectWs();
    voiceStatus.textContent = 'Joining voice room…';

    const r = await fetch(`/api/livekit/token?room=${encodeURIComponent(room)}`);
    if (!r.ok) throw new Error((await r.json()).detail || 'LiveKit not configured');
    const { url, token } = await r.json();

    const { Room, RoomEvent, Track } = LivekitClient;
    const roomObj = new Room({ adaptiveStream: true, dynacast: true });
    roomObj.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach();
        el.setAttribute('data-livekit-track', track.sid || 'audio');
        if (!document.body.contains(el)) {
          document.body.appendChild(el);
        }
        el.play?.().catch(err => console.warn('Audio play warning:', err));
        voiceStatus.textContent = 'Connected — agent speaking';
      }
    });
    roomObj.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach(el => el.remove());
    });
    roomObj.on(RoomEvent.ParticipantConnected, p => {
      if (!p.isLocal) voiceStatus.textContent = 'Connected — agent joined';
    });
    roomObj.on(RoomEvent.ActiveSpeakersChanged, speakers => {
      if (!voiceActive) return;
      const isAgent = speakers.some(s => !s.isLocal);
      const isUser = speakers.some(s => s.isLocal);
      if (isAgent) {
        voiceStatus.textContent = 'Agent speaking…';
      } else if (isUser) {
        voiceStatus.textContent = 'Listening to you…';
      } else {
        voiceStatus.textContent = `Connected to ${room} — speak to order`;
      }
    });
    roomObj.on(RoomEvent.Disconnected, () => {
      if (voiceActive) disconnectVoice({ closeSession: true });
    });

    await roomObj.connect(url, token);
    await roomObj.startAudio?.().catch(() => {});
    await roomObj.localParticipant.setMicrophoneEnabled(true);
    voiceRoom = roomObj;

    const dispatch = await fetch(`/api/livekit/dispatch?room=${encodeURIComponent(room)}`, {
      method: 'POST',
    });
    if (!dispatch.ok) {
      const err = await dispatch.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not start voice agent');
    }

    voiceActive = true;
    setVoiceButton(true);
    voiceStatus.textContent = `Connected to ${room} — speak to order`;
  } catch (e) {
    await disconnectVoice({ closeSession: true });
    voiceStatus.textContent = e.message || String(e);
  } finally {
    joinVoiceBtn.disabled = false;
  }
}

joinVoiceBtn.onclick = async () => {
  if (voiceActive) {
    await disconnectVoice({ closeSession: true });
    return;
  }
  await connectVoice();
};

window.addEventListener('pagehide', () => {
  if (voiceActive) disconnectVoice({ closeSession: true });
});

async function invokeTool(tool, args = {}) {
  const r = await fetch('/api/tools/invoke', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionInput.value.trim(), tool, args })
  });
  return r.json();
}

async function quickAdd() {
  await invokeTool('add_item', { item_name: 'Margherita', size: 'medium' });
}

async function readBack() {
  const r = await invokeTool('read_back_cart');
  alert(r.message);
}

async function finalize() {
  await saveCheckout();
  const r = await invokeTool('finalize_order', {
    payment_method: document.getElementById('payment-method').value,
    customer_phone: document.getElementById('customer-phone').value.trim() || null,
  });
  alert(r.message || 'Order placed!');
  loadOrders();
  loadOverview();
  loadKds();
}

async function saveCheckout() {
  const sessionId = sessionInput.value.trim();
  const payment_method = document.getElementById('payment-method').value;
  const customer_phone = document.getElementById('customer-phone').value.trim();
  try {
    await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payment_method, customer_phone: customer_phone || null }),
    });
  } catch (e) { console.warn('checkout save', e); }
}

async function loadCheckout() {
  const sessionId = sessionInput.value.trim();
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/checkout`);
    if (!r.ok) return;
    const data = await r.json();
    if (data.payment_method) {
      document.getElementById('payment-method').value = data.payment_method;
    }
    if (data.customer_phone) {
      document.getElementById('customer-phone').value = data.customer_phone;
    }
  } catch (e) { console.warn('checkout load', e); }
}
document.getElementById('chat-send').onclick = async () => {
  const msg = document.getElementById('chat-input').value.trim();
  if (!msg) return;
  const log = document.getElementById('chat-log');

  // Fix F04: XSS in chat log - use textContent instead of innerHTML
  const userDiv = document.createElement('div');
  userDiv.className = 'user';
  userDiv.innerHTML = '<b>You:</b> ';
  const userText = document.createTextNode(msg);
  userDiv.appendChild(userText);
  log.appendChild(userDiv);

  const r = await fetch('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionInput.value.trim(), message: msg })
  });
  const data = await r.json();

  // Fix F04: XSS in chat log - use textContent for bot reply
  const botDiv = document.createElement('div');
  botDiv.className = 'bot';
  botDiv.innerHTML = '<b>Agent:</b> ';
  const botText = document.createTextNode(data.reply);
  botDiv.appendChild(botText);
  log.appendChild(botDiv);

  log.scrollTop = log.scrollHeight;
  document.getElementById('chat-input').value = '';
};

// Chat input: send on Enter
document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('chat-send').click();
  }
});

async function loadOrders() {
  const r = await fetch('/api/orders', {
    headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : {}
  });
  if (!r.ok) {
    document.getElementById('orders-content').innerHTML = '<p class="muted">Authentication required</p>';
    return;
  }
  const data = await r.json();
  document.getElementById('orders-content').innerHTML = data.orders.length
    ? data.orders.map(o => `<div class="list-row">
        <strong>${fmtPrice(o.total_cents)}</strong> · ${o.item_count} items · ${fmtTime(o.created_at)}
        ${o.payment_method ? `<span class="badge badge-muted">${escapeHtml(o.payment_method)}</span>` : ''}
        ${o.kitchen_status ? `<span class="badge badge-live">${escapeHtml(o.kitchen_status)}</span>` : ''}
        <div class="muted">${escapeHtml(o.spoken_summary.slice(0, 90))}…</div></div>`).join('')
    : '<p class="muted">No orders yet.</p>';
}

async function loadCalls() {
  const r = await fetch('/api/calls', {
    headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : {}
  });
  if (!r.ok) {
    document.getElementById('calls-content').innerHTML = '<p class="muted">Authentication required</p>';
    return;
  }
  const data = await r.json();
  document.getElementById('calls-content').innerHTML = data.calls.length
    ? data.calls.map(c => `<div class="list-row"><strong>${escapeHtml(c.room_name)}</strong> · ${escapeHtml(c.status)} · ${fmtTime(c.started_at)}<div class="muted">${c.transcript.length} entries</div></div>`).join('')
    : '<p class="muted">No calls logged.</p>';
}

async function loadOverview() {
  let analytics = { revenue_today_cents: 0, orders_today: 0, revenue_week_cents: 0, orders_week: 0, average_order_value_cents: 0, peak_hour: 12, conversion_rate: 0, calls_completed: 0 };
  let platform = { features: {} };
  let recent = [];
  try {
    const r = await fetch('/api/analytics', {
      headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : {}
    });
    if (r.ok) analytics = await r.json();
  } catch (e) { console.warn('analytics', e); }
  try {
    platform = await fetch('/api/platform/status').then(r => r.json());
  } catch (e) { console.warn('platform', e); }
  try {
    const r = await fetch('/api/orders?limit=5', {
      headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : {}
    });
    if (r.ok) {
      const orders = await r.json();
      recent = orders.orders || [];
    }
  } catch (e) { console.warn('orders', e); }

  document.getElementById('stats-grid').innerHTML = `
    <div class="stat-card"><div class="stat-label">Today's Revenue</div><div class="stat-value amber">${fmtPrice(analytics.revenue_today_cents)}</div><div class="stat-sub">${analytics.orders_today} orders today</div></div>
    <div class="stat-card"><div class="stat-label">Weekly Revenue</div><div class="stat-value">${fmtPrice(analytics.revenue_week_cents)}</div><div class="stat-sub">${analytics.orders_week} orders this week</div></div>
    <div class="stat-card"><div class="stat-label">Avg Order Value</div><div class="stat-value green">${fmtPrice(analytics.average_order_value_cents)}</div><div class="stat-sub">Peak hour: ${analytics.peak_hour}:00</div></div>
    <div class="stat-card"><div class="stat-label">Conversion</div><div class="stat-value">${analytics.conversion_rate}%</div><div class="stat-sub">${analytics.calls_completed} calls → orders</div></div>`;

  const features = platform.features || {};
  document.getElementById('feature-grid').innerHTML = Object.entries(features).map(([k, v]) =>
    `<div class="feature-chip ${v ? 'on' : 'off'}">${v ? '✓' : '○'} ${escapeHtml(k.replace(/_/g, ' '))}</div>`
  ).join('');

  document.getElementById('overview-orders').innerHTML = recent.length
    ? recent.slice(0, 5).map(o => `<div class="list-row"><strong>${fmtPrice(o.total_cents)}</strong> · ${fmtTime(o.created_at)}</div>`).join('')
    : '<p class="muted">No orders yet — try voice ordering!</p>';
}

async function loadAnalytics() {
  const r = await fetch('/api/analytics', {
    headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : {}
  });
  if (!r.ok) {
    document.getElementById('analytics-stats').innerHTML = '<p class="muted">Authentication required</p>';
    return;
  }
  const data = await r.json();
  document.getElementById('analytics-stats').innerHTML = `
    <div class="stat-card"><div class="stat-label">Total Orders</div><div class="stat-value">${data.total_orders}</div></div>
    <div class="stat-card"><div class="stat-label">Total Calls</div><div class="stat-value">${data.calls_total}</div></div>
    <div class="stat-card"><div class="stat-label">Active Calls</div><div class="stat-value green">${data.calls_active}</div></div>
    <div class="stat-card"><div class="stat-label">Weekly AOV</div><div class="stat-value amber">${fmtPrice(data.average_order_value_cents)}</div></div>`;

  const hourly = data.hourly_orders || {};
  const max = Math.max(...Object.values(hourly), 1);
  document.getElementById('hourly-chart').innerHTML = Array.from({ length: 24 }, (_, h) => {
    const count = hourly[h] || 0;
    const pct = Math.max(4, (count / max) * 100);
    return `<div class="bar" style="height:${pct}%" title="${h}:00 — ${count} orders"></div>`;
  }).join('');
}

async function loadKds() {
  const r = await fetch('/api/kds/tickets', {
    headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : {}
  });
  if (!r.ok) {
    document.getElementById('kds-queued').innerHTML = '<p class="muted">Auth required</p>';
    document.getElementById('kds-preparing').innerHTML = '<p class="muted">Auth required</p>';
    document.getElementById('kds-ready').innerHTML = '<p class="muted">Auth required</p>';
    return;
  }
  const data = await r.json();
  const buckets = { queued: [], preparing: [], ready: [] };
  (data.tickets || []).forEach(t => {
    const s = t.status === 'served' ? 'ready' : (buckets[t.status] ? t.status : 'queued');
    if (buckets[s]) buckets[s].push(t);
  });

  function render(list, elId, nextStatus) {
    document.getElementById(elId).innerHTML = list.length ? list.map(t =>
      `<div class="kds-ticket" onclick="advanceTicket('${escapeHtml(t.id)}','${escapeHtml(nextStatus)}')" role="button" tabindex="0" aria-label="Advance ticket ${escapeHtml(t.order_id.slice(0, 8))} to ${escapeHtml(nextStatus)}">
        <div class="kds-ticket-id">#${escapeHtml(t.order_id.slice(0, 8))}</div>
        <div class="kds-ticket-meta">${t.item_count} items · ${fmtPrice(t.total_cents)} · ${fmtTime(t.created_at)}</div>
      </div>`).join('') : '<p class="muted">Empty</p>';
  }
  render(buckets.queued, 'kds-queued', 'preparing');
  render(buckets.preparing, 'kds-preparing', 'ready');
  render(buckets.ready, 'kds-ready', 'served');
}

async function advanceTicket(id, status) {
  await fetch(`/api/kds/tickets/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(adminToken ? { Authorization: `Bearer ${adminToken}` } : {})
    },
    body: JSON.stringify({ status })
  });
  loadKds();
}

async function loadRestaurants() {
  const r = await fetch('/api/restaurants');
  const data = await r.json();
  const sel = document.getElementById('restaurant-select');
  sel.innerHTML = (data.restaurants || []).map(rest =>
    `<option value="${rest.id}">${rest.name}</option>`).join('');
  if (data.restaurants?.[0]) {
    document.getElementById('brand-name').textContent = data.restaurants[0].name;
    document.getElementById('brand-logo').textContent = data.restaurants[0].logo_emoji || '🍕';
  }
}

document.getElementById('login-btn').onclick = async () => {
  const r = await fetch('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: document.getElementById('admin-user').value,
      password: document.getElementById('admin-pass').value
    })
  });
  if (!r.ok) { alert('Invalid credentials'); return; }
  const data = await r.json();
  adminToken = data.token;
  localStorage.setItem('adminToken', adminToken);
  document.getElementById('login-card').style.display = 'none';
  document.getElementById('admin-panel').style.display = 'block';
  loadInventory();
};

async function loadInventory() {
  if (!adminToken) return;
  const r = await fetch('/api/inventory', {
    headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : {}
  });
  const data = await r.json();
  const items = (data.items || []);
  const mods = (data.modifiers || []).slice(0, 20);
  const itemsHtml = items.length
    ? `<div class="muted mb-sm">Menu items — mark unavailable when out of stock</div>` +
      items.map(item =>
        `<div class="list-row flex-row" style="justify-content:space-between">
          <span>${escapeHtml(item.name)} ${item.is_available ? '' : '<span class="badge badge-muted">Unavailable</span>'}</span>
          <button class="btn btn-ghost btn-sm" onclick="toggleItemAvailability('${escapeHtml(item.id)}', ${!item.is_available})">${item.is_available ? 'Mark unavailable' : 'Mark available'}</button>
        </div>`).join('')
    : '';
  const modsHtml = mods.length
    ? `<div class="hr"></div><div class="muted mb-sm">Modifiers (86)</div>` +
      mods.map(m =>
        `<div class="list-row flex-row" style="justify-content:space-between">
          <span>${escapeHtml(m.name)} ${m.is_86d ? '<span class="badge badge-muted">86\'d</span>' : ''}</span>
          <button class="btn btn-ghost btn-sm" onclick="toggle86('${escapeHtml(m.id)}', ${!m.is_86d})">${m.is_86d ? 'Restore' : '86'}</button>
        </div>`).join('')
    : '<p class="muted">No modifiers</p>';
  document.getElementById('inventory-content').innerHTML = itemsHtml + modsHtml;
}

async function toggleItemAvailability(id, available) {
  await fetch(`/api/inventory/items/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminToken}` },
    body: JSON.stringify({ is_available: available })
  });
  loadInventory();
}

async function toggle86(id, is86d) {
  await fetch(`/api/inventory/modifiers/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminToken}` },
    body: JSON.stringify({ is_86d: is86d })
  });
  loadInventory();
}

if (adminToken) {
  document.getElementById('login-card').style.display = 'none';
  document.getElementById('admin-panel').style.display = 'block';
}

sessionInput.onchange = () => {
  if (voiceActive) disconnectVoice({ closeSession: true });
  loadCheckout();
};
document.getElementById('payment-method').onchange = saveCheckout;
document.getElementById('customer-phone').onblur = saveCheckout;

document.addEventListener('DOMContentLoaded', () => {
  setSessionBadge(false);
  setVoiceButton(false);
  loadMenu();
  loadOverview();
  loadRestaurants();
  loadCheckout();
  fetch('/api/health').then(r => r.json()).then(h => {
    document.getElementById('sys-status').textContent = `${h.restaurant} · online`;
    document.getElementById('chat-mode').textContent = h.chat_mode === 'groq' ? 'Groq AI' : 'Demo mode';
  });

  // Handle hash-based navigation from landing page links
  handleHash();
});
