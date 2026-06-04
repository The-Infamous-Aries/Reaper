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

    // Only initialize mobile sidebar (hidden on desktop via d-md-none)
    if (!isMobile()) return;

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

// ── Theme Loading ─────────────────────────────────────────────────────────────
async function loadUserTheme() {
    // First check localStorage for recently saved theme (for immediate application)
    const savedTheme = localStorage.getItem('reaper_theme');
    const savedAt = localStorage.getItem('reaper_theme_saved_at');
    const now = Date.now();

    // If theme was saved in the last 5 minutes, use it immediately
    if (savedTheme && savedAt && (now - parseInt(savedAt)) < 300000) {
        try {
            const themeData = JSON.parse(savedTheme);
            console.log('Applying theme from localStorage:', themeData);
            applyThemeToPage(themeData);
        } catch (e) {
            console.error('Failed to parse saved theme:', e);
        }
    }

    // Also fetch from API to ensure we have the latest
    try {
        const response = await fetch('/api/settings');
        if (!response.ok) return;

        const settings = await response.json();
        if (settings && settings.theme_bg_color) {
            console.log('Applying theme from API');
            applyThemeToPage(settings);

            // Update localStorage with latest from API
            localStorage.setItem('reaper_theme', JSON.stringify({
                theme_bg_color: settings.theme_bg_color,
                theme_bg_secondary: settings.theme_bg_secondary,
                theme_bg_tertiary: settings.theme_bg_tertiary,
                theme_gold_primary: settings.theme_gold_primary,
                theme_gold_secondary: settings.theme_gold_secondary,
                theme_text_primary: settings.theme_text_primary,
                theme_text_secondary: settings.theme_text_secondary,
                theme_hide_bg_image: settings.theme_hide_bg_image || 0,
                theme_custom_bg_url: settings.theme_custom_bg_url || null,
            }));
        }

        // Language/i18n hook — reserved for future implementation
    } catch (error) {
        console.debug('Failed to load user theme from API:', error);
    }
}

function applyThemeToPage(settings) {
    const root = document.documentElement;
    if (settings.theme_bg_color) {
        root.style.setProperty('--bg-primary', settings.theme_bg_color);
    }
    if (settings.theme_bg_secondary) {
        root.style.setProperty('--bg-secondary', settings.theme_bg_secondary);
    }
    if (settings.theme_bg_tertiary) {
        root.style.setProperty('--bg-tertiary', settings.theme_bg_tertiary);
    }
    if (settings.theme_gold_primary) {
        root.style.setProperty('--gold-primary', settings.theme_gold_primary);
    }
    if (settings.theme_gold_secondary) {
        root.style.setProperty('--gold-secondary', settings.theme_gold_secondary);
    }
    if (settings.theme_text_primary) {
        root.style.setProperty('--text-primary', settings.theme_text_primary);
    }
    if (settings.theme_text_secondary) {
        root.style.setProperty('--text-secondary', settings.theme_text_secondary);
    }
    // Custom uploaded background takes highest priority
    if (settings.theme_custom_bg_url) {
        document.body.style.backgroundImage    = `url('${settings.theme_custom_bg_url}')`;
        document.body.style.backgroundSize     = 'cover';
        document.body.style.backgroundPosition = 'center';
        document.body.style.backgroundAttachment = 'fixed';
        return;
    }
    // Hide the dark background photo for light/bright themes
    const hide = settings.theme_hide_bg_image === true || settings.theme_hide_bg_image === 1 || settings.theme_hide_bg_image === '1';
    document.body.style.backgroundImage = hide ? 'none' : '';
}

// Load theme on page load
document.addEventListener('DOMContentLoaded', loadUserTheme);

function loadPage(page, scriptPath, scriptType, cssPath) {
    console.log(`[loadPage] Loading page: ${page}, script: ${scriptPath}`);
    let pageFile = page.split('?')[0];
    if (!pageFile.endsWith('.html')) pageFile += '.html';

    // Clean up modals before loading new page
    if (typeof ModalUtils !== 'undefined') {
        ModalUtils.cleanupAllModals();
    } else {
        // Fallback cleanup
        document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');
    }

    // Unload all scripts before loading new page
    if (typeof scriptManager !== 'undefined') {
        console.log('[loadPage] Unloading all scripts...');
        scriptManager.unloadAll();
    }

    // Special handling for settings page - ensure script is loaded
    if (pageFile.includes('settings') && !scriptPath) {
        console.log('[loadPage] Settings page detected without script path, using default');
        scriptPath = '/js/settings.js';
    }
    currentLoadedPage = pageFile;
    if (cssPath && typeof scriptManager !== 'undefined') {
        cssPath.split(' ').filter(Boolean).forEach(p => scriptManager.loadCSS(p));
    }

    // Use centralized cache utils if available, otherwise fallback to timestamp
    const cacheBuster = window.cacheUtils ? 
        window.cacheUtils.getFreshCacheBuster() : 
        `v=${Date.now()}&r=${Math.random().toString(36).substr(2, 9)}`;
    
    const fetchOptions = window.cacheUtils ? 
        window.cacheUtils.getFetchOptions(true) : 
        {
            cache: 'no-cache',
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            }
        };
    
    fetch(`/Pages/${pageFile}?${cacheBuster}`, fetchOptions)
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
                console.log(`[loadPage] scriptPath: ${scriptPath}`);
                console.log(`[loadPage] scriptManager defined: ${typeof scriptManager !== 'undefined'}`);
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
    console.log(`[navigateTo] Navigating to page: ${page}`);
    if (pushState) {
        const url = new URL(window.location);
        url.searchParams.set('page', page);
        Array.from(url.searchParams.keys()).filter(k => k !== 'page').forEach(k => url.searchParams.delete(k));
        Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
        history.pushState({ page, params }, '', url.toString());
    }
    navLinks.forEach(l => l.classList.remove('active'));
    const active = document.querySelector(`.nav-link[data-page='${page}']`);
    console.log(`[navigateTo] Active link found:`, !!active);
    let scriptPath = null, scriptType = 'script', cssPath = null;
    if (active) {
        active.classList.add('active');
        scriptPath = active.getAttribute('data-script');
        scriptType = active.getAttribute('data-script-type') || 'script';
        cssPath    = active.dataset.css || null;
        console.log(`[navigateTo] scriptPath: ${scriptPath}`);
        console.log(`[navigateTo] cssPath: ${cssPath}`);
    } else {
        console.warn(`[navigateTo] No active link found for page: ${page}`);
    }
    loadPage(page, scriptPath, scriptType, cssPath);
}

// Nav click delegation
const _navContainer = document.querySelector('nav.sidebar ul.nav, .sidebar ul.nav');
if (_navContainer) _navContainer.addEventListener('click', function (e) {
    const link = e.target.closest('.nav-link[data-page]');
    if (!link || link.id === 'discord-login-link') return;
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
    
    // Clean up any stray ability tree modals on non-mypet pages
    if (page !== 'mypet') {
        const abilityTreeOverlay = document.getElementById('ability-tree-overlay');
        if (abilityTreeOverlay) {
            abilityTreeOverlay.remove();
        }
    }
});

window.addEventListener('message', e => {
    if (e.data?.type === 'navigate') navigateTo(e.data.page);
});

window.navigateTo = navigateTo;
window.loadPageDirect = loadPage;

// ── Discord user ──────────────────────────────────────────────────────────
let currentUser = null;

async function refreshUserProfile() {
    try {
        const refreshBtn = document.getElementById('uc-refresh-btn');
        if (refreshBtn) {
            refreshBtn.style.opacity = '0.3';
            refreshBtn.innerHTML = '⟳';
            refreshBtn.disabled = true;
        }
        
        let response, result;
        
        console.log('Starting profile refresh...');
        
        // Try main refresh method first
        try {
            response = await fetch('/api/discord/refresh-profile', { method: 'POST' });
            if (response.ok) {
                result = await response.json();
                console.log('Main refresh successful:', result);
            } else if (response.status === 401) {
                // If unauthorized, try automatic token refresh first
                console.log('OAuth session expired, trying automatic token refresh...');
                const tokenResult = await window.refreshTokens();
                if (tokenResult && tokenResult.success) {
                    console.log('Tokens refreshed, retrying main refresh...');
                    response = await fetch('/api/discord/refresh-profile', { method: 'POST' });
                    if (response.ok) {
                        result = await response.json();
                        console.log('Main refresh successful after token refresh:', result);
                    } else {
                        throw new Error('Main refresh still failed after token refresh');
                    }
                } else {
                    // If token refresh failed, try bot sync fallback
                    console.log('Token refresh failed, trying bot sync fallback...');
                    throw new Error('OAuth expired and token refresh failed, trying fallback');
                }
            } else {
                const errorText = await response.text();
                throw new Error(`Main refresh failed: ${response.status} ${response.statusText} - ${errorText}`);
            }
        } catch (error) {
            // If main method fails, try fallback
            console.log('Main refresh failed, trying fallback:', error.message);
            try {
                response = await fetch('/api/discord/refresh-profile-fallback', { method: 'POST' });
                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`Fallback method failed: ${response.status} ${response.statusText} - ${errorText}`);
                }
                result = await response.json();
                console.log('Fallback refresh successful after main failed:', result);
            } catch (fallbackError) {
                console.error('Both refresh methods failed:', fallbackError);
                throw new Error(`Both refresh methods failed. Main: ${error.message}, Fallback: ${fallbackError.message}`);
            }
        }
        
        if (result.success) {
            // Update current user data
            currentUser = result.user;
            console.log('Updated currentUser:', currentUser);
            
            // Force update the display with fresh data
            updateUserDisplay(currentUser);
            
            // Show notification based on method and changes
            const changeCount = Object.keys(result.changes || {}).length;
            const method = result.method || 'unknown';
            
            if (method === 'bot_sync' && changeCount > 0) {
                console.log('Profile updated via bot sync with changes:', result.changes);
                if (refreshBtn) {
                    refreshBtn.innerHTML = '✓';
                    refreshBtn.style.color = '#00ff00';
                    setTimeout(() => {
                        refreshBtn.innerHTML = '↻';
                        refreshBtn.style.color = '#ffd700';
                        refreshBtn.style.opacity = '0.7';
                        refreshBtn.disabled = false;
                    }, 2000);
                }
            } else if (method === 'session_refresh') {
                console.log('Profile refreshed using session data:', result.note || 'Bot sync unavailable');
                if (refreshBtn) {
                    refreshBtn.innerHTML = '⚠';
                    refreshBtn.style.color = '#faa61a';
                    setTimeout(() => {
                        refreshBtn.innerHTML = '↻';
                        refreshBtn.style.color = '#ffd700';
                        refreshBtn.style.opacity = '0.7';
                        refreshBtn.disabled = false;
                    }, 2000);
                }
            } else if (changeCount > 0) {
                console.log('Profile updated with changes:', result.changes);
                if (refreshBtn) {
                    refreshBtn.innerHTML = '✓';
                    refreshBtn.style.color = '#00ff00';
                    setTimeout(() => {
                        refreshBtn.innerHTML = '↻';
                        refreshBtn.style.color = '#ffd700';
                        refreshBtn.style.opacity = '0.7';
                        refreshBtn.disabled = false;
                    }, 2000);
                }
            } else {
                // No changes, show brief "up to date" indicator
                console.log('Profile refreshed - no changes detected');
                if (refreshBtn) {
                    refreshBtn.innerHTML = '✓';
                    refreshBtn.style.color = '#00ff00';
                    setTimeout(() => {
                        refreshBtn.innerHTML = '↻';
                        refreshBtn.style.color = '#ffd700';
                        refreshBtn.style.opacity = '0.7';
                        refreshBtn.disabled = false;
                    }, 1000);
                }
            }
        } else {
            throw new Error('Refresh returned success: false');
        }
        return result;
    } catch (error) {
        console.error('Failed to refresh profile:', error);
        const refreshBtn = document.getElementById('uc-refresh-btn');
        if (refreshBtn) {
            refreshBtn.innerHTML = '✗';
            refreshBtn.style.color = '#ff0000';
            setTimeout(() => {
                refreshBtn.innerHTML = '↻';
                refreshBtn.style.color = '#ffd700';
                refreshBtn.style.opacity = '0.7';
                refreshBtn.disabled = false;
            }, 2000);
        }
        throw error;
    }
}

function updateUserDisplay(user) {
    if (!user) {
        console.warn('updateUserDisplay called with no user data');
        return;
    }
    
    console.log('updateUserDisplay called with user:', {
        id: user.id,
        username: user.username,
        global_name: user.global_name,
        avatar: user.avatar
    });
    
    // Show signed-in card, hide signed-out
    document.getElementById('uc-signed-out').style.display = 'none';
    document.getElementById('uc-signed-in').style.display = 'block';
    
    // Update display name
    const displayName = user.global_name || user.username || 'Unknown User';
    document.getElementById('uc-username').textContent = displayName;
    
    // Also update nav user name
    const navUserName = document.getElementById('nav-user-name');
    if (navUserName) {
        navUserName.textContent = displayName;
    }
    
    console.log(`Display name updated to: ${displayName}`);
    
    // Update avatar with cache busting
    const cacheBuster = `_=${Date.now()}&refresh=${Math.random()}`;
    const avatarUrl = `/api/discord/avatar?${cacheBuster}`;
    const avatarElement = document.getElementById('uc-avatar');
    avatarElement.onerror = null;
    avatarElement.src = avatarUrl;
    console.log(`Avatar URL updated to: ${avatarUrl}`);
    avatarElement.onerror = () => { 
        console.warn('Avatar failed to load, using default');
        avatarElement.onerror = null; 
        avatarElement.src = 'https://cdn.discordapp.com/embed/avatars/0.png'; 
    };
    
    // Also update nav avatar in top menu
    const navAvatarElement = document.getElementById('nav-avatar');
    if (navAvatarElement) {
        navAvatarElement.onerror = null;
        navAvatarElement.src = avatarUrl;
        navAvatarElement.onerror = () => {
            navAvatarElement.onerror = null;
            navAvatarElement.src = 'https://cdn.discordapp.com/embed/avatars/0.png';
        };
    }
    
    // Calculate Discord account age from snowflake ID
    const sinceEl = document.getElementById('uc-since');
    if (user.id) {
        try {
            const DISCORD_EPOCH = 1420070400000;
            const timestamp = (BigInt(user.id) >> 22n) + BigInt(DISCORD_EPOCH);
            const createdDate = new Date(Number(timestamp));
            const now = new Date();
            const years = now.getFullYear() - createdDate.getFullYear();
            const months = now.getMonth() - createdDate.getMonth();
            const totalMonths = years * 12 + months;
            
            let ageStr = '';
            if (totalMonths < 1) {
                ageStr = 'New to Discord';
            } else if (totalMonths < 12) {
                ageStr = `${totalMonths}mo on Discord`;
            } else {
                const y = Math.floor(totalMonths / 12);
                const m = totalMonths % 12;
                ageStr = m > 0 ? `${y}y ${m}mo on Discord` : `${y}y on Discord`;
            }
            sinceEl.textContent = ageStr;
        } catch (e) {
            console.warn('Failed to calculate Discord age:', e);
            sinceEl.textContent = 'Discord User';
        }
    } else {
        sinceEl.textContent = 'Discord User';
    }
    
    // Load pet data
    loadUserPet();
}

async function loadUserPet() {
    try {
        const res = await fetch('/api/user/pet');
        if (!res.ok) {
            console.warn('Pet API returned not ok:', res.status);
            document.getElementById('uc-pet-section').style.display = 'none';
            // Hide nav pet dropdown item
            const petsDropdownItem = document.getElementById('pets-dropdown-item');
            if (petsDropdownItem) petsDropdownItem.style.display = 'none';
            return;
        }
        const data = await res.json();
        console.log('Pet data:', data);
        if (!data.has_pet) {
            console.log('User has no pet');
            document.getElementById('uc-pet-section').style.display = 'none';
            // Hide nav pet dropdown item
            const petsDropdownItem = document.getElementById('pets-dropdown-item');
            if (petsDropdownItem) petsDropdownItem.style.display = 'none';
            return;
        }

        // Show pet section
        document.getElementById('uc-pet-section').style.display = 'block';

        // Pet image
        const species = data.species || 'Basic';
        document.getElementById('uc-pet-img').src = `/static/Emojis/Pets/${species}.png`;

        // Pet name
        document.getElementById('uc-pet-name').textContent = data.name || species;

        // Show and update nav pet dropdown item
        const petsDropdownItem = document.getElementById('pets-dropdown-item');
        const navPetImg = document.getElementById('nav-pet-img');
        const navPetName = document.getElementById('nav-pet-name');
        if (petsDropdownItem && navPetImg && navPetName) {
            petsDropdownItem.style.display = 'block';
            navPetImg.src = `/static/Emojis/Pets/${species}.png`;
            navPetName.textContent = data.name || species;
        }
        
        // Type + element emojis
        const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
        const petType = cap(data.type || data.category || 'Land');
        const e1 = cap(data.element || 'basic');
        const e2 = cap(data.element2 || '');
        const elemBar = document.getElementById('uc-pet-elems');
        if (elemBar) {
            let eHtml = `<img src="/static/Emojis/Pets/Deco/${petType}.png" class="uc-pet-type-img" title="${petType}" onerror="this.style.display='none'">`;
            eHtml += `<img src="/static/Emojis/Pets/Deco/${e1}.png" class="uc-pet-type-img" title="${e1}" onerror="this.style.display='none'">`;
            if (e2) eHtml += `<img src="/static/Emojis/Pets/Deco/${e2}.png" class="uc-pet-type-img" title="${e2}" onerror="this.style.display='none'">`;
            elemBar.innerHTML = eHtml;
        }
        
        // Pet rank
        const level = parseInt(data.level || 1, 10);
        const rank = Math.floor(level / 50);
        const rankImg = Math.min(rank, 58);
        const rankImgEl = document.getElementById('uc-pet-rank-img');
        if (rank > 0) {
            rankImgEl.src = `/static/Emojis/Pet Rank/${rankImg}.png`;
            rankImgEl.style.display = 'inline-block';
        } else {
            rankImgEl.style.display = 'none';
        }
        
        // Pet level
        document.getElementById('uc-pet-level').textContent = `Lv.${level}`;
        
        // Survive score — mirrors survive_score() from ss_brain.py
        // Factors: equipment multiplier (new slot system), ss_ability_mult, stat_mastery_mult
        const ssEl = document.getElementById('uc-pet-ss');
        const eq = data.equipment || {};
        const levelBonus = Math.floor(level / 50);

        // ── New slot system multiplier (mirrors StatsCalculator.get_equipment_xp_multiplier) ──
        function _getSingle(key) {
            var v = eq[key];
            if (Array.isArray(v)) v = v[0] || null;
            return (v && v.name) ? v : null;
        }
        function _getList(key) {
            var v = eq[key] || [];
            if (!Array.isArray(v)) v = (v && v.name) ? [v] : [];
            return v.filter(function(i){ return i && i.name; });
        }
        const mainSlotsDash = [_getSingle('Helmet'), _getSingle('Armor'), _getSingle('Boots'),
                               _getSingle('Ring'), _getSingle('Shield'), _getSingle('Weapon')];
        const mainFilledDash = mainSlotsDash.filter(s => s !== null);
        const materialDash   = _getSingle('Material');
        const monstersDash   = _getList('Monsters');
        const gemsDash       = _getList('Gems');

        const mainSetTagsDash = mainFilledDash.map(i => i.set || null).filter(t => t);
        const matchingSetDash = (mainFilledDash.length === 6 && mainSetTagsDash.length === 6 &&
            new Set(mainSetTagsDash).size === 1);
        const monNamesDash = monstersDash.map(m => (m.name || '').toLowerCase());
        const gemNamesDash = gemsDash.map(g => (g.name || '').toLowerCase());
        const matchingMonsDash  = (monNamesDash.length === 2 && monNamesDash[0] === monNamesDash[1]);
        const matchingGemsDash  = (gemNamesDash.length === 2 && gemNamesDash[0] === gemNamesDash[1]);
        const hasMatDash        = materialDash !== null;
        const ringSubBonusDash  = (matchingMonsDash ? 1 : 0) + (matchingGemsDash ? 1 : 0) + (hasMatDash ? 1 : 0);
        const fullSetDash = (mainFilledDash.length === 6 && matchingSetDash &&
                             _getSingle('Ring') !== null && hasMatDash && matchingMonsDash && matchingGemsDash);
        let baseMult = mainFilledDash.length + (matchingSetDash ? 3 : 0) + ringSubBonusDash + levelBonus;
        if (baseMult < 1) baseMult = 1;
        const multiplier = fullSetDash ? baseMult * 2 : baseMult;

        // ss_ability_mult: att_survive_aggression + def_survive_endurance (multiplicative)
        const abilities = data.abilities || {};
        const _ssAbilDefs = [
            { id: 'att_survive_aggression', base: 1.1, per_level: 0.1 },
            { id: 'def_survive_endurance',  base: 1.1, per_level: 0.1 },
        ];
        let ssAbilityMult = 1.0;
        _ssAbilDefs.forEach(ab => {
            const lvl = parseInt(abilities[ab.id] || 0, 10);
            if (lvl > 0) ssAbilityMult *= ab.base + ab.per_level * (lvl - 1);
        });

        // stat_mastery_mult: average of all 6 stat mastery multipliers (1.0 + points * 0.1)
        const statMastery = data.stat_mastery || {};
        const _ssStats = ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'];
        let statMasterySum = 0;
        _ssStats.forEach(s => {
            const raw = statMastery[s] || 0;
            const pts = (typeof raw === 'object' && raw !== null) ? (raw.points || 0) : parseInt(raw, 10);
            statMasterySum += 1.0 + pts * 0.1;
        });
        const statMasteryMult = statMasterySum / _ssStats.length;

        const ssScore = (level / multiplier / 10 * ssAbilityMult * statMasteryMult).toFixed(2);
        ssEl.innerHTML = `<strong style="color:var(--gold-primary)">SS: ${ssScore}</strong>`;
        ssEl.style.display = 'inline-block';

        // Fetch SS stats — not shown on card
        document.getElementById('uc-pet-ss-stats').style.display = 'none';
        
        // XP bar
        const xpMax = data.xp_for_next_level || 1;
        const xpCur = data.experience || 0;
        const xpPct = xpMax > 0 ? Math.min((xpCur / xpMax) * 100, 100) : 0;
        document.getElementById('uc-xp-bar').style.width = xpPct + '%';
        
        
    } catch (e) {
        console.warn('Failed to load pet data:', e);
        document.getElementById('uc-pet-section').style.display = 'none';
    }
}

function renderEquipmentBar(eq) {
    const slots = [
        {type:'Monsters',idx:0},{type:'Gems',idx:0},
        {type:'Material',idx:0},{type:'Hat'},
        {type:'Material',idx:1},{type:'Gems',idx:1},
        {type:'Monsters',idx:1}
    ];
    
    // Determine set bonuses for glow
    const matCounts = {}, gemCounts = {}, monCounts = {};
    (Array.isArray(eq.Material) ? eq.Material : [eq.Material]).forEach(m => {
        if (m && m.name) matCounts[m.name.toLowerCase()] = (matCounts[m.name.toLowerCase()]||0)+1;
    });
    (eq.Gems||[]).forEach(g => {
        if (g && g.name) gemCounts[g.name.toLowerCase()] = (gemCounts[g.name.toLowerCase()]||0)+1;
    });
    (eq.Monsters||[]).forEach(m => {
        if (m && m.name) monCounts[m.name.toLowerCase()] = (monCounts[m.name.toLowerCase()]||0)+1;
    });
    
    const matPair = Object.values(matCounts).some(c => c >= 2);
    const gemPair = Object.values(gemCounts).some(c => c >= 2);
    const monPair = Object.values(monCounts).some(c => c >= 2);
    const hatEquipped = !!(eq.Hat && eq.Hat.name);
    const fullSet = matPair && gemPair && monPair && hatEquipped;
    
    let html = '';
    slots.forEach(sl => {
        const item = sl.type === 'Hat' ? (eq.Hat||null) : ((eq[sl.type]||[])[sl.idx]||null);
        const isEmpty = !item || !item.name;
        const src = isEmpty ? '/static/Emojis/Pets/Deco/Basic.png' : `/static/Emojis/Pets/Equipment/${equipImgFile(item)}`;
        
        let glowClass = '';
        if (fullSet) {
            glowClass = ' uc-fullset';
        } else {
            const isPair = (sl.type === 'Monsters' && monPair) ||
                           (sl.type === 'Gems' && gemPair) ||
                           (sl.type === 'Material' && matPair);
            if (isPair) glowClass = ' uc-pair';
        }
        
        html += `<div class="uc-equip-slot${isEmpty ? ' uc-empty' : ''}${glowClass}" title="${isEmpty ? 'Empty' : item.name}">
            <img src="${src}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
        </div>`;
    });
    
    document.getElementById('uc-equip-bar').innerHTML = html;
}

function equipImgFile(item) {
    if (!item || !item.name) return 'Basic.png';
    if (item.emoji_file) return item.emoji_file;
    return item.name.replace(/ /g, '') + '.png';
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Dashboard loading, fetching user data...');
    fetch('/api/discord/user')
        .then(r => { 
            console.log('User fetch response status:', r.status);
            if (!r.ok) throw new Error('Not logged in'); 
            return r.json(); 
        })
        .then(user => {
            console.log('User data loaded:', user);
            currentUser = user;
            document.getElementById('uc-signed-out').style.display = 'none';
            updateUserDisplay(user);
            updatePetLink();
            
            // Refresh button hover
            const refreshBtn = document.getElementById('uc-refresh-btn');
            if (refreshBtn) {
                refreshBtn.addEventListener('mouseenter', () => { refreshBtn.style.opacity = '1'; });
                refreshBtn.addEventListener('mouseleave', () => { refreshBtn.style.opacity = ''; });
            }
        })
        .catch((error) => {
            console.log('User not logged in or fetch failed:', error.message);
            document.getElementById('uc-signed-out').style.display = 'block';
            document.getElementById('uc-signed-in').style.display = 'none';
            updatePetLink();
        });
});

// Make functions available globally
window.refreshUserProfile = refreshUserProfile;

window.checkSessionStatus = async function() {
    try {
        const response = await fetch('/api/discord/session-status');
        const status = await response.json();
        console.log('Session Status:', status);
        return status;
    } catch (error) {
        console.error('Failed to check session status:', error);
        return null;
    }
};

window.testUserEndpoint = async function() {
    try {
        const response = await fetch('/api/discord/user');
        if (response.ok) {
            const user = await response.json();
            console.log('User endpoint response:', user);
            return user;
        } else {
            console.error('User endpoint failed:', response.status, response.statusText);
            const error = await response.text();
            console.error('Error details:', error);
            return null;
        }
    } catch (error) {
        console.error('Failed to test user endpoint:', error);
        return null;
    }
};

window.testRefreshFunctionality = async function() {
    try {
        console.log('Testing refresh functionality...');
        const response = await fetch('/api/discord/test-refresh', { method: 'POST' });
        const result = await response.json();
        console.log('Refresh test results:', result);
        return result;
    } catch (error) {
        console.error('Failed to test refresh functionality:', error);
        return null;
    }
};

window.debugBotAccess = async function() {
    try {
        console.log('Checking bot access...');
        const response = await fetch('/api/discord/debug-bot-access');
        const result = await response.json();
        console.log('Bot access debug info:', result);
        return result;
    } catch (error) {
        console.error('Failed to debug bot access:', error);
        return null;
    }
};

window.testBotSync = async function() {
    try {
        console.log('Testing bot sync...');
        const response = await fetch('/api/discord/test-bot-sync', { method: 'POST' });
        const result = await response.json();
        console.log('Bot sync test results:', result);
        return result;
    } catch (error) {
        console.error('Failed to test bot sync:', error);
        return null;
    }
};

window.forceAvatarRefresh = async function() {
    try {
        console.log('Forcing avatar refresh...');
        const response = await fetch('/api/discord/force-avatar-refresh', { method: 'POST' });
        const result = await response.json();
        console.log('Force avatar refresh results:', result);
        
        if (result.success && result.user) {
            currentUser = result.user;
            updateUserDisplay(currentUser);
        }
        
        return result;
    } catch (error) {
        console.error('Failed to force avatar refresh:', error);
        return null;
    }
};

window.clearStaleSession = async function() {
    try {
        console.log('Clearing stale session...');
        const response = await fetch('/api/discord/clear-stale-session', { method: 'POST' });
        const result = await response.json();
        console.log('Clear stale session results:', result);
        
        if (result.success) {
            console.log('Session cleared. You may need to re-login for fresh avatar.');
        }
        
        return result;
    } catch (error) {
        console.error('Failed to clear stale session:', error);
        return null;
    }
};

window.fixAvatarIssue = async function() {
    try {
        console.log('Attempting to fix avatar issue...');
        
        // Step 1: Try force refresh first
        console.log('Step 1: Trying force refresh...');
        let result = await window.forceAvatarRefresh();
        if (result && result.success) {
            console.log('✅ Avatar fixed via force refresh');
            return result;
        }
        
        // Step 2: Try automatic token refresh
        console.log('Step 2: Attempting automatic token refresh...');
        result = await window.refreshTokens();
        if (result && result.success) {
            console.log('✅ Tokens refreshed successfully');
            // Update display with fresh user data
            if (result.user) {
                currentUser = result.user;
                updateUserDisplay(currentUser);
            }
            return result;
        }
        
        // Step 3: Clear stale session
        console.log('Step 3: Clearing stale session...');
        result = await window.clearStaleSession();
        if (result && result.success) {
            console.log('✅ Stale session cleared');
            
            // Step 4: Try refresh again
            console.log('Step 4: Trying refresh after clearing session...');
            result = await window.refreshUserProfile();
            if (result && result.success) {
                console.log('✅ Avatar fixed after clearing session');
                return result;
            }
        }
        
        // Step 5: Suggest re-login
        console.log('⚠️ Automatic fix failed. You may need to log out and back in.');
        return { success: false, message: 'Please log out and back in to fix avatar issue' };
        
    } catch (error) {
        console.error('Failed to fix avatar issue:', error);
        return null;
    }
};

window.refreshTokens = async function() {
    try {
        console.log('Attempting to refresh OAuth tokens...');
        const response = await fetch('/api/discord/refresh-tokens', { method: 'POST' });
        const result = await response.json();
        
        if (response.ok && result.success) {
            if (result.method === 'refresh_token') {
                console.log('✅ Tokens refreshed using refresh token');
                return result;
            } else if (result.method === 'silent_reauth') {
                console.log('🔄 Silent re-authentication required...');
                return await window.performSilentReauth(result.oauth_url);
            }
        } else {
            console.log('❌ Token refresh failed:', result.error || 'Unknown error');
        }
        
        return result;
    } catch (error) {
        console.error('Failed to refresh tokens:', error);
        return null;
    }
};

window.performSilentReauth = async function(oauthUrl) {
    return new Promise((resolve) => {
        console.log('Opening silent re-authentication popup...');
        
        // Open popup for re-authentication
        const popup = window.open(
            oauthUrl,
            'discord_reauth',
            'width=500,height=600,scrollbars=yes,resizable=yes'
        );
        
        if (!popup) {
            console.error('Popup blocked! Please allow popups for this site.');
            resolve({ success: false, error: 'Popup blocked' });
            return;
        }
        
        // Listen for completion message
        const messageHandler = (event) => {
            if (event.data && event.data.type === 'discord_reauth_complete') {
                window.removeEventListener('message', messageHandler);
                
                if (event.data.success) {
                    console.log('✅ Silent re-authentication completed successfully');
                    
                    // Refresh user data after successful re-auth
                    fetch('/api/discord/user')
                        .then(r => r.json())
                        .then(user => {
                            currentUser = user;
                            updateUserDisplay(currentUser);
                            resolve({ 
                                success: true, 
                                method: 'silent_reauth',
                                user: user,
                                message: 'Re-authentication completed successfully'
                            });
                        })
                        .catch(error => {
                            console.error('Failed to fetch user after reauth:', error);
                            resolve({ success: true, method: 'silent_reauth' });
                        });
                } else {
                    console.error('Silent re-authentication failed');
                    resolve({ success: false, error: 'Re-authentication failed' });
                }
            }
        };
        
        window.addEventListener('message', messageHandler);
        
        // Check if popup was closed manually
        const checkClosed = setInterval(() => {
            if (popup.closed) {
                clearInterval(checkClosed);
                window.removeEventListener('message', messageHandler);
                console.log('Re-authentication popup was closed');
                resolve({ success: false, error: 'Popup closed by user' });
            }
        }, 1000);
        
        // Timeout after 2 minutes
        setTimeout(() => {
            if (!popup.closed) {
                popup.close();
            }
            clearInterval(checkClosed);
            window.removeEventListener('message', messageHandler);
            resolve({ success: false, error: 'Re-authentication timeout' });
        }, 120000);
    });
};

function updatePetLink() {
    const link = document.getElementById('my-pet-link');
    if (!link) return;
    link.style.display = 'block';
    fetch('/api/user/pet')
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (data?.has_pet && data.species) {
                const a = link.querySelector('a');
                if (a) a.innerHTML = `<img src="/static/Emojis/Pets/${data.species}.png" alt="My Pet" style="width:20px;height:20px;margin-right:8px;" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'"> ${data.name}`;
            }
        })
        .catch(() => {});
}

// ── Nation Link Bar ───────────────────────────────────────────────────────
const LS_KEY = 'pnw_linked_nation';

function showLinkedNation(nation) {
    document.getElementById('uc-nation-input').style.display = 'none';
    document.getElementById('uc-nation-linked').style.display = 'block';
    document.getElementById('nation-linked-name').textContent = nation.nation_name || `Nation #${nation.nation_id}`;
    const flag = document.getElementById('nation-flag-img');
    if (nation.flag) { 
        flag.src = window.ImageUtils ? window.ImageUtils.proxyImageUrl(nation.flag) : nation.flag; 
        flag.style.display = 'inline-block'; 
    }
    else flag.style.display = 'none';
    loadNationRanks(nation.nation_name || '');
    
    // Also update nav nation dropdown item
    const pnwDropdownItem = document.getElementById('pnw-dropdown-item');
    const navNationFlag = document.getElementById('nav-nation-flag');
    if (pnwDropdownItem && navNationFlag) {
        pnwDropdownItem.style.display = 'block';
        if (nation.flag) {
            navNationFlag.src = window.ImageUtils ? window.ImageUtils.proxyImageUrl(nation.flag) : nation.flag;
            navNationFlag.style.display = 'inline-block';
        } else {
            navNationFlag.style.display = 'none';
        }
    }
}

function showNationInput() {
    document.getElementById('uc-nation-linked').style.display = 'none';
    document.getElementById('uc-nation-input').style.display = 'block';
    document.getElementById('nation-link-error').style.display = 'none';
    
    // Hide nav nation dropdown item
    const pnwDropdownItem = document.getElementById('pnw-dropdown-item');
    if (pnwDropdownItem) {
        pnwDropdownItem.style.display = 'none';
    }
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
            if (r.rank <= 3) slides.push({
                period: label,
                label: r.category_label,
                rank: r.rank,
                total: r.total,
                prefix: r.prefix || '',
                tied_count: r.tied_count || 1,
                tied_names: r.tied_names || [],
            });
        });
    });
    return slides;
}

function showRankSlide(ticker, i) {
    const s = _rankSlides[i];
    const src = s.prefix ? `/static/Emojis/Leaderboards/${s.rank}${s.prefix}.png` : '';
    const img = src ? `<img src="${src}" alt="#${s.rank}" style="width:2rem;height:2rem;object-fit:contain;flex-shrink:0;">` : '';
    const tieStr = s.tied_count > 1 ? ` (tied w/${s.tied_count})` : '';
    const html = `<span class="rank-slide visible" style="display:flex;align-items:center;gap:0.45rem;min-width:0;">
        ${img}
        <span style="display:flex;flex-direction:column;min-width:0;line-height:1.25;">
            <span class="rank-period" style="font-size:0.72rem;color:var(--gold-primary);font-weight:700;white-space:nowrap;">${s.period}</span>
            <span class="rank-label" style="font-size:0.68rem;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${s.label}${tieStr}</span>
        </span>
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




// ── Menu Layout Reordering ──────────────────────────────────────────────────────
// Apply custom menu layout from user settings
async function applyMenuLayout() {
    try {
        // Try to get layout from localStorage first for instant effect
        let layoutData = null;
        const savedLayout = localStorage.getItem('reaper_menu_layout');
        if (savedLayout) {
            try {
                layoutData = JSON.parse(savedLayout);
                console.log('[MenuLayout] Applying layout from localStorage');
            } catch (e) {
                console.warn('[MenuLayout] Failed to parse localStorage layout', e);
            }
        }

        // Also fetch from API for authoritative data
        const response = await fetch('/api/settings');
        if (response.ok) {
            const settings = await response.json();
            if (settings.menu_layout) {
                try {
                    layoutData = JSON.parse(settings.menu_layout);
                    console.log('[MenuLayout] Applying layout from API');
                    // Update localStorage with API version
                    localStorage.setItem('reaper_menu_layout', settings.menu_layout);
                } catch (e) {
                    console.warn('[MenuLayout] Failed to parse API layout', e);
                }
            }
        }

        if (!layoutData) {
            console.log('[MenuLayout] No custom layout found, using default order');
            return;
        }

        // Apply layout to each menu group
        ['pnw', 'pets', 'fun', 'site'].forEach(groupName => {
            const groupOrder = layoutData[groupName];
            if (!groupOrder || !Array.isArray(groupOrder)) return;

            // Find the menu container
            let menuContainer;
            if (groupName === 'pnw') {
                menuContainer = document.querySelector('#pnw-dropdown .mega-menu-grid');
            } else if (groupName === 'pets') {
                menuContainer = document.querySelector('#pets-dropdown .mega-menu-grid');
            } else if (groupName === 'fun') {
                menuContainer = document.querySelector('#fun-dropdown .mega-menu-grid');
            } else if (groupName === 'site') {
                menuContainer = document.querySelector('#site-dropdown .mega-menu-grid');
            }

            if (!menuContainer) {
                console.warn(`[MenuLayout] Menu container not found for group: ${groupName}`);
                return;
            }

            // Get all menu items
            const items = Array.from(menuContainer.querySelectorAll('.mega-menu-item'));
            const itemMap = {};
            items.forEach(item => {
                const pageId = item.dataset.page;
                if (pageId) itemMap[pageId] = item;
            });

            // Reorder based on saved layout
            groupOrder.forEach(pageId => {
                const item = itemMap[pageId];
                if (item) {
                    menuContainer.appendChild(item);
                }
            });

            console.log(`[MenuLayout] Reordered ${groupName} menu with ${groupOrder.length} items`);
        });

    } catch (error) {
        console.error('[MenuLayout] Error applying menu layout:', error);
    }
}

// Apply layout on page load
document.addEventListener('DOMContentLoaded', () => {
    // Wait a bit for the menu to be fully rendered
    setTimeout(applyMenuLayout, 100);
});
