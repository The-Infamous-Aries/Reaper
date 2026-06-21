(function () {
    const root = document.getElementById('generator-lab-page');
    if (!root) return;

    const form = document.getElementById('generator-lab-form');
    const categoryInput = document.getElementById('generator-lab-category');
    const descriptionInput = document.getElementById('generator-lab-description');
    const countInput = document.getElementById('generator-lab-count');
    const submitButton = document.getElementById('generator-lab-submit');
    const clearButton = document.getElementById('generator-lab-clear');
    const copyAllButton = document.getElementById('generator-lab-copy-all');
    const statusText = document.getElementById('generator-lab-status');
    const resultType = document.getElementById('generator-lab-result-type');
    const resultTitle = document.getElementById('generator-lab-result-title');
    const emptyState = document.getElementById('generator-lab-empty');
    const grid = document.getElementById('generator-lab-grid');

    let lastItems = [];
    let lastLabel = '';

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, char => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[char]));
    }

    function itemToText(item) {
        if (item && typeof item === 'object') {
            return [
                `Pet: ${item.pet_name || ''}`,
                `Attack: ${item.attack_name || ''}`,
                `Defend: ${item.defend_name || ''}`,
                `Charge: ${item.charge_name || ''}`,
            ].join('\n');
        }
        return String(item ?? '');
    }

    async function copyText(text, button) {
        try {
            await navigator.clipboard.writeText(text);
            if (button) {
                const original = button.innerHTML;
                button.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
                setTimeout(() => { button.innerHTML = original; }, 1200);
            }
        } catch (error) {
            console.error('Copy failed:', error);
            statusText.textContent = 'Copy failed';
        }
    }

    function setLoading(loading) {
        submitButton.disabled = loading;
        clearButton.disabled = loading;
        categoryInput.disabled = loading;
        descriptionInput.disabled = loading;
        countInput.disabled = loading;
        submitButton.innerHTML = loading
            ? '<i class="fa-solid fa-spinner fa-spin"></i> Generating'
            : '<i class="fa-solid fa-flask"></i> Generate';
        statusText.textContent = loading ? 'Mixing ideas' : 'Ready';
    }

    function renderEmpty(title, message, isError) {
        emptyState.hidden = false;
        grid.hidden = true;
        copyAllButton.hidden = true;
        resultType.textContent = isError ? 'Lab Error' : 'Awaiting Input';
        resultTitle.textContent = title;
        emptyState.classList.toggle('generator-lab-error', Boolean(isError));
        emptyState.innerHTML = `
            <img src="/static/Emojis/Menu/lab.png" alt="">
            <h3>${escapeHtml(title)}</h3>
            <p>${escapeHtml(message)}</p>
        `;
    }

    function renderPetCard(item, index) {
        const text = itemToText(item);
        return `
            <article class="generator-lab-card">
                <div class="generator-lab-card-main">${index + 1}. ${escapeHtml(item.pet_name)}</div>
                <div class="generator-lab-card-body">
                    <div class="generator-lab-move">
                        <span>Attack</span>
                        <strong>${escapeHtml(item.attack_name)}</strong>
                    </div>
                    <div class="generator-lab-move">
                        <span>Defend</span>
                        <strong>${escapeHtml(item.defend_name)}</strong>
                    </div>
                    <div class="generator-lab-move">
                        <span>Charge</span>
                        <strong>${escapeHtml(item.charge_name)}</strong>
                    </div>
                </div>
                <button class="generator-lab-copy" type="button" data-copy="${escapeHtml(text)}">
                    <i class="fa-solid fa-copy"></i>
                    Copy
                </button>
            </article>
        `;
    }

    function renderTextCard(item, index) {
        const text = itemToText(item);
        return `
            <article class="generator-lab-card">
                <div class="generator-lab-card-main">${index + 1}. ${escapeHtml(text)}</div>
                <button class="generator-lab-copy" type="button" data-copy="${escapeHtml(text)}">
                    <i class="fa-solid fa-copy"></i>
                    Copy
                </button>
            </article>
        `;
    }

    function renderResults(data) {
        lastItems = Array.isArray(data.items) ? data.items : [];
        lastLabel = data.label || 'Generator Lab';

        if (!lastItems.length) {
            renderEmpty('No results returned', 'Try a more detailed description or a different generator type.', true);
            return;
        }

        emptyState.hidden = true;
        grid.hidden = false;
        copyAllButton.hidden = false;
        resultType.textContent = data.source === 'ai' ? 'AI Results' : 'Fallback Results';
        resultTitle.textContent = `${lastLabel} (${lastItems.length})`;

        const isPets = data.category === 'pets';
        grid.innerHTML = lastItems
            .map((item, index) => isPets ? renderPetCard(item, index) : renderTextCard(item, index))
            .join('');

        grid.querySelectorAll('.generator-lab-copy').forEach(button => {
            button.addEventListener('click', () => copyText(button.dataset.copy || '', button));
        });
    }

    async function generate(event) {
        event.preventDefault();
        const payload = {
            category: categoryInput.value,
            description: descriptionInput.value.trim(),
            count: Number.parseInt(countInput.value, 10) || 6,
        };

        if (payload.count < 1 || payload.count > 12) {
            renderEmpty('Invalid count', 'Choose between 1 and 12 results.', true);
            return;
        }

        setLoading(true);
        try {
            const response = await fetch('/api/generator-lab/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Generator failed.');
            renderResults(data);
            statusText.textContent = data.source === 'ai' ? 'AI batch complete' : 'Fallback batch complete';
        } catch (error) {
            console.error('Generator Lab failed:', error);
            statusText.textContent = 'Generation failed';
            renderEmpty('Generation failed', error.message || 'The lab could not produce results.', true);
        } finally {
            setLoading(false);
        }
    }

    form.addEventListener('submit', generate);

    clearButton.addEventListener('click', () => {
        descriptionInput.value = '';
        countInput.value = '6';
        categoryInput.value = 'discord_username';
        lastItems = [];
        lastLabel = '';
        statusText.textContent = 'Ready';
        renderEmpty('The lab bench is clean.', 'Choose a generator type, add a description, and generate a batch.', false);
    });

    copyAllButton.addEventListener('click', () => {
        const text = lastItems.map((item, index) => `${index + 1}. ${itemToText(item)}`).join('\n\n');
        copyText(text, copyAllButton);
    });
})();
