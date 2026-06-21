/**
 * news.js — Scythe News Network (SNN)
 *
 * The Grim Reaper watches all of Orbis and reports on events.
 * Every event card shows the Reaper's commentary (body text) prominently.
 * NW events get special gold treatment. Missed WMDs get comedy treatment.
 *
 * Stages:
 *   1. Config, state, utilities
 *   2. API layer
 *   3. Formatters / renderers
 *   4. Feed view
 *   5. Alliance leaderboard view
 *   6. Nations leaderboard view
 *   7. Summary stat cards
 *   8. Toggle / control wiring
 *   9. Auto-refresh + init
 */

(function () {
'use strict';

/* ---------------------------------------------------------------------------
   STAGE 1 — Config, state, utilities
   --------------------------------------------------------------------------- */

const NW_ALLIANCE_ID = 10259;
const FEED_PAGE_SIZE = 50;
const AUTO_REFRESH_MS = 60_000;

const State = {
  view:        'feed',
  period:      'weekly',
  year:        null,
  feedFilter:  'all',
  lbSort:      'total_spent',
  lbSortDir:   'desc',          // 'asc' | 'desc'
  sidebarSort: 'total_spent',
  feedOffset:  0,
  feedHasMore: false,
  available:   {},
  searchType:  null,
  searchId:    null,
  searchName:  null,
};

/* -- Resource image map (uses /static/Emojis/Resources/ folder) ------------- */
// money uses 💰 emoji directly; all others use the Resources image folder
const RESOURCE_IMG = {
  money:     null,   // rendered as 💰 emoji, not an image
  food:      '/static/Emojis/Resources/food.png',
  coal:      '/static/Emojis/Resources/coal.png',
  oil:       '/static/Emojis/Resources/oil.png',
  uranium:   '/static/Emojis/Resources/uranium.png',
  iron:      '/static/Emojis/Resources/iron.png',
  bauxite:   '/static/Emojis/Resources/bauxite.png',
  lead:      '/static/Emojis/Resources/lead.png',
  gasoline:  '/static/Emojis/Resources/gasoline.png',
  munitions: '/static/Emojis/Resources/munitions.png',
  steel:     '/static/Emojis/Resources/steel.png',
  aluminum:  '/static/Emojis/Resources/aluminum.png',
};

// Display order for resources (most valuable / most interesting first)
const RESOURCE_ORDER = [
  'money', 'uranium', 'gasoline', 'munitions', 'steel', 'aluminum',
  'oil', 'iron', 'bauxite', 'lead', 'coal', 'food',
];

// Fallback prices if the API is unavailable
const RESOURCE_PRICE_FALLBACK = {
  coal: 2000, oil: 2000, uranium: 4000, iron: 2000,
  bauxite: 2000, lead: 2000, gasoline: 3000, munitions: 2000,
  steel: 3000, aluminum: 2000, food: 150,
};

// Cached resource prices — populated by fetchResourcePrices() on init
var _resourcePrices = Object.assign({}, RESOURCE_PRICE_FALLBACK);
let _resourcePricesTimestamp = null;

/** Return an <img> tag (or 💰 emoji) for a resource icon */
function resEmoji(resource) {
  var key = resource.toLowerCase();
  if (key === 'money') return '<span class="news-res-emoji-char">💰</span>';
  var src = RESOURCE_IMG[key];
  if (!src) return '<span class="news-res-fallback">📦</span>';
  return '<img src="' + src + '" alt="' + resource + '" class="news-res-img">';
}

/** Format a resource amount — full number with commas, no K/M abbreviation */
function fmtResAmt(amt) {
  amt = Number(amt) || 0;
  if (amt >= 1e6) return (amt / 1e6).toFixed(2) + 'M';
  // Show full number with commas for amounts under 1M
  return amt.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

/** Format a resource price as a full dollar amount (no K/M abbreviation) */
function fmtResPrice(val) {
  val = Number(val) || 0;
  const sign = val < 0 ? '-' : '';
  const abs  = Math.abs(val);
  if (abs >= 1e9)  return sign + '$' + (abs / 1e9).toFixed(2) + 'B';
  if (abs >= 1e6)  return sign + '$' + (abs / 1e6).toFixed(2) + 'M';
  // Full number with commas — no K abbreviation
  return sign + '$' + abs.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/* -- Utility: money formatter ----------------------------------------------- */
function fmtMoney(val) {
  val = Number(val) || 0;
  const sign = val < 0 ? '-' : '';
  const abs  = Math.abs(val);
  if (abs >= 1e12) return sign + '$' + (abs / 1e12).toFixed(2) + 'T';
  if (abs >= 1e9)  return sign + '$' + (abs / 1e9).toFixed(2)  + 'B';
  if (abs >= 1e6)  return sign + '$' + (abs / 1e6).toFixed(1)  + 'M';
  if (abs >= 1e3)  return sign + '$' + (abs / 1e3).toFixed(0)  + 'K';
  return sign + '$' + abs.toLocaleString();
}

/* -- Utility: compact number ------------------------------------------------ */
function fmtNum(val) {
  val = Number(val) || 0;
  if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M';
  if (val >= 1e3) return (val / 1e3).toFixed(0) + 'K';
  return val.toLocaleString();
}

/* -- Utility: coerce a date value (string or Unix epoch number) to a Date -- */
function _toDate(val) {
  if (!val) return null;
  // Unix epoch (seconds) — numbers under ~1e12 are seconds, above are ms
  if (typeof val === 'number') {
    return new Date(val < 1e12 ? val * 1000 : val);
  }
  let s = String(val).replace(' ', 'T');
  // Strip +00:00 / +HH:MM suffix before appending Z to avoid double-offset
  s = s.replace(/\+\d{2}:\d{2}$/, '');
  return new Date(s + (s.includes('Z') || s.includes('+') ? '' : 'Z'));
}

/* -- Utility: relative time ------------------------------------------------- */
function fmtRelTime(dateStr) {
  if (!dateStr) return '';
  const d = _toDate(dateStr);
  if (!d || isNaN(d)) return String(dateStr);
  const diff = Date.now() - d.getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)   return s + 's ago';
  const m = Math.floor(s / 60);
  if (m < 60)   return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24)   return h + 'h ago';
  const day = Math.floor(h / 24);
  if (day < 7)  return day + 'd ago';
  return d.toLocaleDateString();
}

/* -- Utility: format a date string nicely ----------------------------------- */
function fmtDate(dateStr) {
  if (!dateStr) return '—';
  const d = _toDate(dateStr);
  if (!d || isNaN(d)) return String(dateStr);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/* -- Utility: safe HTML escape ---------------------------------------------- */
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* -- Static emoji helper ---------------------------------------------------- */
const E = {
  // Military units
  soldier:     '/static/Emojis/Military/soldier.png',
  tank:        '/static/Emojis/Military/tank.png',
  jet:         '/static/Emojis/Military/jet.png',
  ship:        '/static/Emojis/Military/ship.png',
  missile:     '/static/Emojis/Military/missile.png',
  bomb:        '/static/Emojis/Military/bomb.png',
  spy:         '/static/Emojis/Military/spy.png',
  // War outcomes
  wars:        '/static/Emojis/Military/wars.png',
  win:         '/static/Emojis/Military/win.png',
  lose:        '/static/Emojis/Military/lose.png',
  draw:        '/static/Emojis/Military/draw.png',
  peace:       '/static/Emojis/Military/peace.png',
  peace_1:     '/static/Emojis/Military/peace_1.png',
  raid:        '/static/Emojis/Military/raid.png',
  attrition:   '/static/Emojis/Military/attrition.png',
  strategy:    '/static/Emojis/Military/strategy.png',
  // Watcher
  loot:        '/static/Emojis/Watcher/loot.png',
  infra:       '/static/Emojis/Watcher/infra.png',
  improvement: '/static/Emojis/Watcher/improvement.png',
  cost:        '/static/Emojis/Watcher/cost.png',
  // Menu / misc
  domain:      '/static/Emojis/Menu/domain.png',
  calculator:  '/static/Emojis/Menu/calculator.png',
  alliance:    '/static/Emojis/Menu/alliance.png',
  news:        '/static/Emojis/Menu/news.png',
  pirate:      '/static/Emojis/Menu/pirate.png',
  treaty:      '/static/Emojis/Military/peace.png',
};

/** Return an <img> tag for a static emoji, sized for use as an event badge icon */
function eImg(src, alt, cls) {
  return `<img src="${src}" alt="${alt}" class="news-emoji-icon${cls ? ' ' + cls : ''}" draggable="false">`;
}

/* -- Utility: event type ? icon + label ------------------------------------ */
const EVENT_META = {
  city_purchase:     { img: E.domain,      label: 'City Built'    },
  city_deleted:      { img: E.domain,      label: 'City Deleted'  },
  project_purchase:  { img: E.calculator,  label: 'Project'       },
  city_upgrade:      { img: E.improvement, label: 'Upgrade'       },
  war_declared:      { img: E.wars,        label: 'War'           },
  war_ended:         { img: E.peace,       label: 'War Ended'     },
  wmd_attack:        { img: E.bomb,        label: 'WMD'           },
  loot_attack:       { img: E.loot,        label: 'Loot'          },
  military_purchase: { img: E.soldier,     label: 'Military'      },
  alliance_join:     { img: E.alliance,    label: 'Joined'        },
  alliance_leave:    { img: E.alliance,    label: 'Left'          },
  alliance_change:   { img: E.alliance,    label: 'Moved'         },
  alliance_deleted:  { img: E.alliance,    label: 'Alliance Deleted' },
  bank_deposit:      { img: E.calculator,  label: 'Deposit'       },
  bank_withdrawal:   { img: E.loot,        label: 'Withdrawal'    },
  bank_transfer:     { img: E.calculator,  label: 'Transfer'      },
  trade_completed:   { img: E.calculator,  label: 'Trade'         },
  treaty_signed:     { img: E.peace,       label: 'Treaty Signed' },
  treaty_cancelled:  { img: E.peace,       label: 'Treaty Cancelled' },
};

function eventMeta(type) {
  return EVENT_META[type] || { img: null, label: type };
}

/** Pick the best static emoji for a military_purchase event based on unit_type */
function militaryPurchaseImg(detail) {
  const unit = (detail && detail.unit_type) || '';
  const map = {
    soldiers: E.soldier,
    tanks:    E.tank,
    aircraft: E.jet,
    ships:    E.ship,
    missiles: E.missile,
    nukes:    E.bomb,
    spies:    E.spy,
  };
  return map[unit] || E.soldier;
}

/** Pick the best static emoji for a wmd_attack event based on attack_type */
function wmdImg(detail) {
  const t = (detail && detail.attack_type) || '';
  return t === 'missile' ? E.missile : E.bomb;
}

/**
 * Pick the correct war-ended icon based on outcome and whose perspective
 * this event is recorded from (attacker vs defender).
 *
 * outcome values from news_writer.py:
 *   attacker_win  — attacker defeated the defender
 *   defender_win  — defender repelled the attacker
 *   peace         — both sides agreed to peace
 *   expired       — war timer ran out with no winner
 *
 * The event is recorded twice: once with nation_id = attacker, once with
 * nation_id = defender.  We use detail.attacker.id to tell which side
 * the current event row belongs to.
 */
function warEndedImg(ev, detail) {
  const outcome    = (detail && detail.outcome) || '';
  const attackerId = detail && detail.attacker && String(detail.attacker.id);
  const isAttacker = attackerId && String(ev.nation_id) === attackerId;

  switch (outcome) {
    case 'attacker_win':
      return isAttacker ? E.win : E.lose;
    case 'defender_win':
      return isAttacker ? E.lose : E.win;
    case 'peace':
      return E.peace;
    case 'expired':
      return E.draw;
    default:
      return E.peace_1;   // fallback for unknown/legacy outcomes
  }
}

/* -- Calendar emoji paths --------------------------------------------------- */
const CAL_MONTH_IMGS = [
  'jan','feb','mar','apr','may','jun',
  'jul','aug','sep','oct','nov','dec',
];

function calImg(name) {
  return `/static/Emojis/Calender/${name}.png`;
}

/** Return the calendar image path for a given period + optional date context */
function periodCalImg(period, refDate) {
  const d = refDate || new Date();
  switch (period) {
    case 'weekly':
    case 'prev_weekly':
      return calImg('week');
    case 'monthly':
      return calImg(CAL_MONTH_IMGS[d.getUTCMonth()]);
    case 'prev_monthly': {
      const pm = (d.getUTCMonth() - 1 + 12) % 12;
      return calImg(CAL_MONTH_IMGS[pm]);
    }
    case 'yearly':
      return calImg('year');
    default:
      return calImg('week');
  }
}

/* -- Utility: period ? human label ----------------------------------------- */
function periodLabel(period, year) {
  switch (period) {
    case 'weekly':       return 'This Week';
    case 'prev_weekly':  return 'Last Week';
    case 'monthly':      return 'This Month';
    case 'prev_monthly': return 'Last Month';
    case 'yearly':       return String(year || new Date().getFullYear());
    default:             return period;
  }
}

/* -- Utility: build PnW flag URL -------------------------------------------- */
function flagUrl(url) {
  if (!url) return null;
  // PnW flags are already full URLs; proxy through our image-proxy to avoid CORS
  return '/api/image-proxy?url=' + encodeURIComponent(url);
}

/* -- Utility: flag img tag or placeholder ----------------------------------- */
function flagImg(url, cls, alt) {
  if (url) {
    return `<img src="${esc(flagUrl(url))}" class="${esc(cls)}" alt="${esc(alt)}"
              onerror="this.style.display='none'">`;
  }
  return `<span class="news-lb-flag-placeholder" title="${esc(alt)}">?</span>`;
}

/* -- Utility: net loot for a row (gained - lost) --------------------------- */
function netLoot(row) {
  return (Number(row.loot_gained) || 0) - (Number(row.loot_lost) || 0);
}

/* -- Utility: value for a given sort key ----------------------------------- */
function sortVal(row, key) {
  if (key === 'loot_gained') return netLoot(row);
  return Number(row[key]) || 0;
}

/* -- Utility: format a stat value by key ----------------------------------- */
function fmtStatVal(key, val, row) {
  const moneyKeys = new Set([
    'total_spent','infra_spent','land_spent','improvements_spent',
    'military_spent','loot_gained','loot_lost','infra_destroyed',
  ]);
  if (key === 'loot_gained' && row) return fmtMoney(netLoot(row));
  if (moneyKeys.has(key)) return fmtMoney(val);
  return fmtNum(val);
}

/* -- Utility: get element by id -------------------------------------------- */
function el(id) { return document.getElementById(id); }

/** Sync the active-sort class and ▼/▲ arrow on all leaderboard column headers */
function _syncSortHeaders(key, dir) {
  ['alliance-table-header', 'nations-table-header'].forEach(hid => {
    const hdr = el(hid);
    if (!hdr) return;
    hdr.querySelectorAll('.news-th-sortable').forEach(t => {
      const isActive = t.dataset.sort === key;
      t.classList.toggle('is-active-sort', isActive);
      const arrow = t.querySelector('.news-sort-arrow');
      if (arrow) arrow.textContent = isActive ? (dir === 'asc' ? '▲' : '▼') : '';
    });
  });
}


/* ---------------------------------------------------------------------------
   STAGE 2 — API layer
   All fetch calls go through here. Returns parsed JSON or throws.
   --------------------------------------------------------------------------- */

async function apiFetch(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${path}`);
  return res.json();
}

/** Build query string from a params object, skipping null/undefined */
function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') p.set(k, v);
  }
  const s = p.toString();
  return s ? '?' + s : '';
}

/** Fetch the summary (stat cards + available periods) */
async function fetchSummary() {
  const params = { period: State.period };
  if (State.period === 'yearly' && State.year) params.year = State.year;
  return apiFetch('/api/news/summary' + qs(params));
}

/** Fetch paginated event feed */
async function fetchEvents(offset = 0) {
  const params = {
    period: State.period,
    limit:  FEED_PAGE_SIZE,
    offset,
  };
  if (State.period === 'yearly' && State.year) params.year = State.year;
  if (State.feedFilter && State.feedFilter !== 'all') params.type = State.feedFilter;
  // Search filter: pass nation_id or filter_alliance_id to the API
  if (State.searchId) {
    if (State.searchType === 'nation')   params.nation_id          = State.searchId;
    if (State.searchType === 'alliance') params.filter_alliance_id = State.searchId;
  }
  return apiFetch('/api/news/events' + qs(params));
}

/**
 * Calls /api/news/resolve-names once with all unknown IDs, then patches
 * each event's detail.attacker / detail.defender with real names.
 */
async function resolveEventNames(events) {
  // Collect all IDs that appear as raw tokens in any headline
  const nationIdRe   = /Nation #(\d+)/g;
  const allianceIdRe = /Alliance #(\d+)/g;
  const nationIds    = new Set();
  const allianceIds  = new Set();

  for (const ev of events) {
    const h = ev.headline || '';
    for (const m of h.matchAll(nationIdRe))   nationIds.add(m[1]);
    for (const m of h.matchAll(allianceIdRe)) allianceIds.add(m[1]);
    // Also collect from detail objects
    const d = ev.detail || {};
    for (const side of ['attacker', 'defender']) {
      const s = d[side] || {};
      if (s.id)          nationIds.add(String(s.id));
      if (s.alliance_id) allianceIds.add(String(s.alliance_id));
    }
    if (ev.nation_id)       nationIds.add(String(ev.nation_id));
    if (ev.alliance_id)     allianceIds.add(String(ev.alliance_id));
    if (ev.sec_nation_id)   nationIds.add(String(ev.sec_nation_id));
    if (ev.sec_alliance_id) allianceIds.add(String(ev.sec_alliance_id));
  }

  if (!nationIds.size && !allianceIds.size) return {};

  try {
    const params = {};
    if (nationIds.size)   params.nation_ids   = [...nationIds].join(',');
    if (allianceIds.size) params.alliance_ids = [...allianceIds].join(',');
    const data = await apiFetch('/api/news/resolve-names' + qs(params));
    return { nations: data.nations || {}, alliances: data.alliances || {} };
  } catch (e) {
    console.warn('resolveEventNames failed:', e);
    return { nations: {}, alliances: {} };
  }
}

/** Fetch alliance stats leaderboard */
async function fetchAllianceStats() {
  const params = { period: State.period, limit: 100 };
  if (State.period === 'yearly' && State.year) params.year = State.year;
  return apiFetch('/api/news/alliance-stats' + qs(params));
}

/** Fetch nation stats leaderboard */
async function fetchNationStats(allianceId, nationId) {
  const params = { period: State.period, limit: 200 };
  if (State.period === 'yearly' && State.year) params.year = State.year;
  if (allianceId) params.alliance_id = allianceId;
  if (nationId) params.nation_id = nationId;
  return apiFetch('/api/news/nation-stats' + qs(params));
}

/** Live search nations + alliances from GlobalNations.db */
async function fetchSearch(query) {
  if (!query || !query.trim()) return { nations: [], alliances: [] };
  return apiFetch('/api/news/search' + qs({ q: query.trim() }));
}

/** Fetch which prev DBs exist */
async function fetchAvailable() {
  return apiFetch('/api/news/available');
}

/** Fetch current resource sell prices and cache them */
async function fetchResourcePrices() {
  try {
    const data = await apiFetch('/api/news/resource-prices');
    if (data && data.prices && Object.keys(data.prices).length > 0) {
      _resourcePrices = Object.assign({}, RESOURCE_PRICE_FALLBACK, data.prices);
      _resourcePricesTimestamp = data.timestamp || null;
    }
  } catch (e) {
    console.warn('fetchResourcePrices failed, using fallback prices:', e);
  }
}


/* ---------------------------------------------------------------------------
   STAGE 3 — Renderers
   Pure functions that return HTML strings. No DOM side-effects.
   --------------------------------------------------------------------------- */

/* -- Event feed item -------------------------------------------------------- */
function renderEventItem(ev, nameMap) {
  nameMap = nameMap || { nations: {}, alliances: {} };
  const meta   = eventMeta(ev.event_type);
  const detail = ev.detail || {};

  // NW involvement: primary party OR secondary party
  const isNWPrimary = Number(ev.alliance_id) === NW_ALLIANCE_ID;
  const isNWSec     = Number(ev.sec_alliance_id) === NW_ALLIANCE_ID;
  const isNW        = isNWPrimary || isNWSec;

  // Determine tone class for NW events
  let nwToneCls = '';
  if (isNW) {
    const t = ev.event_type;
    const outcome = detail.outcome || '';
    const missed  = detail.missed;
    const isNWAttacker = detail.is_nw_attacker;
    const isNWDefender = detail.is_nw_defender;

    if (missed) {
      nwToneCls = ' tone-funny';
    } else if (t === 'city_purchase' || t === 'project_purchase' || t === 'city_upgrade') {
      nwToneCls = isNWPrimary ? ' tone-happy' : '';
    } else if (t === 'military_purchase' && isNWPrimary) {
      nwToneCls = ' tone-happy';
    } else if (t === 'war_declared') {
      nwToneCls = isNWAttacker ? ' tone-war' : ' tone-sad';
    } else if (t === 'war_ended') {
      if (outcome === 'attacker_win' && isNWAttacker) nwToneCls = ' tone-happy';
      else if (outcome === 'defender_win' && isNWDefender) nwToneCls = ' tone-happy';
      else if (outcome === 'attacker_win' && isNWDefender) nwToneCls = ' tone-sad';
      else if (outcome === 'defender_win' && isNWAttacker) nwToneCls = ' tone-sad';
      else nwToneCls = ' tone-neutral';
    } else if (t === 'wmd_attack') {
      nwToneCls = isNWDefender ? ' tone-sad' : (isNWAttacker ? ' tone-war' : '');
    } else if (t === 'loot_attack') {
      nwToneCls = isNWDefender ? ' tone-sad' : (isNWAttacker ? ' tone-happy' : '');
    } else if (t === 'alliance_join') {
      nwToneCls = isNWPrimary ? ' tone-happy' : '';
    } else if (t === 'alliance_leave') {
      nwToneCls = isNWPrimary ? ' tone-neutral' : '';
    } else if (t === 'treaty_signed') {
      nwToneCls = isNW ? ' tone-happy' : '';
    } else if (t === 'treaty_cancelled') {
      nwToneCls = isNW ? ' tone-neutral' : '';
    }
  }

  const nwCls = isNW ? ' is-nw' : '';

  // Pick the best icon for this specific event
  let badgeImg;
  if (ev.event_type === 'military_purchase') {
    badgeImg = militaryPurchaseImg(detail);
  } else if (ev.event_type === 'wmd_attack') {
    badgeImg = wmdImg(detail);
  } else if (ev.event_type === 'war_ended') {
    badgeImg = warEndedImg(ev, detail);
  } else {
    badgeImg = meta.img;
  }
  const badgeHtml = badgeImg
    ? eImg(badgeImg, meta.label, 'news-badge-img')
    : `<span style="font-size:1.1rem">📋</span>`;

  // -- Link builders ------------------------------------------------------
  function nationLink(id, name) {
    if (!id) return esc(name || '');
    const resolved = (nameMap.nations[String(id)] || {}).name || name;
    const label = resolved || `Nation #${id}`;
    return `<a href="https://politicsandwar.com/nation/id=${id}" target="_blank" rel="noopener" class="news-pnw-link" onclick="event.stopPropagation()">${esc(label)}</a>`;
  }
  function allianceLink(id, name) {
    if (!id || Number(id) === 0) return esc(name || '');
    const resolved = nameMap.alliances[String(id)] || name;
    const label = resolved || `Alliance #${id}`;
    return `<a href="https://politicsandwar.com/alliance/id=${id}" target="_blank" rel="noopener" class="news-pnw-link" onclick="event.stopPropagation()">${esc(label)}</a>`;
  }

  // -- Replace all Nation/Alliance tokens in headline ---------------------
  const knownNations   = {};
  const knownAlliances = {};

  if (ev.nation_id)       knownNations[ev.nation_id]         = (nameMap.nations[String(ev.nation_id)] || {}).name || ev.nation_name;
  if (ev.alliance_id)     knownAlliances[ev.alliance_id]     = nameMap.alliances[String(ev.alliance_id)] || ev.alliance_name;
  if (ev.sec_nation_id)   knownNations[ev.sec_nation_id]     = (nameMap.nations[String(ev.sec_nation_id)] || {}).name || ev.sec_nation_name;
  if (ev.sec_alliance_id) knownAlliances[ev.sec_alliance_id] = nameMap.alliances[String(ev.sec_alliance_id)] || ev.sec_alliance_name;

  for (const side of ['attacker', 'defender']) {
    const s = detail[side] || {};
    if (s.id)          knownNations[s.id]            = (nameMap.nations[String(s.id)] || {}).name || s.name;
    if (s.alliance_id) knownAlliances[s.alliance_id] = nameMap.alliances[String(s.alliance_id)] || s.alliance_name;
  }
  if (detail.old_alliance_id) knownAlliances[detail.old_alliance_id] = nameMap.alliances[String(detail.old_alliance_id)] || detail.old_alliance_name;
  if (detail.new_alliance_id) knownAlliances[detail.new_alliance_id] = nameMap.alliances[String(detail.new_alliance_id)] || detail.new_alliance_name;

  let headline = ev.headline || '—';
  for (const [id, name] of Object.entries(knownNations)) {
    headline = headline.replace(new RegExp(`Nation #${id}\\b`, 'g'), nationLink(id, name));
  }
  for (const [id, name] of Object.entries(knownAlliances)) {
    headline = headline.replace(new RegExp(`Alliance #${id}\\b`, 'g'), allianceLink(id, name));
  }
  headline = headline.replace(/Nation #(\d+)/g,   (_, id) => nationLink(id, null));
  headline = headline.replace(/Alliance #(\d+)/g, (_, id) => allianceLink(id, null));

  // -- Reaper body text (the main article paragraph) ----------------------
  // Replace Nation/Alliance tokens in body text — ID tokens first (most reliable),
  // then fall back to name-based replacement for any plain names not tokenized.
  let bodyText = detail.body || '';
  if (bodyText) {
    // Track which IDs were already linked via token replacement
    const linkedNationIds  = new Set();
    const linkedAllianceIds = new Set();

    // Replace Nation #ID tokens directly
    bodyText = bodyText.replace(/Nation #(\d+)/g, (_, id) => {
      linkedNationIds.add(id);
      const name = (knownNations[id] || null);
      return nationLink(id, name);
    });
    // Replace Alliance #ID tokens directly
    bodyText = bodyText.replace(/Alliance #(\d+)/g, (_, id) => {
      linkedAllianceIds.add(id);
      const name = (knownAlliances[id] || null);
      return allianceLink(id, name);
    });
    // Fall back to name-based replacement only for IDs not already linked
    for (const [id, name] of Object.entries(knownNations)) {
      if (!name || linkedNationIds.has(id)) continue;
      bodyText = bodyText.replace(new RegExp(`\\b${escRegex(name)}\\b`, 'g'), nationLink(id, name));
    }
    for (const [id, name] of Object.entries(knownAlliances)) {
      if (!name || linkedAllianceIds.has(id)) continue;
      bodyText = bodyText.replace(new RegExp(`\\b${escRegex(name)}\\b`, 'g'), allianceLink(id, name));
    }
  }

  // -- Flags --------------------------------------------------------------
  const nFlag = ev.nation_flag
    ? `<img src="${esc(flagUrl(ev.nation_flag))}" class="news-event-nation-flag" alt="${esc(ev.nation_name)}" onerror="this.style.display='none'">`
    : '';
  const aFlag = ev.alliance_flag
    ? `<img src="${esc(flagUrl(ev.alliance_flag))}" class="news-event-alliance-flag" alt="${esc(ev.alliance_name)}" onerror="this.style.display='none'">`
    : '';

  // -- Value display ------------------------------------------------------
  let valueHtml = '';
  const rawVal = Number(ev.value) || 0;
  const moneyTypes = new Set(['city_purchase','project_purchase','city_upgrade','military_purchase','loot_attack','bank_deposit','bank_withdrawal','bank_transfer','trade_completed']);
  const noValueTypes = new Set(['war_ended', 'war_declared']);
  if (ev.event_type === 'wmd_attack') {
    // Show total destruction (infra + improvements cash + improvements resources)
    const totalDest = Number(detail.total_destruction_value || 0);
    if (totalDest > 0) valueHtml = fmtMoney(totalDest);
  } else if (!noValueTypes.has(ev.event_type) && rawVal > 0) {
    valueHtml = moneyTypes.has(ev.event_type) ? fmtMoney(rawVal) : fmtNum(rawVal);
  }

  // -- Structured detail items (shown on expand, below body text) ---------
  // Skip keys that are rendered elsewhere or are internal
  const SKIP_KEYS = new Set([
    'body', 'city_id', 'city_name', 'is_nw', 'is_nw_attacker', 'is_nw_defender',
    'attacker', 'defender', 'war_id', 'war_type', 'end_reason', 'outcome',
    'winner_id', 'old_alliance_id', 'old_alliance_name', 'new_alliance_id', 'new_alliance_name',
    'joining_nw', 'leaving_nw', 'count', 'projects', 'resource_costs', 'resources_looted',
    'resources',  // legacy bank field — now stored as resource_costs
    'improvements_built', 'improvements_destroyed', 'missed', 'detail',
    // WMD fields rendered in the custom damage breakdown panel instead
    'infra_destroyed_value', 'improvements_cash_cost', 'impr_resource_value', 'total_destruction_value',
    // Trade fields rendered in custom breakdown
    'buyer_id', 'buyer_name', 'buyer_alliance_id', 'buyer_alliance_name',
    'seller_id', 'seller_name', 'seller_alliance_id', 'seller_alliance_name',
    'total_value', 'resource_value',  // Trade: only money_amount is the actual transaction value
  ]);

  // Human-readable labels for detail keys
  const DETAIL_KEY_LABELS = {
    'old_cities':          'Cities Before',
    'new_cities':          'Cities After',
    'cash_cost':           'Cash Cost',
    'resource_value':      'Resource Value',
    'total_value':         'Total Value',
    'total_cost':          'Total Cost',
    'unit_type':           'Unit Type',
    'quantity':            'Quantity',
    'infra_spent':         'Infra Spent',
    'land_spent':          'Land Spent',
    'improvements_spent':  'Improvements Spent',
    'total_spent':         'Total Spent',
    'infra_before':        'Infra Before',
    'infra_after':         'Infra After',
    'land_before':         'Land Before',
    'land_after':          'Land After',
    'money_looted':        'Cash Looted',
    'total_loot_value':    'Total Loot Value',
    'infra_destroyed_value':   'Infra Destroyed',
    'improvements_cash_cost':  'Impr Cost (Cash)',
    'impr_resource_value':     'Impr Cost (Resources)',
    'total_destruction_value': 'Total Destruction',
    'resistance_lost':     'Resistance Lost',
    'attack_type':         'Weapon Type',
    'war_type':            'War Type',
    'reason':              'Reason',
    'end_reason':          'End Reason',
    'bankrec_id':          'Bank Rec ID',
    'sender_id':           'Sender ID',
    'sender_type':         'Sender Type',
    'receiver_id':         'Receiver ID',
    'receiver_type':       'Receiver Type',
    'banker_id':           'Banker ID',
    'money':               'Cash',
    'note':                'Note',
  };

  const detailItems = Object.entries(detail)
    .filter(([k, v]) => {
      if (SKIP_KEYS.has(k)) return false;
      if (v == null || v === '' || v === false) return false;
      if (typeof v === 'object') return false;
      return true;
    })
    .map(([k, v]) => {
      const label = DETAIL_KEY_LABELS[k] || k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      const isMoney = typeof v === 'number' && (k.includes('cost') || k.includes('spent') || k.includes('loot') || k.includes('value') || k.includes('money') || k.includes('infra'));
      const isCount = typeof v === 'number' && (k.includes('quantity') || k.includes('cities') || k.includes('resistance'));
      let displayVal;
      if (isMoney) displayVal = fmtMoney(v);
      else if (isCount) displayVal = fmtNum(v);
      else displayVal = esc(String(v));
      return `<div class="news-detail-item">
        <span class="news-detail-key">${esc(label)}</span>
        <span class="news-detail-val">${displayVal}</span>
      </div>`;
    }).join('');

  // -- Resource costs breakdown -------------------------------------------
  let resourceCostItems = '';
  if (detail.resource_costs && typeof detail.resource_costs === 'object') {
    const costEntries = Object.entries(detail.resource_costs).filter(function(e) { return Number(e[1]) > 0; });
    if (costEntries.length > 0) {
      var costRows = costEntries.map(function(entry) {
        var res = entry[0]; var amt = entry[1];
        var imgTag = resEmoji(res);
        var price = _resourcePrices[res.toLowerCase()] || 0;
        var value = Number(amt) * price;
        return '<div class="news-resource-row">'
          + '<span class="news-resource-emoji">' + imgTag + '</span>'
          + '<span class="news-resource-name">' + esc(res.charAt(0).toUpperCase() + res.slice(1)) + '</span>'
          + '<span class="news-resource-amt">' + fmtResAmt(Number(amt)) + '</span>'
          + (price > 0
            ? '<span class="news-resource-price">@ ' + fmtResPrice(price) + '</span>'
              + '<span class="news-resource-value">= ' + fmtMoney(value) + '</span>'
            : '<span class="news-resource-price"></span><span class="news-resource-value"></span>')
          + '</div>';
      }).join('');
      var priceNote = _resourcePricesTimestamp
        ? '<span class="news-price-note">Prices as of ' + fmtDate(_resourcePricesTimestamp) + ' (best sell)</span>'
        : '';
      var sectionTitle = ev.event_type === 'wmd_attack'
        ? '<img src="/static/Emojis/Watcher/improvement.png" alt="" class="news-res-img"> Resources to Rebuild'
        : '<img src="/static/Emojis/Watcher/improvement.png" alt="" class="news-res-img"> Resources Used';
      resourceCostItems = '<div class="news-resource-section">'
        + '<div class="news-resource-section-title">' + sectionTitle + '</div>'
        + '<div class="news-resource-grid">'
        + '<div class="news-resource-grid-header"><span></span><span>Resource</span><span>Amount</span><span>Sell Price</span><span>Value</span></div>'
        + costRows
        + '</div>'
        + priceNote
        + '</div>';
    }
  }

  // -- Resources looted breakdown -----------------------------------------
  // Shown prominently for loot_attack events — full breakdown with sell prices
  let resourceLootItems = '';
  if (ev.event_type === 'loot_attack' &&
      detail.resources_looted && typeof detail.resources_looted === 'object') {
    const moneyLooted = Number(detail.money_looted || detail.value2 || 0);
    const totalLootValue = Number(detail.total_loot_value || ev.value || 0);

    // Build rows in importance order
    const lootRows = [];

    // Cash first
    if (moneyLooted > 0) {
      lootRows.push('<div class="news-resource-row news-loot-row">'
        + '<span class="news-resource-emoji"><span class="news-res-emoji-char">💰</span></span>'
        + '<span class="news-resource-name">Cash</span>'
        + '<span class="news-resource-amt">' + fmtMoney(moneyLooted) + '</span>'
        + '<span class="news-resource-price"></span>'
        + '<span class="news-resource-value news-loot-value">' + fmtMoney(moneyLooted) + '</span>'
        + '</div>');
    }

    // Resources in importance order
    for (const res of RESOURCE_ORDER) {
      if (res === 'money') continue;
      const amt = Number((detail.resources_looted)[res] || 0);
      if (amt < 0.01) continue;
      const imgTag = resEmoji(res);
      const price = _resourcePrices[res] || RESOURCE_PRICE_FALLBACK[res] || 0;
      const value = amt * price;
      lootRows.push('<div class="news-resource-row news-loot-row">'
        + '<span class="news-resource-emoji">' + imgTag + '</span>'
        + '<span class="news-resource-name">' + esc(res.charAt(0).toUpperCase() + res.slice(1)) + '</span>'
        + '<span class="news-resource-amt">' + fmtResAmt(amt) + '</span>'
        + '<span class="news-resource-price">@ ' + fmtResPrice(price) + '/unit</span>'
        + '<span class="news-resource-value news-loot-value">= ' + fmtMoney(value) + '</span>'
        + '</div>');
    }

    // Infra destroyed
    const infraVal = Number(detail.infra_destroyed_value || 0);
    if (infraVal > 0) {
      lootRows.push('<div class="news-resource-row news-loot-row">'
        + '<span class="news-resource-emoji"><img src="/static/Emojis/Watcher/infra.png" alt="infra" class="news-res-img"></span>'
        + '<span class="news-resource-name">Infrastructure</span>'
        + '<span class="news-resource-amt">destroyed</span>'
        + '<span class="news-resource-price"></span>'
        + '<span class="news-resource-value news-loot-value">= ' + fmtMoney(infraVal) + '</span>'
        + '</div>');
    }

    if (lootRows.length > 0) {
      var priceNote = _resourcePricesTimestamp
        ? '<span class="news-price-note">Prices as of ' + fmtDate(_resourcePricesTimestamp) + ' (best sell)</span>'
        : '<span class="news-price-note">Prices: current best sell</span>';
      var totalRow = totalLootValue > 0
        ? '<div class="news-loot-total-row">'
          + '<span></span><span class="news-loot-total-label">Total Value</span>'
          + '<span></span><span></span>'
          + '<span class="news-loot-total-value">' + fmtMoney(totalLootValue) + '</span>'
          + '</div>'
        : '';
      resourceLootItems = '<div class="news-loot-breakdown">'
        + '<div class="news-loot-breakdown-title"><img src="/static/Emojis/Watcher/loot.png" alt="loot" class="news-res-img"> Full Loot Breakdown</div>'
        + '<div class="news-resource-grid news-loot-grid">'
        + '<div class="news-resource-grid-header"><span></span><span>Resource</span><span>Amount</span><span>Sell Price</span><span>Value</span></div>'
        + lootRows.join('')
        + totalRow
        + '</div>'
        + priceNote
        + '</div>';
    }
  }

  // -- Improvements built/destroyed breakdown -----------------------------
  let improvementsItems = '';
  const impsBuilt = detail.improvements_built;
  const impsDestroyed = detail.improvements_destroyed;
  if (impsBuilt && typeof impsBuilt === 'object' && Object.keys(impsBuilt).length) {
    improvementsItems += Object.entries(impsBuilt)
      .filter(([, c]) => Number(c) > 0)
      .map(([imp, c]) => `<div class="news-detail-item">
        <span class="news-detail-key">built: ${esc(imp.replace(/_/g,' '))}</span>
        <span class="news-detail-val">×${c}</span>
      </div>`).join('');
  }
  if (impsDestroyed && typeof impsDestroyed === 'object' && Object.keys(impsDestroyed).length) {
    improvementsItems += Object.entries(impsDestroyed)
      .filter(([, c]) => Number(c) > 0)
      .map(([imp, c]) => `<div class="news-detail-item">
        <span class="news-detail-key">destroyed: ${esc(imp.replace(/_/g,' '))}</span>
        <span class="news-detail-val">×${c}</span>
      </div>`).join('');
  }

  // -- Project list -------------------------------------------------------
  let projectListItems = '';
  if (ev.event_type === 'project_purchase' && Array.isArray(detail.projects) && detail.projects.length > 0) {
    projectListItems = detail.projects
      .map(p => `<div class="news-detail-item">
        <span class="news-detail-key">project</span>
        <span class="news-detail-val">${esc(p)}</span>
      </div>`).join('');
  }

  // -- Trade resources breakdown -------------------------------------------
  let tradeResourceItems = '';
  if (ev.event_type === 'trade_completed' && detail.resources_traded && typeof detail.resources_traded === 'object') {
    const tradeRows = [];
    for (const res of RESOURCE_ORDER) {
      if (res === 'money') continue;
      const amt = Number((detail.resources_traded)[res] || 0);
      if (amt < 0.01) continue;
      const imgTag = resEmoji(res);
      const price = _resourcePrices[res] || RESOURCE_PRICE_FALLBACK[res] || 0;
      const value = amt * price;
      tradeRows.push('<div class="news-resource-row">'
        + '<span class="news-resource-emoji">' + imgTag + '</span>'
        + '<span class="news-resource-name">' + esc(res.charAt(0).toUpperCase() + res.slice(1)) + '</span>'
        + '<span class="news-resource-amt">' + fmtResAmt(amt) + '</span>'
        + (price > 0
          ? '<span class="news-resource-price">@ ' + fmtResPrice(price) + '/unit</span>'
            + '<span class="news-resource-value">= ' + fmtMoney(value) + '</span>'
          : '<span class="news-resource-price"></span><span class="news-resource-value"></span>')
        + '</div>');
    }

    if (tradeRows.length > 0) {
      var priceNote = _resourcePricesTimestamp
        ? '<span class="news-price-note">Prices as of ' + fmtDate(_resourcePricesTimestamp) + ' (best sell)</span>'
        : '<span class="news-price-note">Prices: current best sell</span>';
      tradeResourceItems = '<div class="news-resource-section">'
        + '<div class="news-resource-section-title"><img src="/static/Emojis/Watcher/improvement.png" alt="" class="news-res-img"> Resources Traded</div>'
        + '<div class="news-resource-grid">'
        + '<div class="news-resource-grid-header"><span></span><span>Resource</span><span>Amount</span><span>Sell Price</span><span>Value</span></div>'
        + tradeRows.join('')
        + '</div>'
        + priceNote
        + '</div>';
    }
  }

  // -- Alliance meta row --------------------------------------------------
  // Use stored alliance_name from the event (reflects alliance at time of event),
  // falling back to live nameMap only when the stored name is missing/blank.
  const storedAllianceName    = ev.alliance_name    || null;
  const storedSecAllianceName = ev.sec_alliance_name || null;
  const resolvedAllianceName    = storedAllianceName    || nameMap.alliances[String(ev.alliance_id)]    || null;
  const resolvedSecAllianceName = ev.sec_alliance_id
    ? (storedSecAllianceName || nameMap.alliances[String(ev.sec_alliance_id)] || null)
    : null;
  let allianceMetaHtml = resolvedAllianceName
    ? `<span class="news-event-alliance">${allianceLink(ev.alliance_id, resolvedAllianceName)}</span>`
    : '';
  if (resolvedSecAllianceName && ev.sec_alliance_id !== ev.alliance_id) {
    allianceMetaHtml += `<span class="news-event-alliance">${allianceLink(ev.sec_alliance_id, resolvedSecAllianceName)}</span>`;
  }

  // -- War costs toggle (NW war_ended only) ------------------------------
  const warId = ev.event_type === 'war_ended' ? (detail.war_id || rawVal || null) : null;
  const showWarCostsBtn = isNW && warId
    ? `<button class="news-war-costs-btn" data-war-id="${esc(String(warId))}" title="Show war costs" aria-expanded="false">${eImg('/static/Emojis/Watcher/cost.png', 'War Costs', 'news-chip-img')} War Costs</button>`
    : '';

  // -- Missed WMD badge ---------------------------------------------------
  const missedBadge = detail.missed
    ? `<span class="news-missed-badge">💨 MISSED</span>`
    : '';

  const hasExpandContent = !!(detailItems || resourceCostItems || improvementsItems || projectListItems || tradeResourceItems)
    || (ev.event_type === 'wmd_attack' && !detail.missed);

  // Build the expand panel with a two-column layout:
  // Left: key-value stats + improvements + projects
  // Right: resource costs section (full width table, not squashed)
  let expandHtml = '';
  if (ev.event_type === 'wmd_attack' && !detail.missed) {
    // ── WMD damage breakdown ─────────────────────────────────────────────
    // Left: clean vertical list — weapon, resistance, infra cost,
    //       each improvement destroyed, impr cash cost, total destruction
    // Right: resource table (steel/aluminum to rebuild, with sell prices)
    const wmdRows = [];

    const mkRow = (label, val, isTot) =>
      `<div class="news-wmd-row${isTot ? ' is-total' : ''}">` +
      `<span class="news-wmd-label">${esc(label)}</span>` +
      `<span class="news-wmd-val">${val}</span></div>`;

    // Weapon type
    if (detail.attack_type) {
      wmdRows.push(mkRow('Weapon', detail.attack_type.charAt(0).toUpperCase() + detail.attack_type.slice(1)));
    }
    // Resistance lost
    if (detail.resistance_lost) {
      wmdRows.push(mkRow('Resistance Lost', fmtNum(detail.resistance_lost)));
    }

    // Separator before costs
    wmdRows.push('<div class="news-wmd-sep"></div>');

    // Infra destroyed
    const infraVal = Number(detail.infra_destroyed_value || 0);
    if (infraVal > 0) {
      wmdRows.push(mkRow('Infra Destroyed', fmtMoney(infraVal)));
    }

    // Each improvement destroyed on its own row
    const impsD = detail.improvements_destroyed;
    if (impsD && typeof impsD === 'object') {
      const impEntries = Object.entries(impsD).filter(([, c]) => Number(c) > 0);
      if (impEntries.length > 0) {
        wmdRows.push('<div class="news-wmd-sep"></div>');
        impEntries.forEach(([imp, c]) => {
          const label = imp.replace(/_/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase());
          wmdRows.push(mkRow('Destroyed: ' + label, '×' + c));
        });
      }
    }

    // Improvements cash cost
    const impCash = Number(detail.improvements_cash_cost || 0);
    if (impCash > 0) {
      wmdRows.push(mkRow('Impr Cost (Cash)', fmtMoney(impCash)));
    }

    // Total destruction — gold highlighted
    const totalDest = Number(detail.total_destruction_value || 0);
    if (totalDest > 0) {
      wmdRows.push('<div class="news-wmd-sep"></div>');
      wmdRows.push(mkRow('Total Destruction', fmtMoney(totalDest), true));
    }

    const wmdLeftHtml = wmdRows.length
      ? `<div class="news-expand-left"><div class="news-wmd-damage">${wmdRows.join('')}</div></div>`
      : '';
    const wmdRightHtml = resourceCostItems
      ? `<div class="news-expand-right">${resourceCostItems}</div>`
      : '';

    if (wmdLeftHtml || wmdRightHtml) {
      expandHtml = `<div class="news-event-detail"><div class="news-expand-layout">${wmdLeftHtml}${wmdRightHtml}</div></div>`;
    }
  } else if (hasExpandContent) {
    const leftItems = projectListItems + detailItems + improvementsItems;
    const leftHtml  = leftItems
      ? `<div class="news-expand-left"><div class="news-detail-grid">${leftItems}</div></div>`
      : '';
    const rightHtml = resourceCostItems || tradeResourceItems
      ? `<div class="news-expand-right">${resourceCostItems || tradeResourceItems}</div>`
      : '';
    expandHtml = `<div class="news-event-detail"><div class="news-expand-layout">${leftHtml}${rightHtml}</div></div>`;
  }

  return `
<div class="news-event-item${nwCls}${nwToneCls}" data-id="${esc(ev.id)}" data-type="${esc(ev.event_type)}">
  <div class="news-event-badge type-${esc(ev.event_type)}">${badgeHtml}</div>
  <div class="news-event-body">
    <div class="news-event-headline">${headline}${missedBadge}</div>
    ${bodyText ? `<div class="news-event-reaper-body">${bodyText}</div>` : ''}
    ${resourceLootItems}
    <div class="news-event-meta">
      ${nFlag}${aFlag}${allianceMetaHtml}
      <span class="news-event-type-tag">${esc(meta.label)}</span>
      <span class="news-event-time">${fmtRelTime(ev.event_date)}</span>
      ${showWarCostsBtn}
      ${hasExpandContent ? `<span class="news-expand-hint" title="Click card to expand details">▼ Details</span>` : ''}
    </div>
    ${expandHtml}
    <div class="news-war-costs-panel" hidden></div>
  </div>
  <div class="news-event-value">${valueHtml}</div>
</div>`;
}

/** Escape a string for use in a RegExp */
function escRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/* -- War costs panel renderer ----------------------------------------------- */
function renderWarCostsPanel(data) {
  if (data.error) {
    return `<div class="news-war-costs-error">⚠️ ${esc(data.error)}</div>`;
  }

  function sideHtml(label, side) {
    if (!side || !Object.keys(side).length) return '';
    const rows = [
      ['Gross Cost',        fmtMoney(side.gross_cost        || 0)],
      ['Net Damage',        fmtMoney(side.net_damage        || 0)],
      ['Infra Lost',        `${fmtNum(side.infra_lost_levels || 0)} lvls (${fmtMoney(side.infra_lost_value || 0)})`],
      ['Units Cost',        fmtMoney(side.units_cost        || 0)],
      ['Soldiers Lost',     fmtNum(side.soldiers_lost       || 0)],
      ['Tanks Lost',        fmtNum(side.tanks_lost          || 0)],
      ['Aircraft Lost',     fmtNum(side.aircraft_lost       || 0)],
      ['Ships Lost',        fmtNum(side.ships_lost          || 0)],
      ['Missiles Lost',     fmtNum(side.missiles_lost       || 0)],
      ['Nukes Lost',        fmtNum(side.nukes_lost          || 0)],
      ['Gas Used',          fmtNum(side.gas_used            || 0)],
      ['Mun Used',          fmtNum(side.mun_used            || 0)],
      ['Loot Net',          fmtMoney(side.loot_net          || 0)],
    ].filter(([, v]) => v !== '0' && v !== '$0' && v !== '0 lvls ($0)');

    return `
<div class="news-wc-side">
  <div class="news-wc-side-label">${esc(label)}</div>
  ${rows.map(([k, v]) => `
  <div class="news-wc-row">
    <span class="news-wc-key">${esc(k)}</span>
    <span class="news-wc-val">${v}</span>
  </div>`).join('')}
</div>`;
  }

  const attLabel = data.att_name || `Nation #${data.att_id}`;
  const defLabel = data.def_name || `Nation #${data.def_id}`;

  return `
<div class="news-war-costs-grid">
  ${sideHtml(attLabel + ' (Attacker)', data.attacker)}
  ${sideHtml(defLabel + ' (Defender)', data.defender)}
</div>`;
}

/** Wire war-costs toggle buttons inside a container element */
function wireWarCostsBtns(container) {
  container.querySelectorAll('.news-war-costs-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation(); // don't toggle the expand/collapse of the parent item
      const warId = btn.dataset.warId;
      const panel = btn.closest('.news-event-body').querySelector('.news-war-costs-panel');
      if (!panel) return;

      const isOpen = btn.getAttribute('aria-expanded') === 'true';
      if (isOpen) {
        panel.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML = `${eImg('/static/Emojis/Watcher/cost.png', 'War Costs', 'news-chip-img')} War Costs`;
        return;
      }

      // Show loading state
      btn.disabled = true;
      btn.innerHTML = `${eImg('/static/Emojis/Watcher/cost.png', '', 'news-chip-img')} Loading…`;
      panel.hidden = false;
      panel.innerHTML = '<div class="news-wc-loading">Loading war costs—</div>';

      try {
        const data = await apiFetch(`/api/news/war-costs/${warId}`);
        panel.innerHTML = renderWarCostsPanel(data);
        btn.setAttribute('aria-expanded', 'true');
        btn.innerHTML = `${eImg('/static/Emojis/Watcher/cost.png', '', 'news-chip-img')} Hide Costs`;
      } catch (err) {
        panel.innerHTML = `<div class="news-war-costs-error">⚠️ Failed to load war costs.</div>`;
        btn.setAttribute('aria-expanded', 'true');
        btn.innerHTML = `${eImg('/static/Emojis/Watcher/cost.png', '', 'news-chip-img')} Hide Costs`;
      } finally {
        btn.disabled = false;
      }
    });
  });
}


function renderSidebarItem(row, rank, sortKey, isNation) {
  const rankCls = rank <= 3 ? ` rank-${rank}` : '';
  const flagSrc = isNation ? row.nation_flag : row.alliance_flag;
  const name    = isNation ? row.nation_name  : row.alliance_name;
  const sub     = isNation ? row.alliance_name : null;
  const val     = fmtStatVal(sortKey, sortVal(row, sortKey), row);
  const dataAttrs = isNation
    ? `data-nation-id="${esc(String(row.nation_id || row.id || ''))}" data-alliance-id="${esc(String(row.alliance_id || ''))}"`
    : `data-alliance-id="${esc(String(row.alliance_id || row.id || ''))}"`;

  return `
<div class="news-lb-item" ${dataAttrs}>
  <span class="news-lb-rank${rankCls}">${rank}</span>
  ${flagImg(flagSrc, 'news-lb-flag', name || '?')}
  <div style="min-width:0">
    <div class="news-lb-name">${esc(name || '—')}</div>
    ${sub ? `<div class="news-lb-name-sub">${esc(sub)}</div>` : ''}
  </div>
  <span class="news-lb-value">${val}</span>
</div>`;
}

/* -- Full alliance table row ------------------------------------------------ */
function renderAllianceRow(row, rank) {
  const rankCls = rank <= 3 ? ` rank-${rank}` : '';
  const isNW    = Number(row.alliance_id) === NW_ALLIANCE_ID;
  const loot    = netLoot(row);
  const lootCls = loot > 0 ? ' news-cell-green' : loot < 0 ? ' news-cell-red' : '';
  const totalCls = (row.total_spent || 0) < 0 ? ' news-cell-profit' : '';

  return `
<div class="news-alliance-row${isNW ? ' is-nw-row' : ''}" data-alliance-id="${esc(String(row.alliance_id || ''))}">
  <span class="news-lb-rank${rankCls}">${rank}</span>
  <div class="news-alliance-name-cell">
    ${flagImg(row.alliance_flag, 'news-lb-flag', row.alliance_name || '?')}
    <div style="min-width:0">
      <div class="news-lb-name">${esc(row.alliance_name || '—')}</div>
    </div>
  </div>
  <span class="hide-mobile news-cell-num">${fmtNum(row.cities_built || 0)}</span>
  <span class="hide-mobile news-cell-num">${fmtNum(row.projects_bought || 0)}</span>
  <span class="hide-mobile news-cell-num">${fmtMoney(row.infra_spent || 0)}</span>
  <span class="hide-mobile news-cell-num">${fmtMoney(row.military_spent || 0)}</span>
  <span class="hide-mobile news-cell-num news-cell-gold">${fmtNum(row.wars_declared || 0)}</span>
  <span class="hide-mobile news-cell-num news-cell-green">${fmtNum(row.wars_won || 0)}</span>
  <span class="hide-mobile news-cell-num news-cell-red">${fmtNum(row.wars_lost || 0)}</span>
  <span class="hide-mobile news-cell-num${lootCls}">${fmtMoney(loot)}</span>
  <span class="hide-mobile news-cell-num">${fmtNum(row.missiles_used || 0)}</span>
  <span class="hide-mobile news-cell-num">${fmtNum(row.nukes_used || 0)}</span>
  <span class="news-cell-num news-cell-total${totalCls}">${fmtMoney(row.total_spent || 0)}</span>
</div>`;
}

/* -- Full nations table row ------------------------------------------------- */
function renderNationRow(row, rank) {
  const rankCls  = rank <= 3 ? ` rank-${rank}` : '';
  const isNW     = Number(row.alliance_id) === NW_ALLIANCE_ID;
  const loot     = netLoot(row);
  const lootCls  = loot > 0 ? ' news-cell-green' : loot < 0 ? ' news-cell-red' : '';
  const totalCls = (row.total_spent || 0) < 0 ? ' news-cell-profit' : '';

  return `
<div class="news-nation-row${isNW ? ' is-nw-row' : ''}" data-nation-id="${esc(String(row.nation_id || row.id || ''))}" data-alliance-id="${esc(String(row.alliance_id || ''))}">
  <span class="news-lb-rank${rankCls}">${rank}</span>
  <div class="news-nation-name-cell">
    ${flagImg(row.nation_flag, 'news-lb-flag', row.nation_name || '?')}
    <div style="min-width:0">
      <div class="news-lb-name">${esc(row.nation_name || '—')}</div>
    </div>
  </div>
  <div class="hide-mobile news-nation-alliance-cell">
    ${flagImg(null, 'news-lb-flag', row.alliance_name || '?')}
    <span class="news-lb-name-sub">${esc(row.alliance_name || '—')}</span>
  </div>
  <span class="hide-mobile news-cell-num">${fmtNum(row.cities_built || 0)}</span>
  <span class="hide-mobile news-cell-num">${fmtNum(row.projects_bought || 0)}</span>
  <span class="hide-mobile news-cell-num">${fmtMoney(row.infra_spent || 0)}</span>
  <span class="hide-mobile news-cell-num">${fmtMoney(row.military_spent || 0)}</span>
  <span class="hide-mobile news-cell-num news-cell-gold">${fmtNum(row.wars_declared || 0)}</span>
  <span class="hide-mobile news-cell-num news-cell-green">${fmtNum(row.wars_won || 0)}</span>
  <span class="hide-mobile news-cell-num news-cell-red">${fmtNum(row.wars_lost || 0)}</span>
  <span class="hide-mobile news-cell-num${lootCls}">${fmtMoney(loot)}</span>
  <span class="news-cell-num news-cell-total${totalCls}">${fmtMoney(row.total_spent || 0)}</span>
</div>`;
}

/* -- Empty state ------------------------------------------------------------ */
function renderEmpty(msg) {
  return `<div class="news-empty">
    <div class="news-empty-icon">📭</div>
    <div>${esc(msg)}</div>
  </div>`;
}

/* -- Loading state ---------------------------------------------------------- */
function renderLoading() {
  return `<div class="news-loading"><span class="news-spinner"></span>Loading…</div>`;
}



/* ---------------------------------------------------------------------------
   STAGE 4 — Feed view controller
   --------------------------------------------------------------------------- */

/** Full feed reload — resets offset, replaces list */
async function loadFeed() {
  State.feedOffset = 0;
  const list     = el('news-event-list');
  const loadMore = el('news-load-more');
  if (list) list.innerHTML = renderLoading();
  if (loadMore) loadMore.style.display = 'none';

  try {
    const data   = await fetchEvents(0);
    const events = data.events || [];
    State.feedOffset  = events.length;
    State.feedHasMore = events.length >= FEED_PAGE_SIZE;

    if (!list) return;
    if (!events.length) {
      list.innerHTML = renderEmpty('No events yet for this period and scope.');
    } else {
      // Resolve all Nation/Alliance IDs to names in one batch call
      const nameMap = await resolveEventNames(events);
      list.innerHTML = events.map(ev => renderEventItem(ev, nameMap)).join('');
      list.querySelectorAll('.news-event-item').forEach(item => {
        item.addEventListener('click', (e) => {
          // Don't toggle if clicking a link or button inside the card
          if (e.target.closest('a, button')) return;
          item.classList.toggle('is-expanded');
          const hint = item.querySelector('.news-expand-hint');
          if (hint) {
            hint.textContent = item.classList.contains('is-expanded') ? '▲ Details' : '▼ Details';
          }
        });
      });
      wireWarCostsBtns(list);
    }

    if (loadMore) loadMore.style.display = State.feedHasMore ? 'block' : 'none';
    updateFeedPeriodBar(data);
  } catch (err) {
    console.error('loadFeed:', err);
    if (list) list.innerHTML = renderEmpty('Failed to load events. Check console.');
  }
}

/** Append next page to existing list */
async function loadMoreFeed() {
  const btn = el('load-more-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }

  try {
    const data   = await fetchEvents(State.feedOffset);
    const events = data.events || [];
    State.feedOffset  += events.length;
    State.feedHasMore  = events.length >= FEED_PAGE_SIZE;

    const list = el('news-event-list');
    if (list && events.length) {
      const nameMap = await resolveEventNames(events);
      const frag = document.createElement('div');
      frag.innerHTML = events.map(ev => renderEventItem(ev, nameMap)).join('');
      frag.querySelectorAll('.news-event-item').forEach(item => {
        item.addEventListener('click', (e) => {
          if (e.target.closest('a, button')) return;
          item.classList.toggle('is-expanded');
          const hint = item.querySelector('.news-expand-hint');
          if (hint) {
            hint.textContent = item.classList.contains('is-expanded') ? '▲ Details' : '▼ Details';
          }
        });
      });
      wireWarCostsBtns(frag);
      while (frag.firstChild) list.appendChild(frag.firstChild);
    }

    const loadMore = el('news-load-more');
    if (loadMore) loadMore.style.display = State.feedHasMore ? 'block' : 'none';
  } catch (err) {
    console.error('loadMoreFeed:', err);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Load More'; }
  }
}

/** Update the period info bar inside the feed panel */
function updateFeedPeriodBar(data) {
  // data may be from fetchEvents (no meta) or fetchSummary (has meta)
  const meta = data.meta || {};
  const start = el('feed-period-start');
  const count = el('feed-event-count');
  if (start) start.textContent = meta.period_start ? fmtDate(meta.period_start) : '—';
  if (count) count.textContent = meta.event_count != null ? fmtNum(meta.event_count) : (data.count != null ? fmtNum(data.count) : '—');
}

/** Load sidebar top-nations leaderboard */
async function loadSidebarLb() {
  const list = el('sidebar-lb-list');
  if (!list) return;
  list.innerHTML = renderLoading();

  try {
    // Apply search filters: alliance or nation
    const allianceFilter = (State.searchType === 'alliance' && State.searchId) ? State.searchId : null;
    const nationFilter = (State.searchType === 'nation' && State.searchId) ? State.searchId : null;
    const data = await fetchNationStats(allianceFilter, nationFilter);
    const rows = (data.nations || []).slice();
    const key  = State.sidebarSort;

    rows.sort((a, b) => sortVal(b, key) - sortVal(a, key));

    if (!rows.length) {
      list.innerHTML = renderEmpty('No data yet.');
      return;
    }
    list.innerHTML = rows.slice(0, 15).map((r, i) => renderSidebarItem(r, i + 1, key, true)).join('');
    _cacheNations(rows);
  } catch (err) {
    console.error('loadSidebarLb:', err);
    list.innerHTML = renderEmpty('Failed to load.');
  }
}

/* ---------------------------------------------------------------------------
   STAGE 5 — Alliance leaderboard controller
   --------------------------------------------------------------------------- */

async function loadAllianceLb() {
  const list  = el('alliance-lb-list');
  const title = el('alliance-lb-title');
  const count = el('alliance-lb-count');
  if (!list) return;
  list.innerHTML = renderLoading();

  try {
    const data = await fetchAllianceStats();
    let rows = data.alliances || [];
    const key = State.lbSort;

    rows.sort((a, b) => {
      const diff = sortVal(b, key) - sortVal(a, key);
      return State.lbSortDir === 'asc' ? -diff : diff;
    });

    if (title) title.textContent = `Alliance Leaderboard — ${periodLabel(State.period, State.year)}`;
    if (count) count.textContent = rows.length ? `${rows.length} alliance${rows.length !== 1 ? 's' : ''}` : '';

    if (!rows.length) {
      list.innerHTML = renderEmpty('No alliance data yet for this period.');
      return;
    }
    list.innerHTML = rows.map((r, i) => renderAllianceRow(r, i + 1)).join('');
    _cacheAlliances(rows);
    _syncSortHeaders(key, State.lbSortDir);
    _applySearchFilter();
  } catch (err) {
    console.error('loadAllianceLb:', err);
    list.innerHTML = renderEmpty('Failed to load alliance data.');
  }
}

/* ---------------------------------------------------------------------------
   STAGE 6 — Nations leaderboard controller
   --------------------------------------------------------------------------- */

async function loadNationsLb() {
  const list  = el('nations-lb-list');
  const title = el('nations-lb-title');
  const count = el('nations-lb-count');
  if (!list) return;
  list.innerHTML = renderLoading();

  try {
    // Apply search filters: alliance or nation
    const allianceFilter = (State.searchType === 'alliance' && State.searchId) ? State.searchId : null;
    const nationFilter = (State.searchType === 'nation' && State.searchId) ? State.searchId : null;
    const data = await fetchNationStats(allianceFilter, nationFilter);
    let rows = data.nations || [];
    const key = State.lbSort;

    rows.sort((a, b) => {
      const diff = sortVal(b, key) - sortVal(a, key);
      return State.lbSortDir === 'asc' ? -diff : diff;
    });

    if (title) title.textContent = `Nation Leaderboard — ${periodLabel(State.period, State.year)}`;
    if (count) count.textContent = rows.length ? `${rows.length} nation${rows.length !== 1 ? 's' : ''}` : '';

    if (!rows.length) {
      list.innerHTML = renderEmpty('No nation data yet for this period.');
      return;
    }
    list.innerHTML = rows.map((r, i) => renderNationRow(r, i + 1)).join('');
    _cacheNations(rows);
    _syncSortHeaders(key, State.lbSortDir);
  } catch (err) {
    console.error('loadNationsLb:', err);
    list.innerHTML = renderEmpty('Failed to load nation data.');
  }
}

/* ---------------------------------------------------------------------------
   STAGE 7 — Summary stat cards + masthead
   --------------------------------------------------------------------------- */

async function loadSummary() {
  try {
    const data = await fetchSummary();

    // Update available period buttons from the response
    if (data.available) {
      State.available = data.available;
      updatePeriodButtons(data.available);
    }

    // Always world stats
    const stats = data.world || {};
    const scopeTxt = '🌍 All Orbis';

    // Stat card helper
    function setCard(id, val, scopeId) {
      const v = el(id);
      const s = el(scopeId);
      if (v) v.textContent = val;
      if (s) s.textContent = scopeTxt;
    }

    setCard('stat-cities',   fmtNum(stats.cities_built    || 0), 'stat-cities-scope');
    setCard('stat-projects', fmtNum(stats.projects_bought || 0), 'stat-projects-scope');
    setCard('stat-spent',    fmtMoney(stats.total_spent   || 0), 'stat-spent-scope');
    setCard('stat-wars',     fmtNum(stats.wars_declared   || 0), 'stat-wars-scope');
    setCard('stat-wins',     fmtNum(stats.wars_won        || 0), 'stat-wins-scope');
    setCard('stat-loot',     fmtMoney(stats.loot_gained   || 0), 'stat-loot-scope');
    setCard('stat-nukes',    fmtNum(stats.nukes_used      || 0), 'stat-nukes-scope');
    setCard('stat-missiles', fmtNum(stats.missiles_used   || 0), 'stat-missiles-scope');

    // Masthead period label
    const pLabel = el('news-period-label');
    if (pLabel) pLabel.textContent = periodLabel(State.period, State.year);

    // Event count in masthead
    const evCount = el('news-event-count');
    if (evCount && data.meta) {
      evCount.textContent = data.meta.event_count != null
        ? `${fmtNum(data.meta.event_count)} events`
        : '';
    }

    // Update feed period bar too
    updateFeedPeriodBar(data);

  } catch (err) {
    console.error('loadSummary:', err);
  }
}

/** Show/hide Last Week / Last Month buttons, update month images, update masthead icon */
function updatePeriodButtons(available) {
  const now = new Date();

  // Show/hide prev-week button
  const prevWeekBtn = el('btn-prev-weekly');
  if (prevWeekBtn) prevWeekBtn.style.display = available.has_prev_weekly ? '' : 'none';

  // Show/hide prev-month button and update its image to the actual previous month
  const prevMonthBtn = el('btn-prev-monthly');
  if (prevMonthBtn) {
    prevMonthBtn.style.display = available.has_prev_monthly ? '' : 'none';
    const prevMonthImg = el('btn-prev-monthly-img');
    if (prevMonthImg) {
      prevMonthImg.src = periodCalImg('prev_monthly', now);
      prevMonthBtn.dataset.calImg = periodCalImg('prev_monthly', now);
    }
  }

  // Update "This Month" button image to actual current month
  const monthBtn = el('btn-monthly');
  if (monthBtn) {
    const monthImg = el('btn-monthly-img');
    if (monthImg) {
      monthImg.src = periodCalImg('monthly', now);
      monthBtn.dataset.calImg = periodCalImg('monthly', now);
    }
  }

  // Update masthead calendar icon to match current period
  updateMastheadCalIcon();
}

/** Update the masthead calendar icon to match the active period — keep SNN icon fixed */
function updateMastheadCalIcon() {
  // The masthead icon is the SNN logo; we don't swap it for calendar images
}

/* ---------------------------------------------------------------------------
   STAGE 8 — View switcher + toggle wiring
   --------------------------------------------------------------------------- */

/** Switch the visible view panel and update control visibility */
function switchView(view) {
  State.view = view;

  // Show/hide panels
  const feedPanel     = el('view-feed');
  const alliancePanel = el('view-alliance');
  const nationsPanel  = el('view-nations');
  if (feedPanel)     feedPanel.style.display     = view === 'feed'     ? '' : 'none';
  if (alliancePanel) alliancePanel.style.display = view === 'alliance' ? '' : 'none';
  if (nationsPanel)  nationsPanel.style.display  = view === 'nations'  ? '' : 'none';

  // Show/hide control accessories — lb-sort-wrap is now empty (sorting via column headers)
  const feedFilterWrap = el('feed-filter-wrap');
  if (feedFilterWrap) feedFilterWrap.style.display = view === 'feed' ? 'flex' : 'none';

  // Update view toggle active state
  document.querySelectorAll('#view-toggle .news-toggle-btn').forEach(btn => {
    btn.classList.toggle('is-active', btn.dataset.view === view);
  });

  // Load only the view-specific data (summary already loaded by caller)
  loadViewData();
}

/** Load only the data for the current view (no summary reload) */
function loadViewData() {
  if (State.view === 'feed') {
    loadFeed();
    loadSidebarLb();
  } else if (State.view === 'alliance') {
    loadAllianceLb();
  } else if (State.view === 'nations') {
    loadNationsLb();
  }
}

/** Full reload: summary + current view data. Called on period/scope changes. */
function loadCurrentView() {
  loadSummary();   // updates stat cards, masthead, period buttons
  loadViewData();  // updates the active view panel
}

/** Reset feed filter chips to "All" */
function resetFeedFilter() {
  State.feedFilter = 'all';
  document.querySelectorAll('#feed-filter-chips .news-filter-chip').forEach(c =>
    c.classList.toggle('is-active', c.dataset.type === 'all'));
}

/* ---------------------------------------------------------------------------
   SEARCH / AUTOCOMPLETE
   --------------------------------------------------------------------------- */

/**
 * Search cache — populated by the leaderboard loads so that rows already
 * on screen are instantly available in the dropdown without an API round-trip.
 * The live /api/news/search endpoint fills in everything else from GlobalNations.
 */
const _searchCache = {
  nations:   [],   // [{id, name, alliance_name, flag}]
  alliances: [],   // [{id, name, flag}]
};

/** Refresh nation cache from leaderboard rows */
function _cacheNations(rows) {
  _searchCache.nations = (rows || []).map(r => ({
    id:            r.nation_id || r.id,
    name:          r.nation_name || r.name || '',
    alliance_name: r.alliance_name || '',
    flag:          r.nation_flag  || r.flag || null,
  })).filter(r => r.name);
}

/** Refresh alliance cache from leaderboard rows */
function _cacheAlliances(rows) {
  _searchCache.alliances = (rows || []).map(r => ({
    id:   r.alliance_id || r.id,
    name: r.alliance_name || r.name || '',
    flag: r.alliance_flag || r.flag || null,
  })).filter(r => r.name);
}

/** Render the dropdown list from an array of suggestion objects */
function _renderSearchDropdown(suggestions) {
  const dd = el('news-search-dropdown');
  if (!dd) return;

  if (!suggestions.length) {
    dd.innerHTML = `<li class="news-search-no-results" role="option">No results</li>`;
    dd.classList.add('is-open');
    return;
  }

  dd.innerHTML = suggestions.map((s, i) => {
    const flagHtml = s.flag
      ? `<img src="${esc(flagUrl(s.flag))}" style="width:18px;height:13px;object-fit:cover;border-radius:2px;border:1px solid rgba(255,255,255,0.1);flex-shrink:0;" alt="" onerror="this.style.display='none'">`
      : '';
    const typeTag = `<span class="news-search-item-type">${s.type === 'alliance' ? 'Alliance' : 'Nation'}</span>`;
    const subHtml = s.sub
      ? `<span class="news-search-item-sub">${esc(s.sub)}</span>`
      : '';
    return `<li role="option" data-idx="${i}" data-type="${esc(s.type)}" data-id="${esc(String(s.id))}" data-name="${esc(s.name)}">${flagHtml}${esc(s.name)}${subHtml}${typeTag}</li>`;
  }).join('');

  dd.classList.add('is-open');
}

/** Apply a search selection — filter the active view */
function applySearch(type, id, name) {
  const input = el('news-search-input');
  const clear = el('news-search-clear');
  const dd    = el('news-search-dropdown');

  if (input) { input.value = name; input.classList.add('has-value'); }
  if (clear) clear.style.display = '';
  if (dd)    { dd.classList.remove('is-open'); dd.innerHTML = ''; }

  State.searchType = type;   // 'nation' | 'alliance' | null
  State.searchId   = id ? Number(id) : null;
  State.searchName = name || null;

  _applySearchFilter();
  // Reload the active view so events/leaderboard are filtered server-side
  loadViewData();
}

/** Clear the active search and reload everything unfiltered */
function clearSearch() {
  const input = el('news-search-input');
  const clear = el('news-search-clear');
  const dd    = el('news-search-dropdown');

  if (input) { input.value = ''; input.classList.remove('has-value'); input.setAttribute('aria-expanded', 'false'); }
  if (clear) clear.style.display = 'none';
  if (dd)    { dd.classList.remove('is-open'); dd.innerHTML = ''; }

  const hadSearch = !!State.searchId;
  State.searchType = null;
  State.searchId   = null;
  State.searchName = null;

  _applySearchFilter();
  if (hadSearch) loadViewData();
}

/** Filter the currently rendered leaderboard rows by the active search */
function _applySearchFilter() {
  if (!State.searchId) {
    document.querySelectorAll('.news-alliance-row, .news-nation-row').forEach(r => {
      r.style.display = '';
    });
    return;
  }

  const id   = State.searchId;
  const type = State.searchType;

  if (type === 'alliance') {
    document.querySelectorAll('.news-alliance-row').forEach(r => {
      const rid = Number(r.dataset.allianceId || r.dataset.id || 0);
      r.style.display = rid === id ? '' : 'none';
    });
    document.querySelectorAll('.news-nation-row').forEach(r => {
      const raid = Number(r.dataset.allianceId || 0);
      r.style.display = raid === id ? '' : 'none';
    });
  } else {
    document.querySelectorAll('.news-nation-row').forEach(r => {
      const rid = Number(r.dataset.nationId || r.dataset.id || 0);
      r.style.display = rid === id ? '' : 'none';
    });
    document.querySelectorAll('.news-alliance-row').forEach(r => {
      r.style.display = '';
    });
  }
}

/** Wire the search input, dropdown, and clear button */
function wireSearch() {
  const input = el('news-search-input');
  const clear = el('news-search-clear');
  const dd    = el('news-search-dropdown');
  if (!input || !dd) return;

  let _focusIdx  = -1;
  let _debounce  = null;

  function closeDropdown() {
    dd.classList.remove('is-open');
    dd.innerHTML = '';
    input.setAttribute('aria-expanded', 'false');
    _focusIdx = -1;
  }

  /**
   * Query the live /api/news/search endpoint, merge with any cached leaderboard
   * rows, deduplicate, sort prefix-matches first, and render the dropdown.
   */
  async function openWithQuery(q) {
    const trimmed = q.trim();
    if (!trimmed) { closeDropdown(); return; }

    const lower = trimmed.toLowerCase();

    // Show cached results immediately while the API call is in flight
    const cachedNations = _searchCache.nations
      .filter(n => n.name.toLowerCase().includes(lower))
      .slice(0, 5)
      .map(n => ({ type: 'nation', id: n.id, name: n.name, sub: n.alliance_name, flag: n.flag }));

    const cachedAlliances = _searchCache.alliances
      .filter(a => a.name.toLowerCase().includes(lower))
      .slice(0, 5)
      .map(a => ({ type: 'alliance', id: a.id, name: a.name, sub: '', flag: a.flag }));

    const immediate = [...cachedAlliances, ...cachedNations];
    if (immediate.length) {
      _renderSearchDropdown(_sortSuggestions(immediate, lower));
      input.setAttribute('aria-expanded', 'true');
    }

    // Debounce the live API call by 200 ms
    clearTimeout(_debounce);
    _debounce = setTimeout(async () => {
      try {
        const data = await fetchSearch(trimmed);
        const apiNations   = (data.nations   || []).map(n => ({ type: 'nation',   id: n.id,   name: n.name, sub: n.alliance_name || '', flag: n.flag || null }));
        const apiAlliances = (data.alliances || []).map(a => ({ type: 'alliance', id: a.id,   name: a.name, sub: '',                    flag: a.flag || null }));

        // Merge API results with cached, deduplicate by type+id
        const seen = new Set();
        const merged = [];
        for (const s of [...apiAlliances, ...apiNations, ...cachedAlliances, ...cachedNations]) {
          const key = `${s.type}:${s.id}`;
          if (!seen.has(key)) { seen.add(key); merged.push(s); }
        }

        _renderSearchDropdown(_sortSuggestions(merged.slice(0, 20), lower));
        input.setAttribute('aria-expanded', 'true');
        _focusIdx = -1;
      } catch (e) {
        // API failed — cached results already shown, nothing more to do
      }
    }, 200);
  }

  function _sortSuggestions(results, lower) {
    return results.slice().sort((a, b) => {
      // Alliances before nations
      const typeOrder = (a.type === 'alliance' ? 0 : 1) - (b.type === 'alliance' ? 0 : 1);
      if (typeOrder !== 0) return typeOrder;
      // Prefix matches first within each type
      const aStarts = a.name.toLowerCase().startsWith(lower) ? 0 : 1;
      const bStarts = b.name.toLowerCase().startsWith(lower) ? 0 : 1;
      return aStarts - bStarts || a.name.localeCompare(b.name);
    });
  }

  input.addEventListener('input', () => {
    const q = input.value;
    if (!q) { clearSearch(); return; }
    // If the user edits after a selection, clear the active filter
    if (State.searchId) {
      State.searchType = null;
      State.searchId   = null;
      State.searchName = null;
      _applySearchFilter();
      loadViewData();
    }
    openWithQuery(q);
  });

  input.addEventListener('keydown', e => {
    const items = dd.querySelectorAll('li[data-idx]');
    if (!items.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _focusIdx = Math.min(_focusIdx + 1, items.length - 1);
      items.forEach((li, i) => li.classList.toggle('is-focused', i === _focusIdx));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _focusIdx = Math.max(_focusIdx - 1, 0);
      items.forEach((li, i) => li.classList.toggle('is-focused', i === _focusIdx));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const focused = _focusIdx >= 0 ? items[_focusIdx] : items[0];
      if (focused) applySearch(focused.dataset.type, focused.dataset.id, focused.dataset.name);
    } else if (e.key === 'Escape') {
      closeDropdown();
    }
  });

  input.addEventListener('focus', () => {
    if (input.value && !State.searchId) openWithQuery(input.value);
  });

  dd.addEventListener('mousedown', e => {
    const li = e.target.closest('li[data-idx]');
    if (!li) return;
    e.preventDefault();
    applySearch(li.dataset.type, li.dataset.id, li.dataset.name);
    input.blur();
  });

  if (clear) {
    clear.addEventListener('click', () => {
      clearSearch();
      input.focus();
    });
  }

  document.addEventListener('mousedown', e => {
    if (!e.target.closest('#news-search-box')) closeDropdown();
  });
}

/** Wire all toggle groups and controls */
function wireControls() {

  // -- View toggle ---------------------------------------------------------
  document.querySelectorAll('#view-toggle .news-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.view === State.view) return;
      switchView(btn.dataset.view);
    });
  });

  // -- Period toggle -------------------------------------------------------
  document.querySelectorAll('#period-toggle .news-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = btn.dataset.period;
      if (p === State.period) return;
      State.period = p;
      // Reset year when switching away from yearly
      if (p !== 'yearly') State.year = null;
      document.querySelectorAll('#period-toggle .news-toggle-btn').forEach(b =>
        b.classList.toggle('is-active', b.dataset.period === State.period));
      // Update masthead icon to match new period
      updateMastheadCalIcon();
      clearSearch();
      resetFeedFilter();
      loadCurrentView();
    });
  });

  // -- Feed filter chips ---------------------------------------------------
  document.querySelectorAll('#feed-filter-chips .news-filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const t = chip.dataset.type;
      State.feedFilter = t;
      document.querySelectorAll('#feed-filter-chips .news-filter-chip').forEach(c =>
        c.classList.toggle('is-active', c.dataset.type === t));
      loadFeed();
    });
  });

  // -- Leaderboard sort: click column headers --------------------------------
  // Clicking a column sorts by that key descending. Clicking the active column
  // again toggles between descending and ascending.
  function wireLbHeaderSort(headerId) {
    const header = el(headerId);
    if (!header) return;
    header.querySelectorAll('.news-th-sortable').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (!key) return;
        if (State.lbSort === key) {
          // Same column — toggle direction
          State.lbSortDir = State.lbSortDir === 'desc' ? 'asc' : 'desc';
        } else {
          // New column — default to descending
          State.lbSort    = key;
          State.lbSortDir = 'desc';
        }
        _syncSortHeaders(State.lbSort, State.lbSortDir);
        if (State.view === 'alliance') loadAllianceLb();
        else if (State.view === 'nations') loadNationsLb();
      });
    });
  }
  wireLbHeaderSort('alliance-table-header');
  wireLbHeaderSort('nations-table-header');

  // -- Sidebar sort --------------------------------------------------------
  const sidebarSort = el('sidebar-lb-sort');
  if (sidebarSort) {
    sidebarSort.addEventListener('change', () => {
      State.sidebarSort = sidebarSort.value;
      loadSidebarLb();
    });
  }

  // -- Load more button ----------------------------------------------------
  const loadMoreBtn = el('load-more-btn');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', loadMoreFeed);
  }

  // -- Modal close ---------------------------------------------------------
  const modalClose = el('modal-close');
  const modal      = el('news-detail-modal');
  if (modalClose && modal) {
    modalClose.addEventListener('click', () => { modal.style.display = 'none'; });
    modal.addEventListener('click', e => {
      if (e.target === modal) modal.style.display = 'none';
    });
  }

  // -- Search box ----------------------------------------------------------
  wireSearch();
}

/* ---------------------------------------------------------------------------
   STAGE 9 — Auto-refresh + init
   --------------------------------------------------------------------------- */

let _refreshTimer = null;
let _visibilityHandler = null;

function startAutoRefresh() {
  stopAutoRefresh();
  _refreshTimer = setInterval(() => {
    // Only silently refresh summary + current view data; don't reset feed scroll
    loadSummary();
    if (State.view === 'feed') {
      // Soft-refresh: reload from top but keep scroll position
      loadFeed();
      loadSidebarLb();
    } else if (State.view === 'alliance') {
      loadAllianceLb();
    } else if (State.view === 'nations') {
      loadNationsLb();
    }
  }, AUTO_REFRESH_MS);
}

function stopAutoRefresh() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}

/** Called once when the page HTML is injected into the dashboard */
function initNewsPage() {
  // Wire all interactive controls
  wireControls();

  // Fetch available periods first so Last Week / Last Month buttons show correctly
  fetchAvailable().then(avail => {
    State.available = avail;
    updatePeriodButtons(avail);
  }).catch(() => {});

  // Fetch current resource sell prices for loot value calculations
  fetchResourcePrices().catch(() => {});

  // Initial data load
  loadCurrentView();

  // Auto-refresh disabled - users must manually refresh to see new events
  // startAutoRefresh();

  // Stop refresh when page is hidden (tab switch), resume when visible
  // _visibilityHandler = () => {
  //   if (document.hidden) stopAutoRefresh();
  //   else startAutoRefresh();
  // };
  // document.addEventListener('visibilitychange', _visibilityHandler);
}

/* -- Bootstrap -------------------------------------------------------------- */
// The dashboard injects HTML then fires 'dashboardPageLoaded' with detail.page = 'news.html'
(function bootstrap() {
  // Stop any previous instance (re-navigation cleanup)
  if (typeof window.__newsCleanup === 'function') {
    window.__newsCleanup();
    window.__newsCleanup = null;
  }

  // Register cleanup for when we navigate away
  window.__newsCleanup = function () {
    stopAutoRefresh();
    document.removeEventListener('visibilitychange', _visibilityHandler);
  };

  function tryInit() {
    if (el('news-event-list')) {
      initNewsPage();
      return true;
    }
    return false;
  }

  // Try immediately (script loaded after HTML injection)
  if (tryInit()) return;

  // Wait for dashboardPageLoaded event (fired after script onload)
  document.addEventListener('dashboardPageLoaded', function onLoad(e) {
    if (e.detail && (e.detail.page === 'news.html' || e.detail.page === 'news')) {
      document.removeEventListener('dashboardPageLoaded', onLoad);
      // Small delay to ensure DOM is fully settled
      setTimeout(() => {
        if (!tryInit()) {
          // Last resort: poll briefly
          let attempts = 0;
          const poll = setInterval(() => {
            attempts++;
            if (tryInit() || attempts > 20) clearInterval(poll);
          }, 50);
        }
      }, 10);
    }
  });

  // Fallback: DOMContentLoaded (standalone page load)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => tryInit());
  }
})(); // end bootstrap IIFE

})(); // end outer IIFE — keeps all const/let out of global scope
