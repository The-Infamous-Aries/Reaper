(function () {
    const root = document.getElementById('fortune-page');
    if (!root) return;

    const grid = document.getElementById('fortune-type-grid');
    const cookie = document.getElementById('fortune-cookie');
    const resetButton = document.getElementById('fortune-reset');
    const fortuneText = document.getElementById('fortune-text');
    const statusText = document.getElementById('fortune-status');

    const state = {
        categories: [],
        pools: new Map(),
        selected: null,
        opened: false,
    };

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, char => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[char]));
    }

    function setStatus(message) {
        if (statusText) statusText.textContent = message;
    }

    function normalizePool(raw) {
        if (Array.isArray(raw)) return raw;
        if (Array.isArray(raw?.entries)) return raw.entries;
        return [];
    }

    async function loadJson(path) {
        const response = await fetch(path, { credentials: 'same-origin' });
        if (!response.ok) throw new Error(`Could not load ${path}`);
        return response.json();
    }

    function renderCategories() {
        grid.innerHTML = state.categories.map(category => `
            <button class="fortune-type${state.selected?.id === category.id ? ' active' : ''}" type="button" data-id="${escapeHtml(category.id)}">
                <span class="fortune-type-icon" aria-hidden="true">${escapeHtml(category.icon || '🥠')}</span>
                <span>
                    <strong>${escapeHtml(category.label)}</strong>
                    <small>${escapeHtml(category.description)}</small>
                </span>
            </button>
        `).join('');

        grid.querySelectorAll('.fortune-type').forEach(button => {
            button.addEventListener('click', () => {
                const next = state.categories.find(category => category.id === button.dataset.id);
                if (!next) return;
                state.selected = next;
                closeCookie();
                renderCategories();
                setStatus(`${next.label} selected. The cookie is ready.`);
            });
        });
    }

    function closeCookie() {
        state.opened = false;
        cookie.classList.remove('opened');
        fortuneText.textContent = 'Tap the cookie.';
        resetButton.classList.remove('visible');
    }

    async function getPool(category) {
        if (state.pools.has(category.id)) return state.pools.get(category.id);
        const raw = await loadJson(category.file);
        const pool = normalizePool(raw).filter(item => item && item.text);
        state.pools.set(category.id, pool);
        return pool;
    }

    function randomFrom(pool) {
        return pool[Math.floor(Math.random() * pool.length)];
    }

    async function getFortune(category) {
        if (category.id === 'reaper_whispers') {
            const response = await fetch('/api/fortune-cookie/reaper-whisper', {
                credentials: 'same-origin',
            });
            const data = await response.json();
            if (!response.ok || !data.text) {
                throw new Error(data.error || 'The Reaper is silent right now.');
            }
            return {
                id: data.id || 'reaper_whisper_ai',
                text: data.text,
                source: data.source || 'ai',
            };
        }

        const pool = await getPool(category);
        if (!pool.length) throw new Error('This fortune pool is empty.');
        return randomFrom(pool);
    }

    function randomInt(min, max) {
        const low = Math.ceil(min);
        const high = Math.floor(max);
        if (window.crypto?.getRandomValues) {
            const range = high - low + 1;
            const maxValid = Math.floor(0xFFFFFFFF / range) * range;
            const buffer = new Uint32Array(1);
            do {
                window.crypto.getRandomValues(buffer);
            } while (buffer[0] >= maxValid);
            return low + (buffer[0] % range);
        }
        return low + Math.floor(Math.random() * (high - low + 1));
    }

    function drawUniqueNumbers(count, min, max) {
        const drawn = new Set();
        while (drawn.size < count) {
            drawn.add(randomInt(min, max));
        }
        return Array.from(drawn).sort((a, b) => a - b);
    }

    function renderFortuneText(fortune, category) {
        let text = String(fortune.text || '');
        if (category.id !== 'lucky_numbers') return text;

        const mainNumbers = drawUniqueNumbers(6, 1, 69);
        const bonusNumber = randomInt(1, 26);
        mainNumbers.forEach((value, index) => {
            text = text.replaceAll(`{n${index + 1}}`, String(value));
        });
        return text
            .replaceAll('{numbers}', mainNumbers.join(' - '))
            .replaceAll('{bonus}', String(bonusNumber));
    }

    async function recordOpened(category, fortune) {
        try {
            await fetch('/api/fortune-cookie/opened', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    category: category.id,
                    fortune_id: fortune.id || '',
                }),
            });
        } catch (error) {
            console.debug('Fortune cookie opened listener failed:', error);
        }
    }

    async function openCookie() {
        if (state.opened || !state.selected) return;
        cookie.disabled = true;
        setStatus('Reading the crumbs.');
        try {
            const fortune = await getFortune(state.selected);
            fortuneText.textContent = renderFortuneText(fortune, state.selected);
            cookie.classList.add('opened');
            state.opened = true;
            resetButton.classList.add('visible');
            setStatus(`${state.selected.label} revealed.`);
            await recordOpened(state.selected, fortune);
        } catch (error) {
            console.error('Fortune open failed:', error);
            setStatus(error.message || 'The cookie refused to open.');
        } finally {
            cookie.disabled = false;
        }
    }

    async function init() {
        try {
            const index = await loadJson('/data/fortune_cookie/index.json');
            state.categories = Array.isArray(index.categories) ? index.categories : [];
            state.selected = state.categories[0] || null;
            renderCategories();
            if (state.selected) {
                setStatus(`${state.selected.label} selected. The cookie is ready.`);
            } else {
                setStatus('No fortune pools found.');
            }
        } catch (error) {
            console.error('Fortune Cookie init failed:', error);
            grid.innerHTML = '<div class="fortune-error">Could not load fortune pools.</div>';
            setStatus('The fortunes are missing.');
        }
    }

    cookie.addEventListener('click', openCookie);
    resetButton.addEventListener('click', closeCookie);
    init();
})();
