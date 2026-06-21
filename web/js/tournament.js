/* ── Tournament JS ──────────────────────────────────────────────────────────── */
(function () {
'use strict';

// ── Helpers ───────────────────────────────────────────────────────────────────
if (typeof window._esc === 'undefined') {
    window._esc = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
const esc = window._esc;

const ELEM_COLORS = {
    fire:'#e74c3c',water:'#3498db',electric:'#f1c40f',ice:'#a8d8ea',
    plant:'#2ecc71',rock:'#95a5a6',air:'#bdc3c7',magic:'#9b59b6',
    holy:'#f9ca24',necro:'#6c5ce7',psychic:'#fd79a8',fighting:'#e17055',
    basic:'#ffd700'
};
function elemColor(e){ return ELEM_COLORS[(e||'basic').toLowerCase()]||'#ffd700'; }

function petImgUrl(sp){ return sp ? `/static/Emojis/Pets/${sp}.png` : '/static/Emojis/Pets/Deco/Basic.png'; }

const TIMER_LABELS = {
    instant:'Instant (after each match)',
    '1h':'1 Hour per round',
    '2h':'2 Hours per round',
    '6h':'6 Hours per round',
    '12h':'12 Hours per round',
    '24h':'24 Hours per round (1 round/day)',
};

// ── State ─────────────────────────────────────────────────────────────────────
let _ws              = null;
let _tournament      = null;    // currently viewed/active tournament detail
let _myUserId        = null;
let _petUsers        = [];      // cached list of users with pets
let _currentMatchId  = null;    // match the local user is currently fighting
let _matchBattle     = null;    // live battle state (same shape as arena _battle)
let _wsReady         = false;

// ── Initialisation ────────────────────────────────────────────────────────────
async function _init() {
    // Get current user
    try {
        const r = await fetch('/api/discord/user');
        if (r.ok) { const u = await r.json(); _myUserId = u.id || null; }
    } catch(_){}

    // Attach card click
    const card = document.getElementById('tournament-card');
    if (card) card.addEventListener('click', e => {
        if (e.target.closest('.tournament-option')) return;
        _showActiveList();
    });

    // Attach size-option clicks
    document.querySelectorAll('.tournament-option').forEach(opt => {
        opt.addEventListener('click', e => {
            e.stopPropagation();
            _showCreateModal(parseInt(opt.dataset.size));
        });
    });
    window._uClickTournament = () => _showActiveList();

    _connectWS();
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function _connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    _ws = new WebSocket(`${proto}//${location.host}/api/ws/tournament`);
    _ws.onopen  = () => { _wsReady = true; };
    _ws.onclose = () => { _wsReady = false; setTimeout(_connectWS, 5000); };
    _ws.onmessage = e => {
        try { _handleWS(JSON.parse(e.data)); } catch(_){}
    };
}

function _handleWS(msg) {
    switch(msg.type) {
        case 'tournament_started':
        case 'tournament_updated':
        case 'tournament_round_update': {
            const t = msg.tournament;
            if (_tournament && _tournament.id === t.id) {
                _tournament = t;
                _refreshOpenModals(t);
            }
            _updateHeaderCard(t);
            break;
        }
        case 'tournament_completed': {
            const t = msg.tournament;
            if (_tournament && _tournament.id === t.id) {
                _tournament = t;
                _refreshOpenModals(t);
            }
            _toast(`🏆 Tournament complete! Champion: ${esc((t.champion||{}).name||'Unknown')}`, 'success');
            break;
        }
    }
}

function _updateHeaderCard(t) {
    const el = document.getElementById('tournament-status');
    if (!el) return;
    const txt = el.querySelector('.tournament-status-text');
    if (txt) {
        if (t.status === 'in_progress')
            txt.textContent = `Round ${t.current_round+1}/${t.max_rounds} — ${t.name}`;
        else if (t.status === 'completed')
            txt.textContent = `Done — ${esc((t.champion||{}).name||'?')} wins!`;
        else
            txt.textContent = `Registration — ${t.name}`;
    }
}

function _refreshOpenModals(t) {
    // Bracket modal
    const bm = document.getElementById('tBracketModal');
    if (bm) _renderBracketInto(bm.querySelector('.t-bracket-area'), t);

    // Check if user now has a match to fight
    _checkMyMatch(t);
}

// ── Create modal ──────────────────────────────────────────────────────────────
function _showCreateModal(size) {
    _removeModal('tCreateModal');
    const rounds = Math.log2(size);
    const timerOpts = Object.entries(TIMER_LABELS).map(([k,v]) =>
        `<option value="${k}" ${k==='instant'?'selected':''}>${esc(v)}</option>`
    ).join('');

    const html = `
    <div class="modal fade" id="tCreateModal" tabindex="-1">
      <div class="modal-dialog modal-xl">
        <div class="modal-content tournament-modal-content">
          <div class="modal-header">
            <h5 class="modal-title">🏆 Create ${size}-Player Tournament</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <div class="row g-3">
              <div class="col-md-6">
                <label class="form-label text-white-50" style="font-size:.75rem">Tournament Name</label>
                <input id="tc-name" type="text" class="form-control bg-dark text-white border-secondary"
                       placeholder="${size}P Tournament" maxlength="50">
              </div>
              <div class="col-md-6">
                <label class="form-label text-white-50" style="font-size:.75rem">Round Timer</label>
                <select id="tc-timer" class="form-select bg-dark text-white border-secondary">${timerOpts}</select>
              </div>
            </div>

            <div class="mt-3">
              <label class="form-label text-white-50" style="font-size:.75rem">Invite Pet Owners (${size-1} more slots)</label>
              <div class="d-flex gap-2 mb-2">
                <input id="tc-search" type="text" class="form-control bg-dark text-white border-secondary"
                       placeholder="Search by username or pet name…" style="flex:1">
                <button class="btn btn-outline-warning btn-sm" onclick="_tcSearchUsers()">Search</button>
              </div>
              <div id="tc-user-list" style="max-height:220px;overflow-y:auto;border:1px solid rgba(255,255,255,.1);border-radius:6px;padding:6px">
                <div class="text-center text-secondary py-3" style="font-size:.75rem">Loading users with pets…</div>
              </div>
            </div>

            <div class="mt-3">
              <div class="d-flex align-items-center justify-content-between mb-1">
                <span style="font-size:.75rem;color:rgba(255,255,255,.6)">Selected participants</span>
                <span id="tc-count" style="font-size:.75rem;color:var(--gold-primary)">1 / ${size}</span>
              </div>
              <div id="tc-selected" style="display:flex;flex-wrap:wrap;gap:6px;min-height:36px;padding:6px;background:rgba(0,0,0,.2);border-radius:6px">
                <!-- organizer chip added by JS -->
              </div>
            </div>

            <div class="mt-3 p-2" style="background:rgba(255,215,0,.05);border:1px solid rgba(255,215,0,.15);border-radius:6px;font-size:.7rem;color:rgba(255,255,255,.6)">
              ⚠️ Empty slots are filled with AI opponents when the tournament starts.
              User vs User matches require both players to play turns on the website.
              AI vs AI matches are simulated automatically.
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
            <button class="btn btn-warning btn-sm" id="tc-submit">🏆 Create Tournament</button>
          </div>
        </div>
      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('tCreateModal'));
    modal.show();
    document.getElementById('tCreateModal').addEventListener('hidden.bs.modal', () =>
        _removeModal('tCreateModal'));

    document.getElementById('tc-submit').addEventListener('click', () => _tcSubmit(size, modal));
    document.getElementById('tc-search').addEventListener('input', () => _tcSearchUsers());

    window._tcSelected = new Map();   // uid → participant
    // Add self as organizer
    if (_myUserId) {
        fetch('/api/discord/user').then(r=>r.json()).then(u => {
            _tcAddSelected({ user_id: u.id, username: u.username, pet_name:'', type:'player' });
        });
    }
    _tcLoadUsers(size);
}

async function _tcLoadUsers(size) {
    const listEl = document.getElementById('tc-user-list');
    if (!listEl) return;
    try {
        if (!_petUsers.length) {
            const r = await fetch('/api/tournament/pet_users');
            if (r.ok) { const d = await r.json(); _petUsers = d.users || []; }
        }
        _tcRenderUsers(_petUsers, size);
    } catch(e) {
        if (listEl) listEl.innerHTML = '<div class="text-danger text-center py-2" style="font-size:.75rem">Failed to load users</div>';
    }
}

function _tcSearchUsers() {
    const q = (document.getElementById('tc-search')?.value || '').toLowerCase().trim();
    const filtered = q ? _petUsers.filter(u =>
        u.username.toLowerCase().includes(q) || u.pet_name.toLowerCase().includes(q)
    ) : _petUsers;
    const size = window._tcSize || 8;
    _tcRenderUsers(filtered, size);
}

function _tcRenderUsers(users, size) {
    const listEl = document.getElementById('tc-user-list');
    if (!listEl) return;
    if (!users.length) {
        listEl.innerHTML = '<div class="text-center text-secondary py-2" style="font-size:.75rem">No users found</div>';
        return;
    }
    listEl.innerHTML = users.map(u => {
        const inSelected = window._tcSelected?.has(u.user_id);
        const isSelf     = u.user_id === _myUserId;
        return `<div class="d-flex align-items-center gap-2 p-1" style="cursor:${isSelf||inSelected?'default':'pointer'};opacity:${isSelf?'.5':'1'}"
                     onclick="${isSelf||inSelected?'':'_tcToggleUser('+JSON.stringify(u.user_id)+')'}">
          <img src="${petImgUrl(u.pet_species)}" style="width:28px;height:28px;object-fit:cover;border-radius:50%;border:1px solid ${elemColor(u.pet_element)}"
               onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
          <div style="flex:1;min-width:0">
            <div style="font-size:.75rem;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(u.username)}</div>
            <div style="font-size:.65rem;color:${elemColor(u.pet_element)}">${esc(u.pet_name)} · Lv${u.pet_level} ${esc(u.pet_species)}</div>
          </div>
          ${inSelected ? '<span style="color:#2ecc71;font-size:.7rem">✓ Added</span>' : (isSelf ? '<span style="font-size:.7rem;color:rgba(255,255,255,.3)">You</span>' : '<span style="font-size:.7rem;color:var(--gold-primary)">+ Add</span>')}
        </div>`;
    }).join('');
}

window._tcToggleUser = function(uid) {
    const u = _petUsers.find(x => x.user_id === uid);
    if (!u) return;
    const size = window._tcSize || 8;
    if (window._tcSelected?.has(uid)) {
        window._tcSelected.delete(uid);
    } else {
        if (window._tcSelected?.size >= size) { _toast(`Max ${size} participants`, 'error'); return; }
        _tcAddSelected(u);
    }
    _tcRenderUsers(_petUsers, size);
};

function _tcAddSelected(u) {
    if (!window._tcSelected) return;
    window._tcSelected.set(u.user_id || u.id, u);
    _tcRenderChips();
}

function _tcRenderChips() {
    const el = document.getElementById('tc-selected');
    const cnt = document.getElementById('tc-count');
    const size = window._tcSize || 8;
    if (!el) return;
    el.innerHTML = Array.from(window._tcSelected.values()).map(u =>
        `<span style="background:rgba(255,215,0,.12);border:1px solid rgba(255,215,0,.3);border-radius:20px;padding:2px 10px;font-size:.7rem;color:var(--gold-primary)">
           ${esc(u.username||u.name||'?')}
         </span>`
    ).join('');
    if (cnt) cnt.textContent = `${window._tcSelected.size} / ${size}`;
}

async function _tcSubmit(size, modal) {
    window._tcSize = size;
    const name      = document.getElementById('tc-name')?.value.trim() || '';
    const timer     = document.getElementById('tc-timer')?.value || 'instant';
    const inviteIds = Array.from(window._tcSelected?.keys() || []).filter(id => id !== _myUserId);

    try {
        const r = await fetch('/api/tournament/create', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ size, name, round_timer: timer }),
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.detail || 'Failed');
        _tournament = d.tournament;

        // Invite selected users
        if (inviteIds.length) {
            await fetch(`/api/tournament/${d.tournament.id}/invite`, {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ user_ids: inviteIds }),
            });
        }

        modal.hide();
        // Refetch with invited users
        const r2 = await fetch(`/api/tournament/${d.tournament.id}`);
        const d2 = await r2.json();
        _tournament = d2.tournament;
        _showBracketModal(_tournament);
        _toast('Tournament created!', 'success');
    } catch(e) {
        _toast(e.message || 'Error', 'error');
    }
}

// ── Active list modal ─────────────────────────────────────────────────────────
async function _showActiveList() {
    _removeModal('tListModal');
    const html = `
    <div class="modal fade" id="tListModal" tabindex="-1">
      <div class="modal-dialog modal-xl">
        <div class="modal-content tournament-modal-content">
          <div class="modal-header">
            <h5 class="modal-title">🏆 Tournaments</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body" id="tListBody">
            <div class="text-center py-4"><div class="spinner-border text-warning" role="status"></div></div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Close</button>
            <button class="btn btn-warning btn-sm" onclick="window._tShowSizeSelect()">➕ New Tournament</button>
          </div>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('tListModal'));
    modal.show();
    document.getElementById('tListModal').addEventListener('hidden.bs.modal', () => _removeModal('tListModal'));

    try {
        const r = await fetch('/api/tournament/active');
        const d = await r.json();
        _renderList(d.tournaments || []);
    } catch(_) {
        document.getElementById('tListBody').innerHTML = '<div class="text-danger text-center">Failed to load</div>';
    }
}

function _renderList(tournaments) {
    const el = document.getElementById('tListBody');
    if (!el) return;
    if (!tournaments.length) {
        el.innerHTML = `<div class="text-center py-5">
            <div style="font-size:3rem">🏆</div>
            <h6 class="mt-2">No active tournaments</h6>
            <button class="btn btn-warning btn-sm mt-3" onclick="window._tShowSizeSelect()">Create one</button>
        </div>`;
        return;
    }
    el.innerHTML = `<div class="row g-3">${tournaments.map(t => {
        const sc = {in_progress:'#f1c40f',registration:'#3498db',completed:'#2ecc71'}[t.status]||'#aaa';
        return `<div class="col-md-6">
          <div class="tournament-card">
            <div class="tournament-card-header">
              <h6>${esc(t.name)}</h6>
              <span style="font-size:.65rem;font-weight:700;color:${sc}">${t.status}</span>
            </div>
            <div class="tournament-card-body">
              <div class="tournament-info">
                <div class="tournament-info-item"><span class="label">Size</span><span class="value">${t.size}P</span></div>
                <div class="tournament-info-item"><span class="label">Round</span><span class="value">${t.current_round+1}/${t.max_rounds}</span></div>
                <div class="tournament-info-item"><span class="label">Players</span><span class="value">${t.participant_count}/${t.size}</span></div>
                <div class="tournament-info-item"><span class="label">Timer</span><span class="value">${t.round_timer||'instant'}</span></div>
              </div>
              <div class="mt-2 d-flex gap-2">
                <button class="btn btn-outline-warning btn-sm flex-fill"
                        onclick="window._tViewBracket('${t.id}')">View Bracket</button>
                ${t.status==='registration'?`<button class="btn btn-success btn-sm" onclick="window._tJoin('${t.id}')">Join</button>`:''}
              </div>
            </div>
          </div>
        </div>`;
    }).join('')}</div>`;
}

window._tShowSizeSelect = function() {
    _removeModal('tSizeModal');
    const html = `
    <div class="modal fade" id="tSizeModal" tabindex="-1">
      <div class="modal-dialog modal-md">
        <div class="modal-content tournament-modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Choose Tournament Size</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <div class="tournament-size-grid">
              ${[4,8,16,32,64].map(s=>`
              <div class="size-option" onclick="bootstrap.Modal.getInstance(document.getElementById('tSizeModal')).hide();_showCreateModal(${s})">
                <div class="size-number">${s}</div>
                <div class="size-label">Players</div>
                <div class="size-rounds">${Math.log2(s)} Rounds</div>
              </div>`).join('')}
            </div>
          </div>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('tSizeModal'));
    modal.show();
    document.getElementById('tSizeModal').addEventListener('hidden.bs.modal', () => _removeModal('tSizeModal'));
};

window._tViewBracket = async function(tid) {
    const r = await fetch(`/api/tournament/${tid}`);
    const d = await r.json();
    if (!d.success) { _toast('Not found', 'error'); return; }
    _tournament = d.tournament;
    // Subscribe WS
    if (_ws?.readyState === WebSocket.OPEN)
        _ws.send(JSON.stringify({type:'subscribe', tournament_id: tid}));
    _showBracketModal(_tournament);
};

window._tJoin = async function(tid) {
    const r = await fetch(`/api/tournament/${tid}/join`, {method:'POST'});
    const d = await r.json();
    _toast(d.message || d.detail || 'OK', d.success ? 'success' : 'error');
    if (d.success) window._tViewBracket(tid);
};

// ── Bracket modal ─────────────────────────────────────────────────────────────
function _showBracketModal(t) {
    _removeModal('tBracketModal');
    const isOrg   = _myUserId && t.organizer_id === _myUserId;
    const canStart = t.status === 'registration' && isOrg;

    const html = `
    <div class="modal fade" id="tBracketModal" tabindex="-1">
      <div class="modal-dialog modal-fullscreen-lg-down" style="--bs-modal-width:min(95vw,1100px)">
        <div class="modal-content tournament-modal-content" style="max-height:92vh;display:flex;flex-direction:column">
          <div class="modal-header" style="flex-shrink:0">
            <div>
              <h5 class="modal-title mb-0">🏆 ${esc(t.name)}</h5>
              <div id="t-meta" style="font-size:.7rem;color:rgba(255,255,255,.5);margin-top:2px"></div>
            </div>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>

          <div class="modal-body p-2" style="overflow-y:auto;flex:1">
            <!-- Champion banner -->
            <div id="t-champion-banner" style="display:none"></div>
            <!-- My match CTA -->
            <div id="t-my-match-cta" style="display:none"></div>
            <!-- Bracket -->
            <div class="t-bracket-area" style="overflow-x:auto;padding-bottom:8px"></div>
          </div>

          <div class="modal-footer" style="flex-shrink:0">
            ${canStart ? `<button class="btn btn-warning btn-sm" id="t-start-btn">🚀 Start Tournament</button>` : ''}
            ${t.status==='registration'&&!isOrg ? `<button class="btn btn-success btn-sm" onclick="window._tJoin('${t.id}')">➕ Join</button>` : ''}
            ${isOrg&&t.status==='registration' ? `<button class="btn btn-outline-info btn-sm" onclick="window._tOpenInvite('${t.id}')">👥 Manage Invites</button>` : ''}
            <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Close</button>
          </div>
        </div>
      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('tBracketModal'));
    modal.show();
    document.getElementById('tBracketModal').addEventListener('hidden.bs.modal', () =>
        _removeModal('tBracketModal'));

    if (canStart) {
        document.getElementById('t-start-btn')?.addEventListener('click', () => _startTournament(t.id));
    }

    _renderBracketModal(t);
}

function _renderBracketModal(t) {
    _updateMeta(t);
    _updateChampion(t);
    const area = document.querySelector('#tBracketModal .t-bracket-area');
    if (area) _renderBracketInto(area, t);
    _checkMyMatch(t);
}

function _updateMeta(t) {
    const el = document.getElementById('t-meta');
    if (!el) return;
    const sc = {in_progress:'#f1c40f',registration:'#3498db',completed:'#2ecc71'}[t.status]||'#aaa';
    const timer = t.round_timer !== 'instant' ? ` · ⏱ ${t.round_timer}/round` : '';
    el.innerHTML = `<span style="color:${sc}">${t.status}</span> &nbsp;·&nbsp; Round ${(t.current_round||0)+1}/${t.max_rounds} &nbsp;·&nbsp; ${t.size}P &nbsp;·&nbsp; By ${esc(t.organizer_name)}${timer}`;
}

function _updateChampion(t) {
    const el = document.getElementById('t-champion-banner');
    if (!el) return;
    if (t.champion) {
        el.style.display = 'block';
        el.innerHTML = `<div style="text-align:center;padding:12px;background:rgba(241,196,15,.1);border:1px solid rgba(241,196,15,.3);border-radius:8px;margin-bottom:10px">
          <div style="font-size:.7rem;color:var(--gold-primary)">🏆 CHAMPION</div>
          <div style="font-size:1.1rem;font-weight:700;color:#f1c40f">${esc(t.champion.name)}</div>
          ${t.champion.species ? `<img src="${petImgUrl(t.champion.species)}" style="width:48px;height:48px;object-fit:contain;margin-top:4px"
                onerror="this.style.display='none'">` : ''}
        </div>`;
    } else {
        el.style.display = 'none';
    }
}

// ── Visual bracket renderer ───────────────────────────────────────────────────
function _renderBracketInto(container, t) {
    if (!container) return;
    const rounds = t.bracket || [];
    if (!rounds.length) {
        container.innerHTML = `<div class="text-center text-secondary py-4" style="font-size:.8rem">
            ${t.status==='registration' ? 'Start the tournament to generate the bracket.' : 'No bracket yet.'}
        </div>`;
        return;
    }

    // Build proper visual bracket using flex columns
    const nRounds = rounds.length;
    let html = `<div class="t-bracket" style="display:flex;gap:0;align-items:stretch;min-width:${nRounds*210}px">`;

    rounds.forEach((round, ri) => {
        const isCurrent = ri === (t.current_round||0);
        const isPast    = ri < (t.current_round||0);
        const nMatches  = round.matches.length;
        const labelColor = isCurrent ? 'var(--gold-primary)' : isPast ? '#2ecc71' : 'rgba(255,255,255,.3)';

        html += `<div class="t-round-col" style="display:flex;flex-direction:column;min-width:200px;width:200px;flex-shrink:0;padding:0 6px">`;
        html += `<div style="text-align:center;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:${labelColor};padding:6px 0;margin-bottom:4px;border-bottom:1px solid ${labelColor}30">
                   ${esc(round.label)}${isCurrent&&t.status==='in_progress'?' ●':''}
                 </div>`;

        // Matches are distributed evenly in the column with equal vertical spacing
        html += `<div style="display:flex;flex-direction:column;flex:1;justify-content:space-around;gap:8px">`;
        round.matches.forEach(m => {
            html += _matchCard(m, t.id, isCurrent, _myUserId);
        });
        html += `</div>`;  // matches col
        html += `</div>`;  // round col

        // Connector lines between rounds (except last)
        if (ri < nRounds - 1) {
            html += `<div class="t-connector" style="display:flex;align-items:center;padding:0 2px;min-width:16px;width:16px;flex-shrink:0">
                       <div style="width:16px;border-top:1px solid rgba(255,255,255,.15)"></div>
                     </div>`;
        }
    });

    html += `</div>`;
    container.innerHTML = html;
}

function _matchCard(m, tid, isCurrent, myUid) {
    const status  = m.status || 'pending';
    const p1      = m.p1;
    const p2      = m.p2;
    const winner  = m.winner;
    const isBye   = status === 'p1_bye' || status === 'p2_bye';
    const isDone  = status === 'done' || winner;
    const isReady = status === 'ready' || status === 'in_progress';

    const myUidStr = String(myUid || '');
    const p1Uid    = String((p1||{}).user_id || '');
    const p2Uid    = String((p2||{}).user_id || '');
    const isMyMatch = isReady && isCurrent && (myUidStr === p1Uid || myUidStr === p2Uid);

    let borderColor = 'rgba(255,255,255,.12)';
    if (isDone)   borderColor = '#2ecc7140';
    if (isReady && isCurrent) borderColor = 'rgba(255,215,0,.35)';
    if (isMyMatch) borderColor = 'var(--gold-primary)';

    function slot(p, isWinner) {
        if (!p) return `<div style="padding:4px 6px;font-size:.68rem;color:rgba(255,255,255,.3);font-style:italic">TBD</div>`;
        const npc  = p.type === 'npc';
        const wc   = isWinner ? '#2ecc71' : (isDone && !isWinner ? 'rgba(255,255,255,.3)' : '#fff');
        const wIcon = isWinner ? '🏆 ' : '';
        const elem = p.element || 'basic';
        return `<div style="display:flex;align-items:center;gap:4px;padding:3px 5px;border-radius:3px;background:${isWinner?'rgba(46,204,113,.08)':'transparent'}">
          <img src="${petImgUrl(p.species)}" style="width:18px;height:18px;object-fit:cover;border-radius:50%;border:1px solid ${elemColor(elem)};flex-shrink:0"
               onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
          <div style="min-width:0;flex:1;overflow:hidden">
            <div style="font-size:.68rem;font-weight:600;color:${wc};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${wIcon}${esc(p.name)}${npc?' 🤖':''}</div>
            ${p.species ? `<div style="font-size:.58rem;color:${elemColor(elem)};white-space:nowrap">${esc(p.species)} Lv${p.level||1}</div>` : ''}
          </div>
        </div>`;
    }

    const p1Win = winner && p1 && winner.user_id === p1.user_id;
    const p2Win = winner && p2 && winner.user_id === p2.user_id;

    let actionBtn = '';
    if (isMyMatch && !m.battle_session) {
        actionBtn = `<button style="margin-top:4px;width:100%;padding:3px;font-size:.65rem;background:rgba(255,215,0,.15);border:1px solid var(--gold-primary);border-radius:4px;color:var(--gold-primary);cursor:pointer"
                             onclick="_tFightMatch('${tid}','${m.id}')">⚔️ Fight!</button>`;
    } else if (isMyMatch && m.battle_session) {
        actionBtn = `<button style="margin-top:4px;width:100%;padding:3px;font-size:.65rem;background:rgba(255,100,0,.15);border:1px solid #e74c3c;border-radius:4px;color:#e74c3c;cursor:pointer"
                             onclick="_tFightMatch('${tid}','${m.id}')">⚔️ Continue Battle</button>`;
    } else if (status === 'bot_sim' && !winner) {
        actionBtn = `<div style="margin-top:4px;text-align:center;font-size:.62rem;color:rgba(255,255,255,.35)">⏳ AI simulating…</div>`;
    } else if (status === 'pending') {
        actionBtn = `<div style="margin-top:4px;text-align:center;font-size:.62rem;color:rgba(255,255,255,.25)">Waiting for previous round</div>`;
    }

    const logHtml = (m.log||[]).slice(0,3).map(l =>
        `<div style="font-size:.6rem;color:rgba(255,255,255,.4);padding:1px 4px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${esc(l)}</div>`
    ).join('');

    return `<div style="background:rgba(0,0,0,.35);border:1px solid ${borderColor};border-radius:6px;padding:5px;transition:border-color .2s">
      <div style="border-bottom:1px solid rgba(255,255,255,.07);padding-bottom:3px;margin-bottom:3px">${slot(p1, p1Win)}</div>
      ${isBye ? '' : slot(p2, p2Win)}
      ${logHtml}
      ${actionBtn}
    </div>`;
}

// ── My match CTA ──────────────────────────────────────────────────────────────
async function _checkMyMatch(t) {
    if (!_myUserId || !t || t.status !== 'in_progress') return;
    try {
        const r = await fetch(`/api/tournament/${t.id}/my_match`);
        const d = await r.json();
        _renderMyMatchCTA(t, d.match, d.round, d.is_p1);
    } catch(_){}
}

function _renderMyMatchCTA(t, match, round, isP1) {
    const el = document.getElementById('t-my-match-cta');
    if (!el) return;
    if (!match) { el.style.display = 'none'; return; }
    const opp = isP1 ? match.p2 : match.p1;
    el.style.display = 'block';
    el.innerHTML = `<div style="background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.4);border-radius:8px;padding:10px 14px;margin-bottom:10px;display:flex;align-items:center;gap:10px">
      <div style="font-size:1.4rem">⚔️</div>
      <div style="flex:1">
        <div style="font-size:.8rem;font-weight:700;color:var(--gold-primary)">Your match is ready!</div>
        <div style="font-size:.7rem;color:rgba(255,255,255,.6)">vs ${esc((opp||{}).name||'TBD')} — Round ${(round||0)+1}</div>
      </div>
      <button style="padding:6px 14px;background:rgba(255,215,0,.2);border:1px solid var(--gold-primary);border-radius:6px;color:var(--gold-primary);font-weight:700;font-size:.75rem;cursor:pointer"
              onclick="_tFightMatch('${t.id}','${match.id}')">Fight Now</button>
    </div>`;
}

// ── Tournament battle flow ────────────────────────────────────────────────────
window._tFightMatch = async function(tid, mid) {
    // Close bracket modal — the battle replaces the panel
    const bm = bootstrap.Modal.getInstance(document.getElementById('tBracketModal'));
    if (bm) bm.hide();

    try {
        const r = await fetch(`/api/tournament/${tid}/match/${mid}/start_battle`, {
            method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({}),
        });
        const d = await r.json();
        if (!d.success) { _toast(d.detail||'Could not start battle', 'error'); return; }

        _currentMatchId = mid;
        _matchBattle = {
            ...d,
            tournamentId: tid,
            matchId: mid,
            sessionKey: d.session_key,
            roomId: null,
        };

        _showTournamentBattleStage(_matchBattle);
    } catch(e) {
        _toast(e.message || 'Error', 'error');
    }
};

function _showTournamentBattleStage(state) {
    // Reuse the exact same arena battle stage — works identically
    // We just need to call the arena's _showBattleStage equivalent.
    // Set up _battle in arena.js scope via a bridge
    if (typeof window._arenaTournamentBattle === 'function') {
        window._arenaTournamentBattle(state);
    } else {
        // Fallback: use the shared panel directly
        _renderTournamentBattlePanel(state);
    }
}

function _renderTournamentBattlePanel(state) {
    const p = state.player, e = state.enemy;
    const labels = state.action_labels || {};
    const atkLabel = labels.attack || 'Attack';
    const defLabel = labels.defend || 'Defend';
    const chgLabel = labels.charge || 'Charge';

    function buildSkillBtns(player) {
        const skills = (player && player.equipped_skills) || [];
        if (!skills.length) return '';
        const cds = (player && player.skill_cooldowns) || {};
        return skills.map((sk, idx) => {
            if (!sk) return `<button class="arena-action-btn arena-skill-empty" disabled
                                     style="background:rgba(100,100,100,.1);border-color:rgba(100,100,100,.3);color:rgba(150,150,150,.5);font-size:.72rem;cursor:not-allowed">
                                ✨ Slot ${idx+1}<span class="arena-action-sub">Empty</span></button>`;
            const cd = cds[String(idx)] || 0;
            const onCd = cd > 0;
            return `<button class="arena-action-btn${onCd?' arena-skill-cd':''}" id="tab-skill-${idx}"
                            style="background:rgba(155,89,182,.15);border-color:rgba(155,89,182,.5);color:#9b59b6;font-size:.72rem"
                            onclick="_tTurn('skill',${idx})" ${onCd?'disabled':''}
                            title="${esc((sk.description||''))}">
                        ✨ ${esc(sk.name)}<span class="arena-action-sub">${onCd?'('+cd+')':'Ready'}</span>
                    </button>`;
        }).join('');
    }

    function imgSrc(pet) {
        if (pet && pet.badge_url) return pet.badge_url;
        return petImgUrl((pet && pet.species) || null);
    }

    const panel = document.getElementById('shared-panel-area');
    if (!panel) return;
    panel.innerHTML = `
    <div class="arena-panel" id="t-battle-panel">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <div class="arena-panel-title" style="margin-bottom:0">🏆 Tournament Match</div>
        <button class="arena-btn danger" style="padding:4px 10px;font-size:.7rem" onclick="_tFlee()">Forfeit</button>
      </div>
      <div class="arena-stage" id="tab-stage">
        <div class="arena-fighter" id="tab-player">
          <div class="arena-fighter-img-wrap" id="tab-player-wrap">
            <div class="arena-charge-ring" id="tab-player-ring"></div>
            <img class="arena-fighter-img" src="${imgSrc(p)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="${esc(p.name)}">
          </div>
          <div class="arena-fighter-name">${esc(p.name)}</div>
          <div class="arena-fighter-sub">${esc(p.species||'')}</div>
          <div class="arena-fighter-hp-wrap"><div class="arena-fighter-hp-bar" id="tab-player-hp" style="width:100%;background:#2ecc71"></div></div>
          <div class="arena-fighter-hp-text" id="tab-player-hp-text">${p.cur_hp} / ${p.max_hp}</div>
        </div>
        <div class="arena-vs-badge">VS</div>
        <div class="arena-fighter enemy" id="tab-enemy">
          <div class="arena-fighter-img-wrap" id="tab-enemy-wrap">
            <div class="arena-charge-ring" id="tab-enemy-ring"></div>
            <img class="arena-fighter-img" src="${petImgUrl(e.species)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="${esc(e.name)}">
          </div>
          <div class="arena-fighter-name">${esc(e.name)}</div>
          <div class="arena-fighter-sub">${esc(e.species||'')} · ${esc(e.element||'')}</div>
          <div class="arena-fighter-hp-wrap"><div class="arena-fighter-hp-bar" id="tab-enemy-hp" style="width:100%;background:#e74c3c"></div></div>
          <div class="arena-fighter-hp-text" id="tab-enemy-hp-text">${e.cur_hp} / ${e.max_hp}</div>
        </div>
      </div>
      <div class="arena-action-row" id="tab-actions">
        <button class="arena-action-btn atk" id="tab-attack" onclick="_tTurn('attack')">⚔️ Attack<span class="arena-action-sub">${esc(atkLabel)}</span></button>
        <button class="arena-action-btn def" id="tab-defend" onclick="_tTurn('defend')">🛡️ Defend<span class="arena-action-sub">${esc(defLabel)}</span></button>
        <button class="arena-action-btn chg" id="tab-charge" onclick="_tTurn('charge')">⚡ Charge<span class="arena-action-sub">${esc(chgLabel)}</span></button>
        ${buildSkillBtns(p)}
      </div>
      <div class="arena-status-text" id="tab-status">Your turn — pick an action!</div>
      <div class="arena-log" id="tab-log"></div>
      <div id="tab-result" style="display:none"></div>
    </div>`;

    // Charge ring colors
    if (typeof window._setChargeRingColors === 'function') {
        window._setChargeRingColors('tab-player-ring', p.element, p.element2);
        window._setChargeRingColors('tab-enemy-ring',  e.element, '');
    }
    // Prevent arena WS from wiping the panel
    document.dispatchEvent(new CustomEvent('arenaBattleStarted'));
}

window._tTurn = async function(action, slotIdx) {
    if (!_matchBattle || _matchBattle.over) return;
    _tSetButtons(false);
    const status = document.getElementById('tab-status');
    if (status) status.textContent = 'Processing turn…';

    try {
        const res = await fetch(`/api/tournament/${_matchBattle.tournamentId}/match/${_matchBattle.matchId}/turn`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                action,
                slot_index: slotIdx !== undefined ? slotIdx : 0,
                player: _matchBattle.player,
                enemy:  _matchBattle.enemy,
                turn:   _matchBattle.turn || 0,
                action_labels: _matchBattle.action_labels || {},
            }),
        });
        const d = await res.json();
        if (!res.ok) { if(status) status.textContent = d.detail||'Error'; _tSetButtons(true); return; }

        _matchBattle.player = d.player;
        _matchBattle.enemy  = d.enemy;
        _matchBattle.turn   = d.turn;
        _matchBattle.over   = d.over;

        // Update HP bars
        _tUpdateHp('tab-player-hp', 'tab-player-hp-text', d.player.cur_hp, d.player.max_hp, false);
        _tUpdateHp('tab-enemy-hp',  'tab-enemy-hp-text',  d.enemy.cur_hp,  d.enemy.max_hp,  true);

        // Charge rings
        if (typeof window._setChargeRingLevel === 'function') {
            window._setChargeRingLevel('tab-player-ring', d.over ? 1 : (d.player.charge||1));
            window._setChargeRingLevel('tab-enemy-ring',  d.over ? 1 : (d.enemy.charge||1));
        }

        // Damage floats
        if (typeof window._showDmgFloat === 'function') {
            const c = d.combat || {};
            setTimeout(() => {
                if (c.e_dmg > 0 || c.e_parry > 0) window._showDmgFloat('tab-player-wrap', (c.e_dmg||0)+(c.e_parry||0), '#e74c3c');
                if (c.p_dmg > 0 || c.p_parry > 0) window._showDmgFloat('tab-enemy-wrap',  (c.p_dmg||0)+(c.p_parry||0), '#2ecc71');
            }, 280);
        }

        // Skill cooldowns
        if (d.skill_cooldowns) _tUpdateSkillCds(d.skill_cooldowns, _matchBattle.player);

        // Log
        _tAppendLog(d.turn, d.lines || []);

        if (d.over) {
            setTimeout(() => _tShowResult(d), 1200);
        } else {
            if (status) status.textContent = `Turn ${d.turn} — pick your next action!`;
            setTimeout(() => _tSetButtons(true), 650);
        }
    } catch(e) {
        if (status) status.textContent = 'Error: ' + e.message;
        _tSetButtons(true);
    }
};

function _tSetButtons(enabled) {
    ['tab-attack','tab-defend','tab-charge'].forEach(id => {
        const b = document.getElementById(id);
        if (b) b.disabled = !enabled;
    });
    if (_matchBattle?.player) {
        const skills = _matchBattle.player.equipped_skills || [];
        const cds    = _matchBattle.player.skill_cooldowns || {};
        skills.forEach((_,idx) => {
            const b = document.getElementById(`tab-skill-${idx}`);
            if (!b) return;
            if (!enabled) { b.disabled = true; return; }
            const cd = cds[String(idx)] || 0;
            b.disabled = cd > 0;
        });
    }
}

function _tUpdateSkillCds(cds, player) {
    if (!player) return;
    const skills = player.equipped_skills || [];
    skills.forEach((sk,idx) => {
        const b = document.getElementById(`tab-skill-${idx}`);
        if (!b || !sk) return;
        const cd = cds[String(idx)] || 0;
        b.disabled = cd > 0;
        b.classList.toggle('arena-skill-cd', cd > 0);
        const sub = b.querySelector('.arena-action-sub');
        if (sub) sub.textContent = cd > 0 ? `(${cd})` : 'Ready';
    });
    if (_matchBattle?.player) _matchBattle.player.skill_cooldowns = cds;
}

function _tUpdateHp(barId, textId, cur, max, isEnemy) {
    const bar  = document.getElementById(barId);
    const text = document.getElementById(textId);
    if (!bar || !text) return;
    const pct = max > 0 ? Math.max(0, Math.min(100, (cur/max)*100)) : 0;
    bar.style.width = pct + '%';
    bar.style.background = isEnemy
        ? (pct > 50 ? '#e74c3c' : pct > 25 ? '#e67e22' : '#c0392b')
        : (pct > 50 ? '#2ecc71' : pct > 25 ? '#f39c12' : '#e74c3c');
    text.textContent = `${cur} / ${max}`;
}

function _tAppendLog(turn, lines) {
    const log = document.getElementById('tab-log');
    if (!log) return;
    const div = document.createElement('div');
    div.style.cssText = 'margin-bottom:4px;padding:4px 6px;background:rgba(0,0,0,.2);border-radius:4px;font-size:.72rem';
    div.innerHTML = `<span style="color:rgba(255,255,255,.35);font-size:.65rem">T${turn}</span> ` +
        lines.map(l => `<span>${esc(l)}</span>`).join(' &nbsp;');
    log.prepend(div);
    // Keep only last 8 entries
    while (log.children.length > 8) log.removeChild(log.lastChild);
}

function _tShowResult(d) {
    const won = d.won;
    const res = document.getElementById('tab-result');
    const status = document.getElementById('tab-status');
    if (res) {
        res.style.display = 'block';
        res.innerHTML = `<div style="text-align:center;padding:14px;background:${won?'rgba(46,204,113,.1)':'rgba(231,76,60,.1)'};border:1px solid ${won?'#2ecc71':'#e74c3c'};border-radius:8px;margin-top:8px">
          <div style="font-size:1.6rem">${won?'🏆':'💀'}</div>
          <div style="font-size:.9rem;font-weight:700;color:${won?'#2ecc71':'#e74c3c'}">${won?'Victory!':'Defeated'}</div>
          ${d.xp_gained ? `<div style="font-size:.75rem;color:var(--gold-primary);margin-top:4px">+${d.xp_gained} XP</div>` : ''}
          <button style="margin-top:10px;padding:6px 16px;background:rgba(255,215,0,.15);border:1px solid var(--gold-primary);border-radius:6px;color:var(--gold-primary);font-size:.75rem;cursor:pointer"
                  onclick="_tBackToBracket()">View Bracket</button>
        </div>`;
    }
    if (status) status.textContent = won ? '🏆 You advance!' : '💀 Eliminated.';
    _currentMatchId = null;
    _matchBattle    = null;
}

async function _tBackToBracket() {
    if (_tournament) {
        const r = await fetch(`/api/tournament/${_tournament.id}`);
        const d = await r.json();
        if (d.success) _tournament = d.tournament;
        _showBracketModal(_tournament);
    }
}

window._tFlee = async function() {
    if (!_matchBattle) return;
    if (!confirm('Forfeit this match? You will be eliminated.')) return;
    // Just close — the round timer will advance it, or they can view bracket
    _tShowResult({ won: false, xp_gained: 0 });
};

// ── Invite manager ────────────────────────────────────────────────────────────
window._tOpenInvite = async function(tid) {
    _removeModal('tInviteModal');
    if (!_petUsers.length) {
        try {
            const r = await fetch('/api/tournament/pet_users');
            const d = await r.json();
            _petUsers = d.users || [];
        } catch(_){}
    }
    const t = _active_tournaments_cache(tid);

    const html = `
    <div class="modal fade" id="tInviteModal" tabindex="-1">
      <div class="modal-dialog modal-lg">
        <div class="modal-content tournament-modal-content">
          <div class="modal-header">
            <h5 class="modal-title">👥 Manage Participants</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <input id="ti-search" type="text" class="form-control bg-dark text-white border-secondary mb-2"
                   placeholder="Search users…" oninput="_tiSearch()">
            <div id="ti-list" style="max-height:350px;overflow-y:auto"></div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Done</button>
          </div>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('tInviteModal'));
    modal.show();
    document.getElementById('tInviteModal').addEventListener('hidden.bs.modal', () => _removeModal('tInviteModal'));
    window._tiTid = tid;
    _tiRender(_petUsers, tid);
};

function _tiRender(users, tid) {
    const el = document.getElementById('ti-list');
    if (!el) return;
    el.innerHTML = users.map(u => {
        return `<div class="d-flex align-items-center gap-2 p-2" style="border-bottom:1px solid rgba(255,255,255,.05)">
          <img src="${petImgUrl(u.pet_species)}" style="width:28px;height:28px;border-radius:50%;border:1px solid ${elemColor(u.pet_element)}"
               onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
          <div style="flex:1">
            <div style="font-size:.78rem;font-weight:600;color:#fff">${esc(u.username)}</div>
            <div style="font-size:.65rem;color:${elemColor(u.pet_element)}">${esc(u.pet_name)} Lv${u.pet_level}</div>
          </div>
          <button style="padding:3px 10px;font-size:.65rem;border:1px solid var(--gold-primary);background:rgba(255,215,0,.1);color:var(--gold-primary);border-radius:4px;cursor:pointer"
                  onclick="_tiAdd('${u.user_id}')">+ Add</button>
        </div>`;
    }).join('');
}

window._tiSearch = function() {
    const q = (document.getElementById('ti-search')?.value||'').toLowerCase();
    const filtered = q ? _petUsers.filter(u=>u.username.toLowerCase().includes(q)||u.pet_name.toLowerCase().includes(q)) : _petUsers;
    _tiRender(filtered, window._tiTid);
};

window._tiAdd = async function(uid) {
    const tid = window._tiTid;
    if (!tid) return;
    try {
        const r = await fetch(`/api/tournament/${tid}/invite`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({user_ids:[uid]}),
        });
        const d = await r.json();
        if (d.success) _toast(`Added! (${d.participant_count} participants)`, 'success');
        else _toast(d.detail||'Could not add', 'error');
    } catch(e) { _toast('Error', 'error'); }
};

// ── Start tournament ──────────────────────────────────────────────────────────
async function _startTournament(tid) {
    const btn = document.getElementById('t-start-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Starting…'; }
    try {
        const r = await fetch(`/api/tournament/${tid}/start`, {method:'POST'});
        const d = await r.json();
        if (d.success) {
            _tournament = d.tournament;
            _renderBracketModal(_tournament);
            _toast('Tournament started!', 'success');
        } else {
            _toast(d.detail||'Failed', 'error');
            if (btn) { btn.disabled = false; btn.textContent = '🚀 Start Tournament'; }
        }
    } catch(e) {
        _toast(e.message||'Error', 'error');
        if (btn) { btn.disabled = false; btn.textContent = '🚀 Start Tournament'; }
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _active_tournaments_cache(tid) {
    return _tournament?.id === tid ? _tournament : null;
}

function _removeModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    try { bootstrap.Modal.getInstance(el)?.hide(); } catch(_){}
    setTimeout(() => { if (document.getElementById(id)) document.getElementById(id).remove(); }, 300);
}

function _toast(msg, type) {
    const el = document.createElement('div');
    el.className = `tournament-notification tournament-notification-${type}`;
    el.innerHTML = `<div class="notification-content">
      <span class="notification-icon">${type==='success'?'✅':type==='error'?'❌':'ℹ️'}</span>
      <span class="notification-text">${esc(msg)}</span>
    </div>`;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add('show'), 10);
    setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.parentNode?.removeChild(el), 300);
    }, 4000);
}

// ── Bridge for arena.js to hand off tournament battle ─────────────────────────
// arena.js can call window._arenaTournamentBattle(state) to start a tournament match
// using the arena UI. We set it up here so the battle stage looks the same.
window._arenaTournamentBattle = function(state) {
    _renderTournamentBattlePanel(state);
};

// ── Boot ──────────────────────────────────────────────────────────────────────
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
} else {
    _init();
}

})();
