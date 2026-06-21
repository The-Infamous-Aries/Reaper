/**
 * access_guard.js — Alliance-verified access enforcement for protected pages.
 *
 * Usage:
 *   Add <script src="/js/access_guard.js"></script> to the <head> of every
 *   protected page, BEFORE page-specific scripts.
 *
 * If the user is not logged in, not verified, or their alliance isn't approved,
 * they are redirected to /dashboard with a human-readable error message in the
 * query string so the dashboard can show a banner.
 *
 * The guard immediately hides the page body to prevent content flash, then
 * shows it only if access is granted. On network errors it fails open.
 */
(function () {
    'use strict';

    /** Pages that require verified + approved-alliance access. */
    const PROTECTED_PAGES = new Set([
        'watch',
        'leaderboard',
        'nations',
        'cost_calc',
        'raids',
        'weapons',
        'destroy',
        'spy_wipe',
        'my_nation',
        'rev_optimizer',
        'library',
        'comparison',
    ]);

    // Derive the current page key.
    // Works for both direct navigation (/Pages/watch.html) AND SPA mode
    // where the page fragment is loaded into the dashboard (?page=watch).
    const pathPage = location.pathname
        .split('/')
        .filter(Boolean)
        .pop() || '';
    const searchPage = new URLSearchParams(location.search).get('page') || '';
    const currentPage = (pathPage || searchPage).replace(/\.html$/i, '');

    // Not a protected page — exit immediately, nothing to do
    if (!PROTECTED_PAGES.has(currentPage)) return;

    // ── Determine if we're running in SPA mode (fragment inside #content) ──
    // In SPA mode, location.pathname is /dashboard and the page is in ?page=
    // We only need to hide content in direct-navigation mode, not SPA mode,
    // because in SPA the redirect lands on the same dashboard page (no flash).
    const isSPA = !!searchPage;

    // ── Hide content to prevent flash (direct navigation only) ───────────
    // In SPA mode we skip this — the redirect is within-page and instant.
    let _hideEl = null;
    if (!isSPA) {
        const _style = document.createElement('style');
        _style.id = '__access_guard_hide';
        _style.textContent = 'body { visibility: hidden !important; }';
        document.head.appendChild(_style);
        _hideEl = _style;
    } else {
        // In SPA mode, hide just the content container to prevent flash
        const contentEl = document.getElementById('content');
        if (contentEl) {
            contentEl.style.visibility = 'hidden';
            _hideEl = contentEl;
        }
    }

    function _showPage() {
        if (!_hideEl) return;
        if (_hideEl.tagName === 'STYLE') {
            _hideEl.remove();
        } else {
            _hideEl.style.visibility = '';
        }
    }

    /** Human-readable denial messages keyed by reason code. */
    const REASON_MESSAGES = {
        not_logged_in:
            'You must log in with Discord to access this page.',
        not_verified:
            'You must verify your nation first. Use /self_verify in Discord.',
        alliance_not_approved: null, // filled dynamically below
    };

    fetch('/api/access/check-alliance', {
        credentials: 'include',
        cache: 'no-store',
    })
    .then(function (resp) {
        // Non-200 means the server errored — fail open, show the page
        if (!resp.ok) {
            console.warn('[access_guard] Server returned', resp.status, '— allowing page load');
            _showPage();
            return;
        }
        return resp.json();
    })
    .then(function (data) {
        if (!data) return; // already handled above (non-ok branch returns undefined)

        if (data.allowed) {
            // ✅ Access granted — reveal the page
            _showPage();
            return;
        }

        // ❌ Access denied — build message and redirect
        let message;
        if (data.reason === 'alliance_not_approved') {
            const allianceName = data.alliance_name
                ? 'Your alliance (' + data.alliance_name + ')'
                : 'Your alliance';
            message = allianceName + ' is not approved for access to this page. ' +
                'Contact your alliance leader or a server admin.';
        } else {
            message = REASON_MESSAGES[data.reason] || 'Access to this page is restricted.';
        }

        if (isSPA) {
            // In SPA mode: clear the content pane and show an inline denial message
            // Use the same banner styling as the dashboard to ensure consistency
            const contentEl = document.getElementById('content');
            if (contentEl) {
                contentEl.style.visibility = '';
                contentEl.innerHTML =
                    '<div style="padding:40px 24px;">' +
                    // Banner similar to dashboard.html
                    '<div style="position:fixed;top:0;left:0;right:0;z-index:99999;' +
                    'background:#c0392b;color:#fff;padding:14px 48px 14px 20px;' +
                    'font-family:inherit;font-size:14px;line-height:1.5;' +
                    'box-shadow:0 2px 8px rgba(0,0,0,.4);display:flex;align-items:center;gap:12px;">' +
                    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>' +
                    '<line x1="12" y1="9" x2="12" y2="13"></line>' +
                    '<line x1="12" y1="17" x2="12.01" y2="17"></line>' +
                    '</svg>' +
                    '<span>' + message + '</span>' +
                    '</div>' +
                    // Main content
                    '<h2 style="margin:100px 0 12px">🔒 Access Denied</h2>' +
                    '<p style="margin:0;font-size:15px">' + message + '</p>' +
                    '<p style="margin:12px 0 0;font-size:13px;opacity:.7">Use <code>/self_verify</code> in Discord to verify your nation.</p>' +
                    '</div>';
            }
        } else {
            // Direct navigation: redirect to dashboard with the denial banner
            window.location.replace(
                '/dashboard?access_denied=' + encodeURIComponent(message)
            );
        }
    })
    .catch(function (err) {
        // Network error — fail open so a CDN blip doesn't lock users out
        console.warn('[access_guard] Access check failed (network error) — allowing page load:', err);
        _showPage();
    });
})();
