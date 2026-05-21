
/**
 * pet_game_loop.js  —  GPP Frontend Implementation
 * =================================================
 * Implements four Game Programming Patterns for the My Pet page:
 *
 *   1. STATE MACHINE  — PetUIStateMachine tracks what the UI is doing
 *      (idle / animating / waiting_server / battle) and prevents
 *      overlapping actions.
 *
 *   2. EVENT QUEUE    — PetEventQueue batches animation events from
 *      server responses and drains them in order, one per frame tick,
 *      so animations never cascade or overlap.
 *
 *   3. GAME LOOP      — PetGameLoop runs at 60 FPS via
 *      requestAnimationFrame.  Each tick it drains one event from the
 *      queue and drives smooth number/bar interpolations.
 *
 *   4. COMPONENT      — Separate renderer objects (StatBarRenderer,
 *      XpBarRenderer, ParticleRenderer, NumberPopRenderer) each own
 *      one visual concern and are updated by the game loop.
 *
 * Usage (mypet.js calls these after every server response):
 *
 *   PetGameLoop.start();                    // call once on page load
 *   PetEventQueue.push(response.animation); // after train/mission/play
 *   PetEventQueue.push(response.animations);// after battle turn (array)
 *
 * The loop auto-stops when the page is hidden and resumes on visibility.
 */

// ─────────────────────────────────────────────────────────────────────────────
// 1. STATE MACHINE
// ─────────────────────────────────────────────────────────────────────────────

var PetUIState = {
    IDLE:           'idle',
    ANIMATING:      'animating',
    WAITING_SERVER: 'waiting_server',
    IN_BATTLE:      'in_battle',
};

var PetUIStateMachine = (function () {
    var _current = PetUIState.IDLE;

    // Valid transitions: from -> [allowed targets]
    var _transitions = {
        idle:           [PetUIState.ANIMATING, PetUIState.WAITING_SERVER, PetUIState.IN_BATTLE],
        animating:      [PetUIState.IDLE, PetUIState.ANIMATING],
        waiting_server: [PetUIState.IDLE, PetUIState.ANIMATING],
        in_battle:      [PetUIState.IDLE, PetUIState.ANIMATING],
    };

    function canTransition(target) {
        var allowed = _transitions[_current] || [];
        return allowed.indexOf(target) !== -1;
    }

    function transition(target) {
        if (!canTransition(target)) {
            console.warn('[PetUI] Invalid transition: ' + _current + ' -> ' + target);
            return false;
        }
        _current = target;
        return true;
    }

    function get() { return _current; }
    function is(state) { return _current === state; }
    function isIdle() { return _current === PetUIState.IDLE; }
    function isBusy() { return _current !== PetUIState.IDLE; }

    // Force-reset (e.g. on page reload or error)
    function reset() { _current = PetUIState.IDLE; }

    return { get: get, is: is, isIdle: isIdle, isBusy: isBusy,
             transition: transition, canTransition: canTransition, reset: reset };
})();

// ─────────────────────────────────────────────────────────────────────────────
// 2. EVENT QUEUE
// ─────────────────────────────────────────────────────────────────────────────

var PetEventQueue = (function () {
    var _queue = [];

    /**
     * Push one animation event or an array of events from a server response.
     * Each event must have: { type, duration_ms, data }
     */
    function push(eventOrArray) {
        if (!eventOrArray) return;
        if (Array.isArray(eventOrArray)) {
            eventOrArray.forEach(function (e) { if (e && e.type) _queue.push(e); });
        } else if (eventOrArray.type) {
            _queue.push(eventOrArray);
        }
    }

    /** Dequeue and return the next event, or null if empty. */
    function shift() {
        return _queue.length ? _queue.shift() : null;
    }

    /** Peek at the next event without removing it. */
    function peek() {
        return _queue.length ? _queue[0] : null;
    }

    function clear() { _queue = []; }
    function size()  { return _queue.length; }

    return { push: push, shift: shift, peek: peek, clear: clear, size: size };
})();

// ─────────────────────────────────────────────────────────────────────────────
// 3. COMPONENT — XP Bar Renderer
// ─────────────────────────────────────────────────────────────────────────────

var XpBarRenderer = (function () {
    var _current  = 0;   // current displayed percentage (0-100)
    var _target   = 0;   // target percentage
    var _speed    = 0.08; // lerp factor per frame (~60fps → ~0.5s to close gap)
    var _oldXp    = 0;
    var _newXp    = 0;
    var _maxXp    = 1;
    var _active   = false;

    function start(oldPct, newPct, oldXp, newXp, maxXp) {
        _current = oldPct;
        _target  = newPct;
        _oldXp   = oldXp;
        _newXp   = newXp;
        _maxXp   = maxXp;
        _active  = true;
    }

    /**
     * Called every game-loop tick.
     * Returns true while still animating, false when done.
     */
    function tick() {
        if (!_active) return false;

        _current += (_target - _current) * _speed;

        // Snap when close enough
        if (Math.abs(_target - _current) < 0.05) {
            _current = _target;
            _active  = false;
        }

        _render();
        return _active;
    }

    function _render() {
        var bar = document.querySelector('.mp-xp-bar');
        if (bar) bar.style.width = _current.toFixed(2) + '%';

        // Interpolate the XP number display
        var progress = _target > 0 ? (_current / _target) : 1;
        var displayed = Math.round(_oldXp + (_newXp - _oldXp) * Math.min(progress, 1));
        var label = document.querySelector('.mp-xp-label');
        if (label) label.textContent = displayed.toLocaleString() + ' / ' + _maxXp.toLocaleString() + ' XP';
    }

    function isActive() { return _active; }

    return { start: start, tick: tick, isActive: isActive };
})();

// ─────────────────────────────────────────────────────────────────────────────
// 3. COMPONENT — Stat Number Pop Renderer
// ─────────────────────────────────────────────────────────────────────────────

var NumberPopRenderer = (function () {
    var _pops = [];  // active pop objects

    /**
     * Spawn a floating number pop anchored to a DOM element.
     * @param {string} text      — e.g. "+3 ATT" or "-2 DEF"
     * @param {string} color     — CSS color string
     * @param {Element} anchor   — DOM element to float above
     */
    function spawn(text, color, anchor) {
        if (!anchor) return;
        var rect = anchor.getBoundingClientRect();
        var el   = document.createElement('div');
        el.className = 'pgp-number-pop';
        el.textContent = text;
        el.style.cssText = [
            'position:fixed',
            'left:' + (rect.left + rect.width / 2) + 'px',
            'top:'  + (rect.top  - 8) + 'px',
            'color:' + color,
            'font-family:Orbitron,sans-serif',
            'font-size:0.9rem',
            'font-weight:700',
            'pointer-events:none',
            'z-index:9997',
            'text-shadow:0 0 8px ' + color,
            'transform:translateX(-50%)',
            'opacity:1',
            'transition:none',
        ].join(';');
        document.body.appendChild(el);
        _pops.push({ el: el, age: 0, duration: 60 }); // 60 frames ~1s
    }

    /** Tick all active pops. Call once per game-loop frame. */
    function tick() {
        var alive = [];
        _pops.forEach(function (pop) {
            pop.age++;
            var progress = pop.age / pop.duration;
            var y = -40 * progress;          // float upward 40px
            var opacity = 1 - progress;
            pop.el.style.transform = 'translateX(-50%) translateY(' + y + 'px)';
            pop.el.style.opacity   = opacity.toFixed(3);
            if (pop.age < pop.duration) {
                alive.push(pop);
            } else {
                if (pop.el.parentNode) pop.el.parentNode.removeChild(pop.el);
            }
        });
        _pops = alive;
    }

    function clear() {
        _pops.forEach(function (p) { if (p.el.parentNode) p.el.parentNode.removeChild(p.el); });
        _pops = [];
    }

    return { spawn: spawn, tick: tick, clear: clear };
})();

// ─────────────────────────────────────────────────────────────────────────────
// 3. COMPONENT — Particle Renderer
// ─────────────────────────────────────────────────────────────────────────────

var ParticleRenderer = (function () {
    var _particles = [];

    var EFFECTS = {
        sparkle_up:   { count: 12, spread: 40, speed: 2.5, color: '#ffd700', shape: 'circle' },
        shake_down:   { count: 8,  spread: 30, speed: 1.8, color: '#e74c3c', shape: 'circle' },
        xp_burst:     { count: 20, spread: 60, speed: 3.0, color: '#2ecc71', shape: 'star'   },
        fail_flash:   { count: 6,  spread: 25, speed: 1.5, color: '#e74c3c', shape: 'circle' },
        float_up:     { count: 10, spread: 50, speed: 2.0, color: '#ffd700', shape: 'circle' },
        level_burst:  { count: 30, spread: 80, speed: 4.0, color: '#ffd700', shape: 'star'   },
        level_drop:   { count: 15, spread: 50, speed: 2.5, color: '#e74c3c', shape: 'circle' },
        attack_hit:   { count: 8,  spread: 35, speed: 3.5, color: '#e74c3c', shape: 'circle' },
        shield_block: { count: 6,  spread: 30, speed: 2.0, color: '#3498db', shape: 'circle' },
        charge_glow:  { count: 10, spread: 40, speed: 2.5, color: '#f1c40f', shape: 'star'   },
        super_effective: { count: 16, spread: 55, speed: 3.5, color: '#ff9800', shape: 'star' },
        not_effective:   { count: 5,  spread: 20, speed: 1.5, color: '#95a5a6', shape: 'circle' },
        chest_open:   { count: 25, spread: 70, speed: 3.5, color: '#ffd700', shape: 'star'   },
    };

    /**
     * Spawn particles at a screen position.
     * @param {string} effectName  — key in EFFECTS
     * @param {number} x           — screen X (px)
     * @param {number} y           — screen Y (px)
     * @param {string} [colorOverride]
     */
    function spawn(effectName, x, y, colorOverride) {
        var cfg = EFFECTS[effectName] || EFFECTS.sparkle_up;
        var color = colorOverride || cfg.color;
        for (var i = 0; i < cfg.count; i++) {
            var angle = (Math.PI * 2 * i) / cfg.count + (Math.random() - 0.5) * 0.8;
            var speed = cfg.speed * (0.6 + Math.random() * 0.8);
            _particles.push({
                x:       x + (Math.random() - 0.5) * 10,
                y:       y + (Math.random() - 0.5) * 10,
                vx:      Math.cos(angle) * speed * (cfg.spread / 40),
                vy:      Math.sin(angle) * speed * (cfg.spread / 40) - speed,
                color:   color,
                shape:   cfg.shape,
                size:    3 + Math.random() * 4,
                life:    1.0,
                decay:   0.025 + Math.random() * 0.02,
                gravity: 0.12,
            });
        }
    }

    /**
     * Spawn particles anchored to a DOM element's center.
     */
    function spawnAt(effectName, el, colorOverride) {
        if (!el) return;
        var rect = el.getBoundingClientRect();
        spawn(effectName, rect.left + rect.width / 2, rect.top + rect.height / 2, colorOverride);
    }

    /** Tick all particles. Requires a canvas element with id="pgp-canvas". */
    function tick() {
        var canvas = _getCanvas();
        if (!canvas) { _particles = []; return; }
        var ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        var alive = [];
        _particles.forEach(function (p) {
            p.x  += p.vx;
            p.y  += p.vy;
            p.vy += p.gravity;
            p.life -= p.decay;
            if (p.life <= 0) return;

            ctx.globalAlpha = Math.max(0, p.life);
            ctx.fillStyle   = p.color;
            ctx.beginPath();
            if (p.shape === 'star') {
                _drawStar(ctx, p.x, p.y, p.size);
            } else {
                ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
            }
            ctx.fill();
            alive.push(p);
        });
        ctx.globalAlpha = 1;
        _particles = alive;
    }

    function _drawStar(ctx, x, y, r) {
        var spikes = 4, outerR = r, innerR = r * 0.4;
        var rot = (Math.PI / 2) * 3;
        var step = Math.PI / spikes;
        ctx.moveTo(x, y - outerR);
        for (var i = 0; i < spikes; i++) {
            ctx.lineTo(x + Math.cos(rot) * outerR, y + Math.sin(rot) * outerR);
            rot += step;
            ctx.lineTo(x + Math.cos(rot) * innerR, y + Math.sin(rot) * innerR);
            rot += step;
        }
        ctx.lineTo(x, y - outerR);
        ctx.closePath();
    }

    var _canvas = null;
    function _getCanvas() {
        if (_canvas && document.body.contains(_canvas)) return _canvas;
        _canvas = document.getElementById('pgp-canvas');
        if (!_canvas) {
            _canvas = document.createElement('canvas');
            _canvas.id = 'pgp-canvas';
            _canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9996;';
            _canvas.width  = window.innerWidth;
            _canvas.height = window.innerHeight;
            document.body.appendChild(_canvas);
            window.addEventListener('resize', function () {
                if (_canvas) { _canvas.width = window.innerWidth; _canvas.height = window.innerHeight; }
            });
        }
        return _canvas;
    }

    function hasActive() { return _particles.length > 0; }
    function clear()     { _particles = []; }

    return { spawn: spawn, spawnAt: spawnAt, tick: tick, hasActive: hasActive, clear: clear };
})();

// ─────────────────────────────────────────────────────────────────────────────
// 3. COMPONENT — Stat Bar Renderer (smooth number interpolation)
// ─────────────────────────────────────────────────────────────────────────────

var StatBarRenderer = (function () {
    // Map of stat -> { current, target, el }
    var _stats = {};

    /**
     * Queue a stat value change for smooth interpolation.
     * @param {string} stat   — "ATT", "DEF", etc.
     * @param {number} from   — old value
     * @param {number} to     — new value
     */
    function animate(stat, from, to) {
        _stats[stat] = { current: from, target: to, speed: 0.1 };
    }

    /** Tick all active stat interpolations. */
    function tick() {
        var anyActive = false;
        Object.keys(_stats).forEach(function (stat) {
            var s = _stats[stat];
            if (Math.abs(s.target - s.current) < 0.5) {
                s.current = s.target;
                _updateStatEl(stat, Math.round(s.current));
                delete _stats[stat];
                return;
            }
            s.current += (s.target - s.current) * s.speed;
            _updateStatEl(stat, Math.round(s.current));
            anyActive = true;
        });
        return anyActive;
    }

    function _updateStatEl(stat, value) {
        // Target the stat display spans inside .mp-stat-row
        var rows = document.querySelectorAll('.mp-stat-row[data-stat="' + stat + '"] span, .mp-stat-hoverable[data-stat="' + stat + '"] span');
        rows.forEach(function (el) {
            // Only update the value part — text like "ATT: 42"
            var text = el.textContent || '';
            var match = text.match(/^([A-Z]+:\s*)(\d+)/);
            if (match) {
                el.textContent = match[1] + value;
            }
        });
    }

    function hasActive() { return Object.keys(_stats).length > 0; }
    function clear()     { _stats = {}; }

    return { animate: animate, tick: tick, hasActive: hasActive, clear: clear };
})();

// ─────────────────────────────────────────────────────────────────────────────
// 3. COMPONENT — Screen Flash Renderer
// ─────────────────────────────────────────────────────────────────────────────

var ScreenFlashRenderer = (function () {
    var _el     = null;
    var _active = false;
    var _age    = 0;
    var _dur    = 20; // frames

    function flash(color, durationFrames) {
        _ensureEl();
        _el.style.background = color || 'rgba(255,215,0,0.18)';
        _el.style.opacity    = '1';
        _age    = 0;
        _dur    = durationFrames || 20;
        _active = true;
    }

    function tick() {
        if (!_active) return false;
        _age++;
        var progress = _age / _dur;
        if (_el) _el.style.opacity = (1 - progress).toFixed(3);
        if (_age >= _dur) {
            _active = false;
            if (_el) _el.style.opacity = '0';
        }
        return _active;
    }

    function _ensureEl() {
        if (_el && document.body.contains(_el)) return;
        _el = document.createElement('div');
        _el.id = 'pgp-flash';
        _el.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:9995;opacity:0;transition:none;';
        document.body.appendChild(_el);
    }

    return { flash: flash, tick: tick };
})();

// ─────────────────────────────────────────────────────────────────────────────
// 4. GAME LOOP
// ─────────────────────────────────────────────────────────────────────────────

var PetGameLoop = (function () {
    var _running    = false;
    var _rafId      = null;
    var _lastTime   = 0;
    var _frameCount = 0;

    // Current animation being played from the queue
    var _currentAnim   = null;
    var _animStartTime = 0;

    /**
     * Start the game loop. Safe to call multiple times — idempotent.
     */
    function start() {
        if (_running) return;
        _running = true;
        _rafId   = requestAnimationFrame(_loop);

        // Pause when tab is hidden, resume when visible
        document.addEventListener('visibilitychange', _onVisibility);
    }

    function stop() {
        _running = false;
        if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; }
        document.removeEventListener('visibilitychange', _onVisibility);
    }

    function _onVisibility() {
        if (document.hidden) {
            if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; }
        } else if (_running) {
            _lastTime = 0;
            _rafId = requestAnimationFrame(_loop);
        }
    }

    function _loop(timestamp) {
        if (!_running) return;
        _rafId = requestAnimationFrame(_loop);

        var delta = _lastTime ? (timestamp - _lastTime) : 16.67;
        _lastTime = timestamp;
        _frameCount++;

        // ── Tick all visual components every frame ────────────────────────────
        ParticleRenderer.tick();
        NumberPopRenderer.tick();
        XpBarRenderer.tick();
        StatBarRenderer.tick();
        ScreenFlashRenderer.tick();

        // ── Drain one event from the queue when no animation is playing ───────
        if (!_currentAnim) {
            var next = PetEventQueue.shift();
            if (next) {
                _playAnimation(next, timestamp);
            } else {
                // Nothing animating — transition UI state back to idle
                if (PetUIStateMachine.is(PetUIState.ANIMATING)) {
                    PetUIStateMachine.transition(PetUIState.IDLE);
                }
            }
        } else {
            // Check if current animation has finished its duration
            var elapsed = timestamp - _animStartTime;
            if (elapsed >= _currentAnim.duration_ms) {
                _currentAnim = null;
                // If more events are queued, stay in ANIMATING state
                if (PetEventQueue.size() === 0 && PetUIStateMachine.is(PetUIState.ANIMATING)) {
                    PetUIStateMachine.transition(PetUIState.IDLE);
                }
            }
        }
    }

    /**
     * Dispatch an animation event to the appropriate component(s).
     */
    function _playAnimation(anim, timestamp) {
        _currentAnim   = anim;
        _animStartTime = timestamp;
        PetUIStateMachine.transition(PetUIState.ANIMATING);

        var d = anim.data || {};

        switch (anim.type) {

            case 'train_result': {
                var statEl = document.querySelector('.mp-stat-hoverable[data-stat="' + d.stat + '"]');
                var sign   = d.delta >= 0 ? '+' : '';
                var color  = d.success ? '#2ecc71' : '#e74c3c';
                NumberPopRenderer.spawn(sign + d.delta + ' ' + d.stat, color, statEl);
                if (statEl) ParticleRenderer.spawnAt(d.effect, statEl, d.color);
                if (!d.success) ScreenFlashRenderer.flash('rgba(231,76,60,0.15)', 18);
                break;
            }

            case 'mission_result': {
                var petImg = document.querySelector('#my-pet-header .mp-pet-img');
                if (d.success) {
                    var xpText = '+' + (d.xp || 0).toLocaleString() + ' XP';
                    NumberPopRenderer.spawn(xpText, '#2ecc71', petImg);
                    ParticleRenderer.spawnAt('xp_burst', petImg, d.color);
                } else {
                    ScreenFlashRenderer.flash('rgba(231,76,60,0.2)', 22);
                    if (petImg) ParticleRenderer.spawnAt('fail_flash', petImg, '#e74c3c');
                }
                break;
            }

            case 'play_result': {
                var petImg2 = document.querySelector('#my-pet-header .mp-pet-img');
                var xpText2 = '+' + (d.xp || 0).toLocaleString() + ' XP';
                NumberPopRenderer.spawn(xpText2, d.color || '#ffd700', petImg2);
                ParticleRenderer.spawnAt('float_up', petImg2, d.color);
                break;
            }

            case 'xp_bar': {
                XpBarRenderer.start(d.old_pct, d.new_pct, d.old_xp, d.new_xp, d.max_xp);
                break;
            }

            case 'level_up': {
                var petImg3 = document.querySelector('#my-pet-header .mp-pet-img');
                ParticleRenderer.spawnAt('level_burst', petImg3, '#ffd700');
                ScreenFlashRenderer.flash('rgba(255,215,0,0.25)', 30);
                NumberPopRenderer.spawn('LEVEL UP!', '#ffd700', petImg3);
                // Animate stat gains
                if (d.gains) {
                    Object.keys(d.gains).forEach(function (stat) {
                        var gain = d.gains[stat];
                        if (gain > 0) {
                            var el = document.querySelector('.mp-stat-hoverable[data-stat="' + stat + '"]');
                            NumberPopRenderer.spawn('+' + gain + ' ' + stat, '#4caf50', el);
                        }
                    });
                }
                break;
            }

            case 'level_down': {
                var petImg4 = document.querySelector('#my-pet-header .mp-pet-img');
                ParticleRenderer.spawnAt('level_drop', petImg4, '#e74c3c');
                ScreenFlashRenderer.flash('rgba(231,76,60,0.25)', 30);
                NumberPopRenderer.spawn('LEVEL DOWN', '#e74c3c', petImg4);
                break;
            }

            case 'loot_drop': {
                var petImg5 = document.querySelector('#my-pet-header .mp-pet-img');
                ParticleRenderer.spawnAt('chest_open', petImg5, '#ffd700');
                if (d.items && d.items.length) {
                    var rarityColors = {
                        Common: '#9e9e9e', Uncommon: '#4caf50',
                        Rare: '#2196f3', Epic: '#9c27b0', Mythic: '#ff9800'
                    };
                    d.items.forEach(function (item, idx) {
                        setTimeout(function () {
                            var col = rarityColors[item.rarity] || '#ffd700';
                            NumberPopRenderer.spawn(item.name, col, petImg5);
                        }, idx * 120);
                    });
                }
                break;
            }

            case 'battle_action': {
                var targetEl = d.is_player
                    ? document.querySelector('.mp-battle-player-hp')
                    : document.querySelector('.mp-battle-enemy-hp');
                if (d.action === 'attack' || d.action === 'skill') {
                    var dmgColor = d.is_player ? '#e74c3c' : '#ff6b6b';
                    if (d.damage > 0) NumberPopRenderer.spawn('-' + d.damage, dmgColor, targetEl);
                    ParticleRenderer.spawnAt(d.effect || 'attack_hit', targetEl, dmgColor);
                } else if (d.action === 'defend') {
                    ParticleRenderer.spawnAt('shield_block', targetEl, '#3498db');
                } else if (d.action === 'charge') {
                    var chargeEl = d.is_player
                        ? document.querySelector('.mp-battle-player-charge')
                        : document.querySelector('.mp-battle-enemy-charge');
                    ParticleRenderer.spawnAt('charge_glow', chargeEl || targetEl, '#f1c40f');
                }
                break;
            }

            default:
                // Unknown animation type — just let the duration expire
                break;
        }
    }

    function isRunning() { return _running; }
    function frameCount() { return _frameCount; }

    return { start: start, stop: stop, isRunning: isRunning, frameCount: frameCount };
})();

// ── 4. GAME LOOP ──────────────────────────────────────────────────────────────
var PetGameLoop = (function () {
    var _running = false, _rafId = null, _lastTime = 0, _frameCount = 0;
    var _currentAnim = null, _animStartTime = 0;
    function start() {
        if (_running) return; _running = true;
        _rafId = requestAnimationFrame(_loop);
        document.addEventListener('visibilitychange', _onVisibility);
    }
    function stop() {
        _running = false;
        if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; }
        document.removeEventListener('visibilitychange', _onVisibility);
    }
    function _onVisibility() {
        if (document.hidden) { if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; } }
        else if (_running) { _lastTime = 0; _rafId = requestAnimationFrame(_loop); }
    }
    function _loop(timestamp) {
        if (!_running) return;
        _rafId = requestAnimationFrame(_loop);
        _lastTime = timestamp; _frameCount++;
        ParticleRenderer.tick(); NumberPopRenderer.tick();
        XpBarRenderer.tick(); StatBarRenderer.tick(); ScreenFlashRenderer.tick();
        if (!_currentAnim) {
            var next = PetEventQueue.shift();
            if (next) { _playAnimation(next, timestamp); }
            else if (PetUIStateMachine.is('animating')) { PetUIStateMachine.transition('idle'); }
        } else {
            if ((timestamp - _animStartTime) >= _currentAnim.duration_ms) {
                _currentAnim = null;
                if (PetEventQueue.size() === 0 && PetUIStateMachine.is('animating')) PetUIStateMachine.transition('idle');
            }
        }
    }
    function _playAnimation(anim, timestamp) {
        _currentAnim = anim; _animStartTime = timestamp;
        PetUIStateMachine.transition('animating');
        var d = anim.data || {};
        var petImg = document.querySelector('#my-pet-header .mp-pet-img');
        switch (anim.type) {
            case 'train_result': {
                var el = document.querySelector('.mp-stat-hoverable[data-stat="' + d.stat + '"]');
                var sign = d.delta >= 0 ? '+' : '';
                var col = d.success ? '#2ecc71' : '#e74c3c';
                NumberPopRenderer.spawn(sign + d.delta + ' ' + d.stat, col, el);
                if (el) ParticleRenderer.spawnAt(d.effect || 'sparkle_up', el, d.color);
                if (!d.success) ScreenFlashRenderer.flash('rgba(231,76,60,0.15)', 18);
                break; }
            case 'mission_result': {
                if (d.success) { NumberPopRenderer.spawn('+' + (d.xp||0).toLocaleString() + ' XP', '#2ecc71', petImg); ParticleRenderer.spawnAt('xp_burst', petImg, d.color); }
                else { ScreenFlashRenderer.flash('rgba(231,76,60,0.2)', 22); ParticleRenderer.spawnAt('fail_flash', petImg, '#e74c3c'); }
                break; }
            case 'play_result': {
                NumberPopRenderer.spawn('+' + (d.xp||0).toLocaleString() + ' XP', d.color || '#ffd700', petImg);
                ParticleRenderer.spawnAt('float_up', petImg, d.color); break; }
            case 'xp_bar': { XpBarRenderer.start(d.old_pct, d.new_pct, d.old_xp, d.new_xp, d.max_xp); break; }
            case 'level_up': {
                ParticleRenderer.spawnAt('level_burst', petImg, '#ffd700');
                ScreenFlashRenderer.flash('rgba(255,215,0,0.25)', 30);
                NumberPopRenderer.spawn('LEVEL UP!', '#ffd700', petImg);
                if (d.gains) { Object.keys(d.gains).forEach(function(s) { var g = d.gains[s]; if (g > 0) { var se = document.querySelector('.mp-stat-hoverable[data-stat="' + s + '"]'); NumberPopRenderer.spawn('+' + g + ' ' + s, '#4caf50', se); } }); }
                break; }
            case 'level_down': {
                ParticleRenderer.spawnAt('level_drop', petImg, '#e74c3c');
                ScreenFlashRenderer.flash('rgba(231,76,60,0.25)', 30);
                NumberPopRenderer.spawn('LEVEL DOWN', '#e74c3c', petImg); break; }
            case 'loot_drop': {
                ParticleRenderer.spawnAt('chest_open', petImg, '#ffd700');
                var rc = {Common:'#9e9e9e',Uncommon:'#4caf50',Rare:'#2196f3',Epic:'#9c27b0',Mythic:'#ff9800'};
                if (d.items) d.items.forEach(function(it,i) { setTimeout(function() { NumberPopRenderer.spawn(it.name, rc[it.rarity]||'#ffd700', petImg); }, i*120); });
                break; }
            case 'battle_action': {
                var tEl = d.is_player ? document.querySelector('.mp-battle-player-hp') : document.querySelector('.mp-battle-enemy-hp');
                if (d.action === 'attack' || d.action === 'skill') { if (d.damage > 0) NumberPopRenderer.spawn('-' + d.damage, '#e74c3c', tEl); ParticleRenderer.spawnAt(d.effect || 'attack_hit', tEl, '#e74c3c'); }
                else if (d.action === 'defend') { ParticleRenderer.spawnAt('shield_block', tEl, '#3498db'); }
                else if (d.action === 'charge') { ParticleRenderer.spawnAt('charge_glow', tEl, '#f1c40f'); }
                break; }
            default: break;
        }
    }
    function isRunning() { return _running; }
    function frameCount() { return _frameCount; }
    return { start: start, stop: stop, isRunning: isRunning, frameCount: frameCount };
})();

// ── Public API ────────────────────────────────────────────────────────────────
// Called by mypet.js after every server response that includes animation data.

window.PetGPP = {
    // Push one or more animation events from a server response
    push: function(animOrArray) { PetEventQueue.push(animOrArray); },

    // Push an XP bar update (old/new values from enriched pet)
    pushXpBar: function(oldPet, newPet) {
        if (!oldPet || !newPet) return;
        var maxXp  = newPet.xp_for_next_level || 1;
        var oldXp  = parseInt(oldPet.experience || 0);
        var newXp  = parseInt(newPet.experience || 0);
        var oldPct = Math.min(oldXp / maxXp, 1) * 100;
        var newPct = Math.min(newXp / maxXp, 1) * 100;
        PetEventQueue.push({ type: 'xp_bar', duration_ms: 700,
            data: { old_pct: oldPct, new_pct: newPct, old_xp: oldXp, new_xp: newXp, max_xp: maxXp } });
    },

    // Push a level-up event from level_change data
    pushLevelChange: function(levelChange) {
        if (!levelChange) return;
        var isUp = levelChange.new_level > levelChange.old_level;
        PetEventQueue.push({
            type: isUp ? 'level_up' : 'level_down',
            duration_ms: 2000,
            data: { old_level: levelChange.old_level, new_level: levelChange.new_level,
                    gains: levelChange.gains || {}, losses: levelChange.losses || {} }
        });
    },

    // Expose sub-systems for direct use
    StateMachine:  PetUIStateMachine,
    EventQueue:    PetEventQueue,
    Particles:     ParticleRenderer,
    NumberPops:    NumberPopRenderer,
    XpBar:         XpBarRenderer,
    StatBars:      StatBarRenderer,
    Flash:         ScreenFlashRenderer,
    Loop:          PetGameLoop,
};

// Auto-start the loop when this script loads
PetGameLoop.start();
