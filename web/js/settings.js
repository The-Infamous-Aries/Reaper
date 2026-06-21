/**
 * settings.js — Settings page logic
 * Tabs: Account, Appearance, Auto-Fill, Notifications, Privacy
 */

/* ── State ─────────────────────────────────────────────────────────────── */
let currentSettings      = {};
let autoFillRaidsExclude = [];
let homeAlliance         = null;  // {id, name} or null
let allianceCache        = null;
let raidsAcIdx           = -1;
let homeAcIdx            = -1;
let themePreviewEnabled  = true;

const THEME_PREVIEW_KEY = 'reaper_theme_preview';
const THEME_PREVIEW_ACTIVE_KEY = 'reaper_theme_preview_active';

/* ── Theme Presets ────────────────────────────────────────────────────── */
const THEME_COLORS = {
  blue:   { label:'Blue',   accent:'#3f8cff', accent2:'#8fc2ff', dark:['#030b18','#07142b','#0d2140'], grey:['#27374e','#344963','#415c7c'], white:['#eaf3ff','#f6fbff','#d8eaff'] },
  green:  { label:'Green',  accent:'#45d16f', accent2:'#96edae', dark:['#041106','#0a1d0e','#112b17'], grey:['#263f2d','#34523b','#42684b'], white:['#ebfff0','#f7fff9','#d9f3df'] },
  yellow: { label:'Yellow', accent:'#f4d03f', accent2:'#ffe78a', dark:['#141001','#221b04','#30270a'], grey:['#4a432b','#625938','#786d45'], white:['#fff9df','#fffdf4','#f1e7b8'] },
  orange: { label:'Orange', accent:'#ff8a2a', accent2:'#ffc078', dark:['#170902','#281003','#3a1907'], grey:['#4e3726','#674934','#805b42'], white:['#fff2e7','#fff9f3','#efd9c8'] },
  red:    { label:'Red',    accent:'#ff4d5a', accent2:'#ff9aa3', dark:['#170305','#28070b','#3b0d13'], grey:['#4f2b30','#663941','#814a51'], white:['#fff0f1','#fff8f8','#efd4d7'] },
  purple: { label:'Purple', accent:'#b36bff', accent2:'#d4a8ff', dark:['#0d0518','#180b2a','#24123e'], grey:['#3c304f','#504064','#65517d'], white:['#f6edff','#fcf8ff','#e3d5f2'] },
  brown:  { label:'Brown',  accent:'#b98254', accent2:'#dbb089', dark:['#100804','#1c0f07','#2b180d'], grey:['#46382f','#5c4a3e','#735d4f'], white:['#f7efe8','#fffaf6','#e5d6ca'] },
  gold:   { label:'Gold',   accent:'#ffd700', accent2:'#ffed4e', dark:['#0a0a0a','#0f0f0f','#141414'], grey:['#3f3820','#554a2a','#6d6037'], white:['#fff8df','#fffdf4','#eadfb8'] },
};

const THEME_SHADES = {
  dark:  { label:'Dark',  text:'#f0f0f0', muted:'#b9bbbe', hideBg:false },
  grey:  { label:'Grey',  text:'#f5f5f5', muted:'#d0d4da', hideBg:true },
  white: { label:'White', text:'#171717', muted:'#4f5660', hideBg:true },
};

const NEUTRAL_PRESETS = {
  black: { label:'Black', theme_bg_color:'#000000', theme_bg_secondary:'#050505', theme_bg_tertiary:'#0b0b0b', theme_gold_primary:'#d9d9d9', theme_gold_secondary:'#ffffff', theme_text_primary:'#f5f5f5', theme_text_secondary:'#b7b7b7', theme_hide_bg_image:false },
  grey:  { label:'Grey',  theme_bg_color:'#2b2f34', theme_bg_secondary:'#3a4047', theme_bg_tertiary:'#4b535c', theme_gold_primary:'#d8dde4', theme_gold_secondary:'#ffffff', theme_text_primary:'#f7f8fa', theme_text_secondary:'#d1d6dc', theme_hide_bg_image:true },
  white: { label:'White', theme_bg_color:'#f4f5f7', theme_bg_secondary:'#ffffff', theme_bg_tertiary:'#e1e5ea', theme_gold_primary:'#5f6977', theme_gold_secondary:'#111827', theme_text_primary:'#14171c', theme_text_secondary:'#4c5563', theme_hide_bg_image:true },
};

const MIXED_PRESETS = {
  fire:       { label:'Fire',       theme_bg_color:'#170300', theme_bg_secondary:'#2b0a00', theme_bg_tertiary:'#4a1a00', theme_gold_primary:'#ff5a1f', theme_gold_secondary:'#ffd166', theme_text_primary:'#fff3e0', theme_text_secondary:'#ffbd8a', theme_hide_bg_image:false },
  coral:      { label:'Coral',      theme_bg_color:'#03161d', theme_bg_secondary:'#06303a', theme_bg_tertiary:'#0b4a4d', theme_gold_primary:'#35d1c8', theme_gold_secondary:'#7ce7a8', theme_text_primary:'#e9fffb', theme_text_secondary:'#a4e7df', theme_hide_bg_image:false },
  aurora:     { label:'Aurora',     theme_bg_color:'#03121b', theme_bg_secondary:'#062336', theme_bg_tertiary:'#12314d', theme_gold_primary:'#42f5b6', theme_gold_secondary:'#8b7dff', theme_text_primary:'#e9fff8', theme_text_secondary:'#a8d8ff', theme_hide_bg_image:false },
  sunset:     { label:'Sunset',     theme_bg_color:'#1a0611', theme_bg_secondary:'#321022', theme_bg_tertiary:'#4d1b35', theme_gold_primary:'#ff7a3d', theme_gold_secondary:'#d66bff', theme_text_primary:'#fff1f5', theme_text_secondary:'#ffc0cf', theme_hide_bg_image:false },
  ocean:      { label:'Ocean',      theme_bg_color:'#02111f', theme_bg_secondary:'#06223a', theme_bg_tertiary:'#0c3850', theme_gold_primary:'#2f9bff', theme_gold_secondary:'#38e6b6', theme_text_primary:'#e7f7ff', theme_text_secondary:'#9bcbe8', theme_hide_bg_image:false },
  volcanic:   { label:'Volcanic',   theme_bg_color:'#090607', theme_bg_secondary:'#1d0a08', theme_bg_tertiary:'#35110a', theme_gold_primary:'#ff3b30', theme_gold_secondary:'#ff9f1c', theme_text_primary:'#fff0ec', theme_text_secondary:'#d0a19a', theme_hide_bg_image:false },
  ember:      { label:'Ember',      theme_bg_color:'#120606', theme_bg_secondary:'#240d09', theme_bg_tertiary:'#3a1b0b', theme_gold_primary:'#ff6b35', theme_gold_secondary:'#f7c948', theme_text_primary:'#fff5e8', theme_text_secondary:'#d9a76f', theme_hide_bg_image:false },
  forest:     { label:'Forest',     theme_bg_color:'#06120a', theme_bg_secondary:'#102014', theme_bg_tertiary:'#22301a', theme_gold_primary:'#62c370', theme_gold_secondary:'#d6b35a', theme_text_primary:'#ecf7e8', theme_text_secondary:'#aec7a2', theme_hide_bg_image:false },
  royal:      { label:'Royal',      theme_bg_color:'#080b24', theme_bg_secondary:'#111540', theme_bg_tertiary:'#21194f', theme_gold_primary:'#7aa2ff', theme_gold_secondary:'#ffd966', theme_text_primary:'#f0f2ff', theme_text_secondary:'#b8c2ee', theme_hide_bg_image:false },
  storm:      { label:'Storm',      theme_bg_color:'#071018', theme_bg_secondary:'#101b27', theme_bg_tertiary:'#1f2738', theme_gold_primary:'#6aa9ff', theme_gold_secondary:'#a887ff', theme_text_primary:'#eef5ff', theme_text_secondary:'#a9b8ca', theme_hide_bg_image:false },
  nebula:     { label:'Nebula',     theme_bg_color:'#0b0518', theme_bg_secondary:'#180b2d', theme_bg_tertiary:'#2a123b', theme_gold_primary:'#bd7cff', theme_gold_secondary:'#ff5d8f', theme_text_primary:'#fbf0ff', theme_text_secondary:'#cfafe8', theme_hide_bg_image:false },
  toxic:      { label:'Toxic',      theme_bg_color:'#061006', theme_bg_secondary:'#12200b', theme_bg_tertiary:'#22310b', theme_gold_primary:'#9dff3f', theme_gold_secondary:'#f3ff65', theme_text_primary:'#f2ffe8', theme_text_secondary:'#b8d58a', theme_hide_bg_image:false },
  cyber:      { label:'Cyber',      theme_bg_color:'#020b12', theme_bg_secondary:'#071923', theme_bg_tertiary:'#102a35', theme_gold_primary:'#00d9ff', theme_gold_secondary:'#baff29', theme_text_primary:'#eaffff', theme_text_secondary:'#8fd6d8', theme_hide_bg_image:false },
  desert:     { label:'Desert',     theme_bg_color:'#130c03', theme_bg_secondary:'#251806', theme_bg_tertiary:'#392709', theme_gold_primary:'#f0b34f', theme_gold_secondary:'#ff7a3d', theme_text_primary:'#fff7e8', theme_text_secondary:'#d7b27c', theme_hide_bg_image:false },
  roseGold:   { label:'Rose Gold',  theme_bg_color:'#17080d', theme_bg_secondary:'#2a1018', theme_bg_tertiary:'#3b1a24', theme_gold_primary:'#ff7aa2', theme_gold_secondary:'#f5c16c', theme_text_primary:'#fff0f4', theme_text_secondary:'#e6a8b7', theme_hide_bg_image:false },
  lava:       { label:'Lava',       theme_bg_color:'#120302', theme_bg_secondary:'#270806', theme_bg_tertiary:'#42140a', theme_gold_primary:'#ff3d00', theme_gold_secondary:'#c08457', theme_text_primary:'#fff0e8', theme_text_secondary:'#db9c7a', theme_hide_bg_image:false },
  glacier:    { label:'Glacier',    theme_bg_color:'#06131b', theme_bg_secondary:'#102733', theme_bg_tertiary:'#dfefff', theme_gold_primary:'#63cfff', theme_gold_secondary:'#73e7d4', theme_text_primary:'#effaff', theme_text_secondary:'#bad8e6', theme_hide_bg_image:false },
  twilight:   { label:'Twilight',   theme_bg_color:'#080a1f', theme_bg_secondary:'#191238', theme_bg_tertiary:'#342044', theme_gold_primary:'#8b7dff', theme_gold_secondary:'#ff9a5c', theme_text_primary:'#f4f0ff', theme_text_secondary:'#c8b9df', theme_hide_bg_image:false },
  harvest:    { label:'Harvest',    theme_bg_color:'#130b04', theme_bg_secondary:'#261509', theme_bg_tertiary:'#3d2410', theme_gold_primary:'#ff9f1c', theme_gold_secondary:'#f4d35e', theme_text_primary:'#fff6e3', theme_text_secondary:'#d9ad69', theme_hide_bg_image:false },
  prism:      { label:'Prism',      theme_bg_color:'#070b18', theme_bg_secondary:'#111b2d', theme_bg_tertiary:'#231c3b', theme_gold_primary:'#5eead4', theme_gold_secondary:'#f472b6', theme_text_primary:'#f4fbff', theme_text_secondary:'#b8c6dc', theme_hide_bg_image:false },
};

const COLOR_SHADE_PRESETS = Object.entries(THEME_COLORS).reduce((acc, [colorKey, color]) => {
  Object.entries(THEME_SHADES).forEach(([shadeKey, shade]) => {
    const id = `${colorKey}-${shadeKey}`;
    acc[id] = {
      label: `${color.label}/${shade.label}`,
      theme_bg_color: color[shadeKey][0],
      theme_bg_secondary: color[shadeKey][1],
      theme_bg_tertiary: color[shadeKey][2],
      theme_gold_primary: color.accent,
      theme_gold_secondary: color.accent2,
      theme_text_primary: shade.text,
      theme_text_secondary: shade.muted,
      theme_hide_bg_image: shade.hideBg,
    };
  });
  return acc;
}, {});

const PRESETS = {
  ...NEUTRAL_PRESETS,
  ...COLOR_SHADE_PRESETS,
  ...MIXED_PRESETS,
};

PRESETS.dark = PRESETS['gold-dark'];
PRESETS.light = PRESETS['gold-white'];

/* ── Initialization ───────────────────────────────────────────────────── */
async function initSettings() {
  console.log('[settings] initSettings()');

  const nationInput = document.getElementById('stn-nation-id-input');
  if (nationInput) nationInput.addEventListener('keypress', e => { if (e.key === 'Enter') linkNation(); });

  renderPresetGrid();
  setupColorPickers();

  const [settingsResult, discordResult] = await Promise.allSettled([
    fetchSettings(),
    fetchDiscordUser(),
  ]);

  const settingsData = settingsResult.status === 'fulfilled' ? settingsResult.value : null;
  const discordData  = discordResult.status  === 'fulfilled' ? discordResult.value  : null;
  if (settingsResult.status === 'rejected') console.warn('[settings] fetchSettings failed:', settingsResult.reason);

  currentSettings = settingsData || {};
  const activePreview = window.ReaperTheme?.readPreviewTheme?.() || null;
  themePreviewEnabled = !!activePreview || sessionStorage.getItem(THEME_PREVIEW_ACTIVE_KEY) !== '0';
  const discordUser = currentSettings.discord_user || discordData || null;

  autoFillRaidsExclude = _parseJsonArray(currentSettings.auto_fill_alliances_raids_exclude);

  // Restore home alliance from saved ID
  if (currentSettings.watch_home_alliance_id) {
    homeAlliance = {
      id: currentSettings.watch_home_alliance_id,
      name: currentSettings.watch_home_alliance_name || `Alliance ${currentSettings.watch_home_alliance_id}`,
    };
  }

  renderDiscordCard(discordUser);
  renderNationCard(currentSettings);
  renderThemeUI(activePreview || currentSettings);
  renderAutoFillUI();
  renderBgImageUI(currentSettings);
  renderPrivacyUI(currentSettings);
  renderAuditUI(currentSettings);
  _setupBgDragDrop();

  applyThemeToPage(activePreview || currentSettings);

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
  if (tab === 'audit') renderAuditUI(currentSettings);
  if (tab === 'pets') loadPetsTab();
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
  renderPresetGrid();
  const defaults = window.ReaperTheme?.DEFAULT_THEME || PRESETS['gold-dark'];
  const merged = { ...defaults, ...(settings || {}) };
  const map = { 'bg-primary': merged.theme_bg_color||'#0a0a0a', 'bg-secondary': merged.theme_bg_secondary||'#0f0f0f', 'bg-tertiary': merged.theme_bg_tertiary||'#141414', 'gold-primary': merged.theme_gold_primary||'#ffd700', 'gold-secondary': merged.theme_gold_secondary||'#ffed4e', 'text-primary': merged.theme_text_primary||'#f0f0f0', 'text-secondary': merged.theme_text_secondary||'#b9bbbe' };
  Object.entries(map).forEach(([id, val]) => { const p = document.getElementById(id); const t = document.getElementById(id+'-text'); if(p) p.value=val; if(t) t.value=val; });
  const keys = ['theme_bg_color','theme_bg_secondary','theme_bg_tertiary','theme_gold_primary','theme_gold_secondary','theme_text_primary','theme_text_secondary'];
  const matched = Object.entries(PRESETS).find(([,p]) => keys.every(k => !merged[k] || !p[k] || merged[k].toLowerCase() === p[k].toLowerCase()));
  document.querySelectorAll('.preset-swatch').forEach(b => b.classList.toggle('active', matched ? b.dataset.preset === matched[0] : false));
  const liveToggle = document.getElementById('theme-live-preview');
  if (liveToggle) liveToggle.checked = themePreviewEnabled;
}

function renderPresetGrid() {
  const grid = document.querySelector('.preset-grid');
  if (!grid) return;

  grid.innerHTML = Object.entries(PRESETS)
    .filter(([id]) => !['dark', 'light'].includes(id))
    .map(([id, preset]) => `
      <button class="preset-swatch" data-preset="${id}" onclick="applyPreset('${id}')" title="${_esc(preset.label)}">
        <span class="preset-colors">
          <span style="background:${preset.theme_bg_color}"></span>
          <span style="background:${preset.theme_bg_tertiary}"></span>
          <span style="background:${preset.theme_gold_primary}"></span>
        </span>
        <span class="preset-label">${_esc(preset.label)}</span>
      </button>
    `).join('');
  grid.dataset.rendered = '1';
}

function setupColorPickers() {
  ['bg-primary','bg-secondary','bg-tertiary','gold-primary','gold-secondary','text-primary','text-secondary'].forEach(id => {
    const p = document.getElementById(id), t = document.getElementById(id+'-text');
    if (!p || !t) return;
    if (p.dataset.themeBound === '1') return;
    p.dataset.themeBound = '1';
    t.dataset.themeBound = '1';
    p.addEventListener('input', () => { t.value = p.value; previewTheme(); });
    t.addEventListener('input', () => { if (/^#[0-9A-Fa-f]{6}$/.test(t.value)) { p.value = t.value; previewTheme(); } });
  });

  const liveToggle = document.getElementById('theme-live-preview');
  if (liveToggle && liveToggle.dataset.themeBound !== '1') {
    liveToggle.dataset.themeBound = '1';
    liveToggle.checked = themePreviewEnabled;
    liveToggle.addEventListener('change', () => setThemePreviewEnabled(liveToggle.checked));
  }
}

function applyPreset(name) {
  const preset = PRESETS[name]; if (!preset) return;
  renderThemeUI(preset);
  document.querySelectorAll('.preset-swatch').forEach(b => b.classList.toggle('active', b.dataset.preset === name));
  stageThemePreview(preset);
  const action = themePreviewEnabled ? 'previewed' : 'selected';
  showStatus('theme-status', 'success', (preset.label||name) + ` theme ${action}. Click Save to keep it.`);
  return;
  showStatus('theme-status', 'success', (preset.label||name) + ' theme previewed — click Save to keep it.');
}

function previewTheme() {
  document.querySelectorAll('.preset-swatch').forEach(b => b.classList.remove('active'));
  stageThemePreview(readThemeDraft());
}

async function saveTheme() {
  const themeData = readThemeDraft();
  const btn = document.getElementById('save-theme-btn');
  if (btn) { btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i> Saving…'; }
  try {
    const r = await fetch('/api/settings', { method:'POST', headers:{'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify(themeData) });
    const data = await r.json();
    if (r.ok && data.success) {
      clearThemePreview();
      applyThemeToPage(themeData);
      localStorage.setItem('reaper_theme', JSON.stringify(themeData));
      localStorage.setItem('reaper_theme_saved_at', Date.now().toString());
      showStatus('theme-status','success','Theme saved and applied!');
      currentSettings = {...currentSettings,...themeData};
      renderThemeUI(currentSettings);
    }
    else showStatus('theme-status','error','Failed to save theme: '+(data.detail||'Unknown error'));
  } catch { showStatus('theme-status','error','Network error saving theme.'); }
  finally { if (btn) { btn.disabled=false; btn.innerHTML='<i class="fas fa-save"></i> Save Theme'; } }
}

function resetTheme() {
  const defaults = window.ReaperTheme?.DEFAULT_THEME || PRESETS['gold-dark'];
  const saved = { ...defaults, ...currentSettings };
  clearThemePreview();
  renderThemeUI(saved); applyThemeToPage(saved);
  showStatus('theme-status','success','Reset to saved theme.');
}

function readColorInputs() {
  return { theme_bg_color:_val('bg-primary'), theme_bg_secondary:_val('bg-secondary'), theme_bg_tertiary:_val('bg-tertiary'), theme_gold_primary:_val('gold-primary'), theme_gold_secondary:_val('gold-secondary'), theme_text_primary:_val('text-primary'), theme_text_secondary:_val('text-secondary') };
}

function readThemeDraft() {
  const draft = readColorInputs();
  if (currentSettings.theme_custom_bg_url) draft.theme_custom_bg_url = currentSettings.theme_custom_bg_url;

  const activeBtn = document.querySelector('.preset-swatch.active');
  const activePreset = activeBtn ? PRESETS[activeBtn.dataset.preset] : null;
  if (activePreset) {
    draft.theme_hide_bg_image = activePreset.theme_hide_bg_image ? 1 : 0;
  } else {
    draft.theme_hide_bg_image = currentSettings.theme_hide_bg_image || 0;
  }

  return draft;
}

function stageThemePreview(theme) {
  const draft = { ...(currentSettings || {}), ...(theme || {}) };
  try {
    sessionStorage.setItem(THEME_PREVIEW_KEY, JSON.stringify(draft));
    sessionStorage.setItem(THEME_PREVIEW_ACTIVE_KEY, themePreviewEnabled ? '1' : '0');
  } catch {
    // Preview still works in the current page without sessionStorage.
  }

  if (themePreviewEnabled) applyThemeToPage(draft);
}

function clearThemePreview() {
  try {
    sessionStorage.removeItem(THEME_PREVIEW_KEY);
    sessionStorage.removeItem(THEME_PREVIEW_ACTIVE_KEY);
  } catch {
    // Nothing to clear.
  }
}

function setThemePreviewEnabled(enabled) {
  themePreviewEnabled = !!enabled;
  const draft = readThemeDraft();
  try {
    sessionStorage.setItem(THEME_PREVIEW_KEY, JSON.stringify({ ...(currentSettings || {}), ...draft }));
    sessionStorage.setItem(THEME_PREVIEW_ACTIVE_KEY, themePreviewEnabled ? '1' : '0');
  } catch {
    // Preview still works in this page.
  }

  if (themePreviewEnabled) {
    applyThemeToPage(draft);
    showStatus('theme-status', 'success', 'Live preview enabled.');
  } else {
    applyThemeToPage(currentSettings);
    showStatus('theme-status', 'success', 'Live preview disabled. Changes will apply after Save.');
  }
}

function applyThemeToPage(t) {
  const merged = { ...(currentSettings || {}), ...(t || {}) };
  if (window.ReaperTheme?.applyThemeToPage) window.ReaperTheme.applyThemeToPage(merged);
}

/* ── Auto-Fill ────────────────────────────────────────────────────────── */
function renderAutoFillUI() {
  _setChecked('auto-fill-nation-raids',  currentSettings.auto_fill_nation_raids);
  _setChecked('auto-fill-nation-revopt', currentSettings.auto_fill_nation_revopt);
  _setChecked('auto-fill-nation-revopt-inline', currentSettings.auto_fill_nation_revopt);
  _setChecked('auto-fill-nation-calc',   currentSettings.auto_fill_nation_calc);
  _setValue('revopt-default-infra', Number(currentSettings.revopt_default_infra || 0) > 0 ? currentSettings.revopt_default_infra : '');
  _setValue('revopt-default-land', Number(currentSettings.revopt_default_land || 0) > 0 ? currentSettings.revopt_default_land : '');
  _setValue('revopt-default-mmr', currentSettings.revopt_default_mmr || '0/3/5/0');
  renderTagList('raids-exclude-tags', autoFillRaidsExclude, removeRaidsExclude);
  renderHomeAllianceTag();
  _setChecked('home-alliance-nations',  currentSettings.home_alliance_nations);
  _setChecked('home-alliance-compare',  currentSettings.home_alliance_compare);
  _setChecked('home-alliance-destroy',  currentSettings.home_alliance_destroy);
  _setChecked('home-alliance-spywipe',  currentSettings.home_alliance_spywipe);
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
function readRevOptDefaultNumber(id) {
  const raw = String(document.getElementById(id)?.value || '').trim();
  if (!raw) return 0;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function readRevOptDefaultMMR() {
  return String(document.getElementById('revopt-default-mmr')?.value || '0/3/5/0')
    .trim()
    .replace(/-/g, '/');
}

function validRevOptDefaultMMR(mmr) {
  return /^([0-5])\/([0-5])\/([0-5])\/([0-3])$/.test(mmr);
}

function syncRevOptNationToggles(sourceId) {
  const main = document.getElementById('auto-fill-nation-revopt');
  const inline = document.getElementById('auto-fill-nation-revopt-inline');
  if (!main || !inline) return;
  const source = document.getElementById(sourceId);
  const val = !!source?.checked;
  main.checked = val;
  inline.checked = val;
}
window.syncRevOptNationToggles = syncRevOptNationToggles;

function renderHomeAllianceTag() {
  const tagEl    = document.getElementById('home-alliance-tags');
  const badgeDot = document.getElementById('home-alliance-dot');
  const badgeLbl = document.getElementById('home-alliance-label');
  if (tagEl) {
    if (homeAlliance) {
      const safe = (homeAlliance.name || '').replace(/'/g, "\\'");
      tagEl.innerHTML = `<span class="stn-tag">${_esc(homeAlliance.name || homeAlliance.id)}<button class="stn-tag-remove" onclick="clearHomeAlliance()" title="Remove">×</button></span>`;
      if (badgeDot) badgeDot.style.background = '#2ecc71';
      if (badgeLbl) badgeLbl.textContent = homeAlliance.name || `ID ${homeAlliance.id}`;
    } else {
      tagEl.innerHTML = '';
      if (badgeDot) badgeDot.style.background = '#636669';
      if (badgeLbl) badgeLbl.textContent = 'Not set';
    }
  }
}

function clearHomeAlliance() {
  homeAlliance = null;
  renderHomeAllianceTag();
  saveAutoFill();
}
window.clearHomeAlliance = clearHomeAlliance;

function removeRaidsExclude(name) { autoFillRaidsExclude = autoFillRaidsExclude.filter(n => n !== name); renderAutoFillUI(); saveAutoFill(); }
window.removeRaidsExclude = removeRaidsExclude;

async function saveAutoFill() {
  const btn = document.getElementById('save-autofill-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }
  try {
    const revoptMMR = readRevOptDefaultMMR();
    if (!validRevOptDefaultMMR(revoptMMR)) {
      showStatus('autofill-status', 'error', 'Revenue Optimizer MMR must be B/F/H/D with caps 5/5/5/3, like 0/3/5/0.');
      return;
    }
    const payload = {
      auto_fill_nation_raids:             document.getElementById('auto-fill-nation-raids')?.checked ? 1 : 0,
      auto_fill_nation_revopt:            (document.getElementById('auto-fill-nation-revopt')?.checked || document.getElementById('auto-fill-nation-revopt-inline')?.checked) ? 1 : 0,
      auto_fill_nation_calc:              document.getElementById('auto-fill-nation-calc')?.checked ? 1 : 0,
      revopt_default_infra:                readRevOptDefaultNumber('revopt-default-infra'),
      revopt_default_land:                 readRevOptDefaultNumber('revopt-default-land'),
      revopt_default_mmr:                  revoptMMR,
      auto_fill_alliances_raids_exclude:  JSON.stringify(autoFillRaidsExclude),
      home_alliance_nations:              document.getElementById('home-alliance-nations')?.checked ? 1 : 0,
      home_alliance_compare:              document.getElementById('home-alliance-compare')?.checked ? 1 : 0,
      home_alliance_destroy:              document.getElementById('home-alliance-destroy')?.checked ? 1 : 0,
      home_alliance_spywipe:              document.getElementById('home-alliance-spywipe')?.checked ? 1 : 0,
    };
    // Include home alliance if set
    if (homeAlliance && homeAlliance.id) {
      payload.watch_home_alliance_id   = homeAlliance.id;
      payload.watch_home_alliance_name = homeAlliance.name || '';
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
      if (homeAlliance && homeAlliance.id) {
        window._watchAllianceId = homeAlliance.id;
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

  // Home alliance — single-select; replaces any existing selection
  _setupAcSingle('add-home-alliance-input', 'home-alliance-dropdown', a => {
    homeAlliance = { id: a.id, name: a.name };
    renderHomeAllianceTag();
    saveAutoFill();
  }, () => homeAcIdx, v => { homeAcIdx = v; });
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
      clearThemePreview();
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
      applyThemeToPage(currentSettings);
      const stored = JSON.parse(localStorage.getItem('reaper_theme') || '{}'); stored.theme_custom_bg_url = data.url; localStorage.setItem('reaper_theme', JSON.stringify({...stored, ...readColorInputs(), theme_custom_bg_url: data.url})); localStorage.setItem('reaper_theme_saved_at', Date.now().toString());
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
      applyThemeToPage(currentSettings);
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
function _setValue(id, val) { const el = document.getElementById(id); if (el) el.value = val ?? ''; }
function _setChecked(id, val) { const el = document.getElementById(id); if (el) el.checked = !!(val === 1 || val === true || val === '1'); }
function _esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }


/* ── Pets Tab ─────────────────────────────────────────────────────────── */

let _settingsPet = null;

async function loadPetsTab() {
  try {
    const r = await fetch('/api/user/pet', { credentials: 'same-origin' });
    if (r.status === 401) {
      _settingsPet = null;
      return;
    }
    const d = await r.json();
    if (!d || !d.has_pet || !d.species) {
      _settingsPet = null;
      return;
    }
    _settingsPet = d;

    const killNameEl = document.getElementById('kill-pet-name-display');
    if (killNameEl) killNameEl.textContent = d.name || d.species;

    // Pre-fill rename fields
    const rnName = document.getElementById('settings-rename-name');
    if (rnName) rnName.value = d.name || '';
    const acts = d.action_labels || {};
    const rnAtk = document.getElementById('settings-rename-atk');
    if (rnAtk) rnAtk.value = acts.attack || '';
    const rnDef = document.getElementById('settings-rename-def');
    if (rnDef) rnDef.value = acts.defense || '';
    const rnChg = document.getElementById('settings-rename-chg');
    if (rnChg) rnChg.value = acts.charge || '';
    // Clear previous result/error
    const rnResult = document.getElementById('settings-rename-result');
    if (rnResult) { rnResult.style.display = 'none'; rnResult.innerHTML = ''; }
    const rnErr = document.getElementById('settings-rename-name-err');
    if (rnErr) { rnErr.style.display = 'none'; rnErr.textContent = ''; }

    await settingsLoadBadges();
    renderBadgeSection();
  } catch (e) {
    _settingsPet = null;
    console.error('[settings] loadPetsTab error:', e);
  }
}

async function killPet() {
  const input = document.getElementById('kill-pet-confirm-input');
  const status = document.getElementById('kill-pet-status');
  const typed = input ? input.value.trim() : '';

  if (!_settingsPet || typed.toLowerCase() !== (_settingsPet.name || '').toLowerCase()) {
    if (status) {
      status.className = 'stn-status-msg error';
      status.textContent = '❌ Name does not match. Type the exact pet name to confirm.';
      status.style.display = 'block';
    }
    return;
  }

  const btn = document.getElementById('kill-pet-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Releasing…'; }

  try {
    const r = await fetch('/api/pets/kill', { method: 'DELETE', credentials: 'same-origin' });
    const d = await r.json();
    if (r.ok && d.success) {
      if (status) {
        status.className = 'stn-status-msg success';
        status.textContent = '✅ Pet released successfully!';
        status.style.display = 'block';
      }
      _settingsPet = null;
      if (input) input.value = '';
      setTimeout(function() { loadPetsTab(); }, 2000);
    } else {
      if (status) {
        status.className = 'stn-status-msg error';
        status.textContent = '❌ ' + (d.detail || d.error || 'Failed to release pet.');
        status.style.display = 'block';
      }
    }
  } catch (e) {
    if (status) {
      status.className = 'stn-status-msg error';
      status.textContent = '❌ ' + (e.message || 'Network error');
      status.style.display = 'block';
    }
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-skull"></i> Release Pet'; }
  }
}

/* ── Rename Pet (Pets Tab) ───────────────────────────────────────────── */

function _el(id) { return document.getElementById(id); }

async function settingsRenamePet() {
  var nameEl  = _el('settings-rename-name');
  var nameErr = _el('settings-rename-name-err');
  var name    = (nameEl ? nameEl.value : '').trim();
  var result  = _el('settings-rename-result');

  if (nameErr) { nameErr.style.display = 'none'; nameErr.textContent = ''; }
  if (nameEl) nameEl.classList.remove('stn-input-error');

  if (!name) {
    if (nameErr) { nameErr.textContent = 'Name is required.'; nameErr.style.display = 'block'; }
    if (nameEl) nameEl.classList.add('stn-input-error');
    return;
  }
  if (name.length > 32 || !/^[a-zA-Z0-9 \-_.,!?']+$/.test(name)) {
    if (nameErr) { nameErr.textContent = 'Invalid name (max 32 chars, basic punctuation only).'; nameErr.style.display = 'block'; }
    if (nameEl) nameEl.classList.add('stn-input-error');
    return;
  }

  if (result) { result.style.display = 'none'; result.className = 'stn-status-msg'; }

  var atkEl = _el('settings-rename-atk'), defEl = _el('settings-rename-def'), chgEl = _el('settings-rename-chg');

  try {
    var r = await fetch('/api/pets/rename', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        name: name,
        actions: {
          Attack:  atkEl ? atkEl.value.trim() : '',
          Defense: defEl ? defEl.value.trim() : '',
          Charge:  chgEl ? chgEl.value.trim() : ''
        }
      })
    });
    var d = await r.json();
    if (r.ok && d.success) {
      if (result) {
        result.className = 'stn-status-msg success';
        result.innerHTML = '✅ Saved! Refreshing...';
        result.style.display = 'block';
      }
      // Update local pet state
      if (_settingsPet) {
        _settingsPet.name = name;
        if (_settingsPet.action_labels) {
          _settingsPet.action_labels.attack  = (atkEl ? atkEl.value.trim() : '') || _settingsPet.action_labels.attack;
          _settingsPet.action_labels.defense = (defEl ? defEl.value.trim() : '') || _settingsPet.action_labels.defense;
          _settingsPet.action_labels.charge  = (chgEl ? chgEl.value.trim() : '') || _settingsPet.action_labels.charge;
        }
      }
      // Apply GPP animation if provided
      if (window.PetGPP && d.animation) {
        try { PetGPP.Animation.applyAnimation(d.animation); } catch(_) {}
      };
      // Flash confirmation via GPP if available
      if (window.PetGPP) PetGPP.Flash.flash('rgba(39,174,96,0.12)', 20);
      setTimeout(function(){ loadPetsTab(); }, 1200);
    } else {
      if (result) {
        result.className = 'stn-status-msg error';
        result.innerHTML = '❌ ' + (d.detail || d.error || 'Failed');
        result.style.display = 'block';
      }
    }
  } catch(e) {
    if (result) {
      result.className = 'stn-status-msg error';
      result.innerHTML = '❌ ' + e.message;
      result.style.display = 'block';
    }
  }
}

/* ── Badge (Pets Tab) ─────────────────────────────────────────────────── */

let _settingsBadgeChoices = [];
let _settingsBadgeDefaultPrompt = '';

function _escArg(v) {
  return JSON.stringify(String(v)).replace(/"/g, '&quot;');
}

function renderBadgeSection() {
  const body = document.getElementById('pets-badge-body');
  if (!body || !_settingsPet) return;

  const pet = _settingsPet;
  const selected = pet.badge_url || '';
  const speciesImg = '/static/Emojis/Pets/' + (pet.species || 'Basic') + '.png';
  const currentImg = selected || speciesImg;
  const currentLabel = selected ? 'Saved badge will show everywhere' : 'No badge saved yet';

  let html = '';
  html += '<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(255,215,0,0.18);border-radius:6px;margin-bottom:12px">';
  html += '<img src="' + _esc(currentImg) + '" style="width:72px;height:72px;object-fit:contain;flex-shrink:0" onerror="this.src=\'/static/Emojis/Pets/Basic.png\'">';
  html += '<div><div style="font-size:0.82rem;font-weight:700;color:var(--gold-primary)">' + _esc(currentLabel) + '</div>';
  html += '<div style="font-size:0.74rem;color:var(--text-secondary);margin-top:2px">' + _esc(pet.name || pet.species || 'Pet') + '</div></div></div>';

  html += '<div style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;margin-bottom:12px">';
  html += '<input class="stn-input" id="settings-badge-upload-file" type="file" accept="image/png,image/jpeg,image/webp" onchange="settingsUploadBadge(this)">';
  html += '<button class="stn-btn stn-btn-danger stn-btn-sm" id="settings-badge-remove-btn" onclick="settingsDeleteBadge()"' + (!selected ? '' : '') + '>Use Pet Emoji</button>';
  html += '</div>';
  html += '<div id="settings-badge-upload-status" style="margin-bottom:8px;font-size:0.74rem;color:var(--gold-secondary)">PNG, JPG, or WebP. Max 5 MB.</div>';

  html += '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-bottom:12px">';
  html += '<label style="display:flex;flex-direction:column;gap:5px;font-size:0.78rem;color:var(--text-secondary)">Images<select class="stn-input" id="settings-badge-generate-count" onchange="settingsUpdateBadgeGenerateLabel()" style="width:auto">';
  [1,2,3,4].forEach(function(n) { html += '<option value="' + n + '"' + (n === 4 ? ' selected' : '') + '>' + n + '</option>'; });
  html += '</select></label>';
  html += '<button class="stn-btn stn-btn-primary" id="settings-badge-generate-btn" onclick="settingsGenerateBadges()" style="margin-top:14px">Generate 4 Badges</button>';
  html += '</div>';
  html += '<div id="settings-badge-generate-status" style="margin-top:8px;font-size:0.78rem;color:var(--text-secondary)"></div>';
  html += '<div id="settings-badge-choice-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:12px"></div>';

  body.innerHTML = html;
  renderSettingsBadgeChoices();

  // Disable remove button if no badge set
  const removeBtn = document.getElementById('settings-badge-remove-btn');
  if (removeBtn) removeBtn.disabled = !selected;
}

function renderSettingsBadgeChoices() {
  const grid = document.getElementById('settings-badge-choice-grid');
  if (!grid) return;
  if (!_settingsBadgeChoices.length) {
    grid.innerHTML = '<div style="padding:1.5rem 0;color:var(--text-secondary);font-size:0.82rem">No generated badges yet. Choose a count and generate to start.</div>';
    return;
  }
  let h = '';
  _settingsBadgeChoices.forEach(function(choice) {
    h += '<div style="background:rgba(0,0,0,0.35);border:1px solid rgba(255,215,0,0.18);border-radius:6px;padding:10px">';
    h += '<img src="' + _esc(choice.url) + '" style="width:100%;height:160px;object-fit:contain;display:block;background:rgba(0,0,0,0.25);border-radius:4px;margin-bottom:8px" onerror="this.src=\'/static/Emojis/Pets/Basic.png\'">';
    h += '<div style="display:flex;justify-content:center">';
    h += '<button class="stn-btn stn-btn-primary stn-btn-sm" onclick="settingsSaveBadge(' + _escArg(choice.id) + ')">Save This One</button>';
    h += '</div></div>';
  });
  grid.innerHTML = h;
}

function settingsBadgePromptDefault() {
  if (_settingsBadgeDefaultPrompt) return _settingsBadgeDefaultPrompt;
  const pet = _settingsPet || {};
  const species = pet.species || 'Basic';
  const type = pet.category || pet.type || 'Land';
  const e1 = pet.element || 'Basic';
  const e2raw = pet.element2;
  const e2 = (e2raw && e2raw !== 'none' && e2raw !== 'basic' && String(e2raw).trim() !== '') ? ', ' + e2raw : '';
  const identity = 'Pet: ' + species + '\nType: ' + type + '\nElement(s): ' + e1 + e2;
  return identity + '\n\nPokemon-style creature design, Ken Sugimori inspired monster companion art, creature collector RPG mascot, cute expressive fantasy pet, bold clean shapes, vibrant cel-shaded colors, full body character sprite, centered subject, entire creature visible, clean readable silhouette, sharp focus, no text, no logo, no frame, no shadow, no floor, no scenery, solid pure white background #FFFFFF';
}

async function settingsLoadBadges() {
  try {
    const res = await fetch('/api/pets/badges', { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.default_prompt) _settingsBadgeDefaultPrompt = data.default_prompt;
    if (data && Array.isArray(data.badges)) _settingsBadgeChoices = data.badges;
  } catch (err) {
    console.warn('[settings] Failed to load badges', err);
  }
}

function settingsUpdateBadgeGenerateLabel() {
  const btn = document.getElementById('settings-badge-generate-btn');
  const countEl = document.getElementById('settings-badge-generate-count');
  if (!btn || !countEl) return;
  const count = Math.max(1, Math.min(4, parseInt(countEl.value, 10) || 4));
  btn.textContent = 'Generate ' + count + ' Badge' + (count === 1 ? '' : 's');
}

async function settingsGenerateBadges() {
  const btn = document.getElementById('settings-badge-generate-btn');
  const status = document.getElementById('settings-badge-generate-status');
  const countEl = document.getElementById('settings-badge-generate-count');
  const count = Math.max(1, Math.min(4, parseInt(countEl ? countEl.value : '4', 10) || 4));
  const prompt = settingsBadgePromptDefault();
  if (btn) btn.disabled = true;
  if (status) status.textContent = 'Generating ' + count + ' badge idea' + (count === 1 ? '' : 's') + '...';
  try {
    const res = await fetch('/api/pets/badges/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ count: count, prompt: prompt })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error || 'Badge generation failed');
    if (data.default_prompt) _settingsBadgeDefaultPrompt = data.default_prompt;
    _settingsBadgeChoices = data.badges || [];
    if (data.pet) {
      _settingsPet = data.pet;
      loadPetsTab();
      return;
    }
    renderSettingsBadgeChoices();
    if (status) status.textContent = 'Pick one of the generated badges below and save it.';
  } catch (err) {
    if (status) status.textContent = err.message || 'Badge generation failed.';
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function settingsUploadBadge(input) {
  const file = input && input.files && input.files[0];
  let status = document.getElementById('settings-badge-upload-status');
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) {
    if (status) status.textContent = 'File exceeds the 5 MB limit.';
    input.value = '';
    return;
  }
  if (status) status.textContent = 'Uploading badge...';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/api/pets/badges/upload', { method: 'POST', credentials: 'include', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error || 'Badge upload failed');
    if (data.pet) {
      _settingsPet = data.pet;
      syncBadgeDisplays(data.pet);
    }
    await settingsLoadBadges();
    loadPetsTab();
  } catch (err) {
    status = document.getElementById('settings-badge-upload-status');
    if (status) status.textContent = err.message || 'Badge upload failed.';
  } finally {
    input.value = '';
  }
}

async function settingsDeleteBadge() {
  const status = document.getElementById('settings-badge-upload-status');
  const btn = document.getElementById('settings-badge-remove-btn');
  if (btn) btn.disabled = true;
  if (status) status.textContent = 'Removing custom badge...';
  try {
    const res = await fetch('/api/pets/badges', { method: 'DELETE', credentials: 'include' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error || 'Failed to remove badge');
    _settingsBadgeChoices = data.badges || [];
    if (data.pet) {
      _settingsPet = data.pet;
      syncBadgeDisplays(data.pet);
    }
    loadPetsTab();
  } catch (err) {
    if (status) status.textContent = err.message || 'Failed to remove badge.';
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function settingsSaveBadge(badgeId) {
  const status = document.getElementById('settings-badge-generate-status');
  if (status) status.textContent = 'Saving selected badge...';
  try {
    const res = await fetch('/api/pets/badges/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ id: badgeId })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error || 'Failed to save badge');
    if (data.pet) {
      _settingsPet = data.pet;
      syncBadgeDisplays(data.pet);
    }
    await settingsLoadBadges();
    loadPetsTab();
  } catch (err) {
    if (status) status.textContent = err.message || 'Failed to save badge.';
  }
}

function syncBadgeDisplays(pet) {
  if (!pet) return;
  const badgeUrl = pet.badge_url || ('/static/Emojis/Pets/' + (pet.species || 'Basic') + '.png');
  const navPetImg = document.getElementById('nav-pet-img');
  if (navPetImg) navPetImg.src = badgeUrl;
  const userCardPetImg = document.getElementById('uc-pet-img');
  if (userCardPetImg) userCardPetImg.src = badgeUrl;
}


/* ── Audit Settings ───────────────────────────────────────────────────── */

const AUDIT_COLORS = [
  { value: 'aqua',    label: 'Aqua'    },
  { value: 'black',   label: 'Black'   },
  { value: 'blue',    label: 'Blue'    },
  { value: 'brown',   label: 'Brown'   },
  { value: 'green',   label: 'Green'   },
  { value: 'lime',    label: 'Lime'    },
  { value: 'maroon',  label: 'Maroon'  },
  { value: 'olive',   label: 'Olive'   },
  { value: 'orange',  label: 'Orange'  },
  { value: 'pink',    label: 'Pink'    },
  { value: 'purple',  label: 'Purple'  },
  { value: 'red',     label: 'Red'     },
  { value: 'white',   label: 'White'   },
  { value: 'yellow',  label: 'Yellow'  },
];

let _auditSelectedColor = 'lime';
let _auditSelectedMMR   = 'basic';  // 'basic' | 'max' | 'B/F/H/D'

function renderAuditUI(settings) {
  _auditSelectedColor = settings.audit_default_color || 'lime';
  _auditSelectedMMR   = settings.audit_default_mmr   || 'basic';

  // Build color grid
  const grid = document.getElementById('audit-color-grid');
  if (grid) {
    grid.innerHTML = AUDIT_COLORS.map(c => `
      <button class="audit-color-chip${_auditSelectedColor === c.value ? ' active' : ''}"
              data-color="${c.value}"
              onclick="selectAuditColor('${c.value}')"
              title="${c.label}">
        <img src="/static/Emojis/Colors/${c.value}.png" alt="${c.label}">
        <span>${c.label}</span>
      </button>
    `).join('');
  }
  _updateColorPreviewIcon(_auditSelectedColor);

  // Set MMR preset buttons
  _applyMMRToUI(_auditSelectedMMR);
}

function selectAuditColor(color) {
  _auditSelectedColor = color;
  document.querySelectorAll('.audit-color-chip').forEach(b =>
    b.classList.toggle('active', b.dataset.color === color)
  );
  _updateColorPreviewIcon(color);
}

function _updateColorPreviewIcon(color) {
  const icon = document.getElementById('audit-color-preview-icon');
  if (icon) icon.src = `/static/Emojis/Colors/${color}.png`;
}

function selectMMRPreset(preset) {
  document.querySelectorAll('.audit-mmr-preset-btn').forEach(b =>
    b.classList.toggle('active', b.id === 'mmr-preset-' + preset)
  );
  const customWrap = document.getElementById('audit-mmr-custom-wrap');
  if (customWrap) customWrap.style.display = preset === 'custom' ? '' : 'none';
  if (preset === 'custom') {
    updateMMRDisplay(); // sets _auditSelectedMMR to the slider string
  } else {
    _auditSelectedMMR = preset;
  }
}

function updateMMRDisplay() {
  const b = document.getElementById('mmr-b')?.value ?? 0;
  const f = document.getElementById('mmr-f')?.value ?? 3;
  const h = document.getElementById('mmr-h')?.value ?? 5;
  const d = document.getElementById('mmr-d')?.value ?? 0;
  _setText('mmr-b-val', b);
  _setText('mmr-f-val', f);
  _setText('mmr-h-val', h);
  _setText('mmr-d-val', d);
  const str = `${b}/${f}/${h}/${d}`;
  _setText('audit-mmr-custom-str', str);
  _auditSelectedMMR = str;
}

function _applyMMRToUI(mmr) {
  const isBasic  = mmr === 'basic';
  const isMax    = mmr === 'max';
  const isCustom = !isBasic && !isMax;

  document.getElementById('mmr-preset-basic')?.classList.toggle('active', isBasic);
  document.getElementById('mmr-preset-max')?.classList.toggle('active', isMax);
  document.getElementById('mmr-preset-custom')?.classList.toggle('active', isCustom);

  const customWrap = document.getElementById('audit-mmr-custom-wrap');
  if (customWrap) customWrap.style.display = isCustom ? '' : 'none';

  if (isCustom) {
    const parts = mmr.split('/');
    if (parts.length === 4) {
      const setSlider = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val;
      };
      setSlider('mmr-b', parts[0]);
      setSlider('mmr-f', parts[1]);
      setSlider('mmr-h', parts[2]);
      setSlider('mmr-d', parts[3]);
      updateMMRDisplay();
    }
  }
}

async function saveAuditSettings() {
  // If custom mode is active, sync slider values into _auditSelectedMMR first
  if (document.getElementById('mmr-preset-custom')?.classList.contains('active')) {
    updateMMRDisplay();
  }

  const btn = document.getElementById('save-audit-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }

  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        audit_default_color: _auditSelectedColor,
        audit_default_mmr:   _auditSelectedMMR,
      }),
    });
    const data = await r.json();
    if (r.ok && data.success) {
      currentSettings.audit_default_color = _auditSelectedColor;
      currentSettings.audit_default_mmr   = _auditSelectedMMR;
      showStatus('audit-settings-status', 'success', `Saved — Color: ${_auditSelectedColor}, MMR: ${_auditSelectedMMR}`);
    } else {
      showStatus('audit-settings-status', 'error', 'Failed to save: ' + (data.detail || 'Unknown error'));
    }
  } catch {
    showStatus('audit-settings-status', 'error', 'Network error saving audit settings.');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save Audit Settings'; }
  }
}

/* ── Layout Tab ───────────────────────────────────────────────────────── */

let currentLayout = null;
let draggedItem = null;
let DEFAULT_LAYOUT = null;
let PAGE_META = null;

/**
 * Auto-discover pages from the actual DOM structure.
 * This eliminates the need to manually update JavaScript when adding new pages.
 * Just add the page to the HTML mega menu and it will be automatically discovered.
 */
function discoverPagesFromDOM() {
  const groups = {
    pnw: { selector: '#pnw-dropdown .mega-menu-item', pages: [], meta: {} },
    tools: { selector: '#tools-dropdown .mega-menu-item', pages: [], meta: {} },
    pets: { selector: '#pets-dropdown .mega-menu-item', pages: [], meta: {} },
    fun: { selector: '#fun-dropdown .mega-menu-item', pages: [], meta: {} },
    site: { selector: '#site-dropdown .mega-menu-item', pages: [], meta: {} }
  };

  Object.entries(groups).forEach(([groupName, config]) => {
    const items = document.querySelectorAll(config.selector);
    items.forEach(item => {
      const pageId = item.dataset.page;
      if (!pageId) return;

      // Skip hidden pages (like casino sub-games)
      const listItem = item.closest('li');
      if (listItem && listItem.style.display === 'none') return;

      // Extract icon and label
      const imgEl = item.querySelector('img');
      const spanEl = item.querySelector('span');
      
      const icon = item.dataset.icon || (imgEl ? imgEl.src.replace(window.location.origin, '') : '/static/Emojis/Menu/default.png');
      const label = spanEl ? spanEl.textContent.trim() : pageId;

      config.pages.push(pageId);
      config.meta[pageId] = { icon, label };
    });
  });

  // Build DEFAULT_LAYOUT and PAGE_META from discovered pages
  DEFAULT_LAYOUT = {
    pnw: groups.pnw.pages,
    tools: groups.tools.pages,
    pets: groups.pets.pages,
    fun: groups.fun.pages,
    site: groups.site.pages
  };

  PAGE_META = {
    ...groups.pnw.meta,
    ...groups.tools.meta,
    ...groups.pets.meta,
    ...groups.fun.meta,
    ...groups.site.meta
  };

  console.log('[LayoutSettings] Auto-discovered pages:', DEFAULT_LAYOUT);
  console.log('[LayoutSettings] Auto-discovered metadata:', PAGE_META);
}

function initLayoutTab() {
  // Auto-discover pages from DOM if not already done
  if (!DEFAULT_LAYOUT || !PAGE_META) {
    discoverPagesFromDOM();
  }

  // Load saved layout or use defaults
  const saved = currentSettings.menu_layout;
  if (saved) {
    try {
      const savedLayout = JSON.parse(saved);
      // Merge saved layout with discovered pages (in case new pages were added)
      currentLayout = mergeLayouts(savedLayout, DEFAULT_LAYOUT);
    } catch {
      currentLayout = JSON.parse(JSON.stringify(DEFAULT_LAYOUT));
    }
  } else {
    currentLayout = JSON.parse(JSON.stringify(DEFAULT_LAYOUT));
  }

  // Render all groups
  renderLayoutGroup('pnw');
  renderLayoutGroup('tools');
  renderLayoutGroup('pets');
  renderLayoutGroup('fun');
  renderLayoutGroup('site');
}

/**
 * Merge saved layout with newly discovered pages.
 * This ensures new pages appear in the layout settings even if they weren't in the saved config.
 */
function mergeLayouts(savedLayout, defaultLayout) {
  const merged = {};
  
  Object.keys(defaultLayout).forEach(groupName => {
    const savedPages = savedLayout[groupName] || [];
    const defaultPages = defaultLayout[groupName] || [];
    
    // Start with saved order
    merged[groupName] = [...savedPages];
    
    // Add any new pages that weren't in the saved layout
    defaultPages.forEach(pageId => {
      if (!merged[groupName].includes(pageId)) {
        merged[groupName].push(pageId);
      }
    });
    
    // Remove any pages that no longer exist in default
    merged[groupName] = merged[groupName].filter(pageId => defaultPages.includes(pageId));
  });
  
  return merged;
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
  ['pnw', 'tools', 'pets', 'fun', 'site'].forEach(group => {
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
  renderLayoutGroup('tools');
  renderLayoutGroup('pets');
  renderLayoutGroup('fun');
  renderLayoutGroup('site');

  showStatus('layout-status', 'success', 'Layout reset to defaults. Click Save to apply.');
}

window.saveLayoutSettings = saveLayoutSettings;
window.resetLayoutSettings = resetLayoutSettings;
window.killPet             = killPet;
window.settingsRenamePet   = settingsRenamePet;
window.settingsUploadBadge  = settingsUploadBadge;
window.settingsDeleteBadge  = settingsDeleteBadge;
window.settingsGenerateBadges = settingsGenerateBadges;
window.settingsUpdateBadgeGenerateLabel = settingsUpdateBadgeGenerateLabel;
window.settingsSaveBadge    = settingsSaveBadge;

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
