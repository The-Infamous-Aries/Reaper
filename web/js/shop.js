/* ══════════════════════════════════════════════════════════════════
   Shop Page — shop.js
   Fetches /api/shop/state, renders 5 shop tabs, handles purchases.
   ══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────────────
    let _shops        = {};   // raw shop data from API
    let _pet          = {};   // { name, level, spendable_xp, xp_into_level, xp_for_next }
    let _activeTab    = 'keys';
    let _soldItems    = {};   // { shopId:slot -> true } — items purchased this session
    let _countdownInt = null;

    // Shop display order
    const SHOP_ORDER = ['keys', 'chests', 'potions', 'rings', 'equipment', 'weapons'];

    // Emoji icons for each shop tab
    const SHOP_ICONS = {
        keys:      '<img src="/static/Emojis/Shop/keystore.png" class="sh-tab-icon" alt="">',
        chests:    '<img src="/static/Emojis/Shop/openchest.png" class="sh-tab-icon" alt="">',
        potions:   '<img src="/static/Emojis/Shop/potionstore.png" class="sh-tab-icon" alt="">',
        rings:     '<img src="/static/Emojis/Shop/ringstore.png" class="sh-tab-icon" alt="">',
        equipment: '<img src="/static/Emojis/Shop/armorstore.png" class="sh-tab-icon" alt="">',
        weapons:   '<img src="/static/Emojis/Shop/weaponstore.png" class="sh-tab-icon" alt="">',
    };

    // ── Image helpers ──────────────────────────────────────────────────────────
    function itemImgSrc(emojiFile) {
        if (!emojiFile) return '';
        return `/static/Emojis/Pets/${emojiFile}`;
    }
    function skullSrc(num) { return `/static/Emojis/Skulls/${num}.png`; }
    function shopSignSrc(open) {
        return open ? '/static/Emojis/Shop/open.png' : '/static/Emojis/Shop/close.png';
    }
    function soldStampSrc() { return '/static/Emojis/Shop/sold.png'; }

    // ── XP bar ─────────────────────────────────────────────────────────────────
    function updateXPBar(pet) {
        if (!pet) return;
        const el   = document.getElementById('sh-xp-value');
        const prog = document.getElementById('sh-xp-progress');
        const next = document.getElementById('sh-xp-next-label');
        const name = document.getElementById('sh-pet-name');

        if (el)   el.textContent = `${fmtNum(pet.spendable_xp)} XP`;
        if (name) name.textContent = pet.name ? `🐾 ${esc(pet.name)} · Lv ${pet.level}` : '';

        const xpInto = pet.xp_into_level || 0;
        const xpNext = pet.xp_for_next   || 1;
        const pct    = Math.min(100, Math.round((xpInto / xpNext) * 100));
        if (prog) prog.style.width = `${pct}%`;
        if (next) next.textContent = `${fmtNum(xpInto)} / ${fmtNum(xpNext)} to Lv ${(pet.level || 1) + 1}`;
    }

    // ── Tabs ───────────────────────────────────────────────────────────────────
    function renderTabs() {
        const container = document.getElementById('sh-tabs');
        if (!container) return;
        container.innerHTML = SHOP_ORDER.map(id => {
            const isChestTab = (id === 'chests');
            const shop  = _shops[id] || {};
            const state = shop.state  || {};
            const isOpen  = isChestTab ? true : state.open;
            const label   = isChestTab ? 'Catacomb Cache' : (shop.label || id);
            const active  = (id === _activeTab) ? 'active' : '';
            const clsd    = !isOpen ? 'closed' : '';
            const dot     = isOpen  ? 'open'   : 'closed';
            return `<button class="sh-tab ${active} ${clsd}" onclick="shSwitchTab('${id}')">
                        <span class="sh-tab-dot ${dot}"></span>
                        ${SHOP_ICONS[id]} ${esc(label)}
                    </button>`;
        }).join('');
    }

    // ── Panels ─────────────────────────────────────────────────────────────────
    function renderPanels() {
        const container = document.getElementById('sh-panels');
        if (!container) return;
        container.innerHTML = SHOP_ORDER.map(id => {
            const activeClass = (id === _activeTab) ? 'active' : '';
            if (id === 'chests') {
                return `<div class="sh-panel ${activeClass}" id="sh-panel-chests">
                            ${renderChestsPanel()}
                        </div>`;
            }
            const shop   = _shops[id] || {};
            const state  = shop.state  || {};
            const isOpen = state.open;
            return `<div class="sh-panel ${activeClass}" id="sh-panel-${id}">
                        ${renderShopCard(id, shop, state, isOpen)}
                    </div>`;
        }).join('');
    }

    function renderShopCard(id, shop, state, isOpen) {
        const closedClass  = isOpen ? '' : 'closed-card';
        const skull        = shop.skull;            // null when closed
        const statusClass  = isOpen ? 'open'   : 'closed';
        const statusText   = isOpen ? '🟢 OPEN' : '🔴 CLOSED';
        const cycleText    = _cycleText(id, state);
        const countdownSecs = state.countdown || 0;

        const countdownHtml = (id !== 'keys' && countdownSecs > 0)
            ? `<div class="sh-countdown" id="sh-cd-${id}">
                   ${isOpen ? 'Closes in' : 'Opens in'}:
                   <span id="sh-cd-val-${id}">${fmtCountdown(countdownSecs)}</span>
                   <small style="color:var(--text-secondary);margin-left:4px">(${cycleText})</small>
               </div>`
            : (id === 'keys'
                ? `<div class="sh-countdown"><span>Always open — never closes</span></div>`
                : '');

        // ── Keeper row — only shown when open ─────────────────────────────────
        const keeperHtml = skull
            ? `<div class="sh-keeper-row">
                   <img class="sh-keeper-avatar"
                        src="${skullSrc(skull)}"
                        alt="Shopkeeper"
                        onerror="this.style.display='none'">
                   <div class="sh-keeper-info">
                       <h6 class="sh-keeper-name">Keeper #${skull}</h6>
                       <p class="sh-keeper-desc">${esc(shop.desc || '')}</p>
                       <span class="sh-status-badge ${statusClass}">${statusText}</span>
                       ${countdownHtml}
                   </div>
               </div>`
            : `<div class="sh-keeper-row">
                   <div class="sh-keeper-absent">
                       <span style="font-size:2rem;opacity:0.35">💀</span>
                   </div>
                   <div class="sh-keeper-info">
                       <p class="sh-keeper-desc" style="color:var(--text-secondary)">
                           The keeper has stepped out. Check back when the shop opens.
                       </p>
                       <span class="sh-status-badge ${statusClass}">${statusText}</span>
                       ${countdownHtml}
                   </div>
               </div>`;

        const itemsHtml = isOpen
            ? renderItems(id, shop.items || [])
            : renderClosedOverlay(id, state);

        return `
        <div class="sh-card ${closedClass}">
            <div class="sh-card-header">
                <h5>${SHOP_ICONS[id]} ${esc(shop.label || id)}</h5>
                <span class="sh-status-badge ${statusClass}">${statusText}</span>
                <img src="${shopSignSrc(isOpen)}" alt="${isOpen ? 'Open' : 'Closed'}"
                     style="width:28px;height:28px;object-fit:contain;margin-left:auto"
                     onerror="this.style.display='none'">
            </div>
            <div class="sh-card-body">
                ${keeperHtml}
                ${itemsHtml}
            </div>
        </div>`;
    }

    function _cycleText(id, state) {
        if (id === 'keys')           return 'always open';
        if (state.cycle === '1h')    return 'alternates hourly';
        if (state.cycle === '2h')    return 'alternates every 2h';
        return '';
    }

    function renderClosedOverlay(id, state) {
        const countdown = state.countdown || 0;
        return `
        <div class="sh-closed-overlay">
            <img class="sh-closed-sign" src="/static/Emojis/Shop/close.png" alt="Closed"
                 onerror="this.style.display='none'">
            <h5 style="font-family:'Orbitron',sans-serif;color:#e74c3c;margin:0.3rem 0">SHOP CLOSED</h5>
            <p>This shop is currently updating its stock.</p>
            ${countdown > 0
                ? `<p style="color:var(--gold-secondary)">Opens in:
                       <strong id="sh-cd-val-${id}-ov">${fmtCountdown(countdown)}</strong>
                   </p>`
                : ''}
        </div>`;
    }

    function renderItems(shopId, items) {
        if (!items || items.length === 0) {
            return `<div class="sh-loading" style="padding:1.5rem"><p>No items available.</p></div>`;
        }
        const spendable = (_pet && _pet.spendable_xp) || 0;
        const isKeys    = (shopId === 'keys');
        const maxBuy    = isKeys ? 999 : 5;

        const cards = items.map(item => {
            const soldKey    = `${shopId}:${item.slot}`;
            const bought    = item.purchases_today || 0;
            // Keys are never "sold out"; other shops cap at 5
            const isSold     = !isKeys && bought >= maxBuy;
            const canAfford  = spendable >= item.cost;
            const soldClass  = isSold ? 'sold-out' : (!canAfford ? 'no-xp' : '');
            const rarityClass = 'rarity-' + (item.rarity || 'common').toLowerCase();
            const imgSrc     = itemImgSrc(item.emoji_file);
            const owned      = item.owned || 0;

            // Show multiplier + bought count for all items
            const metaHtml = `<div class="sh-key-mult" id="sh-mult-${shopId}-${item.slot}">${esc(item.multiplier || '×1')}</div>
                              <div class="sh-key-bought" id="sh-bought-${shopId}-${item.slot}">Bought: ${bought}${isKeys ? ' today' : ''}</div>`;

            let btnHtml;
            if (isSold) {
                btnHtml = `<button class="sh-item-buy-btn" disabled>Sold Out</button>`;
            } else if (!canAfford) {
                btnHtml = `<button class="sh-item-buy-btn" disabled
                            title="Need ${fmtNum(item.cost)} XP">Not enough XP</button>`;
            } else {
                btnHtml = `<button class="sh-item-buy-btn"
                            onclick="shBuy('${esc(shopId)}', ${item.slot}, this)">Buy</button>`;
            }

            const soldStamp = isSold
                ? `<img class="sh-sold-stamp" src="${soldStampSrc()}" alt="Sold"
                        onerror="this.style.display='none'">`
                : '';

            return `
            <div class="sh-item-card ${soldClass}" id="sh-item-${shopId}-${item.slot}">
                ${soldStamp}
                <img class="sh-item-img" src="${imgSrc}" alt="${esc(item.name)}"
                     onerror="this.src='/static/Emojis/Pets/Equipment/${esc(item.emoji_file||'')}';this.onerror=null;">
                <div class="sh-item-name">${esc(item.name)}</div>
                <div class="sh-item-rarity ${rarityClass}">${esc(item.rarity || '')}</div>
                <div class="sh-item-type">${esc(item.type || '')}</div>
                <div class="sh-item-price" id="sh-item-price-${shopId}-${item.slot}">${fmtNum(item.cost)} XP</div>
                <div class="sh-item-price-label">price</div>
                ${metaHtml}
                <div class="sh-item-owned">Owned: <span id="sh-owned-${shopId}-${item.slot}">${owned}</span></div>
                ${btnHtml}
            </div>`;
        }).join('');

        return `<div class="sh-items-grid">${cards}</div>`;
    }

    // ── Open Chests tab ─────────────────────────────────────────────────────────

    // Chest type metadata
    var _CHEST_TYPES = [
        { id:'chest1', label:'Chest 1', cost:'1\u00d7 Key1', items:'1 Common or Uncommon item', color:'#9e9e9e' },
        { id:'chest2', label:'Chest 2', cost:'1\u00d7 Key2', items:'1 Rare item',              color:'#4caf50' },
        { id:'chest3', label:'Chest 3', cost:'1\u00d7 Key3', items:'1 Epic item',              color:'#2196f3' },
        { id:'chest4', label:'Chest 4', cost:'1\u00d7 Key1 + Key2 + Key3', items:'1 picked type + 1 bonus', color:'#ff9800' },
    ];
    var _ITEM_TYPES = ['Material','Gem','Monster','Potion','Ring','Helmet','Armor','Boots','Shield','Dagger','Katana','Sword','Axe','Hammer','Bow'];
    var _selChest = '';
    var _selType  = '';

    function _chestKeyCount(name) {
        var shop = _shops['keys'] || {};
        var item = (shop.items || []).find(function(i){ return i.name === name; });
        return (item && item.owned) || 0;
    }

    function renderChestsPanel() {
        var k1 = _chestKeyCount('Key1'), k2 = _chestKeyCount('Key2'), k3 = _chestKeyCount('Key3');

        var keyBadges = '';
        if (k1 || k2 || k3) {
            var kdata = [
                { n:'Key1', c:k1, f:'Key1.png' },
                { n:'Key2', c:k2, f:'Key2.png' },
                { n:'Key3', c:k3, f:'Key3.png' },
            ];
            var badges = '';
            kdata.forEach(function(kv){
                if (kv.c > 0) {
                    badges += '<div class="sh-key-badge">' +
                        '<img src="/static/Emojis/Pets/Equipment/'+kv.f+'" onerror="this.style.display=\'none\'">' +
                        '<span class="sh-key-badge-count">\u00d7'+kv.c+'</span>' +
                        '<span class="sh-key-badge-name">'+kv.n+'</span></div>';
                }
            });
            if (badges) keyBadges = '<div class="sh-chest-keys-bar"><div class="sh-chest-section-label">\ud83d\uddff Your Keys</div><div class="sh-chest-keys-row">'+badges+'</div></div>';
        }

        var chestCards = _CHEST_TYPES.map(function(c){
            var costHtml = esc(c.cost)
                .replace(/Key1/g,'<img src="/static/Emojis/Pets/Equipment/Key1.png" style="width:14px;height:14px;vertical-align:middle"> Key1')
                .replace(/Key2/g,'<img src="/static/Emojis/Pets/Equipment/Key2.png" style="width:14px;height:14px;vertical-align:middle"> Key2')
                .replace(/Key3/g,'<img src="/static/Emojis/Pets/Equipment/Key3.png" style="width:14px;height:14px;vertical-align:middle"> Key3');
            return '<div class="sh-chest-card" id="sh-chest-'+c.id+'" onclick="shSelectChest(\''+c.id+'\')" style="border-color:'+c.color+'40">'+
                '<img src="/static/Emojis/Pets/Equipment/'+c.id+'.png" class="sh-chest-card-img" onerror="this.style.display=\'none\'">'+
                '<div class="sh-chest-card-label" style="color:'+c.color+'">'+esc(c.label)+'</div>'+
                '<div class="sh-chest-card-cost">'+costHtml+'</div>'+
                '<div class="sh-chest-card-items">'+esc(c.items)+'</div></div>';
        }).join('');

        var typeChips = _ITEM_TYPES.map(function(t){
            return '<div class="sh-type-chip" id="sh-type-'+t+'" onclick="shSelectChest4Type(\''+t+'\')">'+esc(t)+'</div>';
        }).join('');

        return '<div class="sh-card">'+
            '<div class="sh-card-header"><h5>\ud83c\udf81 Catacomb Cache</h5></div>'+
            '<div class="sh-card-body">'+
            '<div class="sh-chest-desc">Use keys to open chests and earn items. Keys are earned from Play, Mission, and Dungeon Crawl activities.</div>'+
            keyBadges+
            '<div class="sh-chest-grid">'+chestCards+'</div>'+
            '<div id="sh-chest-type-row" style="display:none" class="sh-chest-type-row">'+
            '<label class="sh-chest-section-label">Select guaranteed item type (Chest 4)</label>'+
            '<div class="sh-type-chips">'+typeChips+'</div></div>'+
            '<div id="sh-chest-amt-row" class="sh-chest-amt-row">'+
            '<label class="sh-chest-section-label">Amount to open</label>'+
            '<input type="number" class="sh-amt-input" id="sh-chest-amount" min="1" max="10" value="1">'+
            '</div>'+
            '<button class="sh-open-btn" onclick="shOpenChest()">\ud83d\udce6 Open Chest</button>'+
            '<div id="sh-chest-result" class="sh-chest-result"></div>'+
            '</div></div>';
    }

    window.shSelectChest = function(c) {
        _selChest = c; _selType = '';
        _CHEST_TYPES.forEach(function(x){
            var el = document.getElementById('sh-chest-'+x.id);
            if (el) {
                el.style.borderColor = x.id === c ? 'var(--gold-primary)' : x.color+'40';
                el.style.boxShadow   = x.id === c ? '0 0 8px var(--gold-glow)' : '';
            }
        });
        var typeRow = document.getElementById('sh-chest-type-row');
        if (typeRow) typeRow.style.display = c === 'chest4' ? '' : 'none';
        var amtRow = document.getElementById('sh-chest-amt-row');
        if (amtRow) amtRow.style.display = c === 'chest4' ? 'none' : '';
        var result = document.getElementById('sh-chest-result');
        if (result) result.innerHTML = '';
    };

    window.shSelectChest4Type = function(t) {
        _selType = t;
        _ITEM_TYPES.forEach(function(x){
            var el = document.getElementById('sh-type-'+x);
            if (el) {
                el.style.borderColor = x === t ? 'var(--gold-primary)' : 'rgba(255,215,0,0.15)';
                el.style.boxShadow   = x === t ? '0 0 8px var(--gold-glow)' : '';
            }
        });
    };

    window.shOpenChest = async function() {
        if (!_selChest) { _showChestResult('Select a chest first.', false); return; }
        if (_selChest === 'chest4' && !_selType) { _showChestResult('Select an item type for Chest 4.', false); return; }
        var amtEl = document.getElementById('sh-chest-amount');
        var amt   = amtEl ? Math.max(1, parseInt(amtEl.value || '1', 10) || 1) : 1;
        var resultEl = document.getElementById('sh-chest-result');
        if (resultEl) resultEl.innerHTML = '<div style="color:var(--text-secondary)">Opening...</div>';

        var chestImg = '/static/Emojis/Pets/Equipment/'+_selChest+'.png';
        var chestColorMap = { chest1:'#9e9e9e', chest2:'#4caf50', chest3:'#2196f3', chest4:'#ff9800' };
        var chestColor = chestColorMap[_selChest] || '#ffd700';

        try {
            var res = await fetch('/api/pets/loot/open', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ chest:_selChest, amount:amt, selected_type:_selType||null })
            });
            var d = await res.json();
            if (res.ok && d.success) {
                var items = d.items || [];
                _showChestAnimation(chestImg, chestColor, items, function() {
                    var html = '<div class="sh-battle-card" style="border-color:rgba(255,215,0,0.4)">';
                    html += '<div style="font-family:\'Orbitron\',sans-serif;color:var(--gold-primary);font-size:0.85rem;margin-bottom:8px">\ud83d\udce6 Chest Opened!</div>';
                    html += '<div class="sh-chest-result-items">';
                    items.forEach(function(item){
                        var f = item.emoji_file || '';
                        var rcClass = 'rarity-'+(item.rarity||'Common').toLowerCase();
                        html += '<div class="sh-result-item">'+
                            '<img src="/static/Emojis/Pets/Equipment/'+f+'" style="width:28px;height:28px" onerror="this.style.display=\'none\'">'+
                            '<div><div class="fw-bold '+rcClass+'" style="font-size:0.78rem">'+esc(item.name)+'</div>'+
                            '<div style="font-size:0.65rem;color:var(--text-secondary)">'+(item.rarity||'Common')+'</div></div></div>';
                    });
                    html += '</div>';
                    if (d.messages && d.messages.length) {
                        html += '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:8px">'+esc(d.messages.join(', '))+'</div>';
                    }
                    html += '</div>';
                    if (resultEl) resultEl.innerHTML = html;
                    if (d.pet) {
                        _pet = d.pet;
                        updateXPBar(_pet);
                        _refreshAffordability();
                    }
                });
            } else {
                _showChestResult(d.detail || d.error || 'Failed', false);
            }
        } catch(e) {
            _showChestResult('Error: '+e.message, false);
        }
    };

    function _showChestResult(msg, ok) {
        var el = document.getElementById('sh-chest-result');
        if (!el) return;
        el.innerHTML = '<div style="color:'+(ok?'var(--gold-primary)':'#e74c3c')+'">'+esc(msg)+'</div>';
    }

    function _showChestAnimation(chestSrc, chestColor, items, callback) {
        var overlay = document.getElementById('sh-chest-anim-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'sh-chest-anim-overlay';
            overlay.className = 'sh-chest-anim-overlay';
            overlay.innerHTML = '<div class="sh-chest-anim-inner"><img id="sh-chest-anim-img" class="sh-chest-anim-img" src=""><div id="sh-chest-anim-items" class="sh-chest-anim-items"></div></div>';
            document.body.appendChild(overlay);
            overlay.addEventListener('click', function(){
                overlay.style.display = 'none';
                if (typeof callback === 'function') callback();
            });
        }
        var img = document.getElementById('sh-chest-anim-img');
        if (img) {
            img.src = chestSrc;
            img.style.display = 'block';
            img.style.animation = 'none';
            void img.offsetWidth;
            img.style.animation = 'sh-chest-zoom 0.6s ease forwards';
        }
        var itemsContainer = document.getElementById('sh-chest-anim-items');
        if (itemsContainer) {
            itemsContainer.innerHTML = '';
            itemsContainer.style.display = 'none';
        }
        overlay.style.display = 'flex';
        setTimeout(function(){
            if (img) img.style.display = 'none';
            if (itemsContainer) {
                itemsContainer.style.display = 'flex';
                itemsContainer.innerHTML = items.map(function(item){
                    var f = item.emoji_file || '';
                    var rc = 'rarity-'+(item.rarity||'Common').toLowerCase();
                    return '<div class="sh-anim-item"><img src="/static/Emojis/Pets/Equipment/'+f+'" style="width:32px;height:32px" onerror="this.style.display=\'none\'"><div class="'+rc+'" style="font-size:0.72rem">'+esc(item.name)+'</div></div>';
                }).join('');
            }
            setTimeout(function(){
                overlay.style.display = 'none';
                if (typeof callback === 'function') callback();
            }, 1000);
        }, 700);
    }

    // ── Tab switching ──────────────────────────────────────────────────────────
    window.shSwitchTab = function (id) {
        _activeTab = id;
        document.querySelectorAll('.sh-tab').forEach((el, i) => {
            const tid   = SHOP_ORDER[i];
            const isChestTab = tid === 'chests';
            const state = ((_shops[tid] || {}).state || {});
            const clsd  = !isChestTab && !state.open ? 'closed' : '';
            el.className = `sh-tab ${clsd} ${tid === id ? 'active' : ''}`;
        });
        SHOP_ORDER.forEach(tid => {
            const panel = document.getElementById(`sh-panel-${tid}`);
            if (panel) panel.className = `sh-panel ${tid === id ? 'active' : ''}`;
        });
    };

    // ── Purchase ───────────────────────────────────────────────────────────────
    window.shBuy = async function (shopId, slot, btnEl) {
        if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Buying…'; }
        try {
            const r = await apiFetch('/api/shop/buy', 'POST', { shop_id: shopId, slot });
            if (r.ok) {
                // Update pet XP
                if (_pet) {
                    _pet.spendable_xp  = r.new_spendable_xp;
                    _pet.level         = r.new_level;
                    _pet.xp_into_level = r.new_xp_into_level;
                    _pet.xp_for_next   = r.new_xp_for_next;
                }

                const card = document.getElementById(`sh-item-${shopId}-${slot}`);

                if (shopId === 'keys') {
                    // ── Keys/Chests: update price + multiplier in-place, re-enable button ──
                    const priceEl  = document.getElementById(`sh-item-price-${shopId}-${slot}`);
                    const multEl   = document.getElementById(`sh-mult-${shopId}-${slot}`);
                    const boughtEl = document.getElementById(`sh-bought-${shopId}-${slot}`);
                    const ownedEl  = document.getElementById(`sh-owned-${shopId}-${slot}`);

                    if (priceEl)  priceEl.textContent  = `${fmtNum(r.next_cost)} XP`;
                    if (multEl)   multEl.textContent   = r.next_multiplier || '';
                    if (boughtEl) boughtEl.textContent = `Bought: ${r.purchases_today} today`;
                    if (ownedEl)  ownedEl.textContent  = String(parseInt(ownedEl.textContent || '0') + 1);

                    // Re-enable button (or disable if can't afford next price)
                    if (btnEl) {
                        const canAffordNext = (_pet.spendable_xp || 0) >= r.next_cost;
                        btnEl.disabled    = !canAffordNext;
                        btnEl.textContent = canAffordNext ? 'Buy' : 'Not enough XP';
                        if (!canAffordNext && card) card.classList.add('no-xp');
                        else if (card)              card.classList.remove('no-xp');
                    }

                    toast(`Purchased ${r.item_name}! (-${fmtNum(r.cost)} XP)`, 'success');

                } else {
                    // ── Other shops: update price in-place or mark sold-out ────
                    const isNowSold = (r.purchases_today || 0) >= 5;
                    if (isNowSold) {
                        _soldItems[`${shopId}:${slot}`] = true;
                        if (card) {
                            card.classList.add('sold-out');
                            const btn = card.querySelector('.sh-item-buy-btn');
                            if (btn) { btn.disabled = true; btn.textContent = 'Sold Out'; }
                            if (!card.querySelector('.sh-sold-stamp')) {
                                const stamp = document.createElement('img');
                                stamp.className = 'sh-sold-stamp';
                                stamp.src = soldStampSrc();
                                stamp.alt = 'Sold';
                                stamp.onerror = function() { this.style.display = 'none'; };
                                card.appendChild(stamp);
                            }
                        }
                    } else {
                        // Update price + multiplier in-place
                        const priceEl  = document.getElementById(`sh-item-price-${shopId}-${slot}`);
                        const multEl   = document.getElementById(`sh-mult-${shopId}-${slot}`);
                        const boughtEl = document.getElementById(`sh-bought-${shopId}-${slot}`);
                        if (priceEl)  priceEl.textContent  = `${fmtNum(r.next_cost)} XP`;
                        if (multEl)   multEl.textContent   = r.next_multiplier || '';
                        if (boughtEl) boughtEl.textContent = `Bought: ${r.purchases_today}`;
                        if (btnEl) {
                            const canAffordNext = (_pet.spendable_xp || 0) >= r.next_cost;
                            btnEl.disabled    = !canAffordNext;
                            btnEl.textContent = canAffordNext ? 'Buy' : 'Not enough XP';
                            if (!canAffordNext && card) card.classList.add('no-xp');
                            else if (card)              card.classList.remove('no-xp');
                        }
                    }
                    // Increment owned count (works for both sold-out and not-sold-out)
                    const ownedEl = document.getElementById(`sh-owned-${shopId}-${slot}`);
                    if (ownedEl) ownedEl.textContent = String(parseInt(ownedEl.textContent || '0') + 1);
                    toast(`Purchased ${r.item_name}! (-${fmtNum(r.cost)} XP)`, 'success');
                }

                updateXPBar(_pet);
                _refreshAffordability();

            } else {
                if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Buy'; }
                toast(r.error || 'Purchase failed', 'error');
            }
        } catch (e) {
            if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Buy'; }
            toast('Network error', 'error');
        }
    };

    function _refreshAffordability() {
        const spendable = (_pet && _pet.spendable_xp) || 0;
        document.querySelectorAll('.sh-item-card').forEach(card => {
            if (card.classList.contains('sold-out')) return;
            const btn = card.querySelector('.sh-item-buy-btn');
            if (!btn || btn.disabled) return;
            // Read cost from the price element (may have been updated for keys)
            const cardId  = card.id || '';                        // sh-item-{shopId}-{slot}
            const parts   = cardId.split('-');
            const shopId  = parts[2];
            const slot    = parts[3];
            const priceEl = shopId && slot
                ? document.getElementById(`sh-item-price-${shopId}-${slot}`)
                : card.querySelector('.sh-item-price');
            if (!priceEl) return;
            const cost = parseInt(priceEl.textContent.replace(/[^0-9]/g, ''));
            if (isNaN(cost)) return;
            if (spendable < cost) {
                btn.disabled = true;
                btn.textContent = 'Not enough XP';
                card.classList.add('no-xp');
            } else {
                // Re-enable if they had previously been disabled for XP and now can afford
                if (card.classList.contains('no-xp')) {
                    card.classList.remove('no-xp');
                    btn.disabled = false;
                    btn.textContent = 'Buy';
                }
            }
        });
    }

    // ── Countdown ticker ───────────────────────────────────────────────────────
    // Tracks seconds remaining per shop locally — only triggers a full reload
    // when a shop actually transitions (countdown hits 0).
    // Multiple shops hitting 0 in the same tick are batched into one reload.
    function startCountdowns() {
        if (_countdownInt) clearInterval(_countdownInt);

        const remaining = {};
        let reloadTimer = null;

        SHOP_ORDER.forEach(id => {
            const state = (_shops[id] || {}).state || {};
            remaining[id] = state.countdown || 0;
        });

        _countdownInt = setInterval(() => {
            let shouldReload = false;

            SHOP_ORDER.forEach(id => {
                if (id === 'keys') return;
                const wasPositive = remaining[id] > 0;
                if (remaining[id] > 0) remaining[id]--;

                const secs = remaining[id];
                ['', '-ov'].forEach(suffix => {
                    const el = document.getElementById(`sh-cd-val-${id}${suffix}`);
                    if (el) el.textContent = fmtCountdown(secs);
                });

                if (wasPositive && secs <= 0) shouldReload = true;
            });

            if (shouldReload && reloadTimer === null) {
                reloadTimer = setTimeout(() => {
                    reloadTimer = null;
                    loadShops(false);
                }, 500);
            }
        }, 1000);
    }

    // ── Data loading ───────────────────────────────────────────────────────────
    async function loadShops(showLoader = true) {
        if (showLoader) {
            const loading = document.getElementById('sh-loading');
            const main    = document.getElementById('sh-main');
            if (loading) loading.style.display = 'block';
            if (main)    main.style.display    = 'none';
        }

        try {
            const data = await apiFetch('/api/shop/state');
            if (data.error) { showLoginPrompt(data.error); return; }

            _shops = data.shops || {};
            _pet   = data.pet   || {};

            _rebuildSoldItems();
            updateXPBar(_pet);
            renderTabs();
            renderPanels();

            const loading = document.getElementById('sh-loading');
            const main    = document.getElementById('sh-main');
            if (loading) loading.style.display = 'none';
            if (main)    main.style.display    = 'block';

            startCountdowns();

        } catch (e) {
            const loading = document.getElementById('sh-loading');
            if (loading) loading.innerHTML =
                `<p style="color:#e74c3c">Failed to load shops. Please refresh.</p>`;
        }
    }

    function _rebuildSoldItems() {
        _soldItems = {};
        SHOP_ORDER.forEach(id => {
            const shop = _shops[id] || {};
            (shop.items || []).forEach(item => {
                if (item.purchased) {
                    _soldItems[`${id}:${item.slot}`] = true;
                }
            });
        });
    }

    function showLoginPrompt(msg) {
        const loading = document.getElementById('sh-loading');
        if (!loading) return;
        if (msg === 'Not logged in' || msg === 'No user ID') {
            loading.innerHTML = `
            <p style="color:var(--text-secondary)">
                <a href="/api/auth/login" style="color:var(--gold-primary)">Log in with Discord</a>
                to browse the shops.
            </p>`;
        } else {
            loading.innerHTML = `<p style="color:#e74c3c">${esc(msg)}</p>`;
        }
    }

    // ── Utilities ──────────────────────────────────────────────────────────────
    async function apiFetch(url, method = 'GET', body = null) {
        const opts = { method, headers: {} };
        if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
        const r = await fetch(url, opts);
        return await r.json();
    }

    function esc(s) {
        return String(s || '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function fmtNum(n) { return Number(n || 0).toLocaleString(); }

    function fmtCountdown(secs) {
        if (secs <= 0) return '0:00';
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        const s = secs % 60;
        if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
        return `${m}:${String(s).padStart(2,'0')}`;
    }

    let _toastTimer = null;
    function toast(msg, type = 'success') {
        const el = document.getElementById('sh-toast');
        if (!el) return;
        el.textContent = msg;
        el.className   = type;
        el.style.display = 'block';
        clearTimeout(_toastTimer);
        _toastTimer = setTimeout(() => { el.style.display = 'none'; }, 4000);
    }

    // ── Boot ───────────────────────────────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => loadShops(true));
    } else {
        loadShops(true);
    }

})();
