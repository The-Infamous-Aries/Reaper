/* ── Tasks Page JS ──────────────────────────────────────────────────────── */
(function () {
  'use strict';

  console.log('[tasks] IIFE executing');
  try {

  console.log('[tasks] Script loaded and starting initialization...');

  // ── State ──────────────────────────────────────────────────────────────────
  let _slots = [];
  let _prefs = { dm_enabled: false, dm_mode: 'all' };
  let _refreshTimer = null;
  let _goalResetTimer = null;

  // ── Reward display helpers ─────────────────────────────────────────────────
  const REWARD_ICONS = {
    Key1: '🗝️', Key2: '🔑', Key3: '✨',
    chest1: '📦', chest2: '🎁', chest3: '💎', chest4: '🌟',
  };
  const REWARD_LABELS = {
    Key1: 'Key 1', Key2: 'Key 2', Key3: 'Key 3',
    chest1: 'Chest 1', chest2: 'Chest 2', chest3: 'Chest 3', chest4: 'Chest 4',
  };

  function rewardHtml(reward) {
    if (!reward) return '';
    const icon  = REWARD_ICONS[reward.item]  || '🎁';
    const label = REWARD_LABELS[reward.item] || reward.item;
    const count = reward.count > 1 ? ` ×${reward.count}` : '';
    return `<span class="task-reward"><span class="task-reward-icon">${icon}</span>${count} ${label}</span>`;
  }

  // ── Cooldown timer formatting ──────────────────────────────────────────────
  function fmtSeconds(s) {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${sec}s`;
    return `${sec}s`;
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Render daily goal ──────────────────────────────────────────────────────
  function renderGoal(goalSlot) {
    const container = document.getElementById('tasks-goal-container');
    if (!container) return;

    const task    = goalSlot.task;
    const resets  = goalSlot.resets_at || 0;
    const streak  = task?.meta?.streak ?? 0;
    const pct     = task && task.required > 0 ? Math.round((task.progress / task.required) * 100) : 0;

    const streakHtml = streak > 0
      ? `<span class="goal-streak">🔥 ${streak}-day streak</span>`
      : `<span class="goal-streak goal-streak-new">✨ Start your streak today</span>`;

    const chestName = REWARD_LABELS[task?.reward?.item] || task?.reward?.item || 'Chest';
    const chestIcon = REWARD_ICONS[task?.reward?.item] || '📦';

    let bodyHtml = '';
    if (!task || task.dismissed) {
      bodyHtml = `<div class="task-cooldown-display"><i class="fas fa-hourglass-half"></i><span>Loading…</span></div>`;
    } else if (task.completed) {
      const goalClaimed = task.reward_delivered;
      bodyHtml = `
        <div class="task-progress-wrap">
          <div class="task-progress-bar-bg">
            <div class="task-progress-bar-fill goal-bar-fill" style="width:100%"></div>
          </div>
          <div class="task-progress-text">${task.required} / ${task.required}</div>
        </div>
        ${rewardHtml(task.reward)}
        ${goalClaimed
          ? `<div class="task-complete-badge"><i class="fas fa-check-circle"></i> Goal complete — ${chestIcon} ${chestName} delivered!</div>`
          : `<button class="task-claim-btn" id="tasks-claim-goal-btn"><i class="fas fa-gift"></i> Claim Reward</button>`
        }
        <div class="goal-reset-row">Resets in <span class="goal-reset-timer" data-until="${resets}"></span></div>`;
    } else {
      bodyHtml = `
        <div class="task-progress-wrap">
          <div class="task-progress-bar-bg">
            <div class="task-progress-bar-fill goal-bar-fill" style="width:${pct}%"></div>
          </div>
          <div class="task-progress-text">${task.progress} / ${task.required} tasks completed</div>
        </div>
        ${rewardHtml(task.reward)}
        <div class="goal-reset-row">Resets in <span class="goal-reset-timer" data-until="${resets}"></span></div>`;
    }

    container.innerHTML = `
      <div class="goal-card ${task?.completed ? 'completed' : ''}">
        <div class="goal-card-header">
          <span class="goal-badge">DAILY GOAL</span>
          ${streakHtml}
        </div>
        <div class="goal-title">🏆 ${escHtml(task?.label || 'Complete 10 Daily Tasks')}</div>
        <div class="goal-reward-preview">Today's reward: ${chestIcon} <strong>${chestName}</strong></div>
        ${bodyHtml}
      </div>`;

    // Wire up goal claim button if present
    const goalClaimBtn = document.getElementById('tasks-claim-goal-btn');
    if (goalClaimBtn) {
      goalClaimBtn.addEventListener('click', claimGoal);
    }

    startGoalCountdown();
  }

  // ── Render regular slots ───────────────────────────────────────────────────
  function renderSlots() {
    const grid = document.getElementById('tasks-grid');
    if (!grid) return;
    grid.innerHTML = '';

    // slots[0] is the goal — render separately; slots 1-6 go in the grid
    const regular = _slots.slice(1);

    regular.forEach((s) => {
      const idx  = s.slot;
      const card = document.createElement('div');
      card.className = 'task-card';
      card.dataset.slot = idx;

      const badge = `<span class="task-slot-badge">SLOT ${idx}</span>`;

      if (s.on_cooldown) {
        card.classList.add('on-cooldown');
        card.innerHTML = `
          ${badge}
          <div class="task-cooldown-display">
            <i class="fas fa-hourglass-half" style="font-size:1.4rem;opacity:0.5;"></i>
            <span class="task-cooldown-timer" data-until="${s.cooldown_until}" data-slot="${idx}">
              ${fmtSeconds(s.seconds_remaining)}
            </span>
            <span class="task-cooldown-label">New task arriving soon</span>
          </div>`;
      } else if (!s.task || s.task.dismissed) {
        card.classList.add('on-cooldown');
        card.innerHTML = `
          ${badge}
          <div class="task-cooldown-display">
            <i class="fas fa-hourglass-half" style="font-size:1.4rem;opacity:0.5;"></i>
            <span class="task-cooldown-timer">—</span>
            <span class="task-cooldown-label">Loading…</span>
          </div>`;
      } else {
        const task = s.task;
        const pct  = task.required > 0 ? Math.round((task.progress / task.required) * 100) : 0;

        if (task.completed) {
          const claimed = task.reward_claimed;
          card.classList.add('completed');
          card.innerHTML = `
            ${badge}
            <div class="task-label">${escHtml(task.label)}</div>
            <div class="task-progress-wrap">
              <div class="task-progress-bar-bg">
                <div class="task-progress-bar-fill" style="width:100%"></div>
              </div>
              <div class="task-progress-text">${task.required} / ${task.required}</div>
            </div>
            ${rewardHtml(task.reward)}
            ${claimed
              ? `<div class="task-complete-badge"><i class="fas fa-check-circle"></i> Reward collected — new task arriving</div>`
              : `<button class="task-claim-btn" data-slot="${idx}"><i class="fas fa-gift"></i> Claim Reward</button>`
            }`;
        } else {
          card.innerHTML = `
            ${badge}
            <div class="task-label">${escHtml(task.label)}</div>
            <div class="task-progress-wrap">
              <div class="task-progress-bar-bg">
                <div class="task-progress-bar-fill" style="width:${pct}%"></div>
              </div>
              <div class="task-progress-text">${task.progress} / ${task.required}</div>
            </div>
            ${rewardHtml(task.reward)}
            <button class="task-dismiss-btn" data-slot="${idx}">Dismiss (1h cooldown)</button>`;
        }
      }

      grid.appendChild(card);
    });

    grid.querySelectorAll('.task-dismiss-btn').forEach(btn => {
      btn.addEventListener('click', () => dismissTask(parseInt(btn.dataset.slot)));
    });
    grid.querySelectorAll('.task-claim-btn').forEach(btn => {
      btn.addEventListener('click', () => claimTask(parseInt(btn.dataset.slot)));
    });

    startCountdowns();
  }

  // ── Live countdown tickers ─────────────────────────────────────────────────
  function startCountdowns() {
    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => {
      const now = Date.now() / 1000;
      document.querySelectorAll('.task-cooldown-timer[data-until]').forEach(el => {
        const until = parseFloat(el.dataset.until);
        const rem   = Math.max(0, until - now);
        el.textContent = fmtSeconds(rem);
        if (rem <= 0) {
          clearInterval(_refreshTimer);
          loadTasks();
        }
      });
    }, 1000);
  }

  function startGoalCountdown() {
    if (_goalResetTimer) clearInterval(_goalResetTimer);
    _goalResetTimer = setInterval(() => {
      const now = Date.now() / 1000;
      document.querySelectorAll('.goal-reset-timer[data-until]').forEach(el => {
        const until = parseFloat(el.dataset.until);
        const rem   = Math.max(0, until - now);
        el.textContent = fmtSeconds(rem);
        if (rem <= 0) {
          clearInterval(_goalResetTimer);
          loadTasks(); // new UTC day — reload everything
        }
      });
    }, 1000);
  }

  // ── API calls ──────────────────────────────────────────────────────────────
  function loadTasks() {
    var loadingMsg   = document.getElementById('tasks-loading');
    var loginMsg     = document.getElementById('tasks-login-msg');
    var nopetMsg     = document.getElementById('tasks-nopet-msg');
    var errorMsg     = document.getElementById('tasks-error-msg');
    var goalContainer = document.getElementById('tasks-goal-container');
    var gridLabel    = document.getElementById('tasks-grid-label');
    var grid         = document.getElementById('tasks-grid');

    if (loadingMsg)    loadingMsg.style.display    = '';
    if (loginMsg)      loginMsg.style.display      = 'none';
    if (nopetMsg)      nopetMsg.style.display      = 'none';
    if (errorMsg)      errorMsg.style.display      = 'none';
    if (goalContainer) goalContainer.style.display = 'none';
    if (gridLabel)     gridLabel.style.display     = 'none';
    if (grid)          grid.style.display          = 'none';

    fetch('/api/tasks', { credentials: 'include' })
      .then(function(r) {
        if (r.status === 401) { showLoginMsg(); return null; }
        return r.json();
      })
      .then(function(data) {
        if (!data) return;
        if (data.error === 'no_pet') { showNoPetMsg(); return; }
        if (data.error)              { showLoginMsg(); return; }

        _slots = data.slots || [];
        _prefs = data.prefs || { dm_enabled: false, dm_mode: 'all' };

        if (loadingMsg)    loadingMsg.style.display    = 'none';
        if (goalContainer) goalContainer.style.display = '';
        if (gridLabel)     gridLabel.style.display     = '';
        if (grid)          grid.style.display          = '';

        if (_slots[0]) renderGoal(_slots[0]);
        renderSlots();
        updateNavBadge();
      })
      .catch(function(err) {
        console.error('[tasks] loadTasks error:', err);
        showErrorMsg(err.message || 'Unknown error loading tasks.');
      });
  }

  function dismissTask(slot) {
    fetch('/api/tasks/dismiss', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot: slot }),
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.slots) {
          _slots = data.slots;
          if (_slots[0]) renderGoal(_slots[0]);
          renderSlots();
          updateNavBadge();
        }
      })
      .catch(function(e) { console.error('dismissTask error', e); });
  }

  function claimTask(slot) {
    const btn = document.querySelector(`.task-claim-btn[data-slot="${slot}"]`);
    if (btn) { btn.disabled = true; btn.textContent = 'Claiming…'; }
    fetch('/api/tasks/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot: slot }),
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.slots) {
          _slots = data.slots;
          if (_slots[0]) renderGoal(_slots[0]);
          renderSlots();
          updateNavBadge();
        } else if (data.error) {
          console.error('claimTask error:', data.error);
          if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-gift"></i> Claim Reward'; }
        }
      })
      .catch(function(e) {
        console.error('claimTask error', e);
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-gift"></i> Claim Reward'; }
      });
  }

  function claimGoal() {
    const btn = document.getElementById('tasks-claim-goal-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Claiming…'; }
    fetch('/api/tasks/claim-goal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.slots) {
          _slots = data.slots;
          if (_slots[0]) renderGoal(_slots[0]);
          renderSlots();
          updateNavBadge();
        } else if (data.error) {
          console.error('claimGoal error:', data.error);
          if (btn) { btn.disabled = false; btn.textContent = '🎁 Claim Reward'; }
        }
      })
      .catch(function(e) {
        console.error('claimGoal error', e);
        if (btn) { btn.disabled = false; btn.textContent = '🎁 Claim Reward'; }
      });
  }

  function updateNavBadge() {
    const badge = document.getElementById('tasks-nav-badge');
    if (!badge) return;
    // Count incomplete regular tasks only
    const active = _slots.slice(1).filter(s => !s.on_cooldown && s.task && !s.task.completed && !s.task.dismissed).length;
    if (active > 0) {
      badge.textContent = active;
      badge.style.display = '';
    } else {
      badge.style.display = 'none';
    }
  }

  function showNoPetMsg() {
    console.log('[tasks] showNoPetMsg called - hiding loading and showing no pet message');
    const loadingMsg = document.getElementById('tasks-loading');
    if (loadingMsg) {
      loadingMsg.style.display = 'none';
      console.log('[tasks] Loading message hidden');
    }

    const loginMsg = document.getElementById('tasks-login-msg');
    const nopetMsg = document.getElementById('tasks-nopet-msg');
    const errorMsg = document.getElementById('tasks-error-msg');
    const goalContainer = document.getElementById('tasks-goal-container');
    const gridLabel = document.getElementById('tasks-grid-label');
    const grid = document.getElementById('tasks-grid');
    
    if (nopetMsg) {
      nopetMsg.style.display = '';
      console.log('[tasks] No pet message shown');
    } else {
      console.error('[tasks] No pet message element not found!');
    }
    
    if (loginMsg) loginMsg.style.display = 'none';
    if (errorMsg) errorMsg.style.display = 'none';
    if (goalContainer) goalContainer.style.display = 'none';
    if (gridLabel) gridLabel.style.display = 'none';
    if (grid) grid.style.display = 'none';
    
    console.log('[tasks] showNoPetMsg completed');
  }

  function showLoginMsg() {
    console.log('[tasks] showLoginMsg called - hiding loading and showing login message');
    const loadingMsg = document.getElementById('tasks-loading');
    if (loadingMsg) {
      loadingMsg.style.display = 'none';
      console.log('[tasks] Loading message hidden');
    } else {
      console.error('[tasks] Loading message element not found!');
    }

    const loginMsg = document.getElementById('tasks-login-msg');
    const nopetMsg = document.getElementById('tasks-nopet-msg');
    const errorMsg = document.getElementById('tasks-error-msg');
    const goalContainer = document.getElementById('tasks-goal-container');
    const gridLabel = document.getElementById('tasks-grid-label');
    const grid = document.getElementById('tasks-grid');
    
    if (loginMsg) {
      loginMsg.style.display = '';
      console.log('[tasks] Login message shown');
    } else {
      console.error('[tasks] Login message element not found!');
    }
    
    if (nopetMsg) nopetMsg.style.display = 'none';
    if (errorMsg) errorMsg.style.display = 'none';
    if (goalContainer) goalContainer.style.display = 'none';
    if (gridLabel) gridLabel.style.display = 'none';
    if (grid) grid.style.display = 'none';
    
    console.log('[tasks] showLoginMsg completed');
  }

  function showErrorMsg(msg) {
    const loadingMsg = document.getElementById('tasks-loading');
    if (loadingMsg) loadingMsg.style.display = 'none';

    console.log('[tasks] Showing error message:', msg);
    const loginMsg = document.getElementById('tasks-login-msg');
    const nopetMsg = document.getElementById('tasks-nopet-msg');
    const errorMsg = document.getElementById('tasks-error-msg');
    const goalContainer = document.getElementById('tasks-goal-container');
    const gridLabel = document.getElementById('tasks-grid-label');
    const grid = document.getElementById('tasks-grid');
    
    if (errorMsg) { 
      const p = errorMsg.querySelector('p');
      if (p) p.textContent = msg;
      errorMsg.style.display = ''; 
    }
    if (loginMsg) loginMsg.style.display = 'none';
    if (nopetMsg) nopetMsg.style.display = 'none';
    if (goalContainer) goalContainer.style.display = 'none';
    if (gridLabel) gridLabel.style.display = 'none';
    if (grid) grid.style.display = 'none';
  }

  // ── DM Settings Modal ──────────────────────────────────────────────────────
  function openDmModal() {
    const modal = document.getElementById('tasks-dm-modal');
    if (!modal) return;
    document.getElementById('dm-enabled-toggle').checked = !!_prefs.dm_enabled;
    document.getElementById('dm-mode-each').checked = _prefs.dm_mode === 'each';
    document.getElementById('dm-mode-all').checked  = _prefs.dm_mode !== 'each';
    document.getElementById('dm-mode-section').style.display = _prefs.dm_enabled ? '' : 'none';
    modal.style.display = 'flex';
  }

  function closeDmModal() {
    const modal = document.getElementById('tasks-dm-modal');
    if (modal) modal.style.display = 'none';
  }

  function saveDmPrefs() {
    var enabled = document.getElementById('dm-enabled-toggle').checked;
    var mode    = document.getElementById('dm-mode-each').checked ? 'each' : 'all';
    fetch('/api/tasks/dm-prefs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dm_enabled: enabled, dm_mode: mode }),
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.success) {
          _prefs.dm_enabled = data.dm_enabled;
          _prefs.dm_mode    = data.dm_mode;
          closeDmModal();
        }
      })
      .catch(function(e) { console.error('saveDmPrefs error', e); });
  }

  // ── Init ───────────────────────────────────────────────────────────────────
  function init() {
    console.log('[tasks] Initializing tasks page...');
    
    // Check if required DOM elements exist
    const requiredElements = [
      'tasks-login-msg', 'tasks-nopet-msg', 'tasks-error-msg',
      'tasks-goal-container', 'tasks-grid-label', 'tasks-grid'
    ];
    
    for (const id of requiredElements) {
      const el = document.getElementById(id);
      if (!el) {
        console.error(`[tasks] Required element not found: ${id}`);
      } else {
        console.log(`[tasks] Found element: ${id}`);
      }
    }
    
    console.log('[tasks] Starting loadTasks...');
    loadTasks();

    const dmBtn     = document.getElementById('tasks-dm-btn');
    const dmClose   = document.getElementById('tasks-dm-close');
    const dmSave    = document.getElementById('tasks-dm-save');
    const dmToggle  = document.getElementById('dm-enabled-toggle');
    const dmOverlay = document.getElementById('tasks-dm-modal');

    if (dmBtn) {
      dmBtn.addEventListener('click', openDmModal);
      console.log('[tasks] DM button event listener added');
    } else {
      console.warn('[tasks] DM button not found');
    }
    
    if (dmClose) dmClose.addEventListener('click', closeDmModal);
    if (dmSave) dmSave.addEventListener('click', saveDmPrefs);
    if (dmOverlay) dmOverlay.addEventListener('click', e => { if (e.target === dmOverlay) closeDmModal(); });
    if (dmToggle) dmToggle.addEventListener('change', () => {
      document.getElementById('dm-mode-section').style.display = dmToggle.checked ? '' : 'none';
    });
    
    console.log('[tasks] Initialization complete');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  } catch(e) {
    console.error('[tasks] FATAL ERROR in tasks.js:', e);
    var el = document.getElementById('tasks-loading');
    if (el) el.innerHTML = '<p style="color:red">tasks.js error: ' + e.message + '</p>';
  }
})();
