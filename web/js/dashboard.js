// ── Analytics blocker ─────────────────────────────────────────────────────
(function () {
    const origAppend = Element.prototype.appendChild;
    const origInsert = Node.prototype.insertBefore;

    function isAnalytics(el) {
        if (el.tagName !== 'SCRIPT') return false;
        const src = el.src || '';
        const txt = el.textContent || '';
        return src.includes('cloudflareinsights.com') ||
               src.includes('beacon.min.js') ||
               txt.includes('cloudflareinsights') ||
               txt.includes('__cfBeacon');
    }

    Element.prototype.appendChild = function (el) {
        if (isAnalytics(el)) return el;
        return origAppend.call(this, el);
    };
    Node.prototype.insertBefore = function (newNode, ref) {
        if (isAnalytics(newNode)) return newNode;
        return origInsert.call(this, newNode, ref);
    };
})();

// ── Page loader ───────────────────────────────────────────────────────────
const contentDiv = document.getElementById('content');
const navLinks   = document.querySelectorAll('.nav-link');

function isMobile() { return window.innerWidth <= 768; }

function openMobileSidebar() {
    const sidebar  = document.getElementById('main-sidebar');
    const overlay  = document.getElementById('sidebar-overlay');
    if (!sidebar) return;
    sidebar.classList.add('mobile-open');
    overlay?.classList.add('active');
    document.body.classList.add('mobile-menu-open');
}

function closeMobileSidebar() {
    const sidebar  = document.getElementById('main-sidebar');
    const overlay  = document.getElementById('sidebar-overlay');
    if (!sidebar) return;
    sidebar.classList.remove('mobile-open');
    overlay?.classList.remove('active');
    document.body.classList.remove('mobile-menu-open');
}

function initializeSidebar() {
    const sidebar       = document.getElementById('main-sidebar');
    const toggleBtn     = document.getElementById('sidebar-toggle');
    const overlay       = document.getElementById('sidebar-overlay');
    if (!sidebar) return;

    // Mobile open/close toggle
    toggleBtn?.addEventListener('click', () => {
        sidebar.classList.contains('mobile-open') ? closeMobileSidebar() : openMobileSidebar();
    });

    // Overlay tap closes sidebar
    overlay?.addEventListener('click', closeMobileSidebar);

    // Close sidebar on nav link click (mobile)
    sidebar.addEventListener('click', e => {
        if (isMobile() && e.target.closest('.nav-link[data-page]')) {
            closeMobileSidebar();
        }
    });

    // Clean up mobile state on resize to desktop
    window.addEventListener('resize', () => {
        if (!isMobile()) {
            sidebar.classList.remove('mobile-open');
            overlay?.classList.remove('active');
            document.body.classList.remove('mobile-menu-open');
        }
    });
}

let currentLoadedPage = null;

function loadPage(page, scriptPath, scriptType, cssPath) {
    let pageFile = page.split('?')[0];
    if (!pageFile.endsWith('.html')) pageFile += '.html';

    if (typeof scriptManager !== 'undefined') scriptManager.unloadAll();
    currentLoadedPage = pageFile;
    if (cssPath && typeof scriptManager !== 'undefined') {
        cssPath.split(' ').filter(Boolean).forEach(p => scriptManager.loadCSS(p));
    }

    fetch(`/Pages/${pageFile}?v=${Date.now()}`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text(); })
        .then(html => {
            contentDiv.innerHTML = html;

            const dispatch = () => {
                document.dispatchEvent(new CustomEvent('dashboardPageLoaded', { detail: { page: pageFile } }));
            };

            function runInlineScripts(cb) {
                const scripts = Array.from(contentDiv.querySelectorAll('script'));
                (function next(i) {
                    if (i >= scripts.length) { cb?.(); return; }
                    const s = document.createElement('script');
                    Array.from(scripts[i].attributes).forEach(a => s.setAttribute(a.name, a.value));
                    s.textContent = scripts[i].textContent;
                    scripts[i].parentNode.replaceChild(s, scripts[i]);
                    next(i + 1);
                })(0);
            }

            runInlineScripts(() => {
                if (scriptPath && typeof scriptManager !== 'undefined') {
                    console.log(`[loadPage] Loading script: ${scriptPath}`);
                    scriptManager.loadScript(scriptPath, scriptType, dispatch);
                } else {
                    console.log(`[loadPage] No scriptPath for ${pageFile}, dispatching directly`);
                    dispatch();
                }
            });
        })
        .catch(err => {
            console.warn(`Error loading ${pageFile}`, err);
            contentDiv.innerHTML = `<div class="alert alert-danger">Error loading page: ${pageFile}</div>`;
            currentLoadedPage = null;
        });
}

function navigateTo(page, params = {}, pushState = true) {
    if (pushState) {
        const url = new URL(window.location);
        url.searchParams.set('page', page);
        Array.from(url.searchParams.keys()).filter(k => k !== 'page').forEach(k => url.searchParams.delete(k));
        Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
        history.pushState({ page, params }, '', url.toString());
    }
    navLinks.forEach(l => l.classList.remove('active'));
    const active = document.querySelector(`.nav-link[data-page='${page}']`);
    let scriptPath = null, scriptType = 'script', cssPath = null;
    if (active) {
        active.classList.add('active');
        scriptPath = active.getAttribute('data-script');
        scriptType = active.getAttribute('data-script-type') || 'script';
        cssPath    = active.dataset.css || null;
    }
    loadPage(page, scriptPath, scriptType, cssPath);
}

// Nav click delegation
document.querySelector('nav.sidebar ul.nav, .sidebar ul.nav').addEventListener('click', function (e) {
    const link = e.target.closest('.nav-link[data-page]');
    if (!link || link.id === 'discord-login-link' || link.classList.contains('active')) return;
    e.preventDefault();
    navLinks.forEach(l => l.classList.remove('active'));
    link.classList.add('active');
    history.pushState({ page: link.dataset.page }, '', '?page=' + link.dataset.page);
    loadPage(link.dataset.page, link.getAttribute('data-script'), link.getAttribute('data-script-type') || 'script', link.getAttribute('data-css'));
});

window.addEventListener('popstate', () => {
    const page = new URLSearchParams(window.location.search).get('page') || 'homepage';
    navigateTo(page, {}, false);
});

document.addEventListener('DOMContentLoaded', () => {
    const page = new URLSearchParams(window.location.search).get('page') || 'homepage';
    navigateTo(page, {}, false);
    initializeSidebar();
});

window.addEventListener('message', e => {
    if (e.data?.type === 'navigate') navigateTo(e.data.page);
});

window.navigateTo = navigateTo;

// ── Discord user ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/discord/user')
        .then(r => { if (!r.ok) throw new Error('Not logged in'); return r.json(); })
        .then(user => {
            document.getElementById('login-button').style.display = 'none';
            const profile = document.getElementById('user-profile');
            profile.style.display = 'block';
            document.getElementById('user-name').textContent = user.global_name || user.username;
            const img = document.getElementById('user-avatar');
            img.src = `/api/discord/avatar?_=${user.id}`;
            img.onerror = () => { img.onerror = null; img.src = 'https://cdn.discordapp.com/embed/avatars/0.png'; };
            updatePetLink();
            profile.addEventListener('click', e => {
                e.preventDefault();
                if (confirm('Are you sure you want to sign out?')) window.location.href = '/api/discord/logout';
            });
        })
        .catch(() => {
            document.getElementById('login-button').style.display = 'block';
            document.getElementById('user-profile').style.display = 'none';
            updatePetLink();
        });
});

function updatePetLink() {
    const link = document.getElementById('my-pet-link');
    if (!link) return;
    link.style.display = 'block';
    fetch('/api/user/pet')
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (data?.has_pet && data.species) {
                const a = link.querySelector('a');
                if (a) a.innerHTML = `<img src="/static/Emojis/Pets/${data.species}.png" alt="My Pet" style="width:20px;height:20px;margin-right:8px;" onerror="this.src='/static/Emojis/Pets/Basic.png'"> ${data.name}`;
            }
        })
        .catch(() => {});
}

// ── Nation Link Bar ───────────────────────────────────────────────────────
const LS_KEY = 'pnw_linked_nation';

function showLinkedNation(nation) {
    document.getElementById('nation-input-view').style.display = 'none';
    document.getElementById('nation-linked-view').style.display = 'block';
    document.getElementById('nation-linked-name').textContent = nation.nation_name || `Nation #${nation.nation_id}`;
    const flag = document.getElementById('nation-flag-img');
    if (nation.flag) { flag.src = nation.flag; flag.style.display = 'inline-block'; }
    else flag.style.display = 'none';
    loadNationRanks(nation.nation_name || '');
}

function showNationInput() {
    document.getElementById('nation-linked-view').style.display = 'none';
    document.getElementById('nation-input-view').style.display = 'block';
    document.getElementById('nation-link-error').style.display = 'none';
}

function setNationLinkError(msg) {
    const el = document.getElementById('nation-link-error');
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
}

async function initNationLinkBar() {
    try {
        const res = await fetch('/api/discord/linked-nation');
        if (res.ok) {
            const data = await res.json();
            if (data.linked) { localStorage.setItem(LS_KEY, JSON.stringify(data)); showLinkedNation(data); return; }
        }
    } catch (_) {}
    const stored = localStorage.getItem(LS_KEY);
    if (stored) {
        try {
            const nation = JSON.parse(stored);
            if (nation?.nation_id) {
                fetch('/api/discord/link-nation', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(nation) }).catch(() => {});
                showLinkedNation(nation); return;
            }
        } catch (_) {}
    }
    showNationInput();
}

document.getElementById('nation-link-form').addEventListener('submit', async e => {
    e.preventDefault();
    const input = document.getElementById('nation-id-input');
    const id = input.value.trim();
    if (!id || !/^\d+$/.test(id)) { setNationLinkError('Enter a valid numeric Nation ID.'); return; }
    setNationLinkError('');
    const btn = e.target.querySelector('button');
    btn.textContent = '...'; btn.disabled = true;
    try {
        const infoRes = await fetch(`/api/pnw/nation/${id}`);
        if (!infoRes.ok) { const err = await infoRes.json().catch(() => ({})); throw new Error(err.detail || 'Nation not found.'); }
        const nation = await infoRes.json();
        const payload = { nation_id: String(nation.id || id), nation_name: nation.nation_name || '', flag: nation.flag || '' };
        await fetch('/api/discord/link-nation', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        localStorage.setItem(LS_KEY, JSON.stringify(payload));
        input.value = '';
        showLinkedNation(payload);
    } catch (err) {
        setNationLinkError(err.message || 'Failed to link nation.');
    } finally {
        btn.textContent = 'Link'; btn.disabled = false;
    }
});

document.getElementById('nation-unlink-btn').addEventListener('click', async () => {
    await fetch('/api/discord/link-nation', { method: 'DELETE' }).catch(() => {});
    localStorage.removeItem(LS_KEY);
    stopRankTicker();
    showNationInput();
});

document.addEventListener('DOMContentLoaded', initNationLinkBar);

// ── Rank Ticker ───────────────────────────────────────────────────────────
let _rankTimer = null, _rankIndex = 0, _rankSlides = [];

function stopRankTicker() {
    if (_rankTimer) { clearInterval(_rankTimer); _rankTimer = null; }
    const t = document.getElementById('nation-rank-ticker');
    if (t) { t.style.display = 'none'; t.innerHTML = ''; }
    const tb = document.getElementById('topbar-rank-ticker');
    if (tb) { tb.style.display = 'none'; tb.innerHTML = ''; }
    _rankSlides = [];
}

function buildRankSlides(data) {
    const slides = [];
    (data.periods || []).forEach(({ label, ranks }) => {
        (ranks || []).forEach(r => {
            if (r.rank <= 3) slides.push({ period: label, label: r.category_label, rank: r.rank, total: r.total, prefix: r.prefix || '' });
        });
    });
    return slides;
}

function showRankSlide(ticker, i) {
    const s = _rankSlides[i];
    const src = s.prefix ? `/static/Emojis/Leaderboards/${s.rank}${s.prefix}.png` : '';
    const img = src ? `<img src="${src}" alt="#${s.rank}" style="width:1rem;height:1rem;object-fit:contain;vertical-align:middle;flex-shrink:0;">` : '';
    const html = `<span class="rank-slide visible" style="display:flex;align-items:center;gap:0.3rem;min-width:0;flex-wrap:nowrap;">
        ${img}
        <span class="rank-period" style="flex-shrink:0;">${s.period}</span>
        <span class="rank-label" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${s.label}</span>
    </span>`;
    ticker.innerHTML = html;
    // Mirror to topbar ticker if it exists
    const tb = document.getElementById('topbar-rank-ticker');
    if (tb && tb.style.display !== 'none') tb.innerHTML = html;
}

async function loadNationRanks(name) {
    stopRankTicker();
    if (!name) return;
    try {
        const res = await fetch(`/api/watch/nation-ranks/${encodeURIComponent(name)}`);
        if (!res.ok) return;
        _rankSlides = buildRankSlides(await res.json());
        if (!_rankSlides.length) return;
        const ticker = document.getElementById('nation-rank-ticker');
        ticker.style.display = 'block';
        const tb = document.getElementById('topbar-rank-ticker');
        if (tb) tb.style.display = 'flex';
        _rankIndex = 0;
        showRankSlide(ticker, 0);
        if (_rankSlides.length > 1) {
            _rankTimer = setInterval(() => { _rankIndex = (_rankIndex + 1) % _rankSlides.length; showRankSlide(ticker, _rankIndex); }, 4000);
        }
    } catch (_) {}
}

// ── Bazaar live item count badge ──────────────────────────────────────────
(function () {
    let _bws = null, _bRetries = 0;
    const MAX = 8;

    function updateBadge(count) {
        const badge = document.getElementById('bazaar-nav-count');
        if (!badge) return;
        if (count > 0) {
            badge.textContent = count + ' listed';
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    function connect() {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        _bws = new WebSocket(`${proto}://${location.host}/api/bazaar/ws`);

        _bws.onopen = () => {
            _bRetries = 0;
            _bws._ping = setInterval(() => { if (_bws.readyState === 1) _bws.send('ping'); }, 25000);
        };

        _bws.onmessage = e => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'board') updateBadge((msg.listings || []).length);
            } catch (_) {}
        };

        _bws.onclose = () => {
            clearInterval(_bws._ping);
            if (_bRetries < MAX) setTimeout(connect, Math.min(3000 * ++_bRetries, 20000));
        };

        _bws.onerror = () => _bws.close();
    }

    document.addEventListener('DOMContentLoaded', connect);
})();
// Fires CustomEvent('liveRooms', {detail: {arena, casino}}) on document
// whenever the server pushes an update.  Any page script can listen to this
// instead of opening its own WebSocket connection.
(function () {
    let _ws = null, _retries = 0;
    const MAX_RETRIES = 8;

    function dispatch(arena, casino) {
        // Update sidebar badge
        const total = [...(arena||[]), ...(casino||[])].reduce((n, r) => n + (r.occupants||[]).length, 0);
        const badge = document.getElementById('arena-nav-online');
        if (badge) badge.textContent = total > 0 ? total : '';

        // Fire event for any loaded page script to consume
        document.dispatchEvent(new CustomEvent('liveRooms', { detail: { arena: arena||[], casino: casino||[] } }));
    }

    function connect() {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        _ws = new WebSocket(`${proto}://${location.host}/api/ws/unified`);

        _ws.onopen = () => {
            _retries = 0;
            _ws._ping = setInterval(() => { if (_ws.readyState === 1) _ws.send('ping'); }, 25000);
        };

        _ws.onmessage = e => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'unified') dispatch(msg.arena, msg.casino);
            } catch (_) {}
        };

        _ws.onclose = () => {
            clearInterval(_ws._ping);
            if (_retries < MAX_RETRIES) setTimeout(connect, Math.min(3000 * ++_retries, 20000));
        };

        _ws.onerror = () => _ws.close();
    }

    // Expose so page scripts can check readiness and send pings if needed
    window._liveWS = {
        send: (msg) => { if (_ws && _ws.readyState === 1) { _ws.send(msg); return true; } return false; }
    };

    document.addEventListener('DOMContentLoaded', connect);
})();

// ── Survive nav badge — polls /api/ss/state every 15s, live countdown ticker ──
(function () {
    var _ssNavState = null;       // last known game state
    var _ssNavTicker = null;      // setInterval id for countdown tick

    function _fmtTime(secs) {
        secs = Math.max(0, Math.floor(secs));
        var h = Math.floor(secs / 3600);
        var m = Math.floor((secs % 3600) / 60);
        var s = secs % 60;
        return (h > 0 ? h + ':' : '') +
               (h > 0 ? String(m).padStart(2,'0') : m) + ':' +
               String(s).padStart(2,'0');
    }

    function _stopTicker() {
        if (_ssNavTicker) { clearInterval(_ssNavTicker); _ssNavTicker = null; }
    }

    function _renderNav() {
        var badge = document.getElementById('ss-nav-count');
        var timer = document.getElementById('ss-nav-timer');
        if (!badge) return;

        var g = _ssNavState;
        var status = g ? (g.status || 'none') : 'none';

        if (status === 'none') {
            badge.style.display = 'none';
            if (timer) timer.style.display = 'none';
            _stopTicker();
            return;
        }

        // ── Badge label ───────────────────────────────────────────────────────
        var label = '';
        if (status === 'lobby') {
            var lobbyCount = (g.participants || []).filter(function(p) { return !p.is_npc; }).length;
            label = lobbyCount + ' in lobby';
        } else if (status === 'countdown') {
            label = 'Start';
        } else if (status === 'running') {
            var rnd = g.round_index || 0;
            label = rnd === 0 ? 'Starting' : 'Round ' + rnd;
        } else if (status === 'finished') {
            label = 'Finished';
        }

        badge.textContent = label;
        badge.style.display = label ? 'inline-block' : 'none';

        // ── Countdown timer ───────────────────────────────────────────────────
        if (!timer) return;

        if (status === 'countdown' && g.countdown_end) {
            timer.style.display = 'inline-block';
            _stopTicker();
            _ssNavTicker = setInterval(function() {
                var rem = g.countdown_end - Math.floor(Date.now() / 1000);
                if (rem <= 0) { timer.textContent = '0:00'; _stopTicker(); }
                else          { timer.textContent = _fmtTime(rem); }
            }, 1000);
            var remNow = g.countdown_end - Math.floor(Date.now() / 1000);
            timer.textContent = remNow > 0 ? _fmtTime(remNow) : '0:00';
        } else if (status === 'running' && g.next_round_at) {
            timer.style.display = 'inline-block';
            _stopTicker();
            var endEpoch = g.next_round_at;
            _ssNavTicker = setInterval(function() {
                var rem = endEpoch - Math.floor(Date.now() / 1000);
                if (rem <= 0) { timer.textContent = '…'; _stopTicker(); }
                else          { timer.textContent = _fmtTime(rem); }
            }, 1000);
            var remNowR = endEpoch - Math.floor(Date.now() / 1000);
            timer.textContent = remNowR > 0 ? _fmtTime(remNowR) : '…';
        } else {
            timer.style.display = 'none';
            _stopTicker();
        }
    }

    function updateSsNavBadge() {
        fetch('/api/ss/state')
            .then(function(r) { return r.ok ? r.json() : null; })
            .then(function(g) {
                _ssNavState = g;
                _renderNav();
            })
            .catch(function() {});
    }

    // Run immediately and poll every 15s to catch round changes
    updateSsNavBadge();
    setInterval(updateSsNavBadge, 15000);

    // Expose so survive.js SSE handler can trigger an immediate refresh
    window.ssNavRefresh = updateSsNavBadge;

    // Expose so survive.js round countdown ticker can directly update the nav timer
    // without spawning a duplicate interval. Called once per second by survive.js.
    window.ssNavSetRoundTimer = function(nextRoundAt) {
        var timer = document.getElementById('ss-nav-timer');
        if (!timer) return;
        _stopTicker();
        var endEpoch = nextRoundAt;
        _ssNavTicker = setInterval(function() {
            var rem = endEpoch - Math.floor(Date.now() / 1000);
            if (rem <= 0) { timer.textContent = '…'; _stopTicker(); }
            else          { timer.textContent = _fmtTime(rem); }
        }, 1000);
        var remNow = endEpoch - Math.floor(Date.now() / 1000);
        timer.style.display = 'inline-block';
        timer.textContent = remNow > 0 ? _fmtTime(remNow) : '…';
    };
})();
