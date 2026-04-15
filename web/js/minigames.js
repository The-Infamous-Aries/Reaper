/* ── Casino Mini-Games JS — Coin Flip & Rock Paper Scissors ──────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

// ── Shared state ──────────────────────────────────────────────────────────────
let _xp = 0;

// ── Coin Flip state ───────────────────────────────────────────────────────────
const CF = {
    theme:    null,
    pick:     null,   // "heads" | "tails"
    bet:      0,
    funMode:  false,
    busy:     false,
};

// ── RPS state ─────────────────────────────────────────────────────────────────
const RPS = {
    theme:   null,
    choice:  null,
    bet:     0,
    funMode: false,
    busy:    false,
    score:   { player: 0, ai: 0, ties: 0 },
};

const RPS_THEMES = {
    Traditional: {
        rock_1:   { name: "Rock",        img: "/static/Emojis/RPS/rock_1.png" },
        paper:    { name: "Paper",       img: "/static/Emojis/RPS/paper.png" },
        scissor:  { name: "Scissors",    img: "/static/Emojis/RPS/scissor.png" },
    },
    Fantasy: {
        knights:     { name: "Knight",      img: "/static/Emojis/RPS/knights.png" },
        archer:      { name: "Archer",      img: "/static/Emojis/RPS/archer.png" },
        necromancer: { name: "Necromancer", img: "/static/Emojis/RPS/necromancer.png" },
    },
    War: {
        tank: { name: "Tank", img: "/static/Emojis/RPS/tank.png" },
        jet:  { name: "Jet",  img: "/static/Emojis/RPS/jet.png" },
        ship: { name: "Ship", img: "/static/Emojis/RPS/ship.png" },
    },
};

const COIN_THEMES = {
    Raider:    { heads: "Pirate",  tails: "Poop",   headsImg: "/static/Emojis/Coins/Pirate.png",  tailsImg: "/static/Emojis/Coins/Poop.png" },
    Time:      { heads: "Future",  tails: "Retro",  headsImg: "/static/Emojis/Coins/Future.png",  tailsImg: "/static/Emojis/Coins/Retro.png" },
    Battery:   { heads: "Full",    tails: "Empty",  headsImg: "/static/Emojis/Coins/Full.png",    tailsImg: "/static/Emojis/Coins/Empty.png" },
    Electric:  { heads: "Plug",    tails: "Socket", headsImg: "/static/Emojis/Coins/Plug.png",    tailsImg: "/static/Emojis/Coins/Socket.png" },
    Business:  { heads: "Open",    tails: "Close",  headsImg: "/static/Emojis/Coins/Open.png",    tailsImg: "/static/Emojis/Coins/Close.png" },
    Sky:       { heads: "Day",     tails: "Night",  headsImg: "/static/Emojis/Coins/Day.png",     tailsImg: "/static/Emojis/Coins/Night.png" },
    Tempature: { heads: "Hot",     tails: "Cold",   headsImg: "/static/Emojis/Coins/Hot.png",     tailsImg: "/static/Emojis/Coins/Cold.png" },
};

// ── Boot ──────────────────────────────────────────────────────────────────────
function init() {
    if (!$('mg-root')) return;
    loadXP();
    bindEvents();
}

async function loadXP() {
    try {
        const r = await fetch('/api/casino/xp');
        if (!r.ok) return;
        const d = await r.json();
        if (d.has_pet) { _xp = d.total_xp || 0; renderXP(); }
    } catch { /* silent */ }
}

function renderXP() {
    [$('mg-xp-cf'), $('mg-xp-rps')].forEach(el => {
        if (el) el.textContent = _xp.toLocaleString() + ' XP';
    });
}

// ── Events ────────────────────────────────────────────────────────────────────
function bindEvents() {
    document.addEventListener('click', e => {
        if (!$('mg-root')) return;

        // ── Coin Flip ──────────────────────────────────────────────────────
        const cfTheme = e.target.closest('.cf-theme-btn');
        if (cfTheme) {
            document.querySelectorAll('.cf-theme-btn').forEach(b => b.classList.remove('selected'));
            cfTheme.classList.add('selected');
            CF.theme = cfTheme.dataset.theme;
            updateCoinFaces();
            checkCFReady();
            return;
        }

        const cfPick = e.target.closest('.cf-pick-btn');
        if (cfPick) {
            document.querySelectorAll('.cf-pick-btn').forEach(b => b.classList.remove('selected'));
            cfPick.classList.add('selected');
            CF.pick = cfPick.dataset.pick;
            checkCFReady();
            return;
        }

        if (e.target.id === 'cf-flip-btn') { flipCoin(); return; }
        if (e.target.id === 'cf-again-btn') { resetCF(); return; }

        const cfPreset = e.target.closest('.cf-preset');
        if (cfPreset) {
            const inp = $('cf-bet-input');
            if (inp) { inp.value = cfPreset.dataset.amount; CF.bet = parseInt(cfPreset.dataset.amount); checkCFReady(); }
            return;
        }

        // ── RPS ────────────────────────────────────────────────────────────
        const rpsTheme = e.target.closest('.rps-theme-btn');
        if (rpsTheme) {
            document.querySelectorAll('.rps-theme-btn').forEach(b => b.classList.remove('selected'));
            rpsTheme.classList.add('selected');
            RPS.theme = rpsTheme.dataset.theme;
            buildRPSChoices();
            checkRPSReady();
            return;
        }

        const rpsChoice = e.target.closest('.mg-rps-choice');
        if (rpsChoice) {
            document.querySelectorAll('.mg-rps-choice').forEach(b => b.classList.remove('selected'));
            rpsChoice.classList.add('selected');
            RPS.choice = rpsChoice.dataset.choice;
            checkRPSReady();
            return;
        }

        if (e.target.id === 'rps-play-btn') { playRPS(); return; }
        if (e.target.id === 'rps-again-btn') { resetRPS(); return; }

        const rpsPreset = e.target.closest('.rps-preset');
        if (rpsPreset) {
            const inp = $('rps-bet-input');
            if (inp) { inp.value = rpsPreset.dataset.amount; RPS.bet = parseInt(rpsPreset.dataset.amount); checkRPSReady(); }
            return;
        }
    });

    // Bet inputs
    document.addEventListener('input', e => {
        if (!$('mg-root')) return;
        if (e.target.id === 'cf-bet-input')  { CF.bet  = parseInt(e.target.value) || 0; checkCFReady(); }
        if (e.target.id === 'rps-bet-input') { RPS.bet = parseInt(e.target.value) || 0; checkRPSReady(); }
    });

    // Fun mode toggles
    document.addEventListener('change', e => {
        if (!$('mg-root')) return;
        if (e.target.id === 'cf-fun-toggle') {
            CF.funMode = e.target.checked;
            const row = $('cf-bet-row');
            if (row) row.style.display = CF.funMode ? 'none' : '';
            checkCFReady();
        }
        if (e.target.id === 'rps-fun-toggle') {
            RPS.funMode = e.target.checked;
            const row = $('rps-bet-row');
            if (row) row.style.display = RPS.funMode ? 'none' : '';
            checkRPSReady();
        }
    });
}

// ── Coin Flip ─────────────────────────────────────────────────────────────────
function updateCoinFaces() {
    if (!CF.theme) return;
    const td = COIN_THEMES[CF.theme];
    if (!td) return;
    const hImg = $('cf-heads-img'), tImg = $('cf-tails-img');
    const hLbl = $('cf-heads-label'), tLbl = $('cf-tails-label');
    if (hImg) hImg.src = td.headsImg;
    if (tImg) tImg.src = td.tailsImg;
    if (hLbl) hLbl.textContent = td.heads;
    if (tLbl) tLbl.textContent = td.tails;

    // Also update pick buttons
    const hPick = document.querySelector('.cf-pick-btn[data-pick="heads"] img');
    const tPick = document.querySelector('.cf-pick-btn[data-pick="tails"] img');
    const hPickLbl = document.querySelector('.cf-pick-btn[data-pick="heads"] span');
    const tPickLbl = document.querySelector('.cf-pick-btn[data-pick="tails"] span');
    if (hPick) hPick.src = td.headsImg;
    if (tPick) tPick.src = td.tailsImg;
    if (hPickLbl) hPickLbl.textContent = td.heads;
    if (tPickLbl) tPickLbl.textContent = td.tails;
}

function checkCFReady() {
    const btn = $('cf-flip-btn');
    if (!btn) return;
    const ok = CF.theme && CF.pick && (CF.funMode || (CF.bet >= 10 && CF.bet <= _xp));
    btn.disabled = !ok;
}

async function flipCoin() {
    if (CF.busy) return;
    CF.busy = true;
    const btn = $('cf-flip-btn');
    if (btn) btn.disabled = true;

    // Animate coin
    const coin = $('cf-coin');
    if (coin) {
        coin.classList.remove('flipping');
        void coin.offsetWidth; // reflow
        // Set final rotation based on result (we'll know after API call)
        coin.style.setProperty('--final-rot', '0deg');
        coin.classList.add('flipping');
    }

    try {
        const r = await fetch('/api/casino/coinflip/flip', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ theme: CF.theme, pick: CF.pick, bet: CF.funMode ? 0 : CF.bet, fun_mode: CF.funMode })
        });
        const d = await r.json();
        if (!r.ok) { showCFError(d.error || 'Flip failed'); CF.busy = false; checkCFReady(); return; }

        // Update coin final face
        if (coin) {
            const finalRot = d.result === 'heads' ? '0deg' : '180deg';
            coin.style.setProperty('--final-rot', finalRot);
            // Update face images to match result
            const hFace = coin.querySelector('.mg-coin-face:not(.mg-coin-tails) img');
            const tFace = coin.querySelector('.mg-coin-tails img');
            if (hFace) hFace.src = d.heads_img;
            if (tFace) tFace.src = d.tails_img;
        }

        // Wait for animation
        setTimeout(() => {
            showCFResult(d);
            if (!d.fun_mode) loadXP();
            CF.busy = false;
        }, 1500);

    } catch(e) {
        showCFError(e.message);
        CF.busy = false;
        checkCFReady();
    }
}

function showCFResult(d) {
    const area = $('cf-result-area');
    if (!area) return;

    const won  = d.won;
    const xp   = d.xp_change || 0;
    const cls  = won ? 'win' : 'lose';
    const msg  = won ? `🎉 ${d.result.toUpperCase()}! You win!` : `💀 ${d.result.toUpperCase()}! You lose.`;
    const xpTxt = d.fun_mode ? '' :
        `<div class="mg-xp-change ${xp >= 0 ? 'pos' : 'neg'}">${xp >= 0 ? '+' : ''}${xp.toLocaleString()} XP</div>`;

    area.innerHTML = `
        <div class="mg-result">
            <div class="mg-result-text ${cls}">${msg}</div>
            ${xpTxt}
            <button class="mg-btn" id="cf-again-btn" style="margin-top:10px">Flip Again</button>
        </div>`;
    area.style.display = '';

    if (won) spawnSparkles($('cf-coin-wrap'), '#ffd700');
    if (typeof window._casinoLobbyActivity === 'function') {
        const xpStr = !d.fun_mode && xp !== 0 ? ` (${xp >= 0 ? '+' : ''}${xp.toLocaleString()} XP)` : '';
        window._casinoLobbyActivity(`🪙 Coin Flip: ${d.result.toUpperCase()}${xpStr}`);
    }
}

function resetCF() {
    CF.pick = null;
    const area = $('cf-result-area');
    if (area) area.style.display = 'none';
    document.querySelectorAll('.cf-pick-btn').forEach(b => b.classList.remove('selected'));
    const coin = $('cf-coin');
    if (coin) { coin.classList.remove('flipping'); coin.style.transform = ''; }
    checkCFReady();
}

function showCFError(msg) {
    const el = $('cf-error');
    if (el) { el.textContent = msg; el.style.display = ''; setTimeout(() => el.style.display = 'none', 3500); }
}

// ── RPS ───────────────────────────────────────────────────────────────────────
function buildRPSChoices() {
    const wrap = $('rps-choices-wrap');
    if (!wrap || !RPS.theme) return;
    const choices = RPS_THEMES[RPS.theme];
    if (!choices) return;
    wrap.innerHTML = Object.entries(choices).map(([key, val]) =>
        `<button class="mg-rps-choice" data-choice="${key}">
            <img src="${val.img}" alt="${val.name}">
            <div>${val.name}</div>
        </button>`
    ).join('');
    RPS.choice = null;
}

function checkRPSReady() {
    const btn = $('rps-play-btn');
    if (!btn) return;
    const ok = RPS.theme && RPS.choice && (RPS.funMode || (RPS.bet >= 10 && RPS.bet <= _xp));
    btn.disabled = !ok;
}

async function playRPS() {
    if (RPS.busy) return;
    RPS.busy = true;
    const btn = $('rps-play-btn');
    if (btn) btn.disabled = true;

    // Show arena with question mark for AI
    const arena = $('rps-arena');
    if (arena) {
        arena.style.display = '';
        const pImg = $('rps-player-img'), aImg = $('rps-ai-img');
        const pLbl = $('rps-player-lbl'), aLbl = $('rps-ai-lbl');
        const choice = RPS_THEMES[RPS.theme]?.[RPS.choice];
        if (pImg && choice) { pImg.src = choice.img; pImg.alt = choice.name; }
        if (pLbl && choice) pLbl.textContent = choice.name;
        if (aImg) { aImg.src = '/static/Emojis/Cards/BJ.png'; aImg.alt = '?'; }
        if (aLbl) aLbl.textContent = '?';
    }

    try {
        const r = await fetch('/api/casino/rps/play', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ theme: RPS.theme, choice: RPS.choice, bet: RPS.funMode ? 0 : RPS.bet, fun_mode: RPS.funMode })
        });
        const d = await r.json();
        if (!r.ok) { showRPSError(d.error || 'Play failed'); RPS.busy = false; checkRPSReady(); return; }

        // Reveal AI choice with animation
        setTimeout(() => {
            const aImg = $('rps-ai-img'), aLbl = $('rps-ai-lbl');
            if (aImg) { aImg.src = d.ai_img; aImg.alt = d.ai_name; aImg.classList.add('reveal'); }
            if (aLbl) aLbl.textContent = d.ai_name;

            // Update score
            if (d.result === 'win')  RPS.score.player++;
            if (d.result === 'lose') RPS.score.ai++;
            if (d.result === 'tie')  RPS.score.ties++;
            renderRPSScore();

            showRPSResult(d);
            if (!d.fun_mode) loadXP();
            RPS.busy = false;
        }, 600);

    } catch(e) {
        showRPSError(e.message);
        RPS.busy = false;
        checkRPSReady();
    }
}

function renderRPSScore() {
    const el = $('rps-score-display');
    if (el) el.textContent = `You ${RPS.score.player} — AI ${RPS.score.ai}${RPS.score.ties ? ` (${RPS.score.ties} ties)` : ''}`;
}

function showRPSResult(d) {
    const area = $('rps-result-area');
    if (!area) return;

    const cls = d.result === 'win' ? 'win' : d.result === 'tie' ? 'tie' : 'lose';
    const msg = d.result === 'win' ? '🏆 You Win!' : d.result === 'tie' ? '🤝 Tie!' : '💀 AI Wins!';
    const xp  = d.xp_change || 0;
    const xpTxt = d.fun_mode ? '' :
        `<div class="mg-xp-change ${xp > 0 ? 'pos' : xp < 0 ? 'neg' : 'neu'}">${xp >= 0 ? '+' : ''}${xp.toLocaleString()} XP</div>`;

    area.innerHTML = `
        <div class="mg-result">
            <div class="mg-result-text ${cls}">${msg}</div>
            ${xpTxt}
            <button class="mg-btn" id="rps-again-btn" style="margin-top:8px">Play Again</button>
        </div>`;
    area.style.display = '';

    if (d.result === 'win') spawnSparkles($('rps-arena'), '#2ecc71');
    if (typeof window._casinoLobbyActivity === 'function') {
        const xpStr = !d.fun_mode && xp !== 0 ? ` (${xp >= 0 ? '+' : ''}${xp.toLocaleString()} XP)` : '';
        window._casinoLobbyActivity(`✊ RPS: ${d.player_name} vs ${d.ai_name} — ${d.result.toUpperCase()}${xpStr}`);
    }
}

function resetRPS() {
    RPS.choice = null;
    const area = $('rps-result-area');
    if (area) area.style.display = 'none';
    const arena = $('rps-arena');
    if (arena) arena.style.display = 'none';
    document.querySelectorAll('.mg-rps-choice').forEach(b => b.classList.remove('selected'));
    checkRPSReady();
}

function showRPSError(msg) {
    const el = $('rps-error');
    if (el) { el.textContent = msg; el.style.display = ''; setTimeout(() => el.style.display = 'none', 3500); }
}

// ── Sparkle effect ────────────────────────────────────────────────────────────
function spawnSparkles(parent, color) {
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    for (let i = 0; i < 10; i++) {
        const s = document.createElement('div');
        s.className = 'mg-sparkle';
        s.style.background = color;
        s.style.left = (20 + Math.random() * 60) + '%';
        s.style.top  = (20 + Math.random() * 60) + '%';
        const angle = Math.random() * Math.PI * 2;
        const dist  = 30 + Math.random() * 40;
        s.style.setProperty('--sx', Math.cos(angle) * dist + 'px');
        s.style.setProperty('--sy', Math.sin(angle) * dist + 'px');
        s.style.animationDelay = (Math.random() * 0.2) + 's';
        parent.style.position = 'relative';
        parent.appendChild(s);
        setTimeout(() => s.remove(), 900);
    }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();
