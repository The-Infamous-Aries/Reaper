/* ── Bazaar — live board + post/buy/cancel ─────────────────────────────── */
(function () {
    'use strict';

    let currentUser = null;   // { id, username }
    let myPet       = null;   // pet data for the logged-in user
    let ws          = null;
    let wsRetryMs   = 2000;

    // ── Init ──────────────────────────────────────────────────────────────────
    async function init() {
        await Promise.all([fetchUser(), fetchMyPet()]);
        renderPostForm();
        connectWS();
    }

    async function fetchUser() {
        try {
            const r = await fetch('/api/discord/user');
            if (r.ok) {
                const d = await r.json();
                if (d && d.id) currentUser = d;
            }
        } catch (_) {}
    }

    async function fetchMyPet() {
        try {
            const r = await fetch('/api/user/pet');
            if (r.ok) {
                const d = await r.json();
                if (d.has_pet) myPet = d;
            }
        } catch (_) {}
    }

    // ── WebSocket ─────────────────────────────────────────────────────────────
    function connectWS() {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        ws = new WebSocket(`${proto}://${location.host}/api/bazaar/ws`);

        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'board') renderBoard(msg.listings);
        };

        ws.onclose = () => {
            setLive(false);
            setTimeout(() => { wsRetryMs = Math.min(wsRetryMs * 1.5, 30000); connectWS(); }, wsRetryMs);
        };

        ws.onopen = () => { wsRetryMs = 2000; setLive(true); };
        ws.onerror = () => ws.close();

        // Keep-alive ping every 25 s
        setInterval(() => { if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping'); }, 25000);
    }

    function setLive(on) {
        const dot = document.getElementById('bz-live-dot');
        if (dot) dot.style.background = on ? '#2ecc71' : '#e74c3c';
    }

    // ── Board render ──────────────────────────────────────────────────────────
    function renderBoard(listings) {
        const tbody = document.getElementById('bz-tbody');
        if (!tbody) return;

        if (!listings || listings.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6"><div class="bz-empty">📭 No listings yet — be the first to post!</div></td></tr>`;
            return;
        }

        tbody.innerHTML = listings.map(l => {
            const rarityClass = 'rarity-' + (l.item_rarity || 'common').toLowerCase();
            const priceHtml = l.price_type === 'xp'
                ? `<span class="bz-price-xp">✨ ${l.xp_price.toLocaleString()} XP</span>`
                : `<span class="bz-price-trade">🔄 ${l.trade_item_quantity}x ${escHtml(l.trade_item_name)}</span>`;

            // Seller column: show pet emoji + pet name + discord username
            const petEmoji = l.seller_pet_emoji
                ? `<img src="/static/Emojis/Pets/${escAttr(l.seller_pet_emoji)}.png"
                        alt="${escAttr(l.seller_pet_emoji)}"
                        style="width:20px;height:20px;vertical-align:middle;margin-right:4px;border-radius:3px"
                        onerror="this.style.display='none'">`
                : '';
            const petName = l.seller_pet_name
                ? `<span style="color:var(--gold-primary);font-weight:600">${escHtml(l.seller_pet_name)}</span><br>`
                : '';
            const sellerHtml = `${petEmoji}${petName}<small style="color:var(--text-secondary)">${escHtml(l.seller_name)}</small>`;

            const isOwn   = currentUser && String(l.seller_id) === String(currentUser.id);
            const canBuy  = currentUser && !isOwn && myPet;
            const actionBtn = isOwn
                ? `<button class="bz-btn bz-btn-danger" onclick="bzCancel(${l.listing_id})">Cancel</button>`
                : canBuy
                    ? `<button class="bz-btn" onclick="bzBuy(${l.listing_id})">Buy</button>`
                    : `<span style="color:var(--text-secondary);font-size:0.8rem">${currentUser ? '—' : 'Login'}</span>`;

            return `<tr>
                <td><span class="${rarityClass}">${escHtml(l.item_name)}</span>
                    <br><small style="color:var(--text-secondary)">${escHtml(l.item_type)} · ${escHtml(l.item_rarity)} · ×${l.quantity}</small></td>
                <td>${sellerHtml}</td>
                <td>${priceHtml}</td>
                <td style="color:var(--text-secondary);font-size:0.8rem">${timeAgo(l.created_at)}</td>
                <td>${actionBtn}</td>
            </tr>`;
        }).join('');
    }

    // ── Post form ─────────────────────────────────────────────────────────────
    function renderPostForm() {
        const wrap = document.getElementById('bz-post-form');
        if (!wrap) return;

        if (!currentUser) {
            wrap.innerHTML = `<p style="color:var(--text-secondary);text-align:center">
                <a href="/api/auth/login" style="color:var(--gold-primary)">Log in with Discord</a> to post listings.</p>`;
            return;
        }
        if (!myPet) {
            wrap.innerHTML = `<p style="color:var(--text-secondary);text-align:center">You need a pet to use the Bazaar.</p>`;
            return;
        }

        // Build inventory options
        const inv = (myPet.inventory || []).filter(it => it.count > 0);
        const invOpts = inv.map(it =>
            `<option value="${escAttr(it.name)}">${escHtml(it.name)} (×${it.count})</option>`
        ).join('');

        wrap.innerHTML = `
        <div class="row g-3">
            <div class="col-md-4">
                <label class="bz-form-label">Item to sell</label>
                <select id="bz-item-sel" class="bz-input" onchange="bzItemChanged()">
                    <option value="">— choose item —</option>
                    ${invOpts}
                </select>
                <div class="bz-inv-hint" id="bz-item-hint"></div>
            </div>
            <div class="col-md-2">
                <label class="bz-form-label">Quantity</label>
                <input id="bz-qty" type="number" min="1" value="1" class="bz-input">
            </div>
            <div class="col-md-2">
                <label class="bz-form-label">Price type</label>
                <select id="bz-price-type" class="bz-input" onchange="bzPriceTypeChanged()">
                    <option value="xp">XP</option>
                    <option value="trade">Trade</option>
                </select>
            </div>
            <div class="col-md-4" id="bz-price-fields">
                <label class="bz-form-label">XP price</label>
                <input id="bz-xp-price" type="number" min="1" placeholder="e.g. 500" class="bz-input">
            </div>
        </div>
        <div class="mt-3 text-end">
            <button class="bz-btn" onclick="bzPost()">📦 Post Listing</button>
        </div>`;
    }

    window.bzItemChanged = function () {
        const sel  = document.getElementById('bz-item-sel');
        const hint = document.getElementById('bz-item-hint');
        const inv  = (myPet && myPet.inventory) || [];
        const item = inv.find(it => it.name === sel.value);
        if (item && hint) {
            hint.textContent = `${item.rarity} · ${item.type} · You have ×${item.count}`;
            document.getElementById('bz-qty').max = item.count;
        } else if (hint) {
            hint.textContent = '';
        }
    };

    window.bzPriceTypeChanged = function () {
        const type  = document.getElementById('bz-price-type').value;
        const wrap  = document.getElementById('bz-price-fields');
        if (type === 'xp') {
            wrap.innerHTML = `<label class="bz-form-label">XP price</label>
                <input id="bz-xp-price" type="number" min="1" placeholder="e.g. 500" class="bz-input">`;
        } else {
            wrap.innerHTML = `
                <label class="bz-form-label">Want item name</label>
                <input id="bz-trade-name" type="text" placeholder="e.g. Fire Gem" class="bz-input" style="margin-bottom:0.4rem">
                <label class="bz-form-label">Quantity wanted</label>
                <input id="bz-trade-qty" type="number" min="1" value="1" class="bz-input">`;
        }
    };

    window.bzPost = async function () {
        const itemName  = (document.getElementById('bz-item-sel')?.value || '').trim();
        const quantity  = parseInt(document.getElementById('bz-qty')?.value || '1');
        const priceType = document.getElementById('bz-price-type')?.value;
        const xpPrice   = parseInt(document.getElementById('bz-xp-price')?.value || '0');
        const tradeName = (document.getElementById('bz-trade-name')?.value || '').trim();
        const tradeQty  = parseInt(document.getElementById('bz-trade-qty')?.value || '1');

        if (!itemName) return toast('Select an item to sell', 'error');
        if (quantity < 1) return toast('Quantity must be at least 1', 'error');
        if (priceType === 'xp' && xpPrice < 1) return toast('Enter a valid XP price', 'error');
        if (priceType === 'trade' && !tradeName) return toast('Enter the item you want in trade', 'error');

        const body = { item_name: itemName, quantity, price_type: priceType };
        if (priceType === 'xp') body.xp_price = xpPrice;
        else { body.trade_item_name = tradeName; body.trade_item_quantity = tradeQty; }

        const r = await apiFetch('/api/bazaar/post', 'POST', body);
        if (r.ok) {
            toast('Listing posted!', 'success');
            await fetchMyPet();
            renderPostForm();
        } else {
            toast(r.error || 'Failed to post listing', 'error');
        }
    };

    window.bzBuy = async function (listingId) {
        if (!confirm('Confirm purchase?')) return;
        const r = await apiFetch(`/api/bazaar/buy/${listingId}`, 'POST');
        if (r.ok) {
            toast('Purchase complete!', 'success');
            await fetchMyPet();
        } else {
            toast(r.error || 'Purchase failed', 'error');
        }
    };

    window.bzCancel = async function (listingId) {
        if (!confirm('Cancel this listing? The item will be returned to your inventory.')) return;
        const r = await apiFetch(`/api/bazaar/cancel/${listingId}`, 'POST');
        if (r.ok) {
            toast('Listing cancelled — item returned.', 'success');
            await fetchMyPet();
            renderPostForm();
        } else {
            toast(r.error || 'Cancel failed', 'error');
        }
    };

    // ── Utilities ─────────────────────────────────────────────────────────────
    async function apiFetch(url, method = 'GET', body = null) {
        try {
            const opts = { method, headers: {} };
            if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
            const r = await fetch(url, opts);
            return await r.json();
        } catch (e) {
            return { ok: false, error: 'Network error' };
        }
    }

    function escHtml(s) {
        return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    function escAttr(s) {
        return String(s || '').replace(/"/g,'&quot;');
    }

    function timeAgo(iso) {
        if (!iso) return '—';
        const diff = Math.floor((Date.now() - new Date(iso + 'Z').getTime()) / 1000);
        if (diff < 60)   return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
        return `${Math.floor(diff/86400)}d ago`;
    }

    let _toastTimer = null;
    function toast(msg, type = 'success') {
        const el = document.getElementById('bz-toast');
        if (!el) return;
        el.textContent = msg;
        el.className = type;
        el.style.display = 'block';
        clearTimeout(_toastTimer);
        _toastTimer = setTimeout(() => { el.style.display = 'none'; }, 3500);
    }

    // ── Boot ──────────────────────────────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
