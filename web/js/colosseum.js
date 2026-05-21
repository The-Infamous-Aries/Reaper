/* ── Colosseum JS ─────────────────────────────────────────────────────────── */
(function () {
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
var _state       = null;   // last fetched /api/colosseum/state
var _pollTimer   = null;
var _cdTimer     = null;
var _myUserId    = null;
var _panelOpen   = false;

// ── DOM helpers ───────────────────────────────────────────────────────────────
function $c(id)   { return document.getElementById(id); }
function esc(s)   { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function petImg(sp) { return '/static/Emojis/Pets/' + (sp||'Cat') + '.png'; }
function elemImg(e) { return '/static/Emojis/Pets/Deco/' + (e ? (e.charAt(0).toUpperCase()+e.slice(1)) : 'Basic') + '.png'; }

function fmtTime(secs) {
    secs = Math.max(0, Math.floor(secs));
    var h = Math.floor(secs / 3600);
    var m = Math.floor((secs % 3600) / 60);
    var s = secs % 60;
    if (h > 0) return h + 'h ' + m + 'm';
    if (m > 0) return m + 'm ' + s + 's';
    return s + 's';
}

function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n/1e6).toFixed(1) + 'm';
    if (n >= 1e3) return (n/1e3).toFixed(1) + 'k';
    return n.toLocaleString();
}

// ── Emoji helpers ─────────────────────────────────────────────────────────────
var KEY_IMG   = {
    Key1: '/static/Emojis/Pets/Equipment/Key1.png',
    Key2: '/static/Emojis/Pets/Equipment/Key2.png',
    Key3: '/static/Emojis/Pets/Equipment/Key3.png',
};
var KEY_NAMES  = { Key1: 'Key 1', Key2: 'Key 2', Key3: 'Key 3' };

function keyEmoji(k) {
    var src = KEY_IMG[k];
    if (!src) return '🗝️';
    return '<img src="' + src + '" style="height:14px;vertical-align:middle;margin-right:2px" onerror="this.style.display=\'none\'">';
}
function keyLabel(k)    { return KEY_NAMES[k]  || k; }
function potionEmoji(p) {
    // Map potion name to a sensible emoji
    var map = {
        fire_potion: '🔥', water_potion: '💧', electric_potion: '⚡',
        ice_potion: '❄️', air_potion: '🌬️', rock_potion: '🪨',
        plant_potion: '🌿', magic_potion: '🔮', holy_potion: '✨',
        necro_potion: '💀', psychic_potion: '🧠', fighting_potion: '👊',
        health_potion: '❤️', lesser_health_potion: '💊', greater_health_potion: '💖',
        xp_potion: '⭐', lesser_xp_potion: '🌟', mega_potion: '💎',
        att_potion: '⚔️', def_potion: '🛡️', dex_potion: '🏃', int_potion: '🧬',
        hap_potion: '😊', ene_potion: '⚡', luck_potion: '🍀',
        s1_potion: '🌀', s2_potion: '🌀', s3_potion: '🌀',
        basic_potion: '🧪'
    };
    var key = (p || '').toLowerCase().replace(/\s+/g, '_');
    return map[key] || '🧪';
}
function potionLabel(p) {
    // Convert snake_case to Title Case
    return (p || '').replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}
window._colosseumOpen = function() {
    // Don't open the Colosseum panel while a battle is active
    if (typeof window._arenaIsInBattle === 'function' && window._arenaIsInBattle()) return;
    _panelOpen = true;
    var panel = document.getElementById('shared-panel-area');
    if (!panel) return;
    panel.innerHTML = _buildLoadingPanel();
    _fetchState();
};

function _buildLoadingPanel() {
    return '<div class="arena-panel col-panel"><div class="col-panel-header"><span class="col-panel-icon">🏛️</span><span class="col-panel-title">Colosseum</span></div>' +
           '<div class="text-center py-4"><div class="spinner-border" style="color:var(--gold-primary)" role="status"></div>' +
           '<p class="mt-2" style="color:var(--text-secondary);font-size:0.82rem">Loading Colosseum...</p></div></div>';
}

// ── Fetch state ───────────────────────────────────────────────────────────────
function _fetchState() {
    fetch('/api/colosseum/state')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            _state = d;
            // Never overwrite the panel while a battle or game is active
            if (_panelOpen && !(typeof window._arenaIsInBattle === 'function' && window._arenaIsInBattle())) {
                _renderPanel(d);
            }
            _updateHeaderCard(d);
        })
        .catch(function(e) {
            if (_panelOpen && !(typeof window._arenaIsInBattle === 'function' && window._arenaIsInBattle())) {
                var panel = document.getElementById('shared-panel-area');
                if (panel) panel.innerHTML = '<div class="arena-panel col-panel"><p style="color:#e74c3c;text-align:center;padding:20px">Failed to load Colosseum.</p></div>';
            }
        });
}

// ── Update the enriched header card on the arena page ────────────────────────
function _updateHeaderCard(d) {
    var members  = d.members  || [];
    var log      = d.log      || [];
    var nextIn   = d.next_battle_in || 0;
    var roundNum = d.round_num || 0;

    // Fighter count
    var mc = document.getElementById('col-stat-fighters');
    if (mc) mc.textContent = members.length || '0';

    // Round number
    var rc = document.getElementById('col-stat-round');
    if (rc) rc.textContent = roundNum > 0 ? '#' + roundNum : '—';

    // Next battle countdown (live ticker handled by _startCountdown)
    var nb = document.getElementById('col-stat-next');
    if (nb) nb.textContent = nextIn > 0 ? fmtTime(nextIn) : '⚔️ Soon!';

    // Last winner from log
    var lw = document.getElementById('col-stat-last-winner');
    if (lw) {
        var lastEntry = log.length > 0 ? log[0] : null;
        lw.textContent = lastEntry ? lastEntry.winner_name : '—';
    }

    // Mini fighter avatars (show up to 6, then +N)
    var avatarWrap = document.getElementById('col-card-avatars');
    if (avatarWrap) {
        var MAX_SHOW = 6;
        var html = '';
        var shown = members.slice(0, MAX_SHOW);
        var extra = members.length - MAX_SHOW;
        // Render in reverse so first fighter is on top (flex row-reverse)
        shown.slice().reverse().forEach(function(m) {
            var src = m.avatar || ('/static/Emojis/Pets/' + (m.pet_species || 'Cat') + '.png');
            html += '<img class="col-card-avatar" src="' + esc(src) + '" ' +
                    'title="' + esc(m.pet_name) + ' (' + esc(m.username) + ')" ' +
                    'onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">';
        });
        if (extra > 0) {
            html += '<div class="col-card-avatar-more">+' + extra + '</div>';
        }
        avatarWrap.innerHTML = html;
    }

    // Live badge
    var lb = document.getElementById('col-live-badge');
    if (lb) lb.style.display = members.length > 0 ? '' : 'none';

    // Legacy IDs (kept for backward compat)
    var legacyMc = document.getElementById('col-member-count');
    if (legacyMc) legacyMc.textContent = members.length + ' fighters';
    var legacyNb = document.getElementById('col-next-battle');
    if (legacyNb) legacyNb.textContent = nextIn > 0 ? 'Next: ' + fmtTime(nextIn) : 'Battle imminent!';
}



// ── Main panel renderer ───────────────────────────────────────────────────────
function _renderPanel(d) {
    var panel = document.getElementById('shared-panel-area');
    if (!panel) return;

    var myData   = d.my_data || null;
    var inColo   = !!myData;
    var members  = d.members  || [];
    var log      = d.log      || [];
    var nextIn   = d.next_battle_in || 0;
    var roundNum = d.round_num || 0;

    var html = '<div class="arena-panel col-panel">';

    // ── Header ────────────────────────────────────────────────────────────────
    html += '<div class="col-panel-header">' +
            '<span class="col-panel-icon">🏛️</span>' +
            '<div>' +
            '<div class="col-panel-title">Colosseum</div>' +
            '<div class="col-panel-sub">' + members.length + ' fighters · Round ' + roundNum + '</div>' +
            '</div>' +
            '<div class="col-countdown" id="col-cd-display">' + (nextIn > 0 ? fmtTime(nextIn) : '⚔️ Soon!') + '</div>' +
            '</div>';

    // ── Join / Leave + Claim ──────────────────────────────────────────────────
    html += '<div class="col-action-row">';
    if (!inColo) {
        html += '<button class="col-btn col-btn-join" onclick="window._colosseumJoin()">⚔️ Enter Colosseum</button>';
    } else {
        var pendingXp      = myData.pending_xp || 0;
        var pendingKeys    = JSON.parse(myData.pending_keys    || '[]');
        var pendingPotions = JSON.parse(myData.pending_potions || '[]');
        var hasPending     = pendingXp > 0 || pendingKeys.length > 0 || pendingPotions.length > 0;
        html += '<button class="col-btn col-btn-leave" onclick="window._colosseumLeave()">🚪 Leave</button>';
        if (hasPending) {
            var rewardBadges = '';
            if (pendingXp > 0) rewardBadges += '<span class="col-xp-badge">+' + fmtNum(pendingXp) + ' XP</span>';
            // Group keys by name and show counts: {emoji} Key1 - 2
            var keyCounts = {};
            pendingKeys.forEach(function(k) { keyCounts[k] = (keyCounts[k] || 0) + 1; });
            Object.keys(keyCounts).forEach(function(k) {
                var count = keyCounts[k];
                rewardBadges += '<span class="col-reward-badge col-key-badge">' + keyEmoji(k) + ' ' + keyLabel(k) + ' - ' + count + '</span>';
            });
            // Group potions by name and show counts
            var potionCounts = {};
            pendingPotions.forEach(function(p) { potionCounts[p] = (potionCounts[p] || 0) + 1; });
            Object.keys(potionCounts).forEach(function(p) {
                var count = potionCounts[p];
                rewardBadges += '<span class="col-reward-badge col-potion-badge">' + potionEmoji(p) + ' ' + potionLabel(p) + ' - ' + count + '</span>';
            });
            html += '<button class="col-btn col-btn-claim" onclick="window._colosseumClaim()" id="col-claim-btn">' +
                    '💰 Claim Rewards ' + rewardBadges +
                    '</button>';
        } else {
            html += '<button class="col-btn col-btn-claim col-btn-disabled" disabled>💰 No Rewards Yet</button>';
        }
    }
    html += '</div>';

    // ── My stats (if in Colosseum) ────────────────────────────────────────────
    if (inColo) {
        html += '<div class="col-my-stats">' +
                '<div class="col-stat-item"><span class="col-stat-label">Wins</span><span class="col-stat-val col-wins">' + (myData.wins||0) + '</span></div>' +
                '<div class="col-stat-item"><span class="col-stat-label">Losses</span><span class="col-stat-val col-losses">' + (myData.losses||0) + '</span></div>' +
                '<div class="col-stat-item"><span class="col-stat-label">Rounds</span><span class="col-stat-val">' + (myData.rounds||0) + '</span></div>' +
                '<div class="col-stat-item"><span class="col-stat-label">Pending XP</span><span class="col-stat-val col-pending">' + fmtNum(myData.pending_xp||0) + '</span></div>' +
                '</div>';
    }

    // ── Lifetime stats (always shown if we have them) ─────────────────────────
    var lifetime = d.lifetime || null;
    if (lifetime && (lifetime.wins > 0 || lifetime.losses > 0 || lifetime.rounds > 0)) {
        var ltWr = (lifetime.wins + lifetime.losses) > 0
            ? Math.round((lifetime.wins / (lifetime.wins + lifetime.losses)) * 100) : 0;
        html += '<div class="col-lifetime-stats">' +
                '<div class="col-lifetime-title">🏆 All-Time Colosseum Record</div>' +
                '<div class="col-lifetime-row">' +
                '<span class="col-lt-item"><span class="col-lt-label">Wins</span><span class="col-lt-val col-wins">' + (lifetime.wins||0) + '</span></span>' +
                '<span class="col-lt-item"><span class="col-lt-label">Losses</span><span class="col-lt-val col-losses">' + (lifetime.losses||0) + '</span></span>' +
                '<span class="col-lt-item"><span class="col-lt-label">Rounds</span><span class="col-lt-val">' + (lifetime.rounds||0) + '</span></span>' +
                '<span class="col-lt-item"><span class="col-lt-label">Win Rate</span><span class="col-lt-val">' + ltWr + '%</span></span>' +
                '<span class="col-lt-item"><span class="col-lt-label">XP Earned</span><span class="col-lt-val col-pending">' + fmtNum(lifetime.xp_earned||0) + '</span></span>' +
                '</div>' +
                '</div>';
    }

    // ── Claim result area ─────────────────────────────────────────────────────
    html += '<div id="col-claim-result" style="display:none" class="col-claim-result"></div>';

    // ── Active fighters grid ──────────────────────────────────────────────────
    html += '<div class="col-section-title">⚔️ Active Fighters (' + members.length + ')</div>';
    if (members.length === 0) {
        html += '<div class="col-empty">No fighters yet. Be the first to enter!</div>';
    } else {
        html += '<div class="col-fighters-grid" id="col-fighters-grid">';
        members.forEach(function(m) {
            var isMe = _myUserId && m.user_id === _myUserId;
            var winRate = m.rounds > 0 ? Math.round((m.wins / m.rounds) * 100) : 0;
            html += '<div class="col-fighter-card' + (isMe ? ' col-fighter-me' : '') + '">' +
                    '<div class="col-fighter-img-wrap">' +
                    '<img class="col-fighter-img" src="' + esc(petImg(m.pet_species)) + '" ' +
                    'onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'" alt="">' +
                    '<img class="col-fighter-elem" src="' + esc(elemImg(m.pet_element)) + '" ' +
                    'onerror="this.style.display=\'none\'" alt="" title="' + esc(m.pet_element) + '">' +
                    '</div>' +
                    '<div class="col-fighter-name">' + esc(m.pet_name) + (isMe ? ' <span class="col-you-badge">YOU</span>' : '') + '</div>' +
                    '<div class="col-fighter-owner">' + esc(m.username) + '</div>' +
                    '<div class="col-fighter-level">Lv.' + (m.pet_level||1) + '</div>' +
                    '<div class="col-fighter-record">' +
                    '<span class="col-w">' + (m.wins||0) + 'W</span>' +
                    '<span class="col-l">' + (m.losses||0) + 'L</span>' +
                    '<span class="col-wr">' + winRate + '%</span>' +
                    '</div>' +
                    '</div>';
        });
        html += '</div>';
    }

    // ── Round log ─────────────────────────────────────────────────────────────
    html += '<div class="col-section-title">📜 Recent Rounds</div>';
    if (log.length === 0) {
        html += '<div class="col-empty">No rounds yet. First battle starts in ' + fmtTime(nextIn) + '.</div>';
    } else {
        html += '<div class="col-log" id="col-log">';
        log.forEach(function(entry) {
            var ts = new Date(entry.ts * 1000);
            var timeStr = ts.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
            var isNpc   = entry.is_npc;
            var winnerIsA = entry.winner_id === entry.user_a_id;
            // Show the winner's XP gain (xp_a if A won, xp_b if B won)
            var winnerXp = winnerIsA ? entry.xp_a : entry.xp_b;
            html += '<div class="col-log-entry">' +
                    '<div class="col-log-meta">' +
                    '<span class="col-log-round">R' + entry.round_num + '</span>' +
                    '<span class="col-log-time">' + timeStr + '</span>' +
                    (isNpc ? '<span class="col-log-npc">vs NPC</span>' : '<span class="col-log-pvp">⚔️ PvP</span>') +
                    '</div>' +
                    '<div class="col-log-fighters">' +
                    '<span class="col-log-name' + (winnerIsA ? ' col-log-winner' : ' col-log-loser') + '">' + esc(entry.user_a_name) + '</span>' +
                    '<span class="col-log-vs">vs</span>' +
                    '<span class="col-log-name' + (!winnerIsA ? ' col-log-winner' : ' col-log-loser') + '">' + esc(entry.user_b_name) + '</span>' +
                    '</div>' +
                    '<div class="col-log-result">' +
                    '🏆 <strong>' + esc(entry.winner_name) + '</strong> wins' +
                    (winnerXp > 0 ? ' · <span style="color:var(--gold-primary)">+' + fmtNum(winnerXp) + ' XP</span>' : '') +
                    (entry.winner_key ? ' · ' + keyEmoji(entry.winner_key) + ' ' + keyLabel(entry.winner_key) : (!isNpc ? ' · 🗝️ Key' : '')) +
                    (!isNpc ? ' · 🧪🧪 Potions' : '') +
                    '</div>' +
                    '</div>';
        });
        html += '</div>';
    }

    html += '</div>'; // col-panel
    panel.innerHTML = html;

    // Start countdown ticker
    _startCountdown(nextIn);
}



// ── Countdown ticker ──────────────────────────────────────────────────────────
var _cdSecs = 0;
function _startCountdown(secs) {
    if (_cdTimer) clearInterval(_cdTimer);
    _cdSecs = secs;
    _cdTimer = setInterval(function() {
        _cdSecs = Math.max(0, _cdSecs - 1);
        // Panel countdown
        var el = document.getElementById('col-cd-display');
        if (el) el.textContent = _cdSecs > 0 ? fmtTime(_cdSecs) : '⚔️ Soon!';
        // Header card countdown
        var nb = document.getElementById('col-stat-next');
        if (nb) nb.textContent = _cdSecs > 0 ? fmtTime(_cdSecs) : '⚔️ Soon!';
        // Legacy
        var legNb = document.getElementById('col-next-battle');
        if (legNb) legNb.textContent = _cdSecs > 0 ? 'Next: ' + fmtTime(_cdSecs) : 'Battle imminent!';
        if (_cdSecs === 0) {
            setTimeout(_fetchState, 3000);
        }
    }, 1000);
}

// ── Actions ───────────────────────────────────────────────────────────────────
window._colosseumJoin = function() {
    fetch('/api/colosseum/join', {method:'POST', headers:{'Content-Type':'application/json'}})
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success) {
                _fetchState();
            } else {
                alert(d.detail || d.message || 'Failed to join');
            }
        })
        .catch(function(e) { alert('Error: ' + e.message); });
};

window._colosseumLeave = function() {
    if (!confirm('Leave the Colosseum? Your pending rewards will be lost.')) return;
    fetch('/api/colosseum/leave', {method:'POST', headers:{'Content-Type':'application/json'}})
        .then(function(r) { return r.json(); })
        .then(function(d) {
            _fetchState();
        })
        .catch(function(e) { alert('Error: ' + e.message); });
};

window._colosseumClaim = function() {
    var btn = $c('col-claim-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Claiming...'; }

    fetch('/api/colosseum/claim', {method:'POST', headers:{'Content-Type':'application/json'}})
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var res = $c('col-claim-result');
            if (res) {
                res.style.display = '';
                if (d.success) {
                    var parts = [];
                    if (d.xp_claimed > 0) parts.push('⭐ +' + fmtNum(d.xp_claimed) + ' XP');
                    if (d.keys_claimed && d.keys_claimed.length) {
                        // Group by key name and show counts
                        var kc = {};
                        d.keys_claimed.forEach(function(k) { kc[k] = (kc[k] || 0) + 1; });
                        Object.keys(kc).forEach(function(k) {
                            parts.push(keyEmoji(k) + ' ' + keyLabel(k) + ' - ' + kc[k]);
                        });
                    }
                    if (d.potions_claimed && d.potions_claimed.length) {
                        // Group by potion name and show counts
                        var pc = {};
                        d.potions_claimed.forEach(function(p) { pc[p] = (pc[p] || 0) + 1; });
                        Object.keys(pc).forEach(function(p) {
                            parts.push(potionEmoji(p) + ' ' + potionLabel(p) + ' - ' + pc[p]);
                        });
                    }
                    res.className = 'col-claim-result col-claim-success';
                    // Use innerHTML directly — parts contain <img> tags from keyEmoji(), do NOT esc()
                    res.innerHTML = '✅ Claimed: <strong>' + (parts.join(' · ') || 'Rewards applied!') + '</strong>';
                    if (d.level_change && d.level_change.new_level > d.level_change.old_level) {
                        res.innerHTML += ' 🎉 Level Up! ' + d.level_change.old_level + ' → ' + d.level_change.new_level;
                    }
                } else {
                    res.className = 'col-claim-result col-claim-error';
                    res.textContent = d.message || 'Claim failed.';
                }
            }
            // Refresh after short delay
            setTimeout(_fetchState, 1500);
        })
        .catch(function(e) {
            var res = $c('col-claim-result');
            if (res) {
                res.style.display = '';
                res.className = 'col-claim-result col-claim-error';
                res.textContent = 'Error: ' + e.message;
            }
            if (btn) { btn.disabled = false; btn.textContent = '💰 Claim Rewards'; }
        });
};

// ── Poll for updates while panel is open ──────────────────────────────────────
function _startPoll() {
    if (_pollTimer) clearInterval(_pollTimer);
    _pollTimer = setInterval(function() {
        if (_panelOpen) _fetchState();
    }, 15000);  // refresh every 15s
}

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
    // Resolve user identity
    fetch('/api/discord/me')
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(u) {
            if (u && u.id) _myUserId = String(u.id);
        })
        .catch(function() {});

    // Initial state fetch to populate the header card
    fetch('/api/colosseum/state')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            _state = d;
            _updateHeaderCard(d);
            // Start the countdown ticker from the initial fetch
            if (d.next_battle_in > 0) _startCountdown(d.next_battle_in);
        })
        .catch(function() {});

    _startPoll();
}

// ── Close panel when navigating away ─────────────────────────────────────────
document.addEventListener('dashboardPageLoaded', function(e) {
    if (e.detail && e.detail.page && !e.detail.page.includes('arena')) {
        _panelOpen = false;
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
        if (_cdTimer)   { clearInterval(_cdTimer);   _cdTimer   = null; }
    }
});

// ── Close panel when a battle starts so the poll never overwrites battle UI ──
document.addEventListener('arenaBattleStarted', function() {
    _panelOpen = false;
});

init();

})();
