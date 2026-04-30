// ═══════════════════════════════════════════════════════════════════════════════
// ARENA MAP — Animated terrain canvas renderer
// Each zone has a unique living animation matching its element theme.
// Supports zone room navigation. Pet icons rendered with high-contrast backing.
// ═══════════════════════════════════════════════════════════════════════════════

var el  = document.getElementById.bind(document);
var esc = function(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };

// ── Seeded PRNG (mulberry32) ──────────────────────────────────────────────────
function _rng(seed) {
    return function() {
        seed |= 0; seed = seed + 0x6D2B79F5 | 0;
        var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
        t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
        return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
}

// ── Map state ─────────────────────────────────────────────────────────────────
var _map = {
    canvas: null, ctx: null,
    ox: 0, oy: 0, scale: 1,
    dragging: false, dragStart: null,
    _userPanned: false,
    seed: 42,
    W: 1600, H: 1066,  // Fixed map dimensions
    terrain: null,
    animPos: {},
    alive: [], participants: [], events: [], round: 0,
    eliminated: [],
    rounds: [],
    relMap: {},
    chargeStacks: {},
    filter: 'all',
    nextRoundAt: 0,
    imgCache: {},
    animFrame: null,
    // Enhanced terrain system
    terrainLayers: {},  // Individual zone terrain canvases
    visibleZones: {},   // Which zones are currently visible
    zoneTransitions: {}, // Animation states for zone show/hide
    focusedZone: null,  // Currently focused zone (null = show all)
    terrainMode: 'all', // 'all', 'focused', 'selective'
};

// ── Zone layout (4×4 grid — ZERO CONFLICTS, thematically placed) ─────────────
// Verified conflict-free: no element is adjacent to any it beats or loses to.
var MAP_ZONES = (function() {
    var W = 1600, H = 1066;
    var c1 = 0,
        c2 = Math.round(W * 0.25),
        c3 = Math.round(W * 0.50),
        c4 = Math.round(W * 0.75),
        c5 = W;
    var r1 = 0,
        r2 = Math.round(H * 0.25),
        r3 = Math.round(H * 0.50),
        r4 = Math.round(H * 0.75),
        r5 = H;
    return {
        // Row 0 — sky/light themes
        ice:      [c1, r1, c2, r2],
        holy:     [c2, r1, c3, r2],
        air:      [c3, r1, c4, r2],
        psychic:  [c4, r1, c5, r2],
        // Row 1 — left/right flanks, Basic center
        plant:    [c1, r2, c2, r3],
        basic:    [c2, r2, c4, r4],  // 2×2 center block
        rock:     [c4, r2, c5, r3],
        // Row 2 — left/right flanks, Basic center continues
        magic:    [c1, r3, c2, r4],
        fighting: [c4, r3, c5, r4],
        // Row 3 — ground/dark themes
        water:    [c1, r4, c2, r5],
        necro:    [c2, r4, c3, r5],
        electric: [c3, r4, c4, r5],
        fire:     [c4, r4, c5, r5],
    };
}());

var MAP_STYLE_NAMES = {
    water:'Tideways', basic:'Neutral Grounds', fire:'Emberlands',
    electric:'Stormfields', ice:'Frostreach', plant:'Verdant Wilds',
    rock:'Stone Marches', air:'Skylands', magic:'Arcane Vale',
    holy:'Sanctified Plains', necro:'Shadow Wastes',
    fighting:'Battlegrounds', psychic:'Mindscapes',
};

// Element ring / glow colours for pet icons
var ELEM_RING = {
    fire:'rgba(255,90,20,0.95)',   water:'rgba(60,200,255,0.95)',
    electric:'rgba(255,235,0,0.95)', ice:'rgba(190,245,255,0.95)',
    plant:'rgba(50,210,80,0.95)',  rock:'rgba(215,185,120,0.95)',
    air:'rgba(180,235,255,0.95)', magic:'rgba(210,120,255,0.95)',
    holy:'rgba(255,230,100,0.95)', necro:'rgba(170,100,230,0.95)',
    fighting:'rgba(230,60,60,0.95)', psychic:'rgba(100,150,255,0.95)',
    basic:'rgba(190,190,200,0.95)',
};
var ELEM_GLOW = {
    fire:'rgba(255,90,20,0.5)',   water:'rgba(60,200,255,0.4)',
    electric:'rgba(255,235,0,0.6)', ice:'rgba(190,245,255,0.4)',
    plant:'rgba(50,210,80,0.4)',  rock:'rgba(215,185,120,0.3)',
    air:'rgba(180,235,255,0.35)', magic:'rgba(210,120,255,0.55)',
    holy:'rgba(255,230,100,0.55)', necro:'rgba(170,100,230,0.5)',
    fighting:'rgba(230,60,60,0.5)', psychic:'rgba(100,150,255,0.5)',
    basic:'rgba(190,190,200,0.3)',
};

// ── Per-zone animated particle systems ───────────────────────────────────────
// Each zone owns a pool of particles seeded once, updated each frame.
var _zoneParts = {};   // style -> [{x,y,vx,vy,...}]
var _comicBursts = []; // fighting zone comic impacts [{x,y,ts,label}]

function _initZoneParticles(seed) {
    var r = _rng(seed + 999);
    var zones = Object.keys(MAP_ZONES);  // Include all zones including psychic
    zones.forEach(function(style) {
        var z = MAP_ZONES[style];
        var zw = z[2]-z[0], zh = z[3]-z[1];
        var pool = [];
        var count = _particleCount(style);
        for (var i = 0; i < count; i++) {
            pool.push(_makeParticle(style, z, r, zw, zh));
        }
        _zoneParts[style] = pool;
    });
    // Schedule random comic bursts for fighting zone
    _scheduleComicBurst();
}

function _particleCount(style) {
    var counts = {
        fire:40, water:35, plant:30, ice:25, air:28,
        electric:6, magic:22, holy:1, necro:20,
        fighting:8, psychic:16, rock:14, basic:10,
    };
    return counts[style] || 12;
}

// ─────────────────────────────────────────────────────────────────────────────
// RICH TERRAIN SYSTEM — full rewrite for maximum visual fidelity
// _buildTerrain   : static base layer (drawn once to offscreen canvas)
// _makeParticle   : per-particle init
// _tickParticles  : per-frame physics
// _drawZoneParticles : per-frame rendering
// ─────────────────────────────────────────────────────────────────────────────

function _makeParticle(style, z, r, zw, zh) {
    var x = z[0] + r() * zw;
    var y = z[1] + r() * zh;
    var p = {x:x, y:y, ox:x, oy:y, phase: r() * Math.PI * 2, life: r()};
    switch(style) {
        case 'fire':
            // Ember — glows at bottom, rises as a flame tongue
            p.x = z[0]+r()*zw;
            p.y = z[3] - r()*zh*0.15; // spawn near bottom
            p.ox = p.x; p.oy = p.y;
            p.vx = (r()-0.5)*0.5; p.vy = -(0.5+r()*1.2);
            p.size = 4+r()*9; p.alpha = 0.7+r()*0.25;
            p.hue = 10+r()*25; // orange-red
            p.life = r();
            break;
        case 'water':
            // Long smooth current ribbon — slow drift, very gentle undulation
            p.vx = 0.18+r()*0.28; p.vy = 0;
            p.size = 1.8+r()*2.8; p.alpha = 0.22+r()*0.28;
            p.wave = r()*Math.PI*2;
            p.waveAmp = 4+r()*8;      // gentle vertical amplitude
            p.waveFreq = 0.008+r()*0.006; // very low frequency = long smooth curves
            p.len = 80+r()*120;       // long ribbon
            break;
        case 'plant':
            // Grass blade — rooted at bottom, sways with wind
            p.x = z[0]+r()*zw;
            p.y = z[3] - r()*zh*0.35; // root near bottom
            p.ox = p.x; p.oy = p.y;
            p.size = 18+r()*30;  // blade height
            p.width = 1.5+r()*2.5;
            p.alpha = 0.55+r()*0.35;
            p.phase = r()*Math.PI*2;
            p.swaySpeed = 0.018+r()*0.022;
            p.swayAmp = 6+r()*10;
            p.lean = (r()-0.5)*8; // natural lean
            break;
        case 'ice':
            p.vx = (r()-0.5)*0.08; p.vy = 0.15+r()*0.25; // snow fall
            p.size = 1+r()*2.5; p.alpha = 0.5+r()*0.4;
            p.drift = (r()-0.5)*0.06;
            break;
        case 'air':
            // Full cloud — drifts slowly left to right at varying heights
            p.x = z[0] - (60 + r()*80); // start off left edge
            p.y = z[1] + r()*zh*0.85;
            p.ox = p.x; p.oy = p.y;
            p.vx = 0.12 + r()*0.22;
            p.vy = 0;
            p.sc = 28 + r()*38;   // cloud scale
            p.alpha = 0.72 + r()*0.22;
            p.wave = r()*Math.PI*2;
            // Pre-bake puff layout for this cloud
            p.puffs = [
                {dx:-p.sc*0.55, dy: p.sc*0.18, rx:p.sc*0.55, ry:p.sc*0.30},
                {dx: 0,         dy: p.sc*0.22, rx:p.sc*0.62, ry:p.sc*0.28},
                {dx: p.sc*0.52, dy: p.sc*0.18, rx:p.sc*0.50, ry:p.sc*0.28},
                {dx:-p.sc*0.36, dy:-p.sc*0.06, rx:p.sc*0.40, ry:p.sc*0.38},
                {dx: p.sc*0.10, dy:-p.sc*0.12, rx:p.sc*0.48, ry:p.sc*0.42},
                {dx: p.sc*0.46, dy:-p.sc*0.04, rx:p.sc*0.36, ry:p.sc*0.36},
                {dx:-p.sc*0.14, dy:-p.sc*0.38, rx:p.sc*0.30, ry:p.sc*0.36},
                {dx: p.sc*0.26, dy:-p.sc*0.32, rx:p.sc*0.26, ry:p.sc*0.32},
            ];
            break;
        case 'electric':
            // Lightning bolt segment — flickers in and out rapidly
            p.vx = 0; p.vy = 0;
            p.ttl = 0.08+r()*0.12; p.age = r();
            // Store a jagged bolt path from top to bottom of zone
            p.bx = z[0]+r()*zw;
            p.by1 = z[1]+r()*zh*0.25;
            p.segs = [];
            var bx2=p.bx, by2=p.by1;
            var segCount = 6+Math.floor(r()*6);
            for(var si2=0;si2<segCount;si2++){
                bx2 += (r()-0.5)*28;
                by2 += (zh*0.6/segCount)*(0.7+r()*0.6);
                p.segs.push({x:bx2,y:by2});
            }
            p.bright = 0.6+r()*0.4;
            p.size = 1+r()*1.5;
            break;
        case 'magic':
            // Spawn at pentagram center, travel outward in a random direction
            p.x = (z[0]+z[2])/2;
            p.y = (z[1]+z[3])/2;
            p.ox = p.x; p.oy = p.y;
            var mAngle = r() * Math.PI * 2;
            var mSpeed = 0.4 + r() * 0.9;
            p.vx = Math.cos(mAngle) * mSpeed;
            p.vy = Math.sin(mAngle) * mSpeed;
            p.size = 2+r()*4; p.alpha = 0.6+r()*0.35;
            p.hue = 260+r()*80;
            p.life = 0;
            break;
        case 'holy':
            // Single particle drives the whole rotating ray fan
            p.vx = 0; p.vy = 0; p.life = 0; p.alpha = 1;
            break;
        case 'necro':
            // Skull ghost — drifts slowly, fades in and out
            p.x = z[0]+r()*zw;
            p.y = z[1]+r()*zh;
            p.ox = p.x; p.oy = p.y;
            p.vx = (r()-0.5)*0.18; p.vy = (r()-0.5)*0.10;
            p.size = 8+r()*14;
            p.alpha = 0;
            p.targetAlpha = 0.15+r()*0.25;
            p.fadeIn = true;
            p.phase = r()*Math.PI*2;
            p.fadeSpeed = 0.004+r()*0.006;
            break;
        case 'psychic':
            // Dream wave ring — expands outward from center, fades as it grows
            p.ox = (z[0]+z[2])/2; p.oy = (z[1]+z[3])/2;
            p.x = p.ox; p.y = p.oy;
            p.radius = r()*20; // start small
            p.maxRadius = Math.sqrt(zw*zw+zh*zh)*0.45 + r()*Math.sqrt(zw*zw+zh*zh)*0.10;
            p.speed = 0.15+r()*0.18;
            p.alpha = 0.35+r()*0.3;
            p.hue = 200+r()*80; // blue-purple dream palette
            p.life = r(); // stagger start
            break;
        case 'rock':
            // Falling rock/debris — spawns near the peak, tumbles down the slope
            // Peak is roughly at cx, z[1]+zh*0.04 — scatter from there
            var peakCx = (z[0]+z[2])/2;
            var peakCy = z[1] + zh*0.08;
            // Spread the spawn point slightly around the peak tip
            p.x = peakCx + (r()-0.5)*zw*0.18;
            p.y = peakCy + r()*zh*0.12;
            p.ox = p.x; p.oy = p.y;
            // Horizontal velocity: rocks fly left or right off the peak
            p.vx = (r()-0.5)*2.2;
            // Downward velocity — starts slow, gravity does the rest
            p.vy = 0.4 + r()*1.0;
            p.size = 2 + r()*4;
            p.alpha = 0.60 + r()*0.30;
            p.rot  = r()*Math.PI*2;
            p.rotV = (r()-0.5)*0.10;
            p.shape = Math.floor(r()*3);
            break;
        case 'basic':
            p.vx = (r()-0.5)*0.05; p.vy = (r()-0.5)*0.05;
            p.size = 2+r()*3; p.alpha = 0.08+r()*0.08;
            break;
        case 'fighting':
            p.vx = 0; p.vy = 0;
            p.size = 1+r()*2; p.alpha = 0.1+r()*0.1;
            break;
    }
    return p;
}

function _scheduleComicBurst() {
    var delay = 2000 + Math.random() * 4000;
    setTimeout(function() {
        var z = MAP_ZONES.fighting;
        if (!z) return;
        var labels = ['POW!','BAM!','WHAM!','KA-POW!','SMASH!','CRACK!'];
        _comicBursts.push({
            x: z[0] + 20 + Math.random() * (z[2]-z[0]-40),
            y: z[1] + 20 + Math.random() * (z[3]-z[1]-40),
            ts: Date.now(),
            label: labels[Math.floor(Math.random()*labels.length)],
        });
        // Prune old
        _comicBursts = _comicBursts.filter(function(b){ return Date.now()-b.ts < 1200; });
        _scheduleComicBurst();
    }, delay);
}

// ── Update particles one tick ─────────────────────────────────────────────────
function _tickParticles(now) {
    var zones = Object.keys(_zoneParts);
    zones.forEach(function(style) {
        var z = MAP_ZONES[style];
        if (!z) return;
        var zw = z[2]-z[0], zh = z[3]-z[1];
        var pool = _zoneParts[style];
        pool.forEach(function(p) {
            switch(style) {
                case 'fire':
                    p.x += p.vx + Math.sin(now*0.003+p.phase)*0.6 + Math.sin(now*0.007+p.phase*2)*0.25;
                    p.y += p.vy * (0.8 + p.life*0.4);
                    p.life += 0.010 + Math.random()*0.004;
                    p.size *= 0.997;
                    if (p.life > 1 || p.y < z[1]) {
                        p.x=z[0]+Math.random()*zw; p.y=z[3]-Math.random()*20;
                        p.life=0; p.size=4+Math.random()*9;
                        p.vx=(Math.random()-0.5)*0.5; p.vy=-(0.5+Math.random()*1.2);
                    }
                    break;
                case 'water':
                    p.wave += 0.006; // very slow wave advance = smooth undulation
                    p.x += p.vx;
                    if (p.x > z[2]+p.len) { p.x=z[0]-p.len; p.ox=p.x; p.oy=z[1]+Math.random()*zh; }
                    break;
                case 'plant':
                    p.phase += p.swaySpeed;
                    // Tip sways, root stays fixed
                    break;
                case 'ice':
                    p.x += p.drift + Math.sin(now*0.001+p.phase)*0.3;
                    p.y += p.vy;
                    if (p.y > z[3]+5) { p.y=z[1]-5; p.x=z[0]+Math.random()*zw; }
                    break;
                case 'air':
                    p.wave += 0.008;
                    p.x += p.vx;
                    p.y = p.oy + Math.sin(p.wave)*1.5;
                    if (p.x > z[2] + p.sc*1.5) {
                        p.x = z[0] - p.sc*1.5;
                        p.oy = z[1] + Math.random()*zh*0.85;
                        p.y = p.oy;
                    }
                    break;
                case 'electric':
                    p.age += 0.06;
                    if (p.age > p.ttl) {
                        // Respawn a new bolt at a random x position
                        p.bx = z[0]+Math.random()*zw;
                        p.by1 = z[1]+Math.random()*zh*0.2;
                        p.segs = [];
                        var bx3=p.bx, by3=p.by1;
                        var sc=6+Math.floor(Math.random()*6);
                        for(var si3=0;si3<sc;si3++){
                            bx3+=(Math.random()-0.5)*28;
                            by3+=(zh*0.6/sc)*(0.7+Math.random()*0.6);
                            p.segs.push({x:bx3,y:by3});
                        }
                        p.age=0; p.ttl=0.08+Math.random()*0.55;
                        p.bright=0.6+Math.random()*0.4;
                    }
                    break;
                case 'magic':
                    p.x += p.vx;
                    p.y += p.vy;
                    p.life += 0.007;
                    // Respawn at center when faded out or left the zone
                    if (p.life > 1 || p.x < z[0] || p.x > z[2] || p.y < z[1] || p.y > z[3]) {
                        p.x = (z[0]+z[2])/2; p.y = (z[1]+z[3])/2;
                        p.ox = p.x; p.oy = p.y;
                        var ma2 = Math.random() * Math.PI * 2;
                        var ms2 = 0.4 + Math.random() * 0.9;
                        p.vx = Math.cos(ma2) * ms2;
                        p.vy = Math.sin(ma2) * ms2;
                        p.life = 0;
                        p.hue = 260 + Math.random() * 80;
                    }
                    break;
                case 'holy':
                    // No per-frame movement — rotation is driven by now in the draw pass
                    break;
                case 'necro':
                    p.x += p.vx;
                    p.y += p.vy;
                    // Fade in then fade out
                    if (p.fadeIn) {
                        p.alpha += p.fadeSpeed;
                        if (p.alpha >= p.targetAlpha) { p.alpha = p.targetAlpha; p.fadeIn = false; }
                    } else {
                        p.alpha -= p.fadeSpeed * 0.6;
                        if (p.alpha <= 0) {
                            // Respawn at new position
                            p.x = z[0]+Math.random()*zw; p.y = z[1]+Math.random()*zh;
                            p.ox = p.x; p.oy = p.y;
                            p.vx = (Math.random()-0.5)*0.18; p.vy = (Math.random()-0.5)*0.10;
                            p.alpha = 0; p.fadeIn = true;
                            p.targetAlpha = 0.15+Math.random()*0.25;
                        }
                    }
                    // Wrap at zone edges
                    if (p.x < z[0]) p.x = z[2]; if (p.x > z[2]) p.x = z[0];
                    if (p.y < z[1]) p.y = z[3]; if (p.y > z[3]) p.y = z[1];
                    break;
                case 'psychic':
                    p.radius += p.speed;
                    p.life += 0.008;
                    if (p.radius > p.maxRadius || p.life > 1) {
                        p.radius = 0; p.life = 0;
                        p.maxRadius = Math.sqrt(zw*zw+zh*zh)*0.45 + Math.random()*Math.sqrt(zw*zw+zh*zh)*0.10;
                        p.speed = 0.15+Math.random()*0.18;
                        p.hue = 200+Math.random()*80;
                    }
                    break;
                case 'rock':
                    // Gravity + slight horizontal drift — tumbling rock fall
                    p.vy += 0.04;  // gravity acceleration
                    p.x += p.vx + Math.sin(now*0.002+p.phase)*0.3;
                    p.y += p.vy;
                    p.rot += p.rotV;
                    // Reset when it exits the bottom or sides of the zone
                    if (p.y > z[3] + p.size*2 || p.x < z[0]-20 || p.x > z[2]+20) {
                        // Respawn near the mountain peak
                        var rpx = (z[0]+z[2])/2;
                        var rpy = z[1] + (z[3]-z[1])*0.08;
                        p.x = rpx + (Math.random()-0.5)*(z[2]-z[0])*0.18;
                        p.y = rpy + Math.random()*(z[3]-z[1])*0.12;
                        p.ox = p.x; p.oy = p.y;
                        p.vx = (Math.random()-0.5)*2.2;
                        p.vy = 0.4 + Math.random()*1.0;
                        p.rot = Math.random()*Math.PI*2;
                    }
                    break;
            }
        });
    });
}

// ── Build static terrain base (drawn once, cached as offscreen canvas) ────────
function _buildTerrain(seed, W, H) {
    var M = 50;
    var oc = document.createElement('canvas');
    oc.width = W; oc.height = H;
    var ctx = oc.getContext('2d');
    var r = _rng(seed * 1337 + 7);

    // Deep void background
    ctx.fillStyle = '#04040c';
    ctx.fillRect(0, 0, W, H);

    // ── Per-zone static base fills ────────────────────────────────────────────
    function zone(style, drawFn) {
        var z = MAP_ZONES[style];
        if (!z) return;
        ctx.save();
        ctx.beginPath(); ctx.rect(z[0],z[1],z[2]-z[0],z[3]-z[1]); ctx.clip();
        drawFn(ctx, z, r);
        ctx.restore();
    }

    // FIRE — molten rock floor with lava cracks and heat shimmer
    zone('fire', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        // Deep charcoal base
        c.fillStyle='#1a0500'; c.fillRect(z[0],z[1],zw,zh);
        // Lava floor gradient — bright at bottom, dark at top
        var grd=c.createLinearGradient(z[0],z[3],z[0],z[1]);
        grd.addColorStop(0,'rgba(255,80,0,0.70)');
        grd.addColorStop(0.25,'rgba(200,40,0,0.50)');
        grd.addColorStop(0.6,'rgba(120,10,0,0.35)');
        grd.addColorStop(1,'rgba(40,0,0,0.20)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Bright lava pools — radial hot spots
        for (var i=0;i<8;i++) {
            var px=z[0]+r()*zw, py=z[1]+0.5*zh+r()*zh*0.5;
            var pr=c.createRadialGradient(px,py,0,px,py,20+r()*35);
            pr.addColorStop(0,'rgba(255,200,50,0.60)');
            pr.addColorStop(0.4,'rgba(255,80,0,0.35)');
            pr.addColorStop(1,'rgba(0,0,0,0)');
            c.fillStyle=pr; c.fillRect(z[0],z[1],zw,zh);
        }
        // Ember glow at very bottom
        var eg=c.createLinearGradient(z[0],z[3]-30,z[0],z[3]);
        eg.addColorStop(0,'rgba(255,120,0,0)');
        eg.addColorStop(1,'rgba(255,60,0,0.45)');
        c.fillStyle=eg; c.fillRect(z[0],z[3]-30,zw,30);
    });

    // WATER — deep ocean with caustic light patterns and depth layers
    zone('water', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        // Deep ocean base
        c.fillStyle='#001428'; c.fillRect(z[0],z[1],zw,zh);
        // Depth gradient — lighter at surface
        var grd=c.createLinearGradient(z[0],z[1],z[0],z[3]);
        grd.addColorStop(0,'rgba(0,160,220,0.45)');
        grd.addColorStop(0.4,'rgba(0,100,180,0.35)');
        grd.addColorStop(1,'rgba(0,40,100,0.50)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Surface shimmer band
        var sg=c.createLinearGradient(z[0],z[1],z[0],z[1]+40);
        sg.addColorStop(0,'rgba(180,240,255,0.25)');
        sg.addColorStop(1,'rgba(0,0,0,0)');
        c.fillStyle=sg; c.fillRect(z[0],z[1],zw,40);
    });

    // PLANT — dense forest floor with layered foliage and dappled light
    zone('plant', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        // Rich dark soil base
        c.fillStyle='#061206'; c.fillRect(z[0],z[1],zw,zh);
        // Canopy light from above
        var grd=c.createLinearGradient(z[0],z[1],z[0],z[3]);
        grd.addColorStop(0,'rgba(80,200,40,0.30)');
        grd.addColorStop(0.4,'rgba(40,140,20,0.20)');
        grd.addColorStop(1,'rgba(10,60,5,0.40)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Dappled light spots — sun through canopy
        for (var i=0;i<10;i++) {
            var lx=z[0]+r()*zw, ly=z[1]+r()*zh*0.7;
            var lg=c.createRadialGradient(lx,ly,0,lx,ly,15+r()*25);
            lg.addColorStop(0,'rgba(180,255,100,0.18)');
            lg.addColorStop(1,'rgba(0,0,0,0)');
            c.fillStyle=lg; c.fillRect(z[0],z[1],zw,zh);
        }
        // Dense grass blades — multiple layers
        for (var layer=0;layer<3;layer++) {
            var alpha=0.25-layer*0.06;
            var green=layer===0?'rgba(60,200,40,'+alpha+')':layer===1?'rgba(40,160,20,'+alpha+')':'rgba(20,120,10,'+alpha+')';
            c.strokeStyle=green; c.lineWidth=1+layer*0.5;
            var count=50-layer*10;
            for (var i=0;i<count;i++) {
                var bx=z[0]+r()*zw, by=z[1]+zh*0.3+r()*zh*0.7;
                var h=15+r()*35, lean=(r()-0.5)*18;
                c.beginPath(); c.moveTo(bx,by);
                c.quadraticCurveTo(bx+lean*0.5,by-h*0.5, bx+lean,by-h);
                c.stroke();
            }
        }
        // Moss patches on ground
        c.fillStyle='rgba(30,100,20,0.25)';
        for (var i=0;i<8;i++) {
            var mx=z[0]+r()*zw, my=z[1]+zh*0.5+r()*zh*0.5;
            c.beginPath(); c.ellipse(mx,my,20+r()*30,8+r()*12,r()*Math.PI,0,Math.PI*2); c.fill();
        }
    });

    // ICE — frozen lake with hexagonal crystal structure and deep blue depths
    zone('ice', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        // Glacial blue base
        c.fillStyle='#0a1a2e'; c.fillRect(z[0],z[1],zw,zh);
        // Ice surface gradient
        var grd=c.createRadialGradient((z[0]+z[2])/2,(z[1]+z[3])/2,0,(z[0]+z[2])/2,(z[1]+z[3])/2,Math.max(zw,zh)*0.7);
        grd.addColorStop(0,'rgba(210,240,255,0.65)');
        grd.addColorStop(0.5,'rgba(140,200,240,0.40)');
        grd.addColorStop(1,'rgba(60,120,200,0.25)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Hexagonal crystal grid
        var hexR=22, hexH=hexR*Math.sqrt(3);
        c.strokeStyle='rgba(180,230,255,0.18)'; c.lineWidth=0.8;
        for (var hx=z[0]-hexR;hx<z[2]+hexR;hx+=hexR*1.5) {
            for (var hy=z[1]-hexH;hy<z[3]+hexH;hy+=hexH) {
                var offX = (Math.floor((hy-z[1])/hexH)%2)*hexR*0.75;
                var cx2=hx+offX, cy2=hy;
                c.beginPath();
                for (var a=0;a<6;a++) {
                    var ax=cx2+hexR*Math.cos(a*Math.PI/3-Math.PI/6);
                    var ay=cy2+hexR*Math.sin(a*Math.PI/3-Math.PI/6);
                    a===0?c.moveTo(ax,ay):c.lineTo(ax,ay);
                }
                c.closePath(); c.stroke();
            }
        }
        // Frost sparkle highlights
        c.fillStyle='rgba(255,255,255,0.35)';
        for (var i=0;i<20;i++) {
            var fx=z[0]+r()*zw, fy=z[1]+r()*zh;
            c.beginPath(); c.arc(fx,fy,0.8+r()*1.5,0,Math.PI*2); c.fill();
        }
    });

    // AIR — bright blue sky with real puffy cumulus clouds
    zone('air', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        // Sky gradient — bright cerulean at top, pale horizon
        var grd=c.createLinearGradient(z[0],z[1],z[0],z[3]);
        grd.addColorStop(0,'rgba(30,100,210,0.75)');
        grd.addColorStop(0.5,'rgba(80,160,240,0.55)');
        grd.addColorStop(1,'rgba(180,220,255,0.40)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);

        // Helper: draw one real cumulus cloud at (cx,cy) with given scale
        function drawCloud(cx, cy, sc) {
            // A real cloud is a cluster of overlapping circles.
            // Bottom row: 3 wide flat circles forming the base
            // Middle row: 3 taller circles
            // Top row: 2 tall circles forming the peaks
            var puffs = [
                // bottom base — wide, flat
                {dx:-sc*0.55, dy: sc*0.18, rx:sc*0.55, ry:sc*0.32},
                {dx: 0,       dy: sc*0.22, rx:sc*0.65, ry:sc*0.30},
                {dx: sc*0.55, dy: sc*0.18, rx:sc*0.52, ry:sc*0.30},
                // middle tier
                {dx:-sc*0.38, dy:-sc*0.05, rx:sc*0.42, ry:sc*0.40},
                {dx: sc*0.10, dy:-sc*0.10, rx:sc*0.50, ry:sc*0.45},
                {dx: sc*0.48, dy:-sc*0.02, rx:sc*0.38, ry:sc*0.38},
                // top peaks
                {dx:-sc*0.15, dy:-sc*0.38, rx:sc*0.32, ry:sc*0.38},
                {dx: sc*0.28, dy:-sc*0.32, rx:sc*0.28, ry:sc*0.34},
            ];
            // Draw shadow layer first (slightly offset down, grey-blue)
            c.globalAlpha = 0.18;
            c.fillStyle = 'rgba(160,185,220,1)';
            puffs.forEach(function(p2) {
                c.beginPath();
                c.ellipse(cx+p2.dx+sc*0.04, cy+p2.dy+sc*0.06, p2.rx, p2.ry, 0, 0, Math.PI*2);
                c.fill();
            });
            // Draw main white cloud body
            c.globalAlpha = 0.82;
            c.fillStyle = 'rgba(245,250,255,1)';
            puffs.forEach(function(p2) {
                c.beginPath();
                c.ellipse(cx+p2.dx, cy+p2.dy, p2.rx, p2.ry, 0, 0, Math.PI*2);
                c.fill();
            });
            // Bright highlight on upper-left of each puff
            c.globalAlpha = 0.35;
            c.fillStyle = 'rgba(255,255,255,1)';
            puffs.slice(3).forEach(function(p2) {
                c.beginPath();
                c.ellipse(cx+p2.dx-p2.rx*0.2, cy+p2.dy-p2.ry*0.25, p2.rx*0.55, p2.ry*0.45, 0, 0, Math.PI*2);
                c.fill();
            });
            c.globalAlpha = 1;
        }

        // Draw 5–7 static background clouds at varying depths
        var cloudDefs = [
            {x:z[0]+zw*0.12, y:z[1]+zh*0.18, sc:38},
            {x:z[0]+zw*0.42, y:z[1]+zh*0.08, sc:52},
            {x:z[0]+zw*0.72, y:z[1]+zh*0.22, sc:44},
            {x:z[0]+zw*0.25, y:z[1]+zh*0.55, sc:60},
            {x:z[0]+zw*0.60, y:z[1]+zh*0.48, sc:48},
            {x:z[0]+zw*0.85, y:z[1]+zh*0.65, sc:36},
        ];
        cloudDefs.forEach(function(cd) { drawCloud(cd.x, cd.y, cd.sc); });
    });

    // ELECTRIC — storm cell with plasma arcs and charged atmosphere
    zone('electric', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        // Dark storm base
        c.fillStyle='#080818'; c.fillRect(z[0],z[1],zw,zh);
        // Charged atmosphere gradient
        var grd=c.createLinearGradient(z[0],z[1],z[0],z[3]);
        grd.addColorStop(0,'rgba(20,10,80,0.70)');
        grd.addColorStop(0.5,'rgba(40,30,120,0.50)');
        grd.addColorStop(1,'rgba(180,160,0,0.25)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Storm cloud masses
        for (var i=0;i<5;i++) {
            var cx=z[0]+r()*zw, cy=z[1]+r()*zh*0.5;
            var cg=c.createRadialGradient(cx,cy,0,cx,cy,50+r()*60);
            cg.addColorStop(0,'rgba(60,50,140,0.40)');
            cg.addColorStop(1,'rgba(0,0,0,0)');
            c.fillStyle=cg; c.fillRect(z[0],z[1],zw,zh);
        }
        // Plasma glow at ground
        var pg=c.createLinearGradient(z[0],z[3]-20,z[0],z[3]);
        pg.addColorStop(0,'rgba(200,180,0,0)');
        pg.addColorStop(1,'rgba(255,220,0,0.30)');
        c.fillStyle=pg; c.fillRect(z[0],z[3]-20,zw,20);
    });

    // MAGIC — arcane library page with glowing sigils and mystical geometry
    zone('magic', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        var cx=(z[0]+z[2])/2, cy=(z[1]+z[3])/2;
        // Parchment-like dark base
        c.fillStyle='#0d0020'; c.fillRect(z[0],z[1],zw,zh);
        // Deep purple radial atmosphere
        var grd=c.createRadialGradient(cx,cy,0,cx,cy,Math.max(zw,zh)*0.7);
        grd.addColorStop(0,'rgba(100,0,180,0.55)');
        grd.addColorStop(0.5,'rgba(60,0,120,0.40)');
        grd.addColorStop(1,'rgba(20,0,50,0.30)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Outer ritual circle
        c.strokeStyle='rgba(200,120,255,0.30)'; c.lineWidth=2;
        c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.42,0,Math.PI*2); c.stroke();
        // Inner circles
        c.lineWidth=1;
        c.strokeStyle='rgba(180,100,255,0.20)';
        c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.28,0,Math.PI*2); c.stroke();
        c.strokeStyle='rgba(160,80,255,0.15)';
        c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.14,0,Math.PI*2); c.stroke();
        // Pentagram / star polygon
        var starR=Math.min(zw,zh)*0.38;
        c.strokeStyle='rgba(220,140,255,0.22)'; c.lineWidth=1.5;
        c.beginPath();
        for (var i=0;i<5;i++) {
            var a1=i*Math.PI*2/5-Math.PI/2;
            var a2=((i+2)%5)*Math.PI*2/5-Math.PI/2;
            c.moveTo(cx+Math.cos(a1)*starR,cy+Math.sin(a1)*starR);
            c.lineTo(cx+Math.cos(a2)*starR,cy+Math.sin(a2)*starR);
        }
        c.stroke();
        // Rune tick marks on outer circle
        c.strokeStyle='rgba(200,120,255,0.25)'; c.lineWidth=1;
        for (var a=0;a<24;a++) {
            var ang=a*Math.PI/12, outerR=Math.min(zw,zh)*0.42;
            var tickLen=a%6===0?10:a%2===0?6:3;
            c.beginPath();
            c.moveTo(cx+Math.cos(ang)*(outerR-tickLen),cy+Math.sin(ang)*(outerR-tickLen));
            c.lineTo(cx+Math.cos(ang)*outerR,cy+Math.sin(ang)*outerR);
            c.stroke();
        }
        // Scattered glowing rune dots
        for (var i=0;i<12;i++) {
            var rx=z[0]+r()*zw, ry=z[1]+r()*zh;
            var rg=c.createRadialGradient(rx,ry,0,rx,ry,4+r()*6);
            rg.addColorStop(0,'rgba(220,160,255,0.50)');
            rg.addColorStop(1,'rgba(0,0,0,0)');
            c.fillStyle=rg; c.fillRect(z[0],z[1],zw,zh);
        }
    });

    // HOLY — divine light with god rays, golden marble floor and angelic glow
    zone('holy', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        var cx=(z[0]+z[2])/2, cy=(z[1]+z[3])/2;
        // Warm white marble base
        c.fillStyle='#1a1408'; c.fillRect(z[0],z[1],zw,zh);
        // Central divine radiance
        var grd=c.createRadialGradient(cx,cy-zh*0.1,0,cx,cy,Math.max(zw,zh)*0.8);
        grd.addColorStop(0,'rgba(255,250,220,0.70)');
        grd.addColorStop(0.3,'rgba(255,220,100,0.40)');
        grd.addColorStop(0.7,'rgba(200,160,40,0.20)');
        grd.addColorStop(1,'rgba(100,80,20,0.05)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // God rays — wide soft beams from above
        c.save();
        for (var i=0;i<12;i++) {
            var ang=i*Math.PI/6-Math.PI/2+(r()-0.5)*0.15;
            var rayLen=Math.max(zw,zh)*0.9;
            var rayW=8+r()*20;
            c.save();
            c.translate(cx,cy-zh*0.1);
            c.rotate(ang);
            var rg=c.createLinearGradient(0,0,0,rayLen);
            rg.addColorStop(0,'rgba(255,240,160,0.18)');
            rg.addColorStop(1,'rgba(255,240,160,0)');
            c.fillStyle=rg;
            c.beginPath(); c.moveTo(-rayW/2,0); c.lineTo(rayW/2,0); c.lineTo(rayW,rayLen); c.lineTo(-rayW,rayLen); c.closePath(); c.fill();
            c.restore();
        }
        c.restore();
        // Halo ring
        c.strokeStyle='rgba(255,230,100,0.25)'; c.lineWidth=3;
        c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.35,0,Math.PI*2); c.stroke();
        c.strokeStyle='rgba(255,240,160,0.12)'; c.lineWidth=1;
        c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.42,0,Math.PI*2); c.stroke();
    });

    // NECRO — very dark grey void with subtle ground cracks
    zone('necro', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        var cx=(z[0]+z[2])/2, cy=(z[1]+z[3])/2;
        // Very dark grey base
        c.fillStyle='#0a0a0c'; c.fillRect(z[0],z[1],zw,zh);
        // Slightly lighter grey radial centre — gives depth without colour
        var grd=c.createRadialGradient(cx,cy,0,cx,cy,Math.max(zw,zh)*0.75);
        grd.addColorStop(0,'rgba(60,60,65,0.45)');
        grd.addColorStop(0.5,'rgba(30,30,33,0.35)');
        grd.addColorStop(1,'rgba(5,5,6,0.60)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
    });

    // FIGHTING — authentic dojo with worn tatami, training marks and impact scars
    zone('fighting', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        var cx=(z[0]+z[2])/2, cy=(z[1]+z[3])/2;
        // Dark worn wood/mat base
        c.fillStyle='#120404'; c.fillRect(z[0],z[1],zw,zh);
        // Tatami mat gradient
        var grd=c.createLinearGradient(z[0],z[1],z[0],z[3]);
        grd.addColorStop(0,'rgba(100,15,15,0.65)');
        grd.addColorStop(0.5,'rgba(140,25,25,0.50)');
        grd.addColorStop(1,'rgba(80,8,8,0.70)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Tatami grid — thick borders
        var cols=6, rows=4;
        c.strokeStyle='rgba(200,80,80,0.22)'; c.lineWidth=2;
        for (var i=0;i<=cols;i++) { c.beginPath(); c.moveTo(z[0]+i*zw/cols,z[1]); c.lineTo(z[0]+i*zw/cols,z[3]); c.stroke(); }
        for (var j=0;j<=rows;j++) { c.beginPath(); c.moveTo(z[0],z[1]+j*zh/rows); c.lineTo(z[2],z[1]+j*zh/rows); c.stroke(); }
        // Tatami weave texture — thin inner lines
        c.strokeStyle='rgba(160,50,50,0.10)'; c.lineWidth=0.5;
        for (var i=0;i<cols;i++) {
            for (var j=0;j<rows;j++) {
                var tx=z[0]+i*zw/cols, ty=z[1]+j*zh/rows;
                var tw=zw/cols, th=zh/rows;
                for (var k=1;k<4;k++) { c.beginPath(); c.moveTo(tx,ty+k*th/4); c.lineTo(tx+tw,ty+k*th/4); c.stroke(); }
            }
        }
        // Center circle — main combat ring
        c.strokeStyle='rgba(220,100,100,0.35)'; c.lineWidth=3;
        c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.38,0,Math.PI*2); c.stroke();
        c.strokeStyle='rgba(200,80,80,0.20)'; c.lineWidth=1.5;
        c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.20,0,Math.PI*2); c.stroke();
        // Center cross
        c.strokeStyle='rgba(220,100,100,0.25)'; c.lineWidth=2;
        c.beginPath(); c.moveTo(cx-15,cy); c.lineTo(cx+15,cy); c.stroke();
        c.beginPath(); c.moveTo(cx,cy-15); c.lineTo(cx,cy+15); c.stroke();
        // Impact scars — random slash marks
        c.strokeStyle='rgba(180,60,60,0.18)'; c.lineWidth=1.5;
        for (var i=0;i<8;i++) {
            var sx=z[0]+r()*zw, sy=z[1]+r()*zh;
            var ang=r()*Math.PI, len=10+r()*25;
            c.beginPath(); c.moveTo(sx,sy); c.lineTo(sx+Math.cos(ang)*len,sy+Math.sin(ang)*len); c.stroke();
        }
    });

    // PSYCHIC — dreamscape with soft blue-indigo mist and gentle concentric rings
    zone('psychic', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        var cx=(z[0]+z[2])/2, cy=(z[1]+z[3])/2;
        // Deep blue-indigo dream base — NOT purple
        c.fillStyle='#04060f'; c.fillRect(z[0],z[1],zw,zh);
        // Soft dreamy radial glow — blue-teal centre
        var grd=c.createRadialGradient(cx,cy,0,cx,cy,Math.max(zw,zh)*0.75);
        grd.addColorStop(0,'rgba(80,120,220,0.55)');
        grd.addColorStop(0.3,'rgba(50,80,180,0.35)');
        grd.addColorStop(0.65,'rgba(30,40,120,0.20)');
        grd.addColorStop(1,'rgba(5,8,30,0.10)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Soft mist patches — pale blue-white
        for (var i=0;i<6;i++) {
            var mx=z[0]+r()*zw, my=z[1]+r()*zh;
            var mg=c.createRadialGradient(mx,my,0,mx,my,40+r()*70);
            mg.addColorStop(0,'rgba(140,170,255,0.12)');
            mg.addColorStop(1,'rgba(0,0,0,0)');
            c.fillStyle=mg; c.fillRect(z[0],z[1],zw,zh);
        }
        // Concentric dream rings from centre — very faint
        c.strokeStyle='rgba(120,160,255,0.12)'; c.lineWidth=1.5;
        for (var ring=1;ring<=5;ring++) {
            c.beginPath(); c.arc(cx,cy,Math.min(zw,zh)*0.09*ring,0,Math.PI*2); c.stroke();
        }
    });

    // ROCK — jagged mountain peak with cliff faces, snow cap, and falling debris
    zone('rock', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        var cx=(z[0]+z[2])/2;

        // Deep slate base — dark mountain night
        c.fillStyle='#080608'; c.fillRect(z[0],z[1],zw,zh);

        // Sky-to-ground atmosphere gradient — cold blue-grey at peak, dark at base
        var atm=c.createLinearGradient(z[0],z[1],z[0],z[3]);
        atm.addColorStop(0,'rgba(80,100,130,0.55)');
        atm.addColorStop(0.35,'rgba(60,70,90,0.40)');
        atm.addColorStop(0.7,'rgba(40,35,30,0.50)');
        atm.addColorStop(1,'rgba(20,15,10,0.70)');
        c.fillStyle=atm; c.fillRect(z[0],z[1],zw,zh);

        // ── Background mountain silhouette (far range, darker) ───────────────
        c.fillStyle='rgba(35,30,28,0.85)';
        c.beginPath();
        c.moveTo(z[0], z[3]);
        // Far-range jagged ridge
        var farPts = [
            [z[0],          z[1]+zh*0.72],
            [z[0]+zw*0.08,  z[1]+zh*0.55],
            [z[0]+zw*0.18,  z[1]+zh*0.62],
            [z[0]+zw*0.28,  z[1]+zh*0.38],
            [z[0]+zw*0.36,  z[1]+zh*0.50],
            [z[0]+zw*0.46,  z[1]+zh*0.28],
            [z[0]+zw*0.54,  z[1]+zh*0.42],
            [z[0]+zw*0.63,  z[1]+zh*0.32],
            [z[0]+zw*0.72,  z[1]+zh*0.48],
            [z[0]+zw*0.82,  z[1]+zh*0.36],
            [z[0]+zw*0.90,  z[1]+zh*0.52],
            [z[2],          z[1]+zh*0.65],
            [z[2],          z[3]],
        ];
        farPts.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        c.closePath(); c.fill();

        // ── Main mountain — large central peak ───────────────────────────────
        // Build a jagged polygon for the main peak
        var peakX = cx + (r()-0.5)*zw*0.15;
        var peakY = z[1] + zh*0.04;

        // Left cliff face — steep, angular
        var leftBase  = z[0] + zw*0.02;
        var rightBase = z[2] - zw*0.02;

        // Generate jagged left edge
        var leftEdge = [
            [leftBase, z[3]],
            [z[0]+zw*0.05, z[1]+zh*0.78],
            [z[0]+zw*0.10, z[1]+zh*0.65],
            [z[0]+zw*0.08, z[1]+zh*0.52],
            [z[0]+zw*0.15, z[1]+zh*0.42],
            [z[0]+zw*0.12, z[1]+zh*0.30],
            [z[0]+zw*0.20, z[1]+zh*0.22],
            [z[0]+zw*0.25, z[1]+zh*0.14],
            [peakX,        peakY],
        ];
        // Generate jagged right edge
        var rightEdge = [
            [peakX,        peakY],
            [z[0]+zw*0.75, z[1]+zh*0.12],
            [z[0]+zw*0.80, z[1]+zh*0.20],
            [z[0]+zw*0.88, z[1]+zh*0.28],
            [z[0]+zw*0.85, z[1]+zh*0.40],
            [z[0]+zw*0.92, z[1]+zh*0.50],
            [z[0]+zw*0.90, z[1]+zh*0.62],
            [z[0]+zw*0.96, z[1]+zh*0.75],
            [rightBase,    z[3]],
        ];

        // Fill main mountain body — dark grey rock
        var mtnGrd = c.createLinearGradient(peakX, peakY, peakX, z[3]);
        mtnGrd.addColorStop(0,   'rgba(95,88,80,1.0)');
        mtnGrd.addColorStop(0.25,'rgba(75,68,60,1.0)');
        mtnGrd.addColorStop(0.6, 'rgba(55,48,42,1.0)');
        mtnGrd.addColorStop(1,   'rgba(30,25,20,1.0)');
        c.fillStyle = mtnGrd;
        c.beginPath();
        c.moveTo(leftBase, z[3]);
        leftEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        rightEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        c.lineTo(rightBase, z[3]);
        c.closePath(); c.fill();

        // ── Left cliff face highlight (lit side) ─────────────────────────────
        var litGrd = c.createLinearGradient(z[0]+zw*0.05, peakY, z[0]+zw*0.30, z[3]);
        litGrd.addColorStop(0,'rgba(160,145,125,0.55)');
        litGrd.addColorStop(0.4,'rgba(120,108,90,0.35)');
        litGrd.addColorStop(1,'rgba(60,50,40,0.10)');
        c.fillStyle = litGrd;
        c.beginPath();
        c.moveTo(leftBase, z[3]);
        leftEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        c.lineTo(peakX, z[3]);
        c.closePath(); c.fill();

        // ── Rock strata lines across the mountain face ────────────────────────
        c.save();
        // Clip to mountain shape
        c.beginPath();
        c.moveTo(leftBase, z[3]);
        leftEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        rightEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        c.lineTo(rightBase, z[3]);
        c.closePath(); c.clip();

        // Diagonal strata bands — angled like real geological layers
        c.strokeStyle='rgba(200,180,150,0.18)'; c.lineWidth=1.2;
        for (var i=0;i<14;i++) {
            var sy = z[1] + i*(zh/12);
            c.beginPath();
            c.moveTo(z[0], sy + zw*0.12);
            c.lineTo(z[2], sy - zw*0.05);
            c.stroke();
        }
        // Vertical crack fissures
        c.strokeStyle='rgba(20,15,10,0.55)'; c.lineWidth=1.5;
        for (var i=0;i<8;i++) {
            var fx=z[0]+zw*0.1+r()*zw*0.8, fy=z[1]+r()*zh*0.4;
            c.beginPath(); c.moveTo(fx,fy);
            var steps=5+Math.floor(r()*4);
            for (var s=0;s<steps;s++) { fx+=(r()-0.5)*18; fy+=12+r()*20; c.lineTo(fx,fy); }
            c.stroke();
        }
        // Bright quartz/mineral veins
        c.strokeStyle='rgba(230,215,180,0.22)'; c.lineWidth=1;
        for (var i=0;i<6;i++) {
            var vx=z[0]+r()*zw, vy=z[1]+r()*zh;
            c.beginPath(); c.moveTo(vx,vy);
            for (var s=0;s<5;s++) { vx+=(r()-0.5)*25; vy+=(r()-0.5)*18; c.lineTo(vx,vy); }
            c.stroke();
        }
        c.restore();

        // ── Snow cap at the peak ──────────────────────────────────────────────
        var snowLine = z[1] + zh*0.18;
        c.save();
        // Clip to mountain shape again for snow
        c.beginPath();
        c.moveTo(leftBase, z[3]);
        leftEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        rightEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        c.lineTo(rightBase, z[3]);
        c.closePath(); c.clip();

        // Snow fill — bright white at peak fading down
        var snowGrd = c.createLinearGradient(peakX, peakY, peakX, snowLine+zh*0.08);
        snowGrd.addColorStop(0,   'rgba(240,245,255,0.92)');
        snowGrd.addColorStop(0.5, 'rgba(210,220,235,0.70)');
        snowGrd.addColorStop(1,   'rgba(180,195,215,0)');
        c.fillStyle = snowGrd;
        c.fillRect(z[0], peakY, zw, snowLine - peakY + zh*0.10);

        // Snow edge — irregular drip line
        c.fillStyle='rgba(235,242,255,0.85)';
        c.beginPath();
        c.moveTo(z[0]+zw*0.18, snowLine);
        var sx=z[0]+zw*0.18;
        while (sx < z[0]+zw*0.82) {
            var sw=8+r()*18;
            c.lineTo(sx+sw*0.5, snowLine+(r()-0.5)*8);
            sx+=sw;
        }
        c.lineTo(z[0]+zw*0.82, snowLine);
        c.lineTo(peakX+zw*0.15, peakY+zh*0.02);
        c.lineTo(peakX, peakY);
        c.lineTo(peakX-zw*0.15, peakY+zh*0.02);
        c.closePath(); c.fill();
        c.restore();

        // ── Cliff edge rim light ──────────────────────────────────────────────
        c.strokeStyle='rgba(180,165,140,0.30)'; c.lineWidth=2;
        c.beginPath();
        c.moveTo(leftBase, z[3]);
        leftEdge.forEach(function(pt){ c.lineTo(pt[0],pt[1]); });
        c.stroke();
    });

    // BASIC — worn cobblestone courtyard, dull but textured
    zone('basic', function(c, z) {
        var zw=z[2]-z[0], zh=z[3]-z[1];
        c.fillStyle='#0c0c10'; c.fillRect(z[0],z[1],zw,zh);
        var grd=c.createLinearGradient(z[0],z[1],z[0],z[3]);
        grd.addColorStop(0,'rgba(120,120,130,0.35)');
        grd.addColorStop(1,'rgba(80,80,90,0.45)');
        c.fillStyle=grd; c.fillRect(z[0],z[1],zw,zh);
        // Cobblestone grid
        var cw=28, ch=18;
        c.strokeStyle='rgba(60,60,70,0.40)'; c.lineWidth=1;
        for (var ci=0;ci<Math.ceil(zw/cw)+1;ci++) {
            for (var cj=0;cj<Math.ceil(zh/ch)+1;cj++) {
                var offset=(cj%2)*cw*0.5;
                var cx2=z[0]+ci*cw+offset, cy2=z[1]+cj*ch;
                c.beginPath(); c.rect(cx2,cy2,cw-2,ch-2); c.stroke();
            }
        }
        // Worn patches — slightly lighter areas
        c.fillStyle='rgba(140,140,150,0.08)';
        for (var i=0;i<6;i++) {
            var px=z[0]+r()*zw, py=z[1]+r()*zh;
            c.beginPath(); c.ellipse(px,py,15+r()*25,10+r()*15,r()*Math.PI,0,Math.PI*2); c.fill();
        }
    });

    // ── Zone borders ──────────────────────────────────────────────────────────
    ctx.strokeStyle='rgba(255,255,255,0.08)'; ctx.lineWidth=1;
    Object.keys(MAP_ZONES).forEach(function(s) {
        var z=MAP_ZONES[s];
        ctx.strokeRect(z[0],z[1],z[2]-z[0],z[3]-z[1]);
    });

    // ── Zone name labels ──────────────────────────────────────────────────────
    var labelColors = {
        fire:'rgba(255,140,60,0.55)',   water:'rgba(80,200,255,0.55)',
        plant:'rgba(80,210,80,0.55)',   ice:'rgba(180,240,255,0.55)',
        air:'rgba(160,220,255,0.55)',   electric:'rgba(255,230,60,0.55)',
        magic:'rgba(200,120,255,0.55)', holy:'rgba(255,230,120,0.55)',
        necro:'rgba(160,80,220,0.55)',  fighting:'rgba(220,80,80,0.55)',
        psychic:'rgba(220,80,220,0.55)',rock:'rgba(200,170,110,0.55)',
        basic:'rgba(180,180,190,0.40)',
    };
    ctx.textAlign='center'; ctx.textBaseline='middle';
    Object.keys(MAP_ZONES).forEach(function(s) {
        var z=MAP_ZONES[s];
        var cx=(z[0]+z[2])/2, cy=(z[1]+z[3])/2;
        var label=(MAP_STYLE_NAMES[s]||s).toUpperCase();
        ctx.font='bold 12px Orbitron,monospace';
        ctx.fillStyle='rgba(0,0,0,0.6)';
        ctx.fillText(label,cx+1,cy+1);
        ctx.fillStyle=labelColors[s]||'rgba(200,200,200,0.45)';
        ctx.fillText(label,cx,cy);
    });

    return oc;
}

// ── Enhanced Interactive Terrain System ──────────────────────────────────────
// Each zone layer is built by drawing the full terrain onto an offscreen canvas
// and clipping to just that zone — guarantees pixel-perfect match with the
// static terrain canvas without duplicating any drawing code.
// Call this AFTER _buildTerrain so fullTerrain is already rendered.
function _buildTerrainLayers(fullTerrain, W, H) {
    // Initialize all zones as visible
    Object.keys(MAP_ZONES).forEach(function(style) {
        _map.visibleZones[style] = true;
        _map.zoneTransitions[style] = { opacity: 1.0, targetOpacity: 1.0, animating: false };
    });

    _map.terrainLayers = {};

    Object.keys(MAP_ZONES).forEach(function(style) {
        var z = MAP_ZONES[style];
        if (!z) return;

        var layerCanvas = document.createElement('canvas');
        layerCanvas.width = W;
        layerCanvas.height = H;
        var layerCtx = layerCanvas.getContext('2d');

        // Clip to this zone and blit the full terrain — only that zone shows through
        layerCtx.save();
        layerCtx.beginPath();
        layerCtx.rect(z[0], z[1], z[2] - z[0], z[3] - z[1]);
        layerCtx.clip();
        layerCtx.drawImage(fullTerrain, 0, 0);
        layerCtx.restore();

        _map.terrainLayers[style] = layerCanvas;
    });
}



function _updateZoneTransitions() {
    var needsUpdate = false;
    Object.keys(_map.zoneTransitions).forEach(function(style) {
        var trans = _map.zoneTransitions[style];
        if (trans.animating) {
            var speed = 0.08; // Animation speed
            var diff = trans.targetOpacity - trans.opacity;
            if (Math.abs(diff) < 0.01) {
                trans.opacity = trans.targetOpacity;
                trans.animating = false;
            } else {
                trans.opacity += diff * speed;
                needsUpdate = true;
            }
        }
    });
    return needsUpdate;
}

function _drawInteractiveTerrain(ctx) {
    // Update zone transitions
    _updateZoneTransitions();
    
    if (_map.terrainMode === 'focused' && _map.focusedZone) {
        // Only draw the focused zone
        var trans = _map.zoneTransitions[_map.focusedZone];
        if (trans && trans.opacity > 0) {
            ctx.save();
            ctx.globalAlpha = trans.opacity;
            ctx.drawImage(_map.terrainLayers[_map.focusedZone], 0, 0);
            ctx.restore();
        }
    } else {
        // Draw all visible zones with their current opacity
        Object.keys(MAP_ZONES).forEach(function(style) {
            var trans = _map.zoneTransitions[style];
            if (trans && trans.opacity > 0 && _map.visibleZones[style]) {
                ctx.save();
                ctx.globalAlpha = trans.opacity;
                ctx.drawImage(_map.terrainLayers[style], 0, 0);
                ctx.restore();
            }
        });
    }
}

// ── Terrain Control Functions ─────────────────────────────────────────────────
function _toggleZoneVisibility(zoneName, visible) {
    if (!MAP_ZONES[zoneName]) return;
    
    _map.visibleZones[zoneName] = visible;
    var trans = _map.zoneTransitions[zoneName];
    trans.targetOpacity = visible ? 1.0 : 0.0;
    trans.animating = true;
}

function _focusZone(zoneName) {
    if (!MAP_ZONES[zoneName]) {
        _map.focusedZone = null;
        _map.terrainMode = 'all';
        return;
    }
    
    _map.focusedZone = zoneName;
    _map.terrainMode = 'focused';
    
    // Animate to focus on this zone
    var zone = MAP_ZONES[zoneName];
    var zoneW = zone[2] - zone[0];
    var zoneH = zone[3] - zone[1];
    var zoneCX = (zone[0] + zone[2]) / 2;
    var zoneCY = (zone[1] + zone[3]) / 2;
    
    var s = _mapCssSize();
    var targetScale = Math.min(s.w / zoneW, s.h / zoneH) * 0.8;
    
    // Animate to new position
    _animateMapView(zoneCX, zoneCY, targetScale);
}

function _animateMapView(targetCX, targetCY, targetScale) {
    var s = _mapCssSize();
    var startOX = _map.ox;
    var startOY = _map.oy;
    var startScale = _map.scale;
    
    var targetOX = s.w / 2 - targetCX * targetScale;
    var targetOY = s.h / 2 - targetCY * targetScale;
    
    var duration = 800;
    var startTime = null;
    
    function animate(timestamp) {
        if (!startTime) startTime = timestamp;
        var progress = Math.min((timestamp - startTime) / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3); // Ease out cubic
        
        _map.ox = startOX + (targetOX - startOX) * eased;
        _map.oy = startOY + (targetOY - startOY) * eased;
        _map.scale = startScale + (targetScale - startScale) * eased;
        
        if (progress < 1) {
            requestAnimationFrame(animate);
        }
    }
    
    requestAnimationFrame(animate);
    _map._userPanned = true;
}

// ── Draw animated zone particles onto the live canvas ────────────────────────
function _drawZoneParticles(ctx, now) {
    Object.keys(_zoneParts).forEach(function(style) {
        // In focused/room mode, only draw particles for the focused zone
        if (_map.terrainMode === 'focused' && _map.focusedZone && style !== _map.focusedZone) return;

        var z = MAP_ZONES[style];
        if (!z) return;
        var pool = _zoneParts[style];

        ctx.save();
        ctx.beginPath(); ctx.rect(z[0],z[1],z[2]-z[0],z[3]-z[1]); ctx.clip();

        pool.forEach(function(p) {
            ctx.save();
            switch(style) {
                case 'fire': {
                    // Flame tongue rising from ember bed at bottom
                    var fade = 1 - p.life;
                    // Ember glow at base — only for particles near the bottom
                    var distFromBottom = p.oy - p.y;
                    if (distFromBottom < 30) {
                        var emberAlpha = (1 - distFromBottom/30) * 0.7;
                        ctx.globalAlpha = emberAlpha;
                        var eg3 = ctx.createRadialGradient(p.x,p.oy,0,p.x,p.oy,p.size*2.5);
                        eg3.addColorStop(0,'rgba(255,200,50,0.9)');
                        eg3.addColorStop(0.4,'rgba(255,80,0,0.5)');
                        eg3.addColorStop(1,'rgba(180,20,0,0)');
                        ctx.fillStyle=eg3;
                        ctx.beginPath(); ctx.arc(p.x,p.oy,p.size*2.5,0,Math.PI*2); ctx.fill();
                    }
                    // Flame tongue
                    var flameH = p.size * (2.8 + p.life * 1.8);
                    var flameW = p.size * (0.75 - p.life * 0.35);
                    ctx.globalAlpha = p.alpha * fade * 0.92;
                    ctx.save();
                    ctx.translate(p.x, p.y);
                    var grd2 = ctx.createLinearGradient(0, 0, 0, -flameH);
                    grd2.addColorStop(0, 'rgba(255,'+(60+Math.floor(p.hue*2))+',0,0.98)');
                    grd2.addColorStop(0.35,'rgba(255,50,0,0.75)');
                    grd2.addColorStop(0.7,'rgba(200,15,0,0.35)');
                    grd2.addColorStop(1,'rgba(100,0,0,0)');
                    ctx.fillStyle=grd2;
                    ctx.beginPath();
                    ctx.moveTo(0,0);
                    ctx.bezierCurveTo(-flameW,-flameH*0.3,-flameW*0.8,-flameH*0.7,0,-flameH);
                    ctx.bezierCurveTo(flameW*0.8,-flameH*0.7,flameW,-flameH*0.3,0,0);
                    ctx.fill();
                    // Hot white core
                    var coreH2=flameH*0.45, coreW2=flameW*0.38;
                    var cg2=ctx.createLinearGradient(0,-coreH2*0.1,0,-coreH2);
                    cg2.addColorStop(0,'rgba(255,255,210,0.98)');
                    cg2.addColorStop(0.5,'rgba(255,210,60,0.75)');
                    cg2.addColorStop(1,'rgba(255,100,0,0)');
                    ctx.fillStyle=cg2;
                    ctx.beginPath();
                    ctx.moveTo(0,0);
                    ctx.bezierCurveTo(-coreW2,-coreH2*0.3,-coreW2*0.7,-coreH2*0.8,0,-coreH2);
                    ctx.bezierCurveTo(coreW2*0.7,-coreH2*0.8,coreW2,-coreH2*0.3,0,0);
                    ctx.fill();
                    ctx.restore();
                    break;
                }
                case 'water': {
                    // Smooth current ribbon — bezier curves, long gentle undulation
                    ctx.globalAlpha = p.alpha;
                    ctx.lineCap = 'round'; ctx.lineJoin = 'round';

                    // Sample 5 control points along the ribbon length
                    var steps2 = 5;
                    var pts = [];
                    for (var wi2 = 0; wi2 <= steps2; wi2++) {
                        var t = wi2 / steps2;
                        var wx3 = (p.x - p.len) + t * p.len;
                        var wy3 = p.oy + Math.sin(p.wave + t * p.waveFreq * p.len) * p.waveAmp;
                        pts.push({x: wx3, y: wy3});
                    }

                    // Draw as a smooth bezier path through the control points
                    ctx.beginPath();
                    ctx.moveTo(pts[0].x, pts[0].y);
                    for (var wi3 = 1; wi3 < pts.length; wi3++) {
                        var prev = pts[wi3-1], curr = pts[wi3];
                        var cpx = (prev.x + curr.x) / 2;
                        ctx.quadraticCurveTo(prev.x, prev.y, cpx, (prev.y + curr.y) / 2);
                    }
                    ctx.lineTo(pts[pts.length-1].x, pts[pts.length-1].y);

                    // Fade in from left, peak in middle, fade out to right
                    var wg3 = ctx.createLinearGradient(p.x-p.len, p.oy, p.x, p.oy);
                    wg3.addColorStop(0,   'rgba(80,170,240,0)');
                    wg3.addColorStop(0.15,'rgba(110,200,255,' + (p.alpha * 2.2) + ')');
                    wg3.addColorStop(0.5, 'rgba(150,225,255,' + (p.alpha * 2.8) + ')');
                    wg3.addColorStop(0.85,'rgba(90,190,245,'  + (p.alpha * 1.8) + ')');
                    wg3.addColorStop(1,   'rgba(60,160,230,0)');
                    ctx.strokeStyle = wg3;
                    ctx.lineWidth = p.size * 2.2;
                    ctx.stroke();
                    break;
                }
                case 'plant': {
                    // Swaying grass blade — rooted at bottom, tip sways with wind
                    var sway = Math.sin(p.phase + now*0.0008) * p.swayAmp + p.lean;
                    var rootX = p.ox, rootY = p.oy;
                    var midX  = rootX + sway*0.4, midY = rootY - p.size*0.5;
                    var tipX2 = rootX + sway,     tipY2 = rootY - p.size;
                    ctx.globalAlpha = p.alpha;
                    var pg3 = ctx.createLinearGradient(rootX,rootY,tipX2,tipY2);
                    pg3.addColorStop(0,'rgba(15,80,8,0.9)');
                    pg3.addColorStop(0.4,'rgba(40,150,20,0.85)');
                    pg3.addColorStop(0.75,'rgba(80,200,35,0.75)');
                    pg3.addColorStop(1,'rgba(140,230,60,0.45)');
                    ctx.strokeStyle=pg3; ctx.lineWidth=p.width; ctx.lineCap='round';
                    ctx.beginPath();
                    ctx.moveTo(rootX, rootY);
                    ctx.quadraticCurveTo(midX, midY, tipX2, tipY2);
                    ctx.stroke();
                    break;
                }
                case 'ice': {
                    // 6-pointed snowflake with arms and sub-branches
                    ctx.globalAlpha = p.alpha;
                    ctx.strokeStyle = 'rgba(200,240,255,0.85)';
                    ctx.lineWidth = 0.9;
                    ctx.lineCap = 'round';
                    for (var arm=0;arm<6;arm++) {
                        var ang = arm * Math.PI/3;
                        var ax = p.x + Math.cos(ang)*p.size, ay = p.y + Math.sin(ang)*p.size;
                        ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(ax,ay); ctx.stroke();
                        // Sub-branches
                        for (var sb=1;sb<=2;sb++) {
                            var sbf = sb/3;
                            var sbx = p.x + Math.cos(ang)*p.size*sbf;
                            var sby = p.y + Math.sin(ang)*p.size*sbf;
                            var sbLen = p.size*0.35;
                            ctx.beginPath();
                            ctx.moveTo(sbx,sby);
                            ctx.lineTo(sbx+Math.cos(ang+Math.PI/3)*sbLen, sby+Math.sin(ang+Math.PI/3)*sbLen);
                            ctx.stroke();
                            ctx.beginPath();
                            ctx.moveTo(sbx,sby);
                            ctx.lineTo(sbx+Math.cos(ang-Math.PI/3)*sbLen, sby+Math.sin(ang-Math.PI/3)*sbLen);
                            ctx.stroke();
                        }
                    }
                    // Center dot
                    ctx.fillStyle='rgba(230,248,255,0.9)';
                    ctx.beginPath(); ctx.arc(p.x,p.y,1.2,0,Math.PI*2); ctx.fill();
                    break;
                }
                case 'air': {
                    // Real cumulus cloud — cluster of overlapping ellipses
                    if (!p.puffs) break;
                    var cx3 = p.x, cy3 = p.y;
                    // Shadow pass — offset down-right, grey-blue
                    ctx.globalAlpha = p.alpha * 0.18;
                    ctx.fillStyle = 'rgba(150,175,215,1)';
                    for(var pi4=0;pi4<p.puffs.length;pi4++){
                        var pf2=p.puffs[pi4];
                        ctx.beginPath();
                        ctx.ellipse(cx3+pf2.dx+p.sc*0.05, cy3+pf2.dy+p.sc*0.07, pf2.rx, pf2.ry, 0, 0, Math.PI*2);
                        ctx.fill();
                    }
                    // Main white body
                    ctx.globalAlpha = p.alpha * 0.88;
                    ctx.fillStyle = 'rgba(245,250,255,1)';
                    for(var pi5=0;pi5<p.puffs.length;pi5++){
                        var pf3=p.puffs[pi5];
                        ctx.beginPath();
                        ctx.ellipse(cx3+pf3.dx, cy3+pf3.dy, pf3.rx, pf3.ry, 0, 0, Math.PI*2);
                        ctx.fill();
                    }
                    // Bright highlight on upper puffs
                    ctx.globalAlpha = p.alpha * 0.40;
                    ctx.fillStyle = 'rgba(255,255,255,1)';
                    for(var pi6=3;pi6<p.puffs.length;pi6++){
                        var pf4=p.puffs[pi6];
                        ctx.beginPath();
                        ctx.ellipse(cx3+pf4.dx-pf4.rx*0.18, cy3+pf4.dy-pf4.ry*0.22, pf4.rx*0.52, pf4.ry*0.42, 0, 0, Math.PI*2);
                        ctx.fill();
                    }
                    break;
                }
                case 'electric': {
                    // Real jagged lightning bolt — bright white/yellow, flickers
                    var ef = 1 - p.age/p.ttl;
                    if (ef <= 0) break;
                    ctx.globalAlpha = p.bright * ef;
                    // Glow pass — wide soft blur
                    ctx.strokeStyle='rgba(180,220,255,0.25)'; ctx.lineWidth=p.size*5;
                    ctx.lineCap='round'; ctx.lineJoin='round';
                    ctx.shadowColor='rgba(150,200,255,0.8)'; ctx.shadowBlur=18;
                    ctx.beginPath(); ctx.moveTo(p.bx,p.by1);
                    for(var si4=0;si4<p.segs.length;si4++) ctx.lineTo(p.segs[si4].x,p.segs[si4].y);
                    ctx.stroke();
                    // Core bolt — bright white
                    ctx.strokeStyle='rgba(255,255,255,0.95)'; ctx.lineWidth=p.size*0.8;
                    ctx.shadowColor='rgba(200,230,255,1)'; ctx.shadowBlur=8;
                    ctx.beginPath(); ctx.moveTo(p.bx,p.by1);
                    for(var si5=0;si5<p.segs.length;si5++) ctx.lineTo(p.segs[si5].x,p.segs[si5].y);
                    ctx.stroke();
                    ctx.shadowBlur=0;
                    // Bright flash at origin
                    ctx.globalAlpha = p.bright * ef * 0.8;
                    var eg2=ctx.createRadialGradient(p.bx,p.by1,0,p.bx,p.by1,p.size*6);
                    eg2.addColorStop(0,'rgba(255,255,220,0.9)');
                    eg2.addColorStop(1,'rgba(100,150,255,0)');
                    ctx.fillStyle=eg2;
                    ctx.beginPath(); ctx.arc(p.bx,p.by1,p.size*6,0,Math.PI*2); ctx.fill();
                    break;
                }
                case 'magic': {
                    // Arcane mote — glowing orb with hue shift and sparkle trail
                    var mf = 1 - p.life;
                    ctx.globalAlpha = p.alpha * mf;
                    // Outer glow
                    var mg = ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.size*2.5);
                    mg.addColorStop(0,'hsla('+(p.hue)+',100%,80%,0.7)');
                    mg.addColorStop(0.5,'hsla('+(p.hue)+',100%,60%,0.3)');
                    mg.addColorStop(1,'hsla('+(p.hue)+',100%,40%,0)');
                    ctx.fillStyle=mg;
                    ctx.beginPath(); ctx.arc(p.x,p.y,p.size*2.5,0,Math.PI*2); ctx.fill();
                    // Bright core
                    ctx.globalAlpha = p.alpha * mf * 0.9;
                    ctx.fillStyle='hsla('+(p.hue)+',100%,90%,1)';
                    ctx.shadowColor='hsla('+(p.hue)+',100%,70%,0.8)'; ctx.shadowBlur=10;
                    ctx.beginPath(); ctx.arc(p.x,p.y,p.size*0.6,0,Math.PI*2); ctx.fill();
                    ctx.shadowBlur=0;
                    break;
                }
                case 'holy': {
                    // Full rotating god-ray fan — 12 evenly spaced rays all spinning together
                    var cx2 = (z[0]+z[2])/2;
                    var cy2 = (z[1]+z[3])/2 - (z[3]-z[1])*0.08;
                    var rayLen = Math.max(z[2]-z[0], z[3]-z[1]) * 0.95;
                    var numRays = 12;
                    var baseAngle = now * 0.00018; // slow spin
                    var halfW = 0.10; // half-width of each ray in radians

                    for (var ri = 0; ri < numRays; ri++) {
                        var ra = baseAngle + (ri / numRays) * Math.PI * 2;
                        // Alternate rays slightly different opacity for depth
                        var rayAlpha = (ri % 2 === 0) ? 0.22 : 0.13;
                        var rg3 = ctx.createLinearGradient(cx2, cy2,
                            cx2 + Math.cos(ra) * rayLen,
                            cy2 + Math.sin(ra) * rayLen);
                        rg3.addColorStop(0,  'rgba(255,248,190,' + (rayAlpha * 2.2) + ')');
                        rg3.addColorStop(0.15,'rgba(255,235,140,' + rayAlpha + ')');
                        rg3.addColorStop(0.6, 'rgba(255,220,90,'  + (rayAlpha * 0.5) + ')');
                        rg3.addColorStop(1,   'rgba(255,210,60,0)');
                        ctx.globalAlpha = 1;
                        ctx.fillStyle = rg3;
                        ctx.beginPath();
                        ctx.moveTo(cx2, cy2);
                        ctx.lineTo(cx2 + Math.cos(ra - halfW) * rayLen,
                                   cy2 + Math.sin(ra - halfW) * rayLen);
                        ctx.lineTo(cx2 + Math.cos(ra + halfW) * rayLen,
                                   cy2 + Math.sin(ra + halfW) * rayLen);
                        ctx.closePath();
                        ctx.fill();
                    }

                    // Bright glowing core at centre
                    ctx.globalAlpha = 0.9;
                    var coreG = ctx.createRadialGradient(cx2, cy2, 0, cx2, cy2, 28);
                    coreG.addColorStop(0,   'rgba(255,255,230,1)');
                    coreG.addColorStop(0.35,'rgba(255,245,180,0.85)');
                    coreG.addColorStop(0.7, 'rgba(255,220,100,0.40)');
                    coreG.addColorStop(1,   'rgba(255,200,60,0)');
                    ctx.fillStyle = coreG;
                    ctx.beginPath(); ctx.arc(cx2, cy2, 28, 0, Math.PI * 2); ctx.fill();
                    break;
                }
                case 'necro': {
                    // Skull ghost — light grey skull shape fading in/out, drifting slowly
                    if (p.alpha <= 0) break;
                    ctx.globalAlpha = p.alpha;
                    var sk = p.size;
                    ctx.save();
                    ctx.translate(p.x, p.y);
                    // Skull cranium — light grey circle
                    ctx.fillStyle='rgba(180,180,185,0.85)';
                    ctx.beginPath(); ctx.arc(0,-sk*0.1,sk*0.55,0,Math.PI*2); ctx.fill();
                    // Jaw — slightly wider flat bottom
                    ctx.fillStyle='rgba(165,165,170,0.75)';
                    ctx.beginPath();
                    ctx.ellipse(0,sk*0.35,sk*0.38,sk*0.28,0,0,Math.PI); ctx.fill();
                    // Eye sockets — dark holes
                    ctx.fillStyle='rgba(20,20,25,0.85)';
                    ctx.beginPath(); ctx.ellipse(-sk*0.2,-sk*0.1,sk*0.14,sk*0.16,0,0,Math.PI*2); ctx.fill();
                    ctx.beginPath(); ctx.ellipse( sk*0.2,-sk*0.1,sk*0.14,sk*0.16,0,0,Math.PI*2); ctx.fill();
                    // Nose cavity
                    ctx.beginPath(); ctx.ellipse(0,sk*0.18,sk*0.08,sk*0.10,0,0,Math.PI*2); ctx.fill();
                    ctx.restore();
                    break;
                }
                case 'psychic': {
                    // Dream wave — expanding ring from center, fades as it grows
                    var progress = p.radius / p.maxRadius;
                    var pAlpha = p.alpha * (1 - progress) * (1 - progress);
                    if (pAlpha <= 0.005) break;
                    ctx.globalAlpha = pAlpha;
                    // Soft dreamy colour — shifts from blue to lavender
                    var hue2 = p.hue + progress * 40;
                    ctx.strokeStyle='hsla('+hue2+',70%,75%,0.8)';
                    ctx.lineWidth = 1.5 + (1-progress)*2;
                    ctx.beginPath(); ctx.arc(p.ox, p.oy, p.radius, 0, Math.PI*2); ctx.stroke();
                    // Soft inner fill glow
                    if (progress < 0.4) {
                        var pg4=ctx.createRadialGradient(p.ox,p.oy,0,p.ox,p.oy,p.radius);
                        pg4.addColorStop(0,'hsla('+hue2+',60%,80%,'+(pAlpha*0.15)+')');
                        pg4.addColorStop(1,'hsla('+hue2+',60%,70%,0)');
                        ctx.fillStyle=pg4;
                        ctx.beginPath(); ctx.arc(p.ox,p.oy,p.radius,0,Math.PI*2); ctx.fill();
                    }
                    break;
                }
                case 'rock': {
                    // Tumbling rock chunk — angular polygon, rotates as it falls
                    ctx.globalAlpha = p.alpha;
                    ctx.save();
                    ctx.translate(p.x, p.y);
                    ctx.rotate(p.rot);

                    // Rock colour — grey-brown with slight variation
                    var shade = 100 + Math.floor(p.size * 8);
                    var rGrd = ctx.createRadialGradient(-p.size*0.3,-p.size*0.3,0,0,0,p.size*1.4);
                    rGrd.addColorStop(0, 'rgba('+(shade+40)+','+(shade+30)+','+(shade+15)+',0.95)');
                    rGrd.addColorStop(0.5,'rgba('+(shade+10)+','+(shade)+','+(shade-10)+',0.85)');
                    rGrd.addColorStop(1,  'rgba('+(shade-30)+','+(shade-35)+','+(shade-40)+',0.70)');
                    ctx.fillStyle = rGrd;

                    // Draw angular rock shape based on shape type
                    ctx.beginPath();
                    if (p.shape === 0) {
                        // Angular chunk — 5-sided polygon
                        var sides = 5;
                        for (var si=0; si<sides; si++) {
                            var ang = (si/sides)*Math.PI*2;
                            var rad = p.size * (si%2===0 ? 1.0 : 0.65);
                            si===0 ? ctx.moveTo(Math.cos(ang)*rad, Math.sin(ang)*rad)
                                   : ctx.lineTo(Math.cos(ang)*rad, Math.sin(ang)*rad);
                        }
                    } else if (p.shape === 1) {
                        // Chunky quad — 4 irregular corners
                        var pts = [
                            [ p.size*0.9,  -p.size*0.5],
                            [ p.size*0.7,   p.size*0.8],
                            [-p.size*0.8,   p.size*0.6],
                            [-p.size*0.6,  -p.size*0.7],
                        ];
                        ctx.moveTo(pts[0][0],pts[0][1]);
                        for (var pi=1;pi<pts.length;pi++) ctx.lineTo(pts[pi][0],pts[pi][1]);
                    } else {
                        // Shard — elongated triangle
                        ctx.moveTo(0, -p.size*1.2);
                        ctx.lineTo(p.size*0.55, p.size*0.85);
                        ctx.lineTo(-p.size*0.50, p.size*0.90);
                    }
                    ctx.closePath();
                    ctx.fill();

                    // Subtle highlight on one edge only — no stroke ring
                    ctx.globalAlpha = p.alpha * 0.35;
                    ctx.strokeStyle = 'rgba(220,205,175,0.6)';
                    ctx.lineWidth = 0.6;
                    ctx.beginPath();
                    ctx.moveTo(-p.size*0.5, -p.size*0.6);
                    ctx.lineTo( p.size*0.4, -p.size*0.5);
                    ctx.stroke();

                    ctx.restore();
                    break;
                }
                case 'basic': {
                    // Slow drifting dust mote
                    var bf = 0.3 + 0.7*Math.sin(now*0.0008+p.phase);
                    ctx.globalAlpha = p.alpha * bf;
                    ctx.fillStyle='rgba(150,150,160,0.6)';
                    ctx.beginPath(); ctx.arc(p.x,p.y,p.size,0,Math.PI*2); ctx.fill();
                    break;
                }
            }
            ctx.restore();
        });

        ctx.restore();
    });

    // ── Fighting zone: comic impact bursts ────────────────────────────────────
    _comicBursts.forEach(function(b) {
        var age = (now - b.ts) / 1200;
        if (age >= 1) return;
        var scale = 0.5 + age * 0.8;
        var alpha = age < 0.3 ? age/0.3 : 1 - (age-0.3)/0.7;
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.translate(b.x, b.y);
        ctx.scale(scale, scale);
        // Starburst background
        ctx.fillStyle='rgba(255,220,0,0.85)';
        ctx.beginPath();
        for (var i=0;i<10;i++) {
            var ang=i*Math.PI/5;
            var rad=i%2===0?28:14;
            i===0 ? ctx.moveTo(Math.cos(ang)*rad,Math.sin(ang)*rad)
                  : ctx.lineTo(Math.cos(ang)*rad,Math.sin(ang)*rad);
        }
        ctx.closePath(); ctx.fill();
        ctx.strokeStyle='rgba(200,80,0,0.9)'; ctx.lineWidth=2; ctx.stroke();
        // Text
        ctx.fillStyle='rgba(180,0,0,1)';
        ctx.font='bold 14px Impact,sans-serif';
        ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText(b.label,0,0);
        ctx.restore();
    });
    _comicBursts = _comicBursts.filter(function(b){ return now-b.ts < 1200; });
}

// ── Elimination burst effects ─────────────────────────────────────────────────
var _mapBursts = [];

function _triggerElimBursts(newEvents) {
    var existingKeys = {};
    _mapBursts.forEach(function(b){ existingKeys[b.key]=true; });
    (newEvents||[]).forEach(function(ev) {
        if (ev.type !== 'elimination') return;
        var key = ev.user_id+'_'+ev.round;
        if (!existingKeys[key]) {
            _mapBursts.push({key:key, x:ev.x, y:ev.y, startTs:Date.now(),
                text:ev.pet_name||'', style:ev.style||'basic'});
        }
    });
}

function _drawElimBursts(ctx, now) {
    _mapBursts = _mapBursts.filter(function(b){ return now-b.startTs < 2000; });
    _mapBursts.forEach(function(b) {
        var age = (now-b.startTs)/2000;
        if (age>=1) return;
        ctx.save();
        var r1 = 20+age*70;
        ctx.beginPath(); ctx.arc(b.x,b.y,r1,0,Math.PI*2);
        ctx.strokeStyle='rgba(220,50,50,'+(0.7*(1-age)).toFixed(2)+')';
        ctx.lineWidth=3*(1-age)+1; ctx.stroke();
        if (age>0.1) {
            var r2=20+(age-0.1)*90;
            ctx.beginPath(); ctx.arc(b.x,b.y,r2,0,Math.PI*2);
            ctx.strokeStyle='rgba(255,200,50,'+(0.5*(1-(age-0.1)/0.9)).toFixed(2)+')';
            ctx.lineWidth=2; ctx.stroke();
        }
        var rise=age*55;
        var alpha=age<0.5?1:1-(age-0.5)/0.5;
        ctx.globalAlpha=alpha;
        ctx.font='bold 22px serif'; ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText('💀',b.x,b.y-rise);
        if (b.text) {
            ctx.font='bold 10px sans-serif';
            ctx.fillStyle='#ff6060'; ctx.strokeStyle='rgba(0,0,0,0.9)'; ctx.lineWidth=2.5;
            var lbl=b.text.length>14?b.text.slice(0,13)+'…':b.text;
            ctx.strokeText(lbl,b.x,b.y-rise-18); ctx.fillText(lbl,b.x,b.y-rise-18);
        }
        ctx.restore();
    });
}

// ── Draw persistent elim markers ─────────────────────────────────────────────
function _drawElimMarkers(ctx, now) {
    var pulse = 0.5+0.5*Math.sin(now/900);
    (_map.events||[]).forEach(function(ev) {
        if (ev.type!=='elimination') return;
        ctx.save();
        ctx.beginPath(); ctx.arc(ev.x,ev.y,16,0,Math.PI*2);
        ctx.fillStyle='rgba(180,30,30,0.10)'; ctx.fill();
        ctx.strokeStyle='rgba(200,50,50,'+(0.25+pulse*0.15).toFixed(2)+')';
        ctx.lineWidth=1.5; ctx.stroke();
        ctx.globalAlpha=0.75;
        ctx.font='13px serif'; ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText('💀',ev.x,ev.y-1);
        if (ev.pet_name) {
            ctx.font='bold 7px sans-serif'; ctx.globalAlpha=0.55;
            ctx.fillStyle='rgba(255,120,120,1)'; ctx.strokeStyle='rgba(0,0,0,0.8)'; ctx.lineWidth=2;
            var lbl=ev.pet_name.length>12?ev.pet_name.slice(0,11)+'…':ev.pet_name;
            ctx.strokeText(lbl,ev.x,ev.y+13); ctx.fillText(lbl,ev.x,ev.y+13);
        }
        ctx.restore();
    });
}

// ── Draw pet participants ─────────────────────────────────────────────────────
function _drawParticipants(ctx, now) {
    var pulse = 0.5+0.5*Math.sin(now/800);
    var pMap = {};
    (_map.participants||[]).forEach(function(p){ pMap[p.user_id]=p; });
    var aliveSet = {};
    (_map.alive||[]).forEach(function(id){ aliveSet[id]=true; });

    // Build a set of pets eliminated THIS round (shown faded) vs previous rounds (hidden).
    // Pets eliminated in a prior round are removed from the map entirely.
    var elimRound = {};
    (_map.eliminated||[]).forEach(function(e){
        elimRound[e.user_id] = e.round;
    });
    var currentRound = _map.round || 0;

    // Sort: dead first, alive on top
    var sorted = (_map.participants||[]).slice().sort(function(a,b){
        return (aliveSet[a.user_id]?1:0)-(aliveSet[b.user_id]?1:0);
    });

    sorted.forEach(function(p) {
        var uid = p.user_id;
        var apos = _map.animPos[uid];
        if (!apos) return;
        var isAlive = !!aliveSet[uid];

        // Hide pets eliminated in a previous round — only show this round's fresh kills
        if (!isAlive) {
            var er = elimRound[uid];
            // In lobby/pre-game (round 0) show no eliminated markers.
            // During a game, only show pets eliminated in the current round.
            if (currentRound === 0 || er === undefined || er < currentRound) return;
        }

        // Apply filter — skip pets that don't pass
        if (!_petPassesFilter(p)) return;

        // ── TERRAIN FILTERING: Only show pets in visible/focused zones ──
        var petZone = apos.style || 'basic'; // Pet's current zone from position data
        
        if (_map.terrainMode === 'focused' && _map.focusedZone) {
            // In focused mode, only show pets in the focused zone
            if (petZone !== _map.focusedZone) return;
        } else if (_map.terrainMode === 'selective') {
            // In selective mode, only show pets in visible zones
            if (!_map.visibleZones[petZone]) return;
        }
        // In 'all' mode, show all pets regardless of zone visibility

        var x = apos.x, y = apos.y;
        var isNpc = !!p.is_npc;
        var elem = p.element || 'basic';

        // Scale marker size based on how many pets are still alive.
        // Large field (100+) → small icons so they all fit; as pets are
        // eliminated the survivors grow, making late-game feel more epic.
        var aliveCount = (_map.alive || []).length;
        var iconSize;
        if (!isAlive) {
            // Dead markers are always small regardless of field size
            iconSize = 18;
        } else if (aliveCount >= 80) {
            iconSize = 22;
        } else if (aliveCount >= 50) {
            iconSize = 26;
        } else if (aliveCount >= 30) {
            iconSize = 30;
        } else if (aliveCount >= 15) {
            iconSize = 34;
        } else if (aliveCount >= 8) {
            iconSize = 40;
        } else if (aliveCount >= 4) {
            iconSize = 48;
        } else {
            iconSize = 56;
        }
        var ringR = iconSize/2 + 6;
        var ringColor = ELEM_RING[elem] || 'rgba(190,190,200,0.95)';
        var glowColor = ELEM_GLOW[elem] || 'rgba(190,190,200,0.3)';

        ctx.save();
        ctx.globalAlpha = isAlive ? 1.0 : 0.30;

        if (isAlive) {
            // ── Outer glow halo ───────────────────────────────────────────────
            var haloR = ringR + 6 + pulse*5;
            var halo = ctx.createRadialGradient(x,y,ringR,x,y,haloR+4);
            halo.addColorStop(0, glowColor.replace(/[\d.]+\)$/,(0.4+pulse*0.2)+')'));
            halo.addColorStop(1,'rgba(0,0,0,0)');
            ctx.beginPath(); ctx.arc(x,y,haloR+4,0,Math.PI*2);
            ctx.fillStyle=halo; ctx.fill();

            // ── High-contrast backing disc (makes icon pop on any terrain) ───
            ctx.beginPath(); ctx.arc(x,y,iconSize/2+3,0,Math.PI*2);
            ctx.fillStyle='rgba(0,0,0,0.72)'; ctx.fill();

            // ── Element ring ──────────────────────────────────────────────────
            ctx.beginPath(); ctx.arc(x,y,ringR,0,Math.PI*2);
            ctx.strokeStyle=ringColor;
            ctx.lineWidth=isNpc?2:3;
            ctx.shadowColor=glowColor; ctx.shadowBlur=isNpc?6:14;
            ctx.stroke(); ctx.shadowBlur=0;
        } else {
            // Dead: dark backing + grey ring
            ctx.beginPath(); ctx.arc(x,y,iconSize/2+2,0,Math.PI*2);
            ctx.fillStyle='rgba(0,0,0,0.55)'; ctx.fill();
            ctx.beginPath(); ctx.arc(x,y,ringR-2,0,Math.PI*2);
            ctx.strokeStyle='rgba(120,120,120,0.45)'; ctx.lineWidth=1; ctx.stroke();
        }

        // ── Pet image clipped to circle (with padding so emoji isn't cut off) ──
        var img = _map.imgCache[p.species||'Cat'];
        ctx.save();
        ctx.beginPath(); ctx.arc(x,y,iconSize/2,0,Math.PI*2); ctx.clip();
        if (img) {
            // Draw with 10% inset padding so the full emoji is always visible
            var pad = iconSize * 0.10;
            ctx.drawImage(img, x-iconSize/2+pad, y-iconSize/2+pad, iconSize-pad*2, iconSize-pad*2);
        } else {
            ctx.fillStyle=isAlive?ringColor:'rgba(100,100,100,0.4)'; ctx.fill();
            _getPetImg(p.species, function(){ _scheduleMapDraw(); });
        }
        ctx.restore();

        // ── Top-right badge: owner Discord avatar (real) or NPC type emoji ───
        // Hide badge when icons are very small (80+ alive) to reduce clutter
        if (isAlive && iconSize >= 26) {
            var bSize = Math.max(12, Math.round(iconSize * 0.42));
            var bx = x + iconSize/2 - 1;
            var by = y - iconSize/2 + 1;
            var bR = bSize/2;

            if (!isNpc) {
                // ── Real player: show owner Discord avatar ────────────────────
                var aimg = _map.imgCache['__avatar_'+p.user_id];
                if (aimg === undefined && p.avatar_url) {
                    // Not yet loaded — kick off load and skip for now
                    _getOwnerAvatarImg(p.user_id, p.avatar_url, function(){ _scheduleMapDraw(); });
                }
                // Dark backing circle
                ctx.beginPath(); ctx.arc(bx, by, bR+2, 0, Math.PI*2);
                ctx.fillStyle='rgba(0,0,0,0.85)'; ctx.fill();
                // Colored ring border
                ctx.strokeStyle=ringColor; ctx.lineWidth=1.5;
                ctx.beginPath(); ctx.arc(bx, by, bR+2, 0, Math.PI*2); ctx.stroke();
                if (aimg) {
                    ctx.save();
                    ctx.beginPath(); ctx.arc(bx, by, bR, 0, Math.PI*2); ctx.clip();
                    // White base so any transparent pixels in the Discord avatar
                    // don't bleed through the dark backing circle behind it
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(bx-bR, by-bR, bSize, bSize);
                    ctx.globalAlpha = 1.0;
                    ctx.drawImage(aimg, bx-bR, by-bR, bSize, bSize);
                    ctx.restore();
                } else {
                    // Fallback: draw a person silhouette placeholder
                    ctx.fillStyle='rgba(160,160,160,0.6)';
                    ctx.beginPath(); ctx.arc(bx, by, bR, 0, Math.PI*2); ctx.fill();
                    ctx.fillStyle='rgba(80,80,80,0.8)';
                    ctx.beginPath(); ctx.arc(bx, by-bR*0.2, bR*0.38, 0, Math.PI*2); ctx.fill();
                    ctx.beginPath(); ctx.arc(bx, by+bR*0.55, bR*0.55, 0, Math.PI); ctx.fill();
                }
            } else {
                // ── NPC: show element type emoji, full-size and bright ────────
                var eimg = _map.imgCache['__elem_'+elem];
                // Dark backing circle
                ctx.beginPath(); ctx.arc(bx, by, bR+2, 0, Math.PI*2);
                ctx.fillStyle='rgba(0,0,0,0.85)'; ctx.fill();
                // Colored ring border
                ctx.strokeStyle=ringColor; ctx.lineWidth=1.5;
                ctx.beginPath(); ctx.arc(bx, by, bR+2, 0, Math.PI*2); ctx.stroke();
                if (eimg) {
                    // Draw full-brightness element emoji clipped to circle
                    ctx.save();
                    ctx.beginPath(); ctx.arc(bx, by, bR, 0, Math.PI*2); ctx.clip();
                    ctx.drawImage(eimg, bx-bR, by-bR, bSize, bSize);
                    ctx.restore();
                } else if (elem !== 'basic') {
                    _getElemImg(elem, function(){ _scheduleMapDraw(); });
                    // Fallback text label
                    ctx.fillStyle='rgba(200,200,200,0.9)';
                    ctx.font='bold '+(bR)+'px sans-serif';
                    ctx.textAlign='center'; ctx.textBaseline='middle';
                    ctx.fillText(elem.charAt(0).toUpperCase(), bx, by);
                }
            }
        }

        // ── Name label with high-contrast pill ───────────────────────────────
        // Hide labels when icons are very small (80+ alive) to reduce clutter
        if (isAlive && iconSize >= 26) {
            var label = p.pet_name||p.username||'';
            if (label.length>13) label=label.slice(0,12)+'…';
            ctx.font='bold 10px sans-serif';
            ctx.textAlign='center'; ctx.textBaseline='top';
            var tw = ctx.measureText(label).width+10;
            var ty = y+iconSize/2+4;
            // Pill shadow
            ctx.fillStyle='rgba(0,0,0,0.85)';
            if (ctx.roundRect) ctx.roundRect(x-tw/2,ty-1,tw,13,4);
            else ctx.rect(x-tw/2,ty-1,tw,13);
            ctx.fill();
            // Pill border
            ctx.strokeStyle=ringColor; ctx.lineWidth=0.8;
            if (ctx.roundRect) ctx.roundRect(x-tw/2,ty-1,tw,13,4);
            else ctx.rect(x-tw/2,ty-1,tw,13);
            ctx.stroke();
            // Text
            ctx.fillStyle=isNpc?'rgba(210,210,210,0.95)':ringColor;
            ctx.fillText(label,x,ty+1.5);
        }

        ctx.restore();
    });

    // ── Relationship lines (rel filter only) ─────────────────────────────────
    if (_map.filter === 'rel' && _selectedPetUid) {
        var selPos = _map.animPos[_selectedPetUid];
        if (selPos) {
            // Check if selected pet is in a visible zone
            var selPetZone = selPos.style || 'basic';
            var showSelectedPet = true;
            
            if (_map.terrainMode === 'focused' && _map.focusedZone) {
                showSelectedPet = (selPetZone === _map.focusedZone);
            } else if (_map.terrainMode === 'selective') {
                showSelectedPet = _map.visibleZones[selPetZone];
            }
            
            if (showSelectedPet) {
                var relColors = {
                    best_friend: 'rgba(255,215,0,0.7)',
                    friend:      'rgba(80,200,120,0.6)',
                    foe:         'rgba(255,140,0,0.6)',
                    enemy:       'rgba(220,50,50,0.7)',
                };
                var myRels = _map.relMap[_selectedPetUid] || {};
                
                // Forward rels
                Object.keys(myRels).forEach(function(uid2) {
                    var pos2 = _map.animPos[uid2];
                    if (!pos2) return;
                    
                    // Check if target pet is in a visible zone
                    var targetZone = pos2.style || 'basic';
                    var showTargetPet = true;
                    
                    if (_map.terrainMode === 'focused' && _map.focusedZone) {
                        showTargetPet = (targetZone === _map.focusedZone);
                    } else if (_map.terrainMode === 'selective') {
                        showTargetPet = _map.visibleZones[targetZone];
                    }
                    
                    if (!showTargetPet) return; // Don't draw lines to hidden pets
                    
                    var rel = myRels[uid2];
                    ctx.save();
                    ctx.strokeStyle = relColors[rel] || 'rgba(200,200,200,0.4)';
                    ctx.lineWidth = rel === 'enemy' || rel === 'best_friend' ? 2 : 1.5;
                    ctx.setLineDash(rel === 'foe' || rel === 'enemy' ? [6,4] : []);
                    ctx.beginPath(); ctx.moveTo(selPos.x, selPos.y); ctx.lineTo(pos2.x, pos2.y); ctx.stroke();
                    ctx.setLineDash([]);
                    // Midpoint label
                    var mx2 = (selPos.x+pos2.x)/2, my2 = (selPos.y+pos2.y)/2;
                    ctx.font = 'bold 8px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                    ctx.fillStyle = 'rgba(0,0,0,0.7)';
                    ctx.fillRect(mx2-18, my2-7, 36, 14);
                    ctx.fillStyle = relColors[rel] || 'rgba(200,200,200,0.8)';
                    ctx.fillText(rel.replace('_',' '), mx2, my2);
                    ctx.restore();
                });
                
                // Reverse rels (others pointing at selected)
                (_map.participants||[]).forEach(function(p) {
                    var uid2 = p.user_id;
                    if (uid2 === _selectedPetUid) return;
                    if (myRels[uid2]) return; // already drawn
                    var theirRels = _map.relMap[uid2] || {};
                    var rel = theirRels[_selectedPetUid];
                    if (!rel) return;
                    var pos2 = _map.animPos[uid2];
                    if (!pos2) return;
                    
                    // Check if source pet is in a visible zone
                    var sourceZone = pos2.style || 'basic';
                    var showSourcePet = true;
                    
                    if (_map.terrainMode === 'focused' && _map.focusedZone) {
                        showSourcePet = (sourceZone === _map.focusedZone);
                    } else if (_map.terrainMode === 'selective') {
                        showSourcePet = _map.visibleZones[sourceZone];
                    }
                    
                    if (!showSourcePet) return; // Don't draw lines from hidden pets
                    
                    ctx.save();
                    ctx.strokeStyle = relColors[rel] || 'rgba(200,200,200,0.4)';
                    ctx.lineWidth = 1.5;
                    ctx.setLineDash([4,4]);
                    ctx.beginPath(); ctx.moveTo(selPos.x, selPos.y); ctx.lineTo(pos2.x, pos2.y); ctx.stroke();
                    ctx.setLineDash([]);
                    ctx.restore();
                });
            }
        }
    }
}

// ── Image loaders ─────────────────────────────────────────────────────────────
function _getPetImg(species, cb) {
    var key = species||'Cat';
    if (_map.imgCache[key]) { cb(_map.imgCache[key]); return; }
    var img = new Image();
    img.onload = function(){ _map.imgCache[key]=img; cb(img); };
    img.onerror = function(){
        var fb=new Image();
        fb.onload=function(){ _map.imgCache[key]=fb; cb(fb); };
        fb.src='/static/Emojis/Pets/Cat.png';
    };
    img.src='/static/Emojis/Pets/'+key+'.png';
}
function _getElemImg(elem, cb) {
    if (!elem||elem==='basic') { cb(null); return; }
    var key='__elem_'+elem;
    if (_map.imgCache[key]!==undefined) { cb(_map.imgCache[key]); return; }
    var img=new Image();
    img.onload=function(){ _map.imgCache[key]=img; cb(img); };
    img.onerror=function(){ _map.imgCache[key]=null; cb(null); };
    img.src='/static/Emojis/Pets/Deco/'+elem.charAt(0).toUpperCase()+elem.slice(1)+'.png';
}
function _getOwnerAvatarImg(uid, avatarUrl, cb) {
    var key = '__avatar_'+uid;
    if (_map.imgCache[key] !== undefined) { cb(_map.imgCache[key]); return; }
    if (!avatarUrl) { _map.imgCache[key] = null; cb(null); return; }
    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function(){ _map.imgCache[key]=img; cb(img); };
    img.onerror = function(){ _map.imgCache[key]=null; cb(null); };
    img.src = avatarUrl;
}
function _preloadMapImages() {
    (_map.participants||[]).forEach(function(p){
        _getPetImg(p.species,function(){});
        _getElemImg(p.element,function(){});
        if (p.element2) _getElemImg(p.element2,function(){});
        if (!p.is_npc && p.avatar_url) {
            _getOwnerAvatarImg(p.user_id, p.avatar_url, function(){ _scheduleMapDraw(); });
        }
    });
}

// ── Main render loop ──────────────────────────────────────────────────────────
var _mapRafId = null;

function _startMapLoop() {
    if (_mapRafId) return;
    function loop() {
        var now = Date.now();
        _tickParticles(now);
        _drawMap(now);
        // Update round countdown in stats bar every second
        var timerEl = el('ss-map-round-timer');
        if (timerEl && _map.nextRoundAt > 0) {
            var rem = _map.nextRoundAt - Math.floor(now / 1000);
            if (rem > 0) {
                var m = Math.floor(rem / 60), s = rem % 60;
                timerEl.textContent = m + ':' + (s < 10 ? '0' : '') + s;
            } else {
                timerEl.textContent = '0:00';
            }
        } else if (timerEl) {
            timerEl.textContent = '';
        }
        _mapRafId = requestAnimationFrame(loop);
    }
    _mapRafId = requestAnimationFrame(loop);
}

function _stopMapLoop() {
    if (_mapRafId) { cancelAnimationFrame(_mapRafId); _mapRafId=null; }
}

var _mapDrawPending = false;
function _scheduleMapDraw() {
    if (_mapRafId) return; // loop already running
    if (_mapDrawPending) return;
    _mapDrawPending = true;
    requestAnimationFrame(function(){
        _mapDrawPending=false;
        _drawMap(Date.now());
    });
}

function _drawMap(now) {
    var canvas = _map.canvas;
    if (!canvas) return;
    var ctx = _map.ctx;
    var W = _map.W, H = _map.H;
    now = now || Date.now();

    // True fill: read the wrapper's actual rendered size every frame
    var rect = canvas.parentElement.getBoundingClientRect();
    var dpr = window.devicePixelRatio||1;
    var cssW = rect.width;
    var cssH = rect.height;
    if (cssH < 10) cssH = Math.round(cssW * (H/W)); // fallback if wrapper has no height yet

    var pw = Math.floor(cssW*dpr), ph = Math.floor(cssH*dpr);
    if (canvas.width!==pw||canvas.height!==ph) {
        canvas.width=pw; canvas.height=ph;
        if (!_map._userPanned) {
            _map.scale=_fitScale(cssW,cssH,W,H);
            _centerMap(cssW,cssH);
        }
    }

    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.save();
    ctx.scale(dpr,dpr);

    ctx.translate(_map.ox, _map.oy);
    ctx.scale(_map.scale, _map.scale);

    // Interactive terrain system
    if (_map.terrainLayers && Object.keys(_map.terrainLayers).length > 0) {
        _drawInteractiveTerrain(ctx);
    } else if (_map.terrain) {
        // Fallback to static terrain
        ctx.drawImage(_map.terrain, 0, 0);
    }

    // Animated zone particles
    _drawZoneParticles(ctx, now);

    // Persistent elim markers
    _drawElimMarkers(ctx, now);

    // Active burst animations
    _drawElimBursts(ctx, now);

    // Pet icons
    _drawParticipants(ctx, now);

    ctx.restore();
}

// ── Position animation ────────────────────────────────────────────────────────
function _animatePositions(newPositions) {
    var startPos = {};
    Object.keys(_map.animPos).forEach(function(uid){
        startPos[uid]={x:_map.animPos[uid].x,y:_map.animPos[uid].y};
    });
    Object.keys(newPositions).forEach(function(uid){
        if (!startPos[uid]) startPos[uid]={x:newPositions[uid].x,y:newPositions[uid].y};
    });
    var duration=800, start=null;
    function step(ts) {
        if (!start) start=ts;
        var t=Math.min(1,(ts-start)/duration);
        var ease=1-Math.pow(1-t,3);
        Object.keys(newPositions).forEach(function(uid){
            var s=startPos[uid]||newPositions[uid];
            var e=newPositions[uid];
            _map.animPos[uid]={x:s.x+(e.x-s.x)*ease,y:s.y+(e.y-s.y)*ease,style:e.style||'basic'};
        });
        if (t<1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// ── Map stats bar updater ─────────────────────────────────────────────────────
function _updateMapStatsBar() {
    var aliveCount = (_map.alive||[]).length;
    var totalParts = (_map.participants||[]).length;
    var elimCount  = (_map.eliminated||[]).length;

    var aEl = el('ss-map-alive-count');
    var eEl = el('ss-map-elim-count');
    var bar = el('ss-map-alive-fill');
    if (aEl) aEl.textContent = aliveCount;
    if (eEl) eEl.textContent = elimCount;
    if (bar && totalParts > 0) {
        bar.style.width = Math.round((aliveCount / totalParts) * 100) + '%';
    }

    // Round label
    var rl = el('ss-map-round-label');
    if (rl) {
        if (_map.round > 0) rl.textContent = 'Round ' + _map.round;
        else if (totalParts > 0) rl.textContent = 'Pre-game';
        else rl.textContent = '';
    }

    // Player/NPC counts
    var realCount = (_map.participants||[]).filter(function(p){ return !p.is_npc; }).length;
    var npcCount  = totalParts - realCount;
    var pcEl = el('ss-map-part-count');
    if (pcEl) pcEl.textContent = realCount + ' players · ' + npcCount + ' NPCs';
}

// ── Filter helpers ────────────────────────────────────────────────────────────
function _petPassesFilter(p) {
    var uid = p.user_id;
    var aliveSet = {};
    (_map.alive||[]).forEach(function(id){ aliveSet[id]=true; });
    var isAlive = !!aliveSet[uid];
    var isNpc   = !!p.is_npc;

    // For filter purposes, "eliminated" means eliminated this round only
    // (previous-round eliminations are hidden from the map entirely)
    var currentRound = _map.round || 0;
    var elimRound = null;
    if (!isAlive) {
        (_map.eliminated||[]).forEach(function(e){
            if (e.user_id === uid) elimRound = e.round;
        });
        // If eliminated in a prior round, treat as invisible for all filters
        if (currentRound > 0 && (elimRound === null || elimRound < currentRound)) {
            return false;
        }
    }

    switch (_map.filter) {
        case 'player': return !isNpc;
        case 'npc':    return isNpc;
        case 'alive':  return isAlive;
        case 'elim':   return !isAlive;  // only this-round elims reach here
        case 'rel': {
            // Show the selected pet + all pets that have a relationship with it
            if (!_selectedPetUid) return true;
            if (uid === _selectedPetUid) return true;
            var myRels = _map.relMap[_selectedPetUid] || {};
            if (myRels[uid]) return true;
            // Also check reverse direction
            var theirRels = _map.relMap[uid] || {};
            if (theirRels[_selectedPetUid]) return true;
            return false;
        }
        default: return true; // 'all'
    }
}

// Public: set map filter from button clicks
window.ssMapFilter = function(mode) {
    _map.filter = mode;
    // Update active button state
    ['all','player','npc','alive','elim','rel'].forEach(function(m) {
        var btn = el('ss-mf-' + m);
        if (btn) btn.classList.toggle('active', m === mode);
    });
};

// ── Zone Room System (Public API) ────────────────────────────────────────────
// ssEnterZone: zoom into a zone so it fills the canvas like a room
// ssExitZoom:  zoom back out to the full map view

window.ssEnterZone = function(zoneName) {
    if (!MAP_ZONES[zoneName]) return;

    _map.focusedZone = zoneName;
    _map.terrainMode = 'focused';

    // Show back button + zone name label
    var backEl = document.getElementById('ss-map-zone-back');
    var nameEl = document.getElementById('ss-map-zone-name-label');
    if (backEl) backEl.style.display = 'block';
    if (nameEl) {
        var zoneColor = ELEM_RING[zoneName] || 'rgba(190,190,200,0.95)';
        nameEl.textContent = (MAP_STYLE_NAMES[zoneName] || zoneName).toUpperCase();
        nameEl.style.color = zoneColor;
    }

    // Hide the zoom hint while in room mode (hint removed)

    // Animate camera into the zone
    _focusZone(zoneName);
};

window.ssExitZoom = function() {
    _map.focusedZone = null;
    _map.terrainMode = 'all';

    // Hide back button
    var backEl = document.getElementById('ss-map-zone-back');
    if (backEl) backEl.style.display = 'none';

    // Animate back to full map
    _map._userPanned = false;
    var s = _mapCssSize();
    _map.scale = _fitScale(s.w, s.h, _map.W, _map.H);
    _centerMap(s.w, s.h);
    _scheduleMapDraw();
};

// Keep ssFocusZone as an alias for backward compat (used internally)
window.ssFocusZone = window.ssEnterZone;

// ssTerrainMode and ssToggleZone kept as no-ops for any lingering references
window.ssTerrainMode = function() {};
window.ssToggleZone  = function() {};

function _initTerrainControls() {
    // No-op — terrain controls row removed; zone entry is via direct click
}


function _getZoneAtPosition(x, y) {
    // Check which zone contains the given coordinates
    for (var zoneName in MAP_ZONES) {
        var zone = MAP_ZONES[zoneName];
        if (x >= zone[0] && x <= zone[2] && y >= zone[1] && y <= zone[3]) {
            return zoneName;
        }
    }
    return null;
}

// ── Fetch map data from server ────────────────────────────────────────────────
function _refreshMap() {
    fetch('/api/ss/map')
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (!d||d.status==='none') return;
            var needTerrain = !_map.terrain||_map.seed!==d.map_seed;
            _map.seed=d.map_seed;
            _map.W=d.map_size[0]; _map.H=d.map_size[1];
            _map.alive=d.alive_ids||[];
            _map.participants=d.participants||[];
            _map.round=d.round_index||0;
            _map.eliminated=d.eliminated||[];
            _map.rounds=d.rounds||[];
            _map.relMap=d.rel_map||{};
            _map.nextRoundAt=d.next_round_at||0;
            _map.chargeStacks=d.charge_stacks||{};
            _updateMapStatsBar();

            var isFirstLoad = !_map.terrain&&Object.keys(_map.animPos).length===0;
            var prevCount = (_map.events||[]).length;
            _map.events=d.events||[];
            if (!isFirstLoad&&d.events&&d.events.length>prevCount) {
                _triggerElimBursts(d.events.slice(prevCount));
            }

            if (needTerrain) {
                _map.terrain=_buildTerrain(_map.seed,_map.W,_map.H);
                _buildTerrainLayers(_map.terrain,_map.W,_map.H);
                _initZoneParticles(_map.seed);
                // Initialize terrain control buttons
                _initTerrainControls();
            }

            var newPos=d.positions||{};
            if (Object.keys(_map.animPos).length===0) {
                _map.animPos={};
                Object.keys(newPos).forEach(function(uid){
                    _map.animPos[uid]={x:newPos[uid].x,y:newPos[uid].y,style:newPos[uid].style||'basic'};
                });
                _preloadMapImages();
                // Auto-fit on first load — card is now visible so size is real
                _map._userPanned = false;
                var s = _mapCssSize();
                if (s.w > 10 && s.h > 10) {
                    _map.scale = _fitScale(s.w, s.h, _map.W, _map.H);
                    _centerMap(s.w, s.h);
                }
            } else {
                _preloadMapImages();
                _animatePositions(newPos);
            }

            var lbl=document.getElementById('ss-map-round-label');
            if (lbl) lbl.textContent=d.round_index>0?'Round '+d.round_index:'Pre-game';

            // Ensure loop is running
            _startMapLoop();
        })
        .catch(function(){});
}

// ── Viewport helpers ──────────────────────────────────────────────────────────
function _mapCssSize() {
    // Returns {w, h} — the actual CSS pixel size of the canvas wrapper
    var canvas = _map.canvas;
    if (!canvas || !canvas.parentElement) return {w:800, h:533};
    var rect = canvas.parentElement.getBoundingClientRect();
    return {w: rect.width, h: rect.height};
}
function _fitScale(cssW,cssH,W,H) {
    return Math.min(cssW/W,cssH/H);
}
function _centerMap(cssW,cssH) {
    _map.ox=(cssW-_map.W*_map.scale)/2;
    _map.oy=(cssH-_map.H*_map.scale)/2;
}

// ── Public controls ───────────────────────────────────────────────────────────
window.ssMapReset = function() {};
window.ssMapZoomIn = function() {};
window.ssMapZoomOut = function() {};

// ── Pet detail panel ─────────────────────────────────────────────────────────
var _selectedPetUid = null;

function _openPetPanel(uid) {
    _selectedPetUid = uid;
    var panel = el('ss-map-pet-panel');
    if (!panel) return;

    var pMap = {};
    (_map.participants||[]).forEach(function(p){ pMap[p.user_id]=p; });
    var aliveSet = {};
    (_map.alive||[]).forEach(function(id){ aliveSet[id]=true; });

    var p = pMap[uid];
    if (!p) return;

    var isAlive = !!aliveSet[uid];
    var elem  = p.element  || 'basic';
    var elem2 = p.element2 || '';
    var ring  = ELEM_RING[elem] || 'rgba(190,190,200,0.95)';

    // Charge stacks — capped at 5
    var chargeStacks = Math.min(5, (_map.chargeStacks||{})[uid] || 0);

    // Kills by this pet
    var kills = [];
    (_map.eliminated||[]).forEach(function(e){
        var kuids = e.eliminated_by_uids||[];
        if (!kuids.length && e.eliminated_by_uid) kuids=[e.eliminated_by_uid];
        if (kuids.indexOf(uid)!==-1) kills.push(e);
    });

    // How this pet was eliminated
    var elimEntry = null;
    (_map.eliminated||[]).forEach(function(e){ if (e.user_id===uid) elimEntry=e; });

    // Survive score
    var surviveScore = ((p.level||1) / Math.max(1, p.multiplier||1) / 10).toFixed(2);

    // Per-round feed lines mentioning this pet
    var petName = p.pet_name||p.username||'';
    var feedLines = [];
    (_map.rounds||[]).forEach(function(r){
        var rIdx = r.round_index;
        var myActions = (r.actions||[]).filter(function(a){ return a.indexOf(petName)!==-1; });
        var myElims   = (r.eliminations||[]).filter(function(e){ return e.indexOf(petName)!==-1; });
        if (myActions.length||myElims.length) {
            feedLines.push({type:'round', text:'━━━ Round '+rIdx+' ━━━'});
            myActions.forEach(function(a){ feedLines.push({type:'action',text:a}); });
            myElims.forEach(function(e){ feedLines.push({type:'elim',text:e}); });
        }
    });

    var statusBadge = isAlive
        ? '<span style="color:#4caf50;font-weight:700;font-size:0.72rem">● Alive</span>'
        : '<span style="color:#f44336;font-weight:700;font-size:0.72rem">💀 Eliminated R'+(elimEntry?elimEntry.round:'?')+'</span>';

    // ── SECTION 1: Pet identity block ─────────────────────────────────────────
    var headerHtml =
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'+
            // Pet emoji — plain square container, no ring, no clip, full emoji visible
            '<div style="flex-shrink:0;width:66px;height:66px;display:flex;align-items:center;justify-content:center">'+
                '<img src="/static/Emojis/Pets/'+(p.species||'Cat')+'.png" '+
                    'style="width:66px;height:66px;object-fit:contain" '+
                    'onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">'+
            '</div>'+
            '<div style="min-width:0">'+
                '<div style="font-weight:700;font-size:0.92rem;color:'+ring+';white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+esc(p.pet_name||p.username)+'</div>'+
                '<div style="color:rgba(200,200,200,0.65);font-size:0.7rem;margin-top:2px">'+esc(p.species||'Unknown')+'</div>'+
                '<div style="margin-top:4px">'+statusBadge+'</div>'+
            '</div>'+
        '</div>';

    // ── SECTION 2: Owner block ─────────────────────────────────────────────────
    var ownerHtml;
    if (p.is_npc) {
        ownerHtml =
            '<div style="display:flex;align-items:center;gap:8px;padding:6px 9px;background:rgba(100,100,100,0.12);border:1px solid rgba(255,255,255,0.08);border-radius:8px;margin-bottom:10px">'+
                '<div style="width:34px;height:34px;border-radius:50%;background:rgba(70,70,70,0.7);border:1px solid rgba(255,255,255,0.15);display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0">🤖</div>'+
                '<div>'+
                    '<div style="font-size:0.6rem;color:rgba(150,150,150,0.7);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:1px">Owner</div>'+
                    '<div style="font-size:0.78rem;color:rgba(200,200,200,0.85);font-weight:600">NPC</div>'+
                '</div>'+
            '</div>';
    } else {
        var avatarSrc = p.avatar_url || '';
        ownerHtml =
            '<div style="display:flex;align-items:center;gap:8px;padding:6px 9px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);border-radius:8px;margin-bottom:10px">'+
                '<img src="'+esc(avatarSrc)+'" '+
                    'style="width:34px;height:34px;border-radius:50%;border:2px solid '+ring+';object-fit:cover;flex-shrink:0" '+
                    'onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">'+
                '<div style="min-width:0">'+
                    '<div style="font-size:0.6rem;color:rgba(150,150,150,0.7);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:1px">Owner</div>'+
                    '<div style="font-size:0.78rem;color:rgba(220,220,220,0.95);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+esc(p.username||'Unknown')+'</div>'+
                '</div>'+
            '</div>';
    }

    // ── SECTION 3: Stats grid ──────────────────────────────────────────────────
    // Helper: element/category badge img
    function _eBadge(e) {
        if (!e||e==='basic') return '';
        return '<img src="/static/Emojis/Pets/Deco/'+e.charAt(0).toUpperCase()+e.slice(1)+'.png" '+
            'style="width:15px;height:15px;object-fit:contain;vertical-align:middle;margin-right:3px" onerror="this.style.display=\'none\'">';
    }

    // Category (type) — capitalise for display and image lookup
    var cat = p.category || 'land';
    var catDisplay = cat.charAt(0).toUpperCase() + cat.slice(1); // "Land", "Flying", "Swimming"

    // Charge bar — 5 pips max
    var chargeColor = chargeStacks >= 5 ? '#ff6b35' : chargeStacks >= 3 ? '#ffd700' : chargeStacks >= 1 ? '#4caf50' : 'rgba(160,160,160,0.5)';
    var chargePips = '';
    for (var ci=0; ci<5; ci++) {
        chargePips += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 2px;'+
            'background:'+(ci<chargeStacks?chargeColor:'rgba(60,60,60,0.7)')+';'+
            'box-shadow:'+(ci<chargeStacks?'0 0 4px '+chargeColor:'none')+'"></span>';
    }
    var chargeLabel = chargeStacks === 0 ? 'None' : chargeStacks+'/5';

    var lbl = 'style="color:rgba(150,150,150,0.75);font-size:0.67rem;padding-top:1px"';
    var val  = 'style="font-size:0.72rem;color:rgba(220,220,220,0.9)"';

    var statsHtml =
        '<div style="display:grid;grid-template-columns:auto 1fr;gap:5px 10px;margin-bottom:10px;align-items:center">'+
            // Type (category)
            '<span '+lbl+'>Type</span>'+
            '<span '+val+'>'+_eBadge(cat)+'<span style="vertical-align:middle">'+esc(catDisplay)+'</span></span>'+
            // Element 1
            '<span '+lbl+'>Element</span>'+
            '<span '+val+'>'+_eBadge(elem)+'<span style="vertical-align:middle">'+esc(elem)+'</span></span>'+
            // Element 2 (only if present)
            (elem2&&elem2!=='basic'
                ? '<span '+lbl+'>Element 2</span><span '+val+'>'+_eBadge(elem2)+'<span style="vertical-align:middle">'+esc(elem2)+'</span></span>'
                : '')+
            // Survive Score
            '<span '+lbl+'>Survive Score</span>'+
            '<span style="color:var(--gold-primary,#ffd700);font-weight:700;font-size:0.72rem">'+surviveScore+'</span>'+
            // Charge
            '<span '+lbl+'>Charge</span>'+
            '<span style="display:flex;align-items:center;gap:6px">'+
                chargePips+
                '<span style="color:'+chargeColor+';font-weight:600;font-size:0.67rem">'+chargeLabel+'</span>'+
            '</span>'+
            // Eliminations
            '<span '+lbl+'>Eliminations</span>'+
            '<span style="color:'+(kills.length>0?'#4caf50':'rgba(180,180,180,0.5)')+';font-weight:700;font-size:0.72rem">'+kills.length+'</span>'+
        '</div>';

    // ── SECTION 4: Eliminator row (only when dead) ─────────────────────────────
    var elimHtml = '';
    if (!isAlive && elimEntry) {
        elimHtml =
            '<div style="padding:6px 9px;background:rgba(244,67,54,0.10);border:1px solid rgba(244,67,54,0.28);border-radius:7px;margin-bottom:10px;font-size:0.68rem;color:rgba(255,160,160,0.9)">'+
                '💀 Eliminated by <strong style="color:rgba(255,200,200,0.95)">'+esc(elimEntry.eliminated_by||'Unknown')+'</strong>'+
                (elimEntry.location?' <span style="color:rgba(200,160,160,0.7)">at '+esc(elimEntry.location)+'</span>':'')+
                ' <span style="color:rgba(200,140,140,0.6)">(Round '+(elimEntry.round||'?')+')</span>'+
            '</div>';
    }

    // ── SECTION 5: Kill list ───────────────────────────────────────────────────
    var killsHtml = '';
    if (kills.length > 0) {
        killsHtml =
            '<div style="margin-bottom:8px">'+
                '<div style="font-size:0.6rem;color:rgba(150,150,150,0.65);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:4px">Kills</div>'+
                kills.map(function(k){
                    return '<div style="font-size:0.67rem;color:rgba(200,200,200,0.85);padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.04)">'+
                        '⚔️ <strong style="color:rgba(255,255,255,0.9)">'+esc(k.pet_name||k.username||'?')+'</strong>'+
                        ' <span style="color:rgba(150,150,150,0.5)">R'+(k.round||'?')+'</span>'+
                    '</div>';
                }).join('')+
            '</div>';
    }

    // ── SECTION 6: Activity feed ───────────────────────────────────────────────
    var feedHtml = '<div style="font-size:0.6rem;color:rgba(150,150,150,0.65);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:4px">Activity</div>';
    if (feedLines.length > 0) {
        feedHtml +=
            '<div style="max-height:220px;overflow-y:auto;padding-right:2px">'+
                feedLines.map(function(item){
                    var c = item.type==='elim'?'rgba(255,120,120,0.9)':item.type==='round'?'rgba(255,215,0,0.5)':'rgba(200,200,200,0.8)';
                    return '<div style="font-size:0.65rem;color:'+c+';padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.04);line-height:1.4">'+esc(item.text)+'</div>';
                }).join('')+
            '</div>';
    } else {
        feedHtml += '<div style="font-size:0.65rem;color:rgba(150,150,150,0.4);text-align:center;padding:8px 0">No activity recorded yet.</div>';
    }

    var panelBody = el('ss-map-pet-panel-body');
    if (panelBody) panelBody.innerHTML = headerHtml + ownerHtml + statsHtml + elimHtml + killsHtml + feedHtml;
    panel.style.borderColor = ring;
    panel.style.boxShadow = '0 0 28px '+ring.replace('0.95','0.25')+', -2px 0 0 '+ring.replace('0.95','0.15');
    panel.style.display = 'flex';
}

function _closePetPanel() {
    _selectedPetUid = null;
    var panel = el('ss-map-pet-panel');
    if (panel) panel.style.display = 'none';
}
window._closePetPanel = _closePetPanel;

// ── Interaction: pan, zoom, tooltip ──────────────────────────────────────────
function _mapInitInteraction() {
    var canvas = _map.canvas;
    if (!canvas) return;

    // Click: open/close pet detail panel OR zone interaction
    canvas.addEventListener('click', function(e) {
        if (_map._wasDragging) { _map._wasDragging=false; return; }
        var rect=canvas.getBoundingClientRect();
        var mx=(e.clientX-rect.left-_map.ox)/_map.scale;
        var my=(e.clientY-rect.top-_map.oy)/_map.scale;
        
        // First check for pet clicks
        var hit=null, hitDist=9999;
        var aliveSet={};
        (_map.alive||[]).forEach(function(id){ aliveSet[id]=true; });
        var currentRound=_map.round||0;
        var elimRoundMap={};
        (_map.eliminated||[]).forEach(function(e){ elimRoundMap[e.user_id]=e.round; });
        Object.keys(_map.animPos).forEach(function(uid){
            // Skip pets that are hidden (eliminated in a prior round)
            if (!aliveSet[uid]) {
                var er=elimRoundMap[uid];
                if (currentRound===0||er===undefined||er<currentRound) return;
            }
            
            // ── TERRAIN FILTERING: Only check pets in visible zones ──
            var pos = _map.animPos[uid];
            var petZone = pos.style || 'basic';
            
            if (_map.terrainMode === 'focused' && _map.focusedZone) {
                if (petZone !== _map.focusedZone) return;
            } else if (_map.terrainMode === 'selective') {
                if (!_map.visibleZones[petZone]) return;
            }
            
            var dx=mx-pos.x, dy=my-pos.y;
            var d=Math.sqrt(dx*dx+dy*dy);
            if (d<28&&d<hitDist){ hit=uid; hitDist=d; }
        });
        
        if (hit) { 
            _selectedPetUid===hit ? _closePetPanel() : _openPetPanel(hit); 
        } else {
            _closePetPanel();
            
            // Plain click on a zone = enter it as a room (zoom in)
            var clickedZone = _getZoneAtPosition(mx, my);
            if (clickedZone) {
                if (_map.focusedZone === clickedZone) {
                    // Click same zone again = exit
                    ssExitZoom();
                } else {
                    ssEnterZone(clickedZone);
                }
            }
        }
    });

    // Scroll zoom disabled — map is fixed, users navigate via zone clicks only
    canvas.addEventListener('wheel', function(e) { e.preventDefault(); },{passive:false});

    canvas.addEventListener('contextmenu',function(e){ e.preventDefault(); });

    // Hover tooltip
    canvas.addEventListener('mousemove', function(e) {
        if (_map.dragging) return;
        var rect=canvas.getBoundingClientRect();
        var mx=(e.clientX-rect.left-_map.ox)/_map.scale;
        var my=(e.clientY-rect.top-_map.oy)/_map.scale;
        var hit=null, hitDist=9999;
        var pMap={};
        (_map.participants||[]).forEach(function(p){ pMap[p.user_id]=p; });
        var aliveSet={};
        (_map.alive||[]).forEach(function(id){ aliveSet[id]=true; });
        var currentRound2=_map.round||0;
        var elimRoundMap2={};
        (_map.eliminated||[]).forEach(function(e){ elimRoundMap2[e.user_id]=e.round; });
        Object.keys(_map.animPos).forEach(function(uid){
            // Skip hidden pets (eliminated in a prior round)
            if (!aliveSet[uid]) {
                var er=elimRoundMap2[uid];
                if (currentRound2===0||er===undefined||er<currentRound2) return;
            }
            
            // ── TERRAIN FILTERING: Only check pets in visible zones ──
            var pos = _map.animPos[uid];
            var petZone = pos.style || 'basic';
            
            if (_map.terrainMode === 'focused' && _map.focusedZone) {
                if (petZone !== _map.focusedZone) return;
            } else if (_map.terrainMode === 'selective') {
                if (!_map.visibleZones[petZone]) return;
            }
            
            var dx=mx-pos.x,dy=my-pos.y;
            var d=Math.sqrt(dx*dx+dy*dy);
            if (d<26&&d<hitDist){ hit=uid; hitDist=d; }
        });
        var tip=el('ss-map-tooltip');
        if (hit&&tip) {
            // Show pet tooltip (existing code)
            var p=pMap[hit]||{};
            var isAlive=!!aliveSet[hit];
            var elem=p.element||'basic';
            var ring=ELEM_RING[elem]||'rgba(190,190,200,0.95)';
            var tipChargeStacks=Math.min(5,(_map.chargeStacks||{})[hit]||0);
            var killCount=0;
            (_map.eliminated||[]).forEach(function(e){
                var kuids=e.eliminated_by_uids||[];
                if (!kuids.length&&e.eliminated_by_uid) kuids=[e.eliminated_by_uid];
                if (kuids.indexOf(hit)!==-1) killCount++;
            });
            var elimEntry=null;
            (_map.eliminated||[]).forEach(function(e){ if(e.user_id===hit) elimEntry=e; });
            var elemHtml=(elem!=='basic')
                ?'<img src="/static/Emojis/Pets/Deco/'+elem.charAt(0).toUpperCase()+elem.slice(1)+'.png" '+
                 'style="width:13px;height:13px;object-fit:contain;vertical-align:middle;margin-right:2px" onerror="this.style.display=\'none\'">'
                :'';
            var npcHtml=p.is_npc
                ?'<span style="font-size:0.5rem;background:rgba(100,100,100,0.4);border:1px solid rgba(255,255,255,0.1);border-radius:3px;padding:1px 4px;margin-left:4px;color:rgba(200,200,200,0.7)">NPC</span>'
                :'';
            var statusHtml=isAlive
                ?'<span style="color:#4caf50;font-weight:600">● Alive</span>'
                :'<span style="color:#f44336;font-weight:600">💀 R'+(elimEntry?elimEntry.round:'?')+'</span>';
            var elimByRow='';
            if (!isAlive&&elimEntry) {
                elimByRow='<span style="color:rgba(160,160,160,0.6)">Elim by</span>'+
                    '<span style="color:rgba(255,140,140,0.9)">'+esc(elimEntry.eliminated_by||'Unknown')+'</span>';
            }
            // Owner row: Discord avatar for real players, NPC badge for NPCs
            var ownerRowHtml='';
            if (!p.is_npc) {
                ownerRowHtml='<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;padding:4px 6px;background:rgba(255,255,255,0.04);border-radius:5px">'+
                    '<img src="'+esc(p.avatar_url||'')+'" style="width:20px;height:20px;border-radius:50%;border:1px solid '+ring+';object-fit:cover;flex-shrink:0" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">'+
                    '<span style="font-size:0.65rem;color:rgba(200,200,200,0.8)">'+esc(p.username||'Unknown')+'</span>'+
                '</div>';
            }
            // Charge pips
            var tipChargeColor=tipChargeStacks>=5?'#ff6b35':tipChargeStacks>=3?'#ffd700':tipChargeStacks>=1?'#4caf50':'rgba(80,80,80,0.5)';
            var tipChargePips='';
            for(var ci2=0;ci2<5;ci2++) tipChargePips+='<span style="display:inline-block;width:7px;height:7px;border-radius:50%;margin:0 1px;background:'+(ci2<tipChargeStacks?tipChargeColor:'rgba(60,60,60,0.6)')+'"></span>';
            tip.style.cssText='position:absolute;pointer-events:none;z-index:10;'+
                'background:rgba(6,6,14,0.97);border:1px solid '+ring+';'+
                'border-radius:10px;padding:9px 11px;font-size:0.7rem;'+
                'color:rgba(255,255,255,0.9);'+
                'box-shadow:0 0 18px '+ring.replace('0.95','0.25')+';min-width:170px;max-width:230px';
            tip.innerHTML=
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'+
                    '<div style="width:38px;height:38px;border-radius:50%;border:2px solid '+ring+';background:rgba(0,0,0,0.5);overflow:hidden;display:flex;align-items:center;justify-content:center;flex-shrink:0">'+
                        '<img src="/static/Emojis/Pets/'+(p.species||'Cat')+'.png" '+
                            'style="width:34px;height:34px;object-fit:contain" '+
                            'onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">'+
                    '</div>'+
                    '<div>'+
                        '<div style="font-weight:700;font-size:0.78rem;color:'+ring+'">'+esc(p.pet_name||p.username)+npcHtml+'</div>'+
                        '<div style="color:rgba(190,190,190,0.7);font-size:0.63rem">'+esc(p.species||'Unknown')+'</div>'+
                    '</div>'+
                '</div>'+
                ownerRowHtml+
                '<div style="display:grid;grid-template-columns:auto 1fr;gap:2px 9px;font-size:0.64rem;color:rgba(200,200,200,0.85)">'+
                    '<span style="color:rgba(160,160,160,0.6)">Status</span><span>'+statusHtml+'</span>'+
                    '<span style="color:rgba(160,160,160,0.6)">Type</span><span>'+elemHtml+esc(elem)+'</span>'+
                    '<span style="color:rgba(160,160,160,0.6)">Charge</span><span>'+tipChargePips+'</span>'+
                    '<span style="color:rgba(160,160,160,0.6)">Kills</span><span style="color:'+(killCount>0?'#4caf50':'rgba(200,200,200,0.4)')+';font-weight:600">'+killCount+'</span>'+
                    elimByRow+
                '</div>'+
                '<div style="margin-top:6px;font-size:0.58rem;color:rgba(160,160,160,0.4);text-align:center">click for full details</div>';
            tip.style.display='block';
            var tipX=e.clientX-rect.left+14, tipY=e.clientY-rect.top-14;
            if (tipX+240>rect.width) tipX=e.clientX-rect.left-250;
            if (tipY+200>rect.height) tipY=e.clientY-rect.top-200;
            tip.style.left=tipX+'px'; tip.style.top=tipY+'px';
            canvas.style.cursor = 'pointer';
        } else {
            // Check for zone hover (show zone info if no pet)
            var hoveredZone = _getZoneAtPosition(mx, my);
            if (hoveredZone && tip) {
                var zoneName = MAP_STYLE_NAMES[hoveredZone] || hoveredZone;
                var zoneColor = ELEM_RING[hoveredZone] || 'rgba(190,190,200,0.95)';
                var isVisible = _map.visibleZones[hoveredZone];
                var isFocused = _map.focusedZone === hoveredZone;
                
                // Count pets in this zone (only visible ones)
                var petsInZone = 0;
                Object.keys(_map.animPos).forEach(function(uid) {
                    var pos = _map.animPos[uid];
                    var zone = MAP_ZONES[hoveredZone];
                    if (pos.x >= zone[0] && pos.x <= zone[2] && pos.y >= zone[1] && pos.y <= zone[3]) {
                        // Check if pet is visible (not eliminated in prior round)
                        if (aliveSet[uid]) {
                            petsInZone++;
                        } else {
                            var er = elimRoundMap2[uid];
                            if (currentRound2 === 0 || (er !== undefined && er >= currentRound2)) {
                                petsInZone++;
                            }
                        }
                    }
                });
                
                tip.style.cssText='position:absolute;pointer-events:none;z-index:10;'+
                    'background:rgba(6,6,14,0.97);border:1px solid '+zoneColor+';'+
                    'border-radius:8px;padding:8px 10px;font-size:0.7rem;'+
                    'color:rgba(255,255,255,0.9);'+
                    'box-shadow:0 0 15px '+zoneColor.replace('0.95','0.25')+';min-width:140px;max-width:200px';
                tip.innerHTML=
                    '<div style="font-weight:700;font-size:0.8rem;color:'+zoneColor+';margin-bottom:4px">'+esc(zoneName)+'</div>'+
                    '<div style="font-size:0.65rem;color:rgba(200,200,200,0.8);line-height:1.4">'+
                        '<div>Element: <span style="color:'+zoneColor+'">'+esc(hoveredZone)+'</span></div>'+
                        '<div>Pets: <span style="color:#fff;font-weight:600">'+petsInZone+'</span></div>'+
                    '</div>'+
                    '<div style="margin-top:5px;font-size:0.55rem;color:rgba(160,160,160,0.5);text-align:center">'+
                        (isFocused ? '← click to exit room' : 'click to enter room')+
                    '</div>';
                tip.style.display='block';
                var tipX=e.clientX-rect.left+14, tipY=e.clientY-rect.top-14;
                if (tipX+200>rect.width) tipX=e.clientX-rect.left-210;
                if (tipY+120>rect.height) tipY=e.clientY-rect.top-130;
                tip.style.left=tipX+'px'; tip.style.top=tipY+'px';
                // Pointer cursor to signal the zone is clickable
                canvas.style.cursor = 'pointer';
            } else if (tip) {
                tip.style.display='none';
                canvas.style.cursor = 'default';
            }
        }
    });
    canvas.addEventListener('mouseleave',function(){
        var tip=el('ss-map-tooltip');
        if (tip) tip.style.display='none';
    });
}

// ── Init ──────────────────────────────────────────────────────────────────────
function _mapInit() {
    _map.canvas=el('ss-map-canvas');
    if (!_map.canvas) return;
    _map.ctx=_map.canvas.getContext('2d');
    // Initial fit — wrapper height is set by CSS, just compute scale
    var s=_mapCssSize();
    _map.scale=_fitScale(s.w,s.h,_map.W,_map.H);
    _centerMap(s.w,s.h);
    _mapInitInteraction();
    window.addEventListener('resize',function(){
        if (!_map._userPanned) ssMapReset();
    });
}

// Show/hide map card — always show when there's any game state or lobby
function _updateMapVisibility(status) {
    var card=document.getElementById('ss-map-card');
    if (!card) return;
    // Show for all states except 'none' (no game at all)
    if (status !== 'none') {
        card.style.display='flex';
        _refreshMap();
        _startMapLoop();
    } else {
        card.style.display='none';
        _stopMapLoop();
    }
}

_mapInit();
