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
    if (cssPath && typeof scriptManager !== 'undefined') scriptManager.loadCSS(cssPath);

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
                    scriptManager.loadScript(scriptPath, scriptType, dispatch);
                } else {
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
