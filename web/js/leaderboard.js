(() => {
    // ── Category definitions ──────────────────────────────────────────────
    // field: key in nation data | fmt: value formatter | emoji prefix (c/m/r/a)
    const CATEGORIES = [
        { id: 'lowest_cost',           label: 'Lowest Cost',                      field: 'gross_cost',              fmt: fmtMoney,  prefix: 'c', asc: true  },
        { id: 'highest_cost',          label: 'Highest Cost',                     field: 'gross_cost',              fmt: fmtMoney,  prefix: 'c', asc: false },
        { id: 'best_net',              label: 'Best Net',                         field: 'net_damage',              fmt: fmtMoney,  prefix: 'n', asc: true, allowNeg: true },
        { id: 'most_damage',           label: 'Most Damage Dealt',                field: 'total_damages',           fmt: fmtMoney,  prefix: 'n', asc: false },
        { id: 'most_wins',             label: 'Most Wins',                        field: 'wins_count',              fmt: fmtInt,    prefix: 'd', asc: false },
        { id: 'most_losses',           label: 'Most Losses',                      field: 'losses_count',            fmt: fmtInt,    prefix: 'p', asc: false },
        { id: 'most_draws',            label: 'Most Draws',                       field: 'draws_count',             fmt: fmtInt,    prefix: 'd', asc: false },
        { id: 'most_peace',            label: 'Most Peace',                       field: 'peace_count',             fmt: fmtInt,    prefix: 'p', asc: false },
        { id: 'most_off_wars',         label: 'Most Offensive Wars',              field: 'offense_wars_count',      fmt: fmtInt,    prefix: 'c', asc: false },
        { id: 'most_def_wars',         label: 'Most Defensive Wars',              field: 'defense_wars_count',      fmt: fmtInt,    prefix: 'c', asc: false },
        { id: 'most_raid_wars',        label: 'Most Raid Wars',                   field: 'raid_wars_count',         fmt: fmtInt,    prefix: 'w', asc: false },
        { id: 'most_attrition_wars',   label: 'Most Attrition Wars',              field: 'attrition_wars_count',    fmt: fmtInt,    prefix: 'w', asc: false },
        { id: 'most_money_loot',       label: 'Most Money Looted/Stolen',         field: 'gains_cash',              fmt: fmtMoney,  prefix: 'm', asc: false },
        { id: 'most_res_loot',         label: 'Most Resource Value Looted',       field: 'gains_res_total',         fmt: fmtMoney,  prefix: 'm', asc: false },
        { id: 'most_infra_lvl',        label: 'Most Infra Levels Destroyed',      field: 'enemy_infra_destroyed',   fmt: fmtNum,    prefix: 'r', asc: false },
        { id: 'most_infra_val',        label: 'Most Infra Value Destroyed',       field: 'enemy_infra_destroyed_value', fmt: fmtMoney, prefix: 'r', asc: false },
        { id: 'most_soldiers_killed',  label: 'Most Soldiers Killed',             field: 'enemy_soldiers_killed',   fmt: fmtInt,    prefix: 'k', asc: false },
        { id: 'most_tanks_killed',     label: 'Most Tanks Killed',                field: 'enemy_tanks_killed',      fmt: fmtInt,    prefix: 'k', asc: false },
        { id: 'most_aircraft_killed',  label: 'Most Aircraft Killed',             field: 'enemy_aircraft_killed',   fmt: fmtInt,    prefix: 'k', asc: false },
        { id: 'most_ships_killed',     label: 'Most Ships Killed',                field: 'enemy_ships_killed',      fmt: fmtInt,    prefix: 'k', asc: false },
        { id: 'most_soldiers_lost',    label: 'Most Soldiers Lost',               field: 'soldiers_lost',           fmt: fmtInt,    prefix: 'l', asc: false },
        { id: 'most_tanks_lost',       label: 'Most Tanks Lost',                  field: 'tanks_lost',              fmt: fmtInt,    prefix: 'l', asc: false },
        { id: 'most_aircraft_lost',    label: 'Most Aircraft Lost',               field: 'aircraft_lost',           fmt: fmtInt,    prefix: 'l', asc: false },
        { id: 'most_ships_lost',       label: 'Most Ships Lost',                  field: 'ships_lost',              fmt: fmtInt,    prefix: 'l', asc: false },
        { id: 'most_missiles_sent',    label: 'Most Missiles Sent',               field: 'missiles_hit',            fmt: fmtInt,    prefix: 'a', asc: false },
        { id: 'most_missiles_miss',    label: 'Most Missiles Missed',             field: 'missiles_missed',         fmt: fmtInt,    prefix: 'a', asc: false },
        { id: 'most_missiles_eat',     label: 'Most Missiles Eaten',              field: 'missiles_eaten',          fmt: fmtInt,    prefix: 'a', asc: false },
        { id: 'most_missiles_blk',     label: 'Most Missiles Blocked',            field: 'missiles_blocked',        fmt: fmtInt,    prefix: 'a', asc: false },
        { id: 'most_nukes_sent',       label: 'Most Nukes Sent',                  field: 'nukes_hit',               fmt: fmtInt,    prefix: 'a', asc: false },
        { id: 'most_nukes_miss',       label: 'Most Nukes Missed',                field: 'nukes_missed',            fmt: fmtInt,    prefix: 'a', asc: false },
        { id: 'most_nukes_eat',        label: 'Most Nukes Eaten',                 field: 'nukes_eaten',             fmt: fmtInt,    prefix: 'a', asc: false },
        { id: 'most_nukes_blk',        label: 'Most Nukes Blocked',               field: 'nukes_blocked',           fmt: fmtInt,    prefix: 'a', asc: false },
    ];

    // Category icons (Watcher emojis for card headers)
    const CAT_ICONS = {
        lowest_cost:           '/static/Emojis/Watcher/cost.png',
        highest_cost:          '/static/Emojis/Watcher/cost.png',
        best_net:              '/static/Emojis/Watcher/net.png',
        most_damage:           '/static/Emojis/Watcher/damages.png',
        most_off_wars:         '/static/Emojis/Watcher/off.png',
        most_def_wars:         '/static/Emojis/Watcher/def.png',
        most_raid_wars:        '/static/Emojis/Military/raid.png',
        most_attrition_wars:   '/static/Emojis/Military/attrition.png',
        most_wins:             '/static/Emojis/Military/win.png',
        most_losses:           '/static/Emojis/Military/lose.png',
        most_draws:            '/static/Emojis/Military/draw.png',
        most_peace:            '/static/Emojis/Military/peace.png',
        most_money_loot:       '/static/Emojis/Watcher/loot.png',
        most_res_loot:         '/static/Emojis/Watcher/loot.png',
        most_infra_lvl:        '/static/Emojis/Watcher/infra.png',
        most_infra_val:        '/static/Emojis/Watcher/infra.png',
        most_soldiers_killed:  '/static/Emojis/Watcher/soldier.png',
        most_tanks_killed:     '/static/Emojis/Watcher/tank.png',
        most_aircraft_killed:  '/static/Emojis/Watcher/jet.png',
        most_ships_killed:     '/static/Emojis/Watcher/ship.png',
        most_soldiers_lost:    '/static/Emojis/Watcher/soldier.png',
        most_tanks_lost:       '/static/Emojis/Watcher/tank.png',
        most_aircraft_lost:    '/static/Emojis/Watcher/jet.png',
        most_ships_lost:       '/static/Emojis/Watcher/ship.png',
        most_missiles_sent:    '/static/Emojis/Watcher/missile.png',
        most_missiles_miss:    '/static/Emojis/Watcher/missile.png',
        most_missiles_eat:     '/static/Emojis/Watcher/missile.png',
        most_missiles_blk:     '/static/Emojis/Watcher/missile.png',
        most_nukes_sent:       '/static/Emojis/Watcher/bomb.png',
        most_nukes_miss:       '/static/Emojis/Watcher/bomb.png',
        most_nukes_eat:        '/static/Emojis/Watcher/bomb.png',
        most_nukes_blk:        '/static/Emojis/Watcher/bomb.png',
    };

    // ── Formatters ────────────────────────────────────────────────────────
    function fmtMoney(v) {
        if (v === null || v === undefined) return '—';
        const abs = Math.abs(v);
        if (abs >= 1e9) return '$' + (v / 1e9).toFixed(2) + 'B';
        if (abs >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'M';
        if (abs >= 1e3) return '$' + (v / 1e3).toFixed(1) + 'K';
        return '$' + v.toFixed(0);
    }
    function fmtNum(v) {
        if (v === null || v === undefined) return '—';
        if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M';
        if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'K';
        return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    function fmtInt(v) {
        if (v === null || v === undefined) return '—';
        return Math.round(v).toLocaleString();
    }

    // ── Date helpers ──────────────────────────────────────────────────────
    function toISO(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    // Periods loaded from API — keyed by period id string or {start,end,label} object
    // _periodMap holds the resolved {start, end, label} for named periods
    const _periodMap = {};   // 'this_month' | 'this_week' → {start, end, label}

    function getPeriodRange(period) {
        if (typeof period === 'object' && period !== null) return period;
        return _periodMap[period] || null;
    }

    // ── Data enrichment ───────────────────────────────────────────────────
    function enrichNation(n) {
        // gains_cash and gains_res_* live inside loot_breakdown (same as watch.html)
        const lb = n.loot_breakdown || {};
        n.gains_cash = lb.cash || 0;
        const LOOT_RES = ['coal','oil','uranium','iron','bauxite','lead','gasoline','munitions','steel','aluminum','food'];
        LOOT_RES.forEach(r => {
            n[`gains_res_${r}`] = (lb.resources || {})[r]?.value || 0;
        });
        n.gains_res_total = LOOT_RES.reduce((s, r) => s + (n[`gains_res_${r}`] || 0), 0);

        // missiles_lost = missiles the nation fired (consumed on launch = "sent")
        // missiles_eaten = enemy missiles that successfully hit us (infra_destroyed > 0)
        // missiles_blocked = enemy missiles we blocked (infra_destroyed == 0)
        // missiles_missed = our missiles that enemy blocked (infra_destroyed == 0)
        n.missiles_used = n.missiles_lost ?? null;
        n.nukes_used = n.nukes_lost ?? null;
        // blocked/missed/eaten fields come directly from the API — ensure they exist
        n.missiles_blocked = n.missiles_blocked ?? 0;
        n.nukes_blocked    = n.nukes_blocked    ?? 0;
        n.missiles_missed  = n.missiles_missed  ?? 0;
        n.nukes_missed     = n.nukes_missed     ?? 0;
        n.missiles_eaten   = n.missiles_eaten   ?? 0;
        n.nukes_eaten      = n.nukes_eaten      ?? 0;
        n.missiles_hit     = n.missiles_hit     ?? 0;
        n.nukes_hit        = n.nukes_hit        ?? 0;
        // enemy unit kills
        n.enemy_soldiers_killed = n.enemy_soldiers_killed ?? 0;
        n.enemy_tanks_killed    = n.enemy_tanks_killed    ?? 0;
        n.enemy_aircraft_killed = n.enemy_aircraft_killed ?? 0;
        n.enemy_ships_killed    = n.enemy_ships_killed    ?? 0;
        return n;
    }

    // ── Ranking ───────────────────────────────────────────────────────────
    function rankNations(nations, field, asc, allowNeg) {
        const list = Object.values(nations)
            .map(n => enrichNation({ ...n }))
            .filter(n => {
                const v = n[field];
                if (v === null || v === undefined || isNaN(v)) return false;
                if (!allowNeg && v === 0) return false;
                return true;
            });
        list.sort((a, b) => asc ? a[field] - b[field] : b[field] - a[field]);

        // Assign dense ranks and collect into rank groups
        // Returns array of {rank, value, nations:[]} — only ranks 1-3 (dense)
        const groups = [];
        let denseRank = 1;
        for (let i = 0; i < list.length; i++) {
            if (i > 0 && list[i][field] !== list[i - 1][field]) {
                denseRank = i + 1;
            }
            if (denseRank > 3) break;
            const last = groups[groups.length - 1];
            if (last && last.rank === denseRank) {
                last.nations.push(list[i]);
            } else {
                groups.push({ rank: denseRank, value: list[i][field], nations: [list[i]] });
            }
        }
        return groups;
    }

    // ── Render ────────────────────────────────────────────────────────────
    function rankImg(rank, prefix) {
        return `/static/Emojis/Leaderboards/${rank}${prefix}.png`;
    }

    // ── Tie Modal ─────────────────────────────────────────────────────────
    const _tieModal = document.getElementById('lb-tie-modal');
    const _tieModalClose = document.getElementById('lb-tie-modal-close');
    if (_tieModal && _tieModalClose) {
        _tieModalClose.addEventListener('click', () => _tieModal.classList.remove('visible'));
        _tieModal.addEventListener('click', e => { if (e.target === _tieModal) _tieModal.classList.remove('visible'); });
    }
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && _tieModal) _tieModal.classList.remove('visible'); });

    function renderCard(cat, nations) {
        const groups = rankNations(nations, cat.field, cat.asc, cat.allowNeg);
        const icon = CAT_ICONS[cat.id] || '/static/Emojis/Watcher/war.png';

        let rows = '';
        if (groups.length === 0) {
            rows = `<div class="lb-empty">No data for this period</div>`;
        } else {
            rows = groups.map(({ rank, value, nations: tied }) => {
                const isTie = tied.length > 1;
                // Store field on each nation for modal value display
                tied.forEach(n => n._field = cat.field);
                const displayName = isTie
                    ? `${tied.length} Tied for #${rank}`
                    : escHtml(tied[0].name);
                const tooltip = isTie
                    ? `Click to see all ${tied.length} tied nations`
                    : escHtml(tied[0].name);
                const tiedData = isTie
                    ? ` data-tied="${escHtml(JSON.stringify(tied.map(n => ({ name: n.name, val: n[cat.field] }))))}"
                        data-rank="${rank}" data-prefix="${cat.prefix}"
                        data-cat="${escHtml(cat.label)}" data-value="${value}"
                        data-fmt="${cat.id}"`
                    : '';
                return `<div class="lb-row${isTie ? ' lb-row--tied' : ''}" title="${tooltip}"${tiedData}>
                    <img class="lb-rank-img" src="${rankImg(rank, cat.prefix)}" alt="${rank}">
                    <span class="lb-nation">${displayName}</span>
                    <span class="lb-value">${cat.fmt(value)}</span>
                    ${isTie ? `<span class="lb-tie-badge">👥</span>` : ''}
                </div>`;
            }).join('');
        }

        return `<div class="lb-card">
            <div class="lb-card-header">
                <img class="lb-card-icon" src="${icon}" alt="">
                <p class="lb-card-title">${escHtml(cat.label)}</p>
            </div>
            <div class="lb-podium">${rows}</div>
        </div>`;
    }

    function escHtml(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function setStatus(msg, isError) {
        const el = document.getElementById('lb-status');
        el.textContent = msg;
        el.style.display = msg ? 'block' : 'none';
        el.classList.toggle('is-error', !!isError);
    }

    // ── Fetch & render ────────────────────────────────────────────────────
    let activePeriod = 'this_month';
    let fetchToken = 0;

    async function load(period) {
        const token = ++fetchToken;
        const range = getPeriodRange(period);
        if (!range) return;

        document.getElementById('lb-period-display').textContent = range.label;
        document.getElementById('lb-war-count').textContent = '…';
        document.getElementById('lb-loading').style.display = 'grid';
        document.getElementById('lb-grid').style.display = 'none';
        setStatus('');

        try {
            const url = `/api/watch/wars?start_date=${range.start}&end_date=${range.end}`;
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (token !== fetchToken) return;

            if (data.error) {
                setStatus(data.error, true);
                document.getElementById('lb-loading').style.display = 'none';
                return;
            }

            const nations = data.nations || {};
            const warCount = data.meta?.war_count ?? Object.keys(nations).length;
            document.getElementById('lb-war-count').textContent = warCount.toLocaleString();

            const grid = document.getElementById('lb-grid');
            grid.innerHTML = CATEGORIES.map(cat => renderCard(cat, nations)).join('');
            document.getElementById('lb-loading').style.display = 'none';
            grid.style.display = 'grid';
        } catch (err) {
            if (token !== fetchToken) return;
            setStatus('Failed to load leaderboard data.', true);
            document.getElementById('lb-loading').style.display = 'none';
        }
    }

    // ── Tab switching ─────────────────────────────────────────────────────
    // Simple tabs (this_month, this_week)
    document.querySelectorAll('.lb-tab[data-period]').forEach(btn => {
        btn.addEventListener('click', () => {
            setActiveTab(null);
            btn.classList.add('active');
            activePeriod = btn.dataset.period;
            load(activePeriod);
        });
    });

    // Dropdown groups
    function setActiveTab(subItem) {
        document.querySelectorAll('.lb-tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.lb-sub-item').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.lb-tab-group').forEach(g => g.classList.remove('open'));
        const cr = document.getElementById('lb-custom-range');
        if (cr) cr.classList.remove('visible');
        if (subItem) subItem.classList.add('active');
    }

    function setupDropdown(groupId, btnId) {
        const group = document.getElementById(groupId);
        const btn = document.getElementById(btnId);
        if (!group || !btn) return;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = group.classList.contains('open');
            document.querySelectorAll('.lb-tab-group').forEach(g => g.classList.remove('open'));
            if (!isOpen) group.classList.add('open');
        });
    }
    setupDropdown('prev-months-group', 'prev-months-btn');
    setupDropdown('prev-weeks-group', 'prev-weeks-btn');

    // Custom range picker
    const customBtn = document.getElementById('custom-range-btn');
    const customPanel = document.getElementById('lb-custom-range');
    const startInput = document.getElementById('lb-start-date');
    const endInput = document.getElementById('lb-end-date');

    let validDates = []; // sorted ASC, populated from /api/watch/periods

    function applyDateConstraints(dates) {
        if (!dates || !dates.length) return;
        validDates = dates;
        if (startInput) {
            startInput.min = dates[0];
            startInput.max = dates[dates.length - 1];
            startInput.value = dates[0];
        }
        if (endInput) {
            endInput.min = dates[0];
            endInput.max = dates[dates.length - 1];
            endInput.value = dates[dates.length - 1];
        }
    }

    function snapToValid(value, snapBack) {
        if (!validDates.length || validDates.includes(value)) return value;
        // snapBack=true → find nearest date <= value; false → nearest >= value
        if (snapBack) return [...validDates].reverse().find(d => d <= value) || validDates[0];
        return validDates.find(d => d >= value) || validDates[validDates.length - 1];
    }

    if (startInput) startInput.addEventListener('change', () => {
        startInput.value = snapToValid(startInput.value, true);
        if (endInput && endInput.value < startInput.value) endInput.value = startInput.value;
    });
    if (endInput) endInput.addEventListener('change', () => {
        endInput.value = snapToValid(endInput.value, false);
        if (startInput && startInput.value > endInput.value) startInput.value = endInput.value;
    });

    if (customBtn) customBtn.addEventListener('click', () => {
        if (!customPanel) return;
        const isOpen = customPanel.classList.contains('visible');
        if (!isOpen) {
            setActiveTab(null);
            customBtn.classList.add('active');
            document.querySelectorAll('.lb-tab-group').forEach(g => g.classList.remove('open'));
        }
        customPanel.classList.toggle('visible', !isOpen);
        if (isOpen) customBtn.classList.remove('active');
    });

    const applyRangeBtn = document.getElementById('lb-apply-range');
    if (applyRangeBtn) applyRangeBtn.addEventListener('click', () => {
        const start = startInput ? startInput.value : '';
        const end = endInput ? endInput.value : '';
        if (!start || !end) return;
        if (end < start) { setStatus('End date must be after start date.', true); return; }
        setStatus('');
        const label = `${start} – ${end}`;
        activePeriod = { start, end, label };
        loadCustomRange(activePeriod);
    });

    document.addEventListener('click', () => {
        document.querySelectorAll('.lb-tab-group').forEach(g => g.classList.remove('open'));
    });

    // ── Load available periods from API ───────────────────────────────────
    async function loadPeriods() {
        try {
            const res = await fetch('/api/watch/periods');
            if (!res.ok) return;
            const data = await res.json();

            if (data.dates && data.dates.length) applyDateConstraints(data.dates);

            const monthsMenu = document.getElementById('prev-months-menu');
            const weeksMenu  = document.getElementById('prev-weeks-menu');
            const months = data.months || [];
            const weeks  = data.weeks  || [];

            // ── Wire up "This Month" tab from API data ────────────────────
            const currentMonth = months.find(m => m.is_current);
            if (currentMonth) {
                _periodMap['this_month'] = { start: currentMonth.start, end: currentMonth.end, label: currentMonth.label };
            } else {
                // No data yet for current month — disable the tab
                const btn = document.querySelector('.lb-tab[data-period="this_month"]');
                if (btn) { btn.disabled = true; btn.title = 'No data for current month'; }
            }

            // ── Wire up "This Week" tab from API data ─────────────────────
            const currentWeek = weeks.find(w => w.is_current);
            if (currentWeek) {
                _periodMap['this_week'] = { start: currentWeek.start, end: currentWeek.end, label: currentWeek.label };
            } else {
                const btn = document.querySelector('.lb-tab[data-period="this_week"]');
                if (btn) { btn.disabled = true; btn.title = 'No data for current week'; }
            }

            // ── Months dropdown — ALL months, current labeled ─────────────
            if (months.length === 0) {
                monthsMenu.innerHTML = '<div class="lb-sub-item" style="color:var(--text-secondary);cursor:default;">No data</div>';
            } else {
                monthsMenu.innerHTML = months.map(m => {
                    const label = m.is_current ? `${m.label} ★` : m.label;
                    return `<button class="lb-sub-item${m.is_current ? ' lb-sub-item--current' : ''}" data-start="${m.start}" data-end="${m.end}" data-label="${m.label}">${label}</button>`;
                }).join('');
            }

            // ── Weeks dropdown — ALL weeks, current labeled ───────────────
            if (weeks.length === 0) {
                weeksMenu.innerHTML = '<div class="lb-sub-item" style="color:var(--text-secondary);cursor:default;">No data</div>';
            } else {
                weeksMenu.innerHTML = weeks.map(w => {
                    const label = w.is_current ? `${w.label} ★` : w.label;
                    return `<button class="lb-sub-item${w.is_current ? ' lb-sub-item--current' : ''}" data-start="${w.start}" data-end="${w.end}" data-label="${w.label}">${label}</button>`;
                }).join('');
            }

            // ── Attach click handlers to all dropdown items ───────────────
            document.querySelectorAll('.lb-sub-item[data-start]').forEach(item => {
                item.addEventListener('click', (e) => {
                    e.stopPropagation();
                    setActiveTab(item);
                    document.querySelectorAll('.lb-tab-group').forEach(g => g.classList.remove('open'));
                    activePeriod = { start: item.dataset.start, end: item.dataset.end, label: item.dataset.label };
                    loadCustomRange(activePeriod);
                });
            });

            // ── Now that _periodMap is populated, load the default period ──
            // Re-trigger the initial load so it uses the API-sourced date range
            load(activePeriod);

        } catch (e) {
            console.warn('Could not load periods:', e);
        }
    }

    async function loadCustomRange(range) {
        const token = ++fetchToken;
        document.getElementById('lb-period-display').textContent = range.label;
        document.getElementById('lb-war-count').textContent = '…';
        document.getElementById('lb-loading').style.display = 'grid';
        document.getElementById('lb-grid').style.display = 'none';
        setStatus('');
        try {
            const url = `/api/watch/wars?start_date=${range.start}&end_date=${range.end}`;
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (token !== fetchToken) return;
            if (data.error) { setStatus(data.error, true); document.getElementById('lb-loading').style.display = 'none'; return; }
            const nations = data.nations || {};
            document.getElementById('lb-war-count').textContent = (data.meta?.war_count ?? Object.keys(nations).length).toLocaleString();
            const grid = document.getElementById('lb-grid');
            grid.innerHTML = CATEGORIES.map(cat => renderCard(cat, nations)).join('');
            document.getElementById('lb-loading').style.display = 'none';
            grid.style.display = 'grid';
        } catch (err) {
            if (token !== fetchToken) return;
            setStatus('Failed to load leaderboard data.', true);
            document.getElementById('lb-loading').style.display = 'none';
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────
    // loadPeriods() populates _periodMap then calls load() itself
    loadPeriods();

    // ── Tied-row click delegation ─────────────────────────────────────────
    // Build a fmt lookup so we can format values in the modal
    const _fmtById = {};
    CATEGORIES.forEach(c => { _fmtById[c.id] = c.fmt; });

    const _lbGrid = document.getElementById('lb-grid');
    if (_lbGrid) _lbGrid.addEventListener('click', e => {
        const row = e.target.closest('.lb-row--tied');
        if (!row) return;
        const rank   = parseInt(row.dataset.rank, 10);
        const prefix = row.dataset.prefix;
        const catId  = row.dataset.fmt;
        const catLabel = row.dataset.cat;
        const value  = parseFloat(row.dataset.value);
        const fmt    = _fmtById[catId] || (v => v);
        let tied;
        try { tied = JSON.parse(row.dataset.tied); } catch { return; }

        if (_tieModal) {
            const img = document.getElementById('lb-tie-modal-img');
            if (img) { img.src = rankImg(rank, prefix); img.alt = `#${rank}`; }
            const titleEl = document.getElementById('lb-tie-modal-title');
            if (titleEl) titleEl.textContent = catLabel;
            const subtitleEl = document.getElementById('lb-tie-modal-subtitle');
            if (subtitleEl) subtitleEl.textContent = `${tied.length} nations tied for #${rank} · ${fmt(value)}`;
            const listEl = document.getElementById('lb-tie-modal-list');
            if (listEl) listEl.innerHTML = tied.map((n, i) =>
                `<div class="lb-tie-item">
                    <div class="lb-tie-item-num">${i + 1}</div>
                    <span class="lb-tie-item-name">${escHtml(n.name)}</span>
                    <span class="lb-tie-item-value">${fmt(n.val)}</span>
                </div>`
            ).join('');
            _tieModal.classList.add('visible');
        }
    });
})();
