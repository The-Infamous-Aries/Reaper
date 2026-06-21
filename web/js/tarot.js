(function () {
    const root = document.getElementById('tarot-page');
    if (!root) return;

    const spreadButtons = Array.from(root.querySelectorAll('.tarot-spread'));
    const drawButton = document.getElementById('tarot-draw-btn');
    const emptyState = document.getElementById('tarot-empty');
    const reading = document.getElementById('tarot-reading');
    const readingTitle = document.getElementById('tarot-reading-title');
    const energyBox = document.getElementById('tarot-energy');
    const cardGrid = document.getElementById('tarot-card-grid');
    const summaryBox = document.getElementById('tarot-summary');
    const summaryText = document.getElementById('tarot-summary-text');
    const dealerSkull = document.getElementById('tarot-dealer-skull');
    const dealerState = document.getElementById('tarot-dealer-state');

    let selectedSpread = '1 Card';
    let isDrawing = false;

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, char => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[char]));
    }

    function setLoading(loading) {
        isDrawing = loading;
        drawButton.disabled = loading;
        spreadButtons.forEach(button => { button.disabled = loading; });
        drawButton.innerHTML = loading
            ? '<i class="fa-solid fa-spinner fa-spin"></i> Reading'
            : '<i class="fa-solid fa-skull"></i> Draw Reading';
        dealerState.textContent = loading ? 'Shuffling the bones' : 'The cards have spoken';
    }

    function setSpread(spread) {
        selectedSpread = spread;
        spreadButtons.forEach(button => {
            button.classList.toggle('active', button.dataset.spread === spread);
        });
    }

    function renderKeywords(keywords) {
        if (!Array.isArray(keywords) || !keywords.length) return '';
        return `<div class="tarot-keywords">${keywords.slice(0, 4).map(k => `<span>${escapeHtml(k)}</span>`).join('')}</div>`;
    }

    function renderQuestions(questions) {
        if (!Array.isArray(questions) || !questions.length) return '';
        return `
            <div class="tarot-questions">
                <h4>Questions to Ask</h4>
                ${questions.slice(0, 3).map(q => `<p>${escapeHtml(q)}</p>`).join('')}
            </div>
        `;
    }

    function renderCard(card) {
        const reversedClass = card.reversed ? ' reversed' : '';
        const majorMark = card.is_major ? '<span class="tarot-major-mark">Major</span>' : '';
        const meaning = (card.meaning_preview || card.meaning || []).slice(0, 3).map(item => `<li>${escapeHtml(item)}</li>`).join('');
        const lore = [
            card.archetype ? `<span><b>Archetype</b>${escapeHtml(card.archetype)}</span>` : '',
            card.elemental ? `<span><b>Elemental</b>${escapeHtml(card.elemental)}</span>` : '',
            card.numerology ? `<span><b>Numerology</b>${escapeHtml(card.numerology)}</span>` : '',
        ].filter(Boolean).join('');

        return `
            <article class="tarot-card-panel">
                <div class="tarot-position">
                    <span>${escapeHtml(card.position_num)}</span>
                    <div>
                        <strong>${escapeHtml(card.position_name)}</strong>
                        <em>${escapeHtml(card.transition)}</em>
                    </div>
                </div>
                <div class="tarot-card-body">
                    <div class="tarot-card-art${reversedClass}">
                        <img src="${escapeHtml(card.image)}" alt="${escapeHtml(card.name)}">
                    </div>
                    <div class="tarot-card-read">
                        <div class="tarot-card-title">
                            <div>
                                <h3>${escapeHtml(card.name)}</h3>
                                <p>${escapeHtml(card.orientation)} · ${escapeHtml(card.arcana || card.suit || 'Tarot')}</p>
                            </div>
                            ${majorMark}
                        </div>
                        ${renderKeywords(card.keywords)}
                        <ul class="tarot-meaning">${meaning}</ul>
                        <blockquote>${escapeHtml(card.fortune)}</blockquote>
                        ${lore ? `<div class="tarot-lore">${lore}</div>` : ''}
                        ${renderQuestions(card.questions)}
                    </div>
                </div>
            </article>
        `;
    }

    function renderReading(data) {
        if (data.dealer && data.dealer.skull) {
            dealerSkull.src = data.dealer.skull;
        }

        emptyState.hidden = true;
        reading.hidden = false;
        readingTitle.textContent = `${data.spread} Reading`;
        cardGrid.innerHTML = (data.cards_info || []).map(renderCard).join('');

        if (data.dominant_energy) {
            energyBox.hidden = false;
            energyBox.textContent = data.dominant_energy;
        } else {
            energyBox.hidden = true;
            energyBox.textContent = '';
        }

        if (data.ai_summary) {
            summaryBox.hidden = false;
            summaryText.textContent = data.ai_summary;
        } else {
            summaryBox.hidden = true;
            summaryText.textContent = '';
        }
    }

    async function drawReading() {
        if (isDrawing) return;
        setLoading(true);

        try {
            const response = await fetch('/api/astrology/tarot/reading', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ spread: selectedSpread, include_summary: true }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Tarot reading failed.');
            renderReading(data);
        } catch (error) {
            dealerState.textContent = 'The veil resisted';
            cardGrid.innerHTML = '';
            emptyState.hidden = false;
            reading.hidden = true;
            emptyState.innerHTML = `
                <div class="tarot-error"><i class="fa-solid fa-triangle-exclamation"></i></div>
                <h2>Reading failed.</h2>
                <p>${escapeHtml(error.message)}</p>
            `;
        } finally {
            setLoading(false);
        }
    }

    spreadButtons.forEach(button => {
        button.addEventListener('click', () => setSpread(button.dataset.spread));
    });

    drawButton.addEventListener('click', drawReading);
})();
