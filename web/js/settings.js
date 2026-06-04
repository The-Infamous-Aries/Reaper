/**
 * settings.js — Settings page logic
 * Tabs: Account, Appearance, Auto-Fill, Notifications, Privacy
 */

/* ── State ─────────────────────────────────────────────────────────────── */
let currentSettings      = {};
let autoFillRaidsExclude = [];
let autoFillCompareHome  = [];
let watchHomeAlliance    = null;  // {id, name} or null
let allianceCache        = null;
let raidsAcIdx           = -1;
let compareAcIdx         = -1;
let watchHomeAcIdx       = -1;

/* ── Theme Presets ────────────────────────────────────────────────────── */
const PRESETS = {
  dark:     { label:'🌑 Dark',     theme_bg_color:'#0a0a0a', theme_bg_secondary:'#0f0f0f', theme_bg_tertiary:'#141414', theme_gold_primary:'#ffd700', theme_gold_secondary:'#ffed4e', theme_text_primary:'#f0f0f0', theme_text_secondary:'#b9bbbe', theme_hide_bg_image:false },
  light:    { label:'☀️ Light',    theme_bg_color:'#e8e8e8', theme_bg_secondary:'#f2f2f2', theme_bg_tertiary:'#ffffff', theme_gold_primary:'#b8860b', theme_gold_secondary:'#d4a017', theme_text_primary:'#1a1a1a', theme_text_secondary:'#4a4a4a', theme_hide_bg_image:true },
  fire:     { label:'🔥 Fire',     theme_bg_color:'#120500', theme_bg_secondary:'#1e0a00', theme_bg_tertiary:'#2e1000', theme_gold_primary:'#ff6a00', theme_gold_secondary:'#ffb347', theme_text_primary:'#fff3e0', theme_text_secondary:'#ffb380', theme_hide_bg_image:false },
  ember:    { label:'🌋 Ember',    theme_bg_color:'#1a0505', theme_bg_secondary:'#260808', theme_bg_tertiary:'#361010', theme_gold_primary:'#e74c3c', theme_gold_secondary:'#ff8c69', theme_text_primary:'#fce4e4', theme_text_secondary:'#e8a0a0', theme_hide_bg_image:false },
  forest:   { label:'🌲 Forest',   theme_bg_color:'#050f08', theme_bg_secondary:'#0a1a0d', theme_bg_tertiary:'#112614', theme_gold_primary:'#4caf50', theme_gold_secondary:'#81c784', theme_text_primary:'#e8f5e9', theme_text_secondary:'#a5d6a7', theme_hide_bg_image:false },
  coral:    { label:'🪸 Coral',    theme_bg_color:'#041a1a', theme_bg_secondary:'#082626', theme_bg_tertiary:'#0d3333', theme_gold_primary:'#26c6da', theme_gold_secondary:'#80deea', theme_text_primary:'#e0f7fa', theme_text_secondary:'#80cbc4', theme_hide_bg_image:false },
  midnight: { label:'🌌 Midnight', theme_bg_color:'#05071a', theme_bg_secondary:'#0a0e2a', theme_bg_tertiary:'#10163a', theme_gold_primary:'#7c83fd', theme_gold_secondary:'#b3b8ff', theme_text_primary:'#e8eaf6', theme_text_secondary:'#9fa8da', theme_hide_bg_image:false },
  aurora:   { label:'🌠 Aurora',   theme_bg_color:'#030d1a', theme_bg_secondary:'#051526', theme_bg_tertiary:'#072033', theme_gold_primary:'#00e5ff', theme_gold_secondary:'#64ffda', theme_text_primary:'#e0f7ff', theme_text_secondary:'#80deea', theme_hide_bg_image:false },
  nebula:   { label:'🔭 Nebula',   theme_bg_color:'#0d0520', theme_bg_secondary:'#140830', theme_bg_tertiary:'#1c0d42', theme_gold_primary:'#ce93d8', theme_gold_secondary:'#f3a4ff', theme_text_primary:'#f3e5f5', theme_text_secondary:'#ce93d8', theme_hide_bg_image:false },
  storm:    { label:'⛈️ Storm',    theme_bg_color:'#080c12', theme_bg_secondary:'#0e1420', theme_bg_tertiary:'#161e2e', theme_gold_primary:'#5c9eff', theme_gold_secondary:'#90caf9', theme_text_primary:'#eceff1', theme_text_secondary:'#90a4ae', theme_hide_bg_image:false },
  obsidian: { label:'🪨 Obsidian', theme_bg_color:'#0a0a0f', theme_bg_secondary:'#0f0f18', theme_bg_tertiary:'#161622', theme_gold_primary:'#e0e0e0', theme_gold_secondary:'#f5f5f5', theme_text_primary:'#fafafa', theme_text_secondary:'#bdbdbd', theme_hide_bg_image:false },
  bronze:   { label:'⚙️ Bronze',   theme_bg_color:'#100a04', theme_bg_secondary:'#1a1005', theme_bg_tertiary:'#261808', theme_gold_primary:'#cd7f32', theme_gold_secondary:'#e6a96a', theme_text_primary:'#fdf0e0', theme_text_secondary:'#d4a96a', theme_hide_bg_image:false },
  neon:     { label:'⚡ Neon',     theme_bg_color:'#030303', theme_bg_secondary:'#080808', theme_bg_tertiary:'#0e0e0e', theme_gold_primary:'#39ff14', theme_gold_secondary:'#7fff00', theme_text_primary:'#f0fff0', theme_text_secondary:'#a0d0a0', theme_hide_bg_image:false },
  dusk:     { label:'🌅 Dusk',     theme_bg_color:'#100508', theme_bg_secondary:'#1a0a10', theme_bg_tertiary:'#281018', theme_gold_primary:'#ff6b9d', theme_gold_secondary:'#ffa3c0', theme_text_primary:'#fff0f5', theme_text_secondary:'#e0a0b8', theme_hide_bg_image:false },
  sand:     { label:'🏜️ Sand',     theme_bg_color:'#120d04', theme_bg_secondary:'#1e1608', theme_bg_tertiary:'#2c200e', theme_gold_primary:'#f5c842', theme_gold_secondary:'#fad96a', theme_text_primary:'#fdf8ec', theme_text_secondary:'#c8a96e', theme_hide_bg_image:false },
  rose:     { label:'🌹 Rose',     theme_bg_color:'#120608', theme_bg_secondary:'#1c0a0e', theme_bg_tertiary:'#280f14', theme_gold_primary:'#f06292', theme_gold_secondary:'#f48fb1', theme_text_primary:'#fce4ec', theme_text_secondary:'#ef9a9a', theme_hide_bg_image:false },
};

/* ── Initialization ───────────────────────────────────────────────────── */
async function initSettings() {
  console.log('[settings] initSettings()');

  const nationInput = document.getElementById('stn-nation-id-input');
  if (nationInput) nationInput.addEventListener('keypress', e => { if (e.key === 'Enter') linkNation(); });

  setupColorPickers();

  const [settingsResult, discordResult] = await Promise.allSettled([
    fetchSettings(),
    fetchDiscordUser(),
  ]);

  const settingsData = settingsResult.status === 'fulfilled' ? settingsResult.value : null;
  const discordData  = discordResult.status  === 'fulfilled' ? discordResult.value  : null;
  if (settingsResult.status === 'rejected') console.warn('[settings] fetchSettings failed:', settingsResult.reason);

  currentSettings = settingsData || {};
  const discordUser = currentSettings.discord_user || discordData || null;

  autoFillRaidsExclude = _parseJsonArray(currentSettings.auto_fill_alliances_raids_exclude);
  autoFillCompareHome  = _parseJsonArray(currentSettings.auto_fill_alliances_compare_home);

  // Restore watch home alliance from saved ID
  if (currentSettings.watch_home_alliance_id) {
    watchHomeAlliance = {
      id: currentSettings.watch_home_alliance_id,
      name: currentSettings.watch_home_alliance_name || `Alliance ${currentSettings.watch_home_alliance_id}`,
    };
  }

  renderDiscordCard(discordUser);
  renderNationCard(currentSettings);
  renderThemeUI(currentSettings);
  renderAutoFillUI();
  renderBgImageUI(currentSettings);
  renderPrivacyUI(currentSettings);
  _setupBgDragDrop();

  if (currentSettings.theme_bg_color) applyThemeToPage(currentSettings);

  setupAllianceAutocomplete();

  // Load notifications tab data if user is logged in
  if (currentSettings.logged_in) {
    loadNotificationsTab();
  }
}

function _parseJsonArray(raw) {
  try { const v = JSON.parse(raw); return Array.isArray(v) ? v : []; } catch { return []; }
}

/* ── API helpers ──────────────────────────────────────────────────────── */
async function fetchSettings() {
  try {
    const r = await fetch('/api/settings', { credentials: 'same-origin' });
    if (!r.ok) { console.warn('[settings] GET /api/settings returned', r.status); return null; }
    return await r.json();
  } catch (err) { console.warn('[settings] GET /api/settings fetch error:', err); return null; }
}

async function fetchDiscordUser() {
  try {
    const r = await fetch('/api/discord/user', { credentials: 'same-origin' });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

/* ── Tab switching ────────────────────────────────────────────────────── */
function switchTab(tab) {
  document.querySelectorAll('.settings-nav-item').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.settings-tab').forEach(s => { s.style.display = s.id === 'tab-' + tab ? '' : 'none'; });
  if (tab === 'notifications' && currentSettings.logged_in) loadNotificationsTab();
  if (tab === 'layout') initLayoutTab();
}

/* ── Discord card ─────────────────────────────────────────────────────── */
function renderDiscordCard(user) {
  const badge = document.getElementById('discord-badge');
  const notConnected = document.getElementById('discord-not-connected');
  const connected    = document.getElementById('discord-connected');
  function _setBadge(el, ok, label) {
    if (!el) return;
    const dot = el.querySelector('.badge-dot');
    if (dot) dot.className = 'badge-dot ' + (ok ? 'connected' : 'disconnected');
    let tn = null; el.childNodes.forEach(n => { if (n.nodeType === Node.TEXT_NODE) tn = n; });
    if (tn) tn.textContent = ' ' + label; else el.appendChild(document.createTextNode(' ' + label));
  }
  const hasUser = user && !user.error && user.id;
  if (!hasUser) {
    _setBadge(badge, false, 'Not connected');
    if (notConnected) notConnected.style.display = '';
    if (connected)    connected.style.display    = 'none';
    return;
  }
  _setBadge(badge, true, 'Connected');
  if (notConnected) notConnected.style.display = 'none';
  if (connected)    connected.style.display    = '';
  const avatarEl = document.getElementById('stn-discord-avatar');
  if (avatarEl) { avatarEl.src = '/api/discord/avatar?_=' + Date.now(); avatarEl.onerror = () => { avatarEl.onerror=null; avatarEl.src='https://cdn.discordapp.com/embed/avatars/0.png'; }; }
  const dn = user.global_name || user.username || 'Unknown';
  const disc = user.discriminator && user.discriminator !== '0' ? '#' + user.discriminator : '';
  _setText('stn-discord-name',   dn);
  _setText('stn-discord-handle', '@' + (user.username || '') + disc);
  _setText('stn-discord-id',     'ID: ' + user.id);
}

/* ── Nation card ──────────────────────────────────────────────────────── */
function renderNationCard(settings) {
  const raw      = settings && settings.linked_nation_id;
  const nationId = (raw !== null && raw !== undefined && raw !== 'null' && raw !== 'undefined' && String(raw).trim() !== '') ? String(raw).trim() : null;
  const pnwBadge = document.getElementById('pnw-badge');
  const notLinked = document.getElementById('pnw-not-linked');
  const linked    = document.getElementById('pnw-linked');
  function _setBadge(el, ok, label) {
    if (!el) return;
    const dot = el.querySelector('.badge-dot');
    if (dot) dot.className = 'badge-dot ' + (ok ? 'connected' : 'disconnected');
    let tn = null; el.childNodes.forEach(n => { if (n.nodeType === Node.TEXT_NODE) tn = n; });
    if (tn) tn.textContent = ' ' + label; else el.appendChild(document.createTextNode(' ' + label));
  }
  if (nationId) {
    _setBadge(pnwBadge, true, 'Linked');
    if (notLinked) notLinked.style.display = 'none';
    if (linked)    linked.style.display    = '';
    const displayTitle = settings.linked_nation_leader ? `${settings.linked_nation_leader} of ${settings.linked_nation_name || 'Unknown Nation'}` : (settings.linked_nation_name || 'Unknown Nation');
    _setText('stn-nation-name', displayTitle);
    _setText('stn-nation-id',   nationId);
    const flagEl = document.getElementById('stn-nation-flag');
    if (flagEl) { const url = settings.linked_nation_flag || `https://politicsandwar.com/api/nation/flag/${nationId}.png`; flagEl.style.backgroundImage = `url('${url}')`; flagEl.style.backgroundSize = 'cover'; }
    const extLink = document.getElementById('stn-nation-ext-link');
    if (extLink) extLink.href = 'https://politicsandwar.com/nation/id=' + nationId;
  } else {
    _setBadge(pnwBadge, false, 'Not linked');
    if (notLinked) notLinked.style.display = '';
    if (linked)    linked.style.display    = 'none';
  }
}

/* ── Link / Unlink nation ─────────────────────────────────────────────── */
async function linkNation() {
  const input = document.getElementById('stn-nation-id-input');
  const nationId = input ? input.value.trim() : '';
  if (!nationId || !/^\d+$/.test(nationId)) { showStatus('nation-status', 'error', 'Please enter a valid numeric nation ID.'); return; }
  const btn = document.getElementById('link-nation-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Linking…'; }
  try {
    const r = await fetch('/api/settings/link-nation', { method:'POST', headers:{'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify({ nation_id: nationId }) });
    const data = await r.json();
    if (r.ok && data.success) {
      currentSettings.linked_nation_id     = data.nation_id;
      currentSettings.linked_nation_name   = data.nation_name;
      currentSettings.linked_nation_leader = data.leader_name || '';
      currentSettings.linked_nation_flag   = data.flag || '';
      renderNationCard(currentSettings);
      showStatus('nation-status-linked', 'success', 'Nation linked successfully!');
      if (input) input.value = '';
    } else { showStatus('nation-status', 'error', data.detail || 'Nation not found. Check the ID and try again.'); }
  } catch { showStatus('nation-status', 'error', 'Network error — please try again.'); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-link"></i> Link Nation'; } }
}

async function unlinkNation() {
  const btn = document.getElementById('unlink-nation-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Unlinking…'; }
  try {
    const r = await fetch('/api/settings/link-nation', { method:'DELETE', credentials:'same-origin' });
    const data = await r.json();
    if (r.ok && data.success) { currentSettings.linked_nation_id = null; currentSettings.linked_nation_name = null; renderNationCard(currentSettings); }
    else showStatus('nation-status-linked', 'error', 'Failed to unlink nation.');
  } catch { showStatus('nation-status-linked', 'error', 'Network error — please try again.'); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-unlink"></i> Unlink Nation'; } }
}

async function refreshDiscord() {
  try {
    await fetch('/api/discord/refresh-profile', { method:'POST', credentials:'same-origin' });
    const user = await fetchDiscordUser();
    renderDiscordCard(user);
    showStatus('nation-status', 'success', 'Discord profile refreshed!');
  } catch { showStatus('nation-status', 'error', 'Failed to refresh Discord profile.'); }
}

/* ── Theme ────────────────────────────────────────────────────────────── */
function renderThemeUI(settings) {
  const map = { 'bg-primary': settings.theme_bg_color||'#0a0a0a', 'bg-secondary': settings.theme_bg_secondary||'#0f0f0f', 'bg-tertiary': settings.theme_bg_tertiary||'#141414', 'gold-primary': settings.theme_gold_primary||'#ffd700', 'gold-secondary': settings.theme_gold_secondary||'#ffed4e', 'text-primary': settings.theme_text_primary||'#f0f0f0', 'text-secondary': settings.theme_text_secondary||'#b9bbbe' };
  Object.entries(map).forEach(([id, val]) => { const p = document.getElementById(id); const t = document.getElementById(id+'-text'); if(p) p.value=val; if(t) t.value=val; });
  const keys = ['theme_bg_color','theme_bg_secondary','theme_bg_tertiary','theme_gold_primary','theme_gold_secondary','theme_text_primary','theme_text_secondary'];
  const matched = Object.entries(PRESETS).find(([,p]) => keys.every(k => !settings[k] || !p[k] || settings[k].toLowerCase() === p[k].toLowerCase()));
  document.querySelectorAll('.preset-swatch').forEach(b => b.classList.toggle('active', matched ? b.dataset.preset === matched[0] : false));
}

function setupColorPickers() {
  ['bg-primary','bg-secondary','bg-tertiary','gold-primary','gold-secondary','text-primary','text-secondary'].forEach(id => {
    const p = document.getElementById(id), t = document.getElementById(id+'-text');
    if (!p || !t) return;
    p.addEventListener('input', () => { t.value = p.value; previewTheme(); });
    t.addEventListener('input', () => { if (/^#[0-9A-Fa-f]{6}$/.test(t.value)) { p.value = t.value; previewTheme(); } });
  });
}

function applyPreset(name) {
  const preset = PRESETS[name]; if (!preset) return;
  renderThemeUI(preset); applyThemeToPage(preset);
  document.querySelectorAll('.preset-swatch').forEach(b => b.classList.toggle('active', b.dataset.preset === name));
  showStatus('theme-status', 'success', (preset.label||name) + ' theme previewed — click Save to keep it.');
}

function previewTheme() { applyThemeToPage(readColorInputs()); document.querySelectorAll('.preset-swatch').forEach(b => b.classList.remove('active')); }

async function saveTheme() {
  const themeData = readColorInputs();
  const activeBtn = document.querySelector('.preset-swatch.active');
  if (activeBtn) { const p = PRESETS[activeBtn.dataset.preset]; if (p) themeData.theme_hide_bg_image = p.theme_hide_bg_image ? 1 : 0; }
  else themeData.theme_hide_bg_image = currentSettings.theme_hide_bg_image || 0;
  const btn = document.getElementById('save-theme-btn');
  if (btn) { btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i> Saving…'; }
  try {
    const r = await fetch('/api/settings', { method:'POST', headers:{'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify(themeData) });
    const data = await r.json();
    if (r.ok && data.success) { applyThemeToPage(themeData); localStorage.setItem('reaper_theme', JSON.stringify(themeData)); localStorage.setItem('reaper_theme_saved_at', Date.now().toString()); showStatus('theme-status','success','Theme saved and applied!'); currentSettings = {...currentSettings,...themeData}; }
    else showStatus('theme-status','error','Failed to save theme: '+(data.detail||'Unknown error'));
  } catch { showStatus('theme-status','error','Network error saving theme.'); }
  finally { if (btn) { btn.disabled=false; btn.innerHTML='<i class="fas fa-save"></i> Save Theme'; } }
}

function resetTheme() {
  const saved = { theme_bg_color:currentSettings.theme_bg_color||'#0a0a0a', theme_bg_secondary:currentSettings.theme_bg_secondary||'#0f0f0f', theme_bg_tertiary:currentSettings.theme_bg_tertiary||'#141414', theme_gold_primary:currentSettings.theme_gold_primary||'#ffd700', theme_gold_secondary:currentSettings.theme_gold_secondary||'#ffed4e', theme_text_primary:currentSettings.theme_text_primary||'#f0f0f0', theme_text_secondary:currentSettings.theme_text_secondary||'#b9bbbe', theme_hide_bg_image:currentSettings.theme_hide_bg_image||0 };
  renderThemeUI(saved); applyThemeToPage(saved);
  document.querySelectorAll('.preset-swatch').forEach(b => b.classList.remove('active'));
  showStatus('theme-status','success','Reset to saved theme.');
}

function readColorInputs() {
  return { theme_bg_color:_val('bg-primary'), theme_bg_secondary:_val('bg-secondary'), theme_bg_tertiary:_val('bg-tertiary'), theme_gold_primary:_val('gold-primary'), theme_gold_secondary:_val('gold-secondary'), theme_text_primary:_val('text-primary'), theme_text_secondary:_val('text-secondary') };
}

function applyThemeToPage(t) {
  const r = document.documentElement;
  if (t.theme_bg_color)       r.style.setProperty('--bg-primary',    t.theme_bg_color);
  if (t.theme_bg_secondary)   r.style.setProperty('--bg-secondary',  t.theme_bg_secondary);
  if (t.theme_bg_tertiary)    r.style.setProperty('--bg-tertiary',   t.theme_bg_tertiary);
  if (t.theme_gold_primary)   r.style.setProperty('--gold-primary',  t.theme_gold_primary);
  if (t.theme_gold_secondary) r.style.setProperty('--gold-secondary',t.theme_gold_secondary);
  if (t.theme_text_primary)   r.style.setProperty('--text-primary',  t.theme_text_primary);
  if (t.theme_text_secondary) r.style.setProperty('--text-secondary',t.theme_text_secondary);
  if (t.theme_custom_bg_url) { document.body.style.backgroundImage=`url('${t.theme_custom_bg_url}')`; document.body.style.backgroundSize='cover'; document.body.style.backgroundPosition='center'; document.body.style.backgroundAttachment='fixed'; return; }
  const hide = t.theme_hide_bg_image===true||t.theme_hide_bg_image===1||t.theme_hide_bg_image==='1';
  document.body.style.backgroundImage = hide ? 'none' : '';
}

/* ── Auto-Fill ────────────────────────────────────────────────────────── */
function renderAutoFillUI() {
  _setChecked('auto-fill-nation-raids',  currentSettings.auto_fill_nation_raids);
  _setChecked('auto-fill-nation-revopt', currentSettings.auto_fill_nation_revopt);
  _setChecked('auto-fill-nation-calc',   currentSettings.auto_fill_nation_calc);
  renderTagList('raids-exclude-tags', autoFillRaidsExclude, removeRaidsExclude);
  renderTagList('compare-home-tags',  autoFillCompareHome,  removeCompareHome);
  renderWatchHomeTag();
}

function renderTagList(containerId, arr, removeFn) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = arr.map(name => {
    const safe = name.replace(/'/g, "\\'");
    return `<span class="stn-tag">${_esc(name)}<button class="stn-tag-remove" onclick="${removeFn.name}('${safe}')" title="Remove">×</button></span>`;
  }).join('');
}

/* Watch home alliance — single-select (not a multi-tag list) */
function renderWatchHomeTag() {
  const tagEl    = document.getElementById('watch-home-tags');
  const badgeDot = document.getElementById('watch-alliance-dot');
  const badgeLbl = document.getElementById('watch-alliance-label');
  if (tagEl) {
    if (watchHomeAlliance) {
      const safe = (watchHomeAlliance.name || '').replace(/'/g, "\\'");
      tagEl.innerHTML = `<span class="stn-tag">${_esc(watchHomeAlliance.name || watchHomeAlliance.id)}<button class="stn-tag-remove" onclick="clearWatchHomeAlliance()" title="Remove">×</button></span>`;
      if (badgeDot) badgeDot.style.background = '#2ecc71';
      if (badgeLbl) badgeLbl.textContent = watchHomeAlliance.name || `ID ${watchHomeAlliance.id}`;
    } else {
      tagEl.innerHTML = '';
      if (badgeDot) badgeDot.style.background = '#636669';
      if (badgeLbl) badgeLbl.textContent = 'Default (Darkstar)';
    }
  }
}

function clearWatchHomeAlliance() {
  watchHomeAlliance = null;
  renderWatchHomeTag();
  saveAutoFill();
}
window.clearWatchHomeAlliance = clearWatchHomeAlliance;

function removeRaidsExclude(name) { autoFillRaidsExclude = autoFillRaidsExclude.filter(n => n !== name); renderAutoFillUI(); saveAutoFill(); }
function removeCompareHome(name)  { autoFillCompareHome  = autoFillCompareHome.filter(n => n !== name);  renderAutoFillUI(); saveAutoFill(); }
window.removeRaidsExclude = removeRaidsExclude;
window.removeCompareHome  = removeCompareHome;

async function saveAutoFill() {
  const btn = document.getElementById('save-autofill-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }
  try {
    const payload = {
      auto_fill_nation_raids:             document.getElementById('auto-fill-nation-raids')?.checked ? 1 : 0,
      auto_fill_nation_revopt:            document.getElementById('auto-fill-nation-revopt')?.checked ? 1 : 0,
      auto_fill_nation_calc:              document.getElementById('auto-fill-nation-calc')?.checked ? 1 : 0,
      auto_fill_alliances_raids_exclude:  JSON.stringify(autoFillRaidsExclude),
      auto_fill_alliances_compare_home:   JSON.stringify(autoFillCompareHome),
    };
    // Include watch home alliance if set
    if (watchHomeAlliance && watchHomeAlliance.id) {
      payload.watch_home_alliance_id   = watchHomeAlliance.id;
      payload.watch_home_alliance_name = watchHomeAlliance.name || '';
    } else {
      payload.watch_home_alliance_id   = null;
      payload.watch_home_alliance_name = null;
    }
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (r.ok && data.success) {
      // Update window._watchAllianceId immediately so Watch page uses new alliance on next visit
      if (watchHomeAlliance && watchHomeAlliance.id) {
        window._watchAllianceId = watchHomeAlliance.id;
      } else {
        window._watchAllianceId = undefined;
      }
      showStatus('autofill-status', 'success', 'Auto-fill settings saved!');
    } else {
      showStatus('autofill-status', 'error', 'Failed to save: ' + (data.detail || 'Unknown error'));
    }
  } catch (err) {
    showStatus('autofill-status', 'error', 'Network error saving auto-fill settings.');
    console.error('[settings] saveAutoFill error:', err);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save Auto-Fill Settings'; }
  }
}

/* ── Alliance autocomplete ────────────────────────────────────────────── */
function setupAllianceAutocomplete() {
  _setupAc('add-raids-exclude-input', 'raids-exclude-dropdown', autoFillRaidsExclude, name => {
    if (!autoFillRaidsExclude.includes(name)) { autoFillRaidsExclude.push(name); renderAutoFillUI(); saveAutoFill(); }
  }, () => raidsAcIdx, v => { raidsAcIdx = v; });

  _setupAc('add-compare-home-input', 'compare-home-dropdown', autoFillCompareHome, name => {
    if (!autoFillCompareHome.includes(name)) { autoFillCompareHome.push(name); renderAutoFillUI(); saveAutoFill(); }
  }, () => compareAcIdx, v => { compareAcIdx = v; });

  // Watch home alliance — single-select; replaces any existing selection
  _setupAcSingle('add-watch-home-input', 'watch-home-dropdown', a => {
    watchHomeAlliance = { id: a.id, name: a.name };
    renderWatchHomeTag();
    saveAutoFill();
  }, () => watchHomeAcIdx, v => { watchHomeAcIdx = v; });
}

async function loadAllianceData() {
  if (allianceCache) return;
  try {
    const r = await fetch('/api/raids/alliances_ac', { credentials: 'same-origin' });
    allianceCache = r.ok ? await r.json() : [];
  } catch { allianceCache = []; }
}

function _setupAc(inputId, dropdownId, excludeList, onSelect, getIdx, setIdx) {
  const input    = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  if (!input || !dropdown) return;
  input.addEventListener('focus', async () => { await loadAllianceData(); _buildDropdown(input, dropdown, excludeList, onSelect, getIdx, setIdx); });
  input.addEventListener('input', () => _buildDropdown(input, dropdown, excludeList, onSelect, getIdx, setIdx));
  input.addEventListener('keydown', e => _handleAcKey(e, input, dropdown, onSelect, getIdx, setIdx));
  document.addEventListener('click', e => { if (!input.contains(e.target) && !dropdown.contains(e.target)) dropdown.style.display = 'none'; });
}

function _setupAcSingle(inputId, dropdownId, onSelect, getIdx, setIdx) {
  const input    = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  if (!input || !dropdown) return;
  input.addEventListener('focus', async () => { await loadAllianceData(); _buildDropdown(input, dropdown, [], item => { onSelect(item); input.value = ''; dropdown.style.display = 'none'; input.focus(); }, getIdx, setIdx, true); });
  input.addEventListener('input', () => _buildDropdown(input, dropdown, [], item => { onSelect(item); input.value = ''; dropdown.style.display = 'none'; input.focus(); }, getIdx, setIdx, true));
  input.addEventListener('keydown', e => _handleAcKey(e, input, dropdown, item => { onSelect(item); input.value = ''; dropdown.style.display = 'none'; }, getIdx, setIdx));
  document.addEventListener('click', e => { if (!input.contains(e.target) && !dropdown.contains(e.target)) dropdown.style.display = 'none'; });
}

function _buildDropdown(input, dropdown, excludeList, onSelect, getIdx, setIdx, passFullObj = false) {
  dropdown.innerHTML = '';
  setIdx(-1);
  const q = (input.value || '').trim().toLowerCase();
  if (!allianceCache || !q) { dropdown.style.display = 'none'; return; }
  const items = allianceCache.filter(a => a.name && a.name.toLowerCase().includes(q) && !excludeList.includes(a.name)).slice(0, 20);
  if (!items.length) { dropdown.style.display = 'none'; return; }
  items.forEach(a => {
    const el = document.createElement('div');
    el.className = 'ac-item';
    el.innerHTML = `<span>${_esc(a.name)}</span><span class="ac-item-id">${a.id || ''}</span>`;
    el.addEventListener('mousedown', ev => {
      ev.preventDefault();
      passFullObj ? onSelect(a) : onSelect(a.name);
      if (!passFullObj) { input.value = ''; dropdown.style.display = 'none'; input.focus(); }
    });
    dropdown.appendChild(el);
  });
  _positionDropdown(input, dropdown);
  dropdown.style.display = 'block';
}

function _positionDropdown(input, dropdown) {
  dropdown.style.top   = (input.offsetTop + input.offsetHeight + 4) + 'px';
  dropdown.style.left  = input.offsetLeft + 'px';
  dropdown.style.width = input.offsetWidth + 'px';
}

function _handleAcKey(e, input, dropdown, onSelect, getIdx, setIdx) {
  const items = dropdown.querySelectorAll('.ac-item');
  if (e.key === 'ArrowDown') { e.preventDefault(); const n = Math.min(getIdx()+1, items.length-1); setIdx(n); items.forEach((el,i) => el.classList.toggle('active', i===n)); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); const n = Math.max(getIdx()-1, 0); setIdx(n); items.forEach((el,i) => el.classList.toggle('active', i===n)); }
  else if (e.key === 'Enter') { e.preventDefault(); if (getIdx() >= 0 && items[getIdx()]) items[getIdx()].dispatchEvent(new MouseEvent('mousedown')); else { const v = input.value.trim(); if (v) { onSelect(v); input.value = ''; dropdown.style.display = 'none'; } } }
  else if (e.key === 'Escape') { dropdown.style.display = 'none'; }
  else if (e.key === 'Backspace' && !input.value) {
    if (dropdown.id === 'raids-exclude-dropdown' && autoFillRaidsExclude.length) removeRaidsExclude(autoFillRaidsExclude[autoFillRaidsExclude.length-1]);
    if (dropdown.id === 'compare-home-dropdown'  && autoFillCompareHome.length)  removeCompareHome(autoFillCompareHome[autoFillCompareHome.length-1]);
  }
}

/* ── Notifications Tab ────────────────────────────────────────────────── */
let _notifLoaded = false;

async function loadNotificationsTab() {
  if (_notifLoaded) return;
  _notifLoaded = true;

  try {
    // Load price alerts
    const r = await fetch('/api/alerts', { credentials: 'same-origin' });
    if (r.ok) {
      const alerts = await r.json();
      renderAlertsList(alerts);
      // Show the add-alert form only for logged-in users
      const formEl = document.getElementById('notif-add-alert-form');
      if (formEl) formEl.style.display = '';
    }
  } catch (e) {
    console.debug('[settings] Failed to load alerts:', e);
  }

  try {
    // Load beige alert count
    const rb = await fetch('/api/raids/beige-alerts', { credentials: 'same-origin' });
    if (rb.ok) {
      const beige = await rb.json();
      const el = document.getElementById('notif-beige-count');
      if (el) el.textContent = Array.isArray(beige) ? beige.length : '0';
    }
  } catch (e) {
    console.debug('[settings] Failed to load beige count:', e);
  }

  // Update alerts badge
  const badgeDot = document.getElementById('alerts-badge-dot');
  const badgeLbl = document.getElementById('alerts-badge-label');
}

function renderAlertsList(alerts) {
  const container = document.getElementById('notif-alerts-list');
  if (!container) return;

  const RESOURCE_EMOJIS = { food:'🌾', coal:'⛏️', oil:'🛢️', uranium:'☢️', lead:'🔩', iron:'🔩', bauxite:'🪨', gasoline:'⛽', munitions:'💣', steel:'⚙️', aluminum:'🪙', credit:'💳' };

  if (!alerts.length) {
    container.innerHTML = '<p class="settings-hint" style="margin:0">No price alerts set. Add one below.</p>';
    const badgeDot = document.getElementById('alerts-badge-dot');
    const badgeLbl = document.getElementById('alerts-badge-label');
    if (badgeDot) badgeDot.style.background = '#636669';
    if (badgeLbl) badgeLbl.textContent = '0 alerts';
    return;
  }

  const badgeDot = document.getElementById('alerts-badge-dot');
  const badgeLbl = document.getElementById('alerts-badge-label');
  if (badgeDot) { badgeDot.style.background = '#2ecc71'; badgeDot.style.boxShadow = '0 0 6px #2ecc71'; }
  if (badgeLbl) badgeLbl.textContent = `${alerts.length} alert${alerts.length !== 1 ? 's' : ''}`;

  container.innerHTML = alerts.map(a => {
    const emoji = RESOURCE_EMOJIS[a.resource] || '📊';
    const dirLabel = a.direction === 'above' ? '↑ above' : '↓ below';
    const typeLabel = a.price_type === 'buy' ? 'Buy' : 'Sell';
    const thr = Number(a.threshold).toLocaleString();
    const safeArgs = `'${a.resource}','${a.price_type}','${a.direction}'`;
    return `<div class="notif-alert-row">
      <div class="notif-alert-info">
        <div class="notif-alert-resource">${emoji} ${a.resource.charAt(0).toUpperCase()+a.resource.slice(1)}</div>
        <div class="notif-alert-desc">${typeLabel} price ${dirLabel} $${thr}</div>
      </div>
      <button class="stn-btn stn-btn-danger stn-btn-sm" onclick="deletePriceAlert(${safeArgs})">
        <i class="fas fa-trash-alt"></i>
      </button>
    </div>`;
  }).join('');
}

async function addPriceAlert() {
  const resource   = document.getElementById('notif-resource')?.value;
  const price_type = document.getElementById('notif-price-type')?.value;
  const direction  = document.getElementById('notif-direction')?.value;
  const threshold  = parseFloat(document.getElementById('notif-threshold')?.value || '');

  if (!resource || !price_type || !direction || isNaN(threshold) || threshold <= 0) {
    showStatus('notif-alert-status', 'error', 'Please fill in all fields with a positive threshold.');
    return;
  }

  try {
    const r = await fetch('/api/alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ resource, price_type, direction, threshold }),
    });
    const data = await r.json();
    if (r.ok && data.ok) {
      showStatus('notif-alert-status', 'success', 'Alert added!');
      _notifLoaded = false;
      await loadNotificationsTab();
    } else {
      showStatus('notif-alert-status', 'error', data.detail || 'Failed to add alert.');
    }
  } catch { showStatus('notif-alert-status', 'error', 'Network error — please try again.'); }
}

async function deletePriceAlert(resource, price_type, direction) {
  try {
    const r = await fetch(`/api/alerts?resource=${resource}&price_type=${price_type}&direction=${direction}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    });
    if (r.ok) {
      _notifLoaded = false;
      await loadNotificationsTab();
    } else {
      showStatus('notif-alert-status', 'error', 'Failed to delete alert.');
    }
  } catch { showStatus('notif-alert-status', 'error', 'Network error.'); }
}

window.addPriceAlert     = addPriceAlert;
window.deletePriceAlert  = deletePriceAlert;

/* ── Privacy ──────────────────────────────────────────────────────────── */
function renderPrivacyUI(settings) {
  // Default to 1 (visible) — checked means public
  const def = (key) => settings && settings[key] !== undefined ? settings[key] : 1;
  _setChecked('privacy-show-pet-leaderboard',     def('privacy_show_pet_leaderboard'));
  _setChecked('privacy-show-nations-leaderboard', def('privacy_show_nations_leaderboard'));
  _setChecked('privacy-show-watch-nations',       def('privacy_show_watch_nations'));
  _setChecked('privacy-show-nations-rankings',    def('privacy_show_nations_rankings'));
}

async function savePrivacySettings() {
  const btn = document.querySelector('#tab-privacy .stn-btn-primary');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }
  try {
    const payload = {
      privacy_show_pet_leaderboard:     document.getElementById('privacy-show-pet-leaderboard')?.checked     ? 1 : 0,
      privacy_show_nations_leaderboard: document.getElementById('privacy-show-nations-leaderboard')?.checked ? 1 : 0,
      privacy_show_watch_nations:       document.getElementById('privacy-show-watch-nations')?.checked       ? 1 : 0,
      privacy_show_nations_rankings:    document.getElementById('privacy-show-nations-rankings')?.checked    ? 1 : 0,
    };
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (r.ok && data.success) {
      showStatus('privacy-status', 'success', 'Privacy settings saved!');
      currentSettings = { ...currentSettings, ...payload };
    } else {
      showStatus('privacy-status', 'error', 'Failed to save: ' + (data.detail || 'Unknown error'));
    }
  } catch { showStatus('privacy-status', 'error', 'Network error saving privacy settings.'); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save Privacy Settings'; } }
}

async function deleteMySettings() {
  if (!confirm('Are you sure you want to delete all your settings data? This cannot be undone.')) return;
  try {
    const r = await fetch('/api/settings', { method: 'DELETE', credentials: 'same-origin' });
    const data = await r.json();
    if (r.ok && data.success) {
      showStatus('privacy-delete-status', 'success', 'Settings data deleted. Reloading…');
      localStorage.removeItem('reaper_theme');
      localStorage.removeItem('reaper_theme_saved_at');
      setTimeout(() => location.reload(), 1500);
    } else {
      showStatus('privacy-delete-status', 'error', 'Failed to delete settings.');
    }
  } catch { showStatus('privacy-delete-status', 'error', 'Network error.'); }
}

window.savePrivacySettings = savePrivacySettings;
window.deleteMySettings    = deleteMySettings;

/* ── Background Image Upload ──────────────────────────────────────────── */
function renderBgImageUI(settings) {
  const url   = settings && settings.theme_custom_bg_url;
  const wrap  = document.getElementById('bg-preview-wrap');
  const img   = document.getElementById('bg-preview-img');
  const fname = document.getElementById('bg-preview-filename');
  const dot   = document.getElementById('bg-image-badge-dot');
  const label = document.getElementById('bg-image-badge-label');
  const zone  = document.getElementById('bg-upload-zone');
  if (url) {
    if (wrap)  wrap.style.display = '';
    if (zone)  zone.style.display = 'none';
    if (img)   img.style.backgroundImage = `url('${url}?_=${Date.now()}')`;
    if (fname) fname.textContent = url.split('/').pop();
    if (dot)   dot.className = 'badge-dot connected';
    if (label) label.textContent = 'Custom';
  } else {
    if (wrap)  wrap.style.display = 'none';
    if (zone)  zone.style.display = '';
    if (dot)   dot.className = 'badge-dot disconnected';
    if (label) label.textContent = 'Default';
  }
}

async function handleBgFileSelect(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { showStatus('bg-upload-status','error','File exceeds the 5 MB limit.'); input.value=''; return; }
  const zone = document.getElementById('bg-upload-zone'), progress = document.getElementById('bg-upload-progress'), bar = document.getElementById('bg-progress-bar');
  if (zone) zone.style.opacity = '.5';
  if (progress) progress.style.display = '';
  if (bar) bar.style.width = '30%';
  const fd = new FormData(); fd.append('file', file);
  try {
    if (bar) bar.style.width = '60%';
    const r = await fetch('/api/settings/upload-background', { method:'POST', credentials:'same-origin', body: fd });
    if (bar) bar.style.width = '90%';
    const data = await r.json();
    if (r.ok && data.success) {
      if (bar) bar.style.width = '100%';
      currentSettings.theme_custom_bg_url = data.url;
      renderBgImageUI(currentSettings);
      document.body.style.backgroundImage = `url('${data.url}')`;
      document.body.style.backgroundSize = 'cover'; document.body.style.backgroundPosition = 'center'; document.body.style.backgroundAttachment = 'fixed';
      const stored = JSON.parse(localStorage.getItem('reaper_theme') || '{}'); stored.theme_custom_bg_url = data.url; localStorage.setItem('reaper_theme', JSON.stringify(stored)); localStorage.setItem('reaper_theme_saved_at', Date.now().toString());
      showStatus('bg-upload-status','success','Background uploaded and applied!');
    } else { showStatus('bg-upload-status','error', data.detail || 'Upload failed.'); }
  } catch { showStatus('bg-upload-status','error','Network error — please try again.'); }
  finally { if (zone) zone.style.opacity = '1'; setTimeout(() => { if (progress) progress.style.display='none'; if (bar) bar.style.width='0%'; }, 600); input.value = ''; }
}

async function removeBackground() {
  const btn = document.getElementById('remove-bg-btn');
  if (btn) { btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; }
  try {
    const r = await fetch('/api/settings/upload-background', { method:'DELETE', credentials:'same-origin' });
    const data = await r.json();
    if (r.ok && data.success) {
      currentSettings.theme_custom_bg_url = null;
      renderBgImageUI(currentSettings);
      const hide = currentSettings.theme_hide_bg_image === 1 || currentSettings.theme_hide_bg_image === true;
      document.body.style.backgroundImage = hide ? 'none' : '';
      const stored = JSON.parse(localStorage.getItem('reaper_theme') || '{}'); delete stored.theme_custom_bg_url; localStorage.setItem('reaper_theme', JSON.stringify(stored)); localStorage.setItem('reaper_theme_saved_at', Date.now().toString());
      showStatus('bg-upload-status','success','Background removed.');
    } else { showStatus('bg-upload-status','error','Failed to remove background.'); }
  } catch { showStatus('bg-upload-status','error','Network error.'); }
  finally { if (btn) { btn.disabled=false; btn.innerHTML='<i class="fas fa-trash-alt"></i> Remove'; } }
}

function _setupBgDragDrop() {
  const zone = document.getElementById('bg-upload-zone');
  if (!zone) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('drag-over');
    const file = e.dataTransfer.files && e.dataTransfer.files[0]; if (!file) return;
    const dt = new DataTransfer(); dt.items.add(file);
    const input = document.getElementById('bg-file-input');
    if (input) { input.files = dt.files; handleBgFileSelect(input); }
  });
}

/* ── Utility helpers ──────────────────────────────────────────────────── */
function showStatus(id, type, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'stn-status-msg ' + type;
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(el._timeout);
  el._timeout = setTimeout(() => { el.style.display = 'none'; }, 6000);
}

function _setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function _val(id) { const el = document.getElementById(id); return el ? el.value : ''; }
function _setChecked(id, val) { const el = document.getElementById(id); if (el) el.checked = !!(val === 1 || val === true || val === '1'); }
function _esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

/* ── Layout Tab ───────────────────────────────────────────────────────── */

// Default page order for each group
const DEFAULT_LAYOUT = {
  pnw: ['game_info', 'news', 'nations', 'watch', 'leaderboard', 'raids', 'cost_calc', 'comparison', 'treaty_universe', 'weapons', 'rev_optimizer', 'my_nation', 'fullmill', 'library'],
  pets: ['mypet', 'tasks', 'petconnector', 'bazaar', 'arena', 'survive', 'dungeon', 'pet_stock', 'casino', 'what_are_pets', 'pets'],
  fun: ['astrology'],
  site: ['contact', 'privacy', 'terms', 'commands', 'settings']
};

// Page metadata (icon paths and labels)
const PAGE_META = {
  // PnW pages
  game_info: { icon: '/static/Emojis/Menu/game_info.png', label: 'Game Info' },
  news: { icon: '/static/Emojis/Menu/news.png', label: 'Scythe News' },
  nations: { icon: '/static/Emojis/Menu/darkstar.png', label: 'The Void' },
  watch: { icon: '/static/Emojis/Menu/wars.png', label: 'War Stats' },
  leaderboard: { icon: '/static/Emojis/Menu/leaderboard.png', label: 'Leaderboards' },
  raids: { icon: '/static/Emojis/Menu/pirate.png', label: 'Raid Finder' },
  cost_calc: { icon: '/static/Emojis/Menu/calculator.png', label: 'Calculators' },
  comparison: { icon: '/static/Emojis/Menu/comparison.png', label: 'Comparison' },
  treaty_universe: { icon: '/static/Emojis/Menu/universe.png', label: 'Treaty Universe' },
  weapons: { icon: '/static/Emojis/Menu/snipe.png', label: 'Weapon Eff' },
  rev_optimizer: { icon: '/static/Emojis/Menu/revenue.png', label: 'Rev Optimizer' },
  my_nation: { icon: '/static/Emojis/Menu/mynation.png', label: 'My Nation' },
  fullmill: { icon: '/static/Emojis/Menu/fullmill.png', label: 'Full Mill Rankings' },
  library: { icon: '/static/Emojis/Menu/script.png', label: 'Scriptorium' },
  // Pets pages
  mypet: { icon: '/static/Emojis/Menu/pets.png', label: 'My Pet' },
  tasks: { icon: '/static/Emojis/Menu/tasks.png', label: 'Tasks' },
  petconnector: { icon: '/static/Emojis/Menu/world.png', label: 'Pet Connector' },
  bazaar: { icon: '/static/Emojis/Menu/bazaar.png', label: 'Item Board' },
  arena: { icon: '/static/Emojis/Menu/arena.png', label: 'Arena' },
  survive: { icon: '/static/Emojis/Menu/survive.png', label: 'Survive' },
  dungeon: { icon: '/static/Emojis/Menu/crawl.png', label: 'Dungeon Crawler' },
  pet_stock: { icon: '/static/Emojis/Menu/pet_stock.png', label: 'Pet Stocks' },
  casino: { icon: '/static/Emojis/Menu/casino.png', label: 'Casino' },
  what_are_pets: { icon: '/static/Emojis/Menu/what_pets.png', label: 'Breakdown' },
  pets: { icon: '/static/Emojis/Menu/pets.png', label: 'Types & Items' },
  // Fun pages
  astrology: { icon: '/static/Emojis/Menu/astrology.png', label: 'Astrology' },
  // Site pages
  contact: { icon: '/static/Emojis/Menu/contact.png', label: 'Contact' },
  privacy: { icon: '/static/Emojis/Menu/privacy.png', label: 'Privacy' },
  terms: { icon: '/static/Emojis/Menu/terms.png', label: 'Terms' },
  commands: { icon: '/static/Emojis/Menu/discord.png', label: 'Commands' },
  settings: { icon: '/static/Emojis/Menu/settings.png', label: 'Settings' }
};

let currentLayout = null;
let draggedItem = null;

function initLayoutTab() {
  // Load saved layout or use defaults
  const saved = currentSettings.menu_layout;
  if (saved) {
    try {
      currentLayout = JSON.parse(saved);
    } catch {
      currentLayout = JSON.parse(JSON.stringify(DEFAULT_LAYOUT));
    }
  } else {
    currentLayout = JSON.parse(JSON.stringify(DEFAULT_LAYOUT));
  }

  // Render all groups
  renderLayoutGroup('pnw');
  renderLayoutGroup('pets');
  renderLayoutGroup('fun');
  renderLayoutGroup('site');
}

function renderLayoutGroup(groupName) {
  const container = document.getElementById(`layout-${groupName}`);
  if (!container) return;

  const pages = currentLayout[groupName] || [];
  container.innerHTML = '';

  pages.forEach(pageId => {
    const meta = PAGE_META[pageId];
    if (!meta) return;

    const item = document.createElement('div');
    item.className = 'layout-item';
    item.draggable = true;
    item.dataset.page = pageId;
    item.dataset.group = groupName;

    item.innerHTML = `
      <img src="${meta.icon}" alt="${meta.label}" class="layout-item-icon">
      <div class="layout-item-label">${meta.label}</div>
    `;

    // Drag events
    item.addEventListener('dragstart', handleDragStart);
    item.addEventListener('dragend', handleDragEnd);
    item.addEventListener('dragover', handleDragOver);
    item.addEventListener('drop', handleDrop);

    container.appendChild(item);
  });

  // Make container a drop zone
  container.addEventListener('dragover', handleContainerDragOver);
  container.addEventListener('drop', handleContainerDrop);
}

function handleDragStart(e) {
  draggedItem = e.target;
  e.target.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/html', e.target.innerHTML);
}

function handleDragEnd(e) {
  e.target.classList.remove('dragging');
  document.querySelectorAll('.layout-items-grid').forEach(c => c.classList.remove('drag-over'));
}

function handleDragOver(e) {
  if (e.preventDefault) e.preventDefault();
  e.dataTransfer.dropEffect = 'move';

  const target = e.target.closest('.layout-item');
  if (target && target !== draggedItem) {
    const container = target.parentNode;
    const items = Array.from(container.querySelectorAll('.layout-item'));
    const draggedIdx = items.indexOf(draggedItem);
    const targetIdx = items.indexOf(target);

    if (draggedIdx > targetIdx) {
      container.insertBefore(draggedItem, target);
    } else {
      container.insertBefore(draggedItem, target.nextSibling);
    }
  }

  return false;
}

function handleDrop(e) {
  if (e.stopPropagation) e.stopPropagation();
  return false;
}

function handleContainerDragOver(e) {
  if (e.preventDefault) e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  e.currentTarget.classList.add('drag-over');
  return false;
}

function handleContainerDrop(e) {
  if (e.stopPropagation) e.stopPropagation();
  e.preventDefault();

  const container = e.currentTarget;
  container.classList.remove('drag-over');

  if (draggedItem && draggedItem.dataset.group === container.dataset.group) {
    // Already handled by item drop
  }

  return false;
}

async function saveLayoutSettings() {
  // Collect current order from DOM
  ['pnw', 'pets', 'fun', 'site'].forEach(group => {
    const container = document.getElementById(`layout-${group}`);
    if (!container) return;

    const items = Array.from(container.querySelectorAll('.layout-item'));
    currentLayout[group] = items.map(item => item.dataset.page);
  });

  const btn = document.querySelector('#tab-layout button.stn-btn-primary');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';
  }

  try {
    const payload = {
      menu_layout: JSON.stringify(currentLayout)
    };

    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload)
    });

    const data = await r.json();

    if (r.ok && data.success) {
      currentSettings.menu_layout = JSON.stringify(currentLayout);
      showStatus('layout-status', 'success', 'Layout saved! Refresh the page to see your new menu order.');
      
      // Store in localStorage for immediate effect
      localStorage.setItem('reaper_menu_layout', JSON.stringify(currentLayout));
    } else {
      showStatus('layout-status', 'error', 'Failed to save: ' + (data.detail || 'Unknown error'));
    }
  } catch (err) {
    showStatus('layout-status', 'error', 'Network error saving layout.');
    console.error('[settings] saveLayoutSettings error:', err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-save"></i> Save Layout';
    }
  }
}

function resetLayoutSettings() {
  if (!confirm('Reset to default page order? This will discard your custom layout.')) return;

  currentLayout = JSON.parse(JSON.stringify(DEFAULT_LAYOUT));
  
  renderLayoutGroup('pnw');
  renderLayoutGroup('pets');
  renderLayoutGroup('fun');
  renderLayoutGroup('site');

  showStatus('layout-status', 'success', 'Layout reset to defaults. Click Save to apply.');
}

window.saveLayoutSettings = saveLayoutSettings;
window.resetLayoutSettings = resetLayoutSettings;

/* ── Boot ─────────────────────────────────────────────────────────────── */
window.switchTab          = switchTab;
window.linkNation         = linkNation;
window.unlinkNation       = unlinkNation;
window.refreshDiscord     = refreshDiscord;
window.applyPreset        = applyPreset;
window.previewTheme       = previewTheme;
window.saveTheme          = saveTheme;
window.resetTheme         = resetTheme;
window.saveAutoFill       = saveAutoFill;
window.handleBgFileSelect = handleBgFileSelect;
window.removeBackground   = removeBackground;

window.settingsInitialized = false;

function _boot() {
  if (window.settingsInitialized) return;
  if (!document.querySelector('.settings-page')) return;
  window.settingsInitialized = true;
  initSettings();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _boot);
} else {
  _boot();
}

document.addEventListener('dashboardPageLoaded', e => {
  if (e.detail?.page && e.detail.page.includes('settings')) {
    window.settingsInitialized = false;
    _notifLoaded = false;  // reset so notifications reload on re-visit
    setTimeout(_boot, 30);
  }
});

setTimeout(() => {
  if (!window.settingsInitialized && document.querySelector('.settings-page')) {
    window.settingsInitialized = false;
    _boot();
  }
}, 400);
