(function () {
    const root = document.getElementById('wyr-page');
    if (!root) return;

    const dateText = document.getElementById('wyr-date');
    const sourceText = document.getElementById('wyr-source');
    const statusText = document.getElementById('wyr-status');
    const refreshButton = document.getElementById('wyr-refresh');
    const grid = document.getElementById('wyr-grid');

    let dailyState = null;
    let isBusy = false;

    const typeMeta = {
        weirdness: {
            eyebrow: 'Insanity',
            title: 'Insanity',
            note: 'No logic required. Pick the nonsense you would survive best.',
            icon: 'fa-wand-magic-sparkles',
        },
        moral: {
            eyebrow: 'Crossroads',
            title: 'Crossroads',
            note: 'No perfect answer. Choose the principle you would stand behind.',
            icon: 'fa-scale-balanced',
        },
        pnw: {
            eyebrow: 'PnW Choas',
            title: 'PnW Choas',
            note: 'A real Politics & War tradeoff for people who know the game.',
            icon: 'fa-shield-halved',
        },
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

    function prettyDay(day) {
        if (!day) return 'Today';
        const date = new Date(`${day}T00:00:00Z`);
        if (Number.isNaN(date.getTime())) return day;
        return date.toLocaleDateString(undefined, {
            month: 'long',
            day: 'numeric',
            year: 'numeric',
            timeZone: 'UTC',
        });
    }

    function setBusy(busy) {
        isBusy = busy;
        if (refreshButton) {
            refreshButton.disabled = busy;
            refreshButton.innerHTML = busy
                ? '<i class="fa-solid fa-spinner fa-spin"></i> Loading'
                : '<i class="fa-solid fa-rotate-right"></i> Refresh';
        }
    }

    function renderEmpty(title, message) {
        grid.innerHTML = `
            <article class="wyr-empty">
                <img src="/static/Emojis/Menu/wouldyourather.png" alt="">
                <h2>${escapeHtml(title)}</h2>
                <p>${escapeHtml(message)}</p>
            </article>
        `;
    }

    function voteData(questionId) {
        return dailyState?.votes?.[questionId] || {
            counts: [0, 0],
            percents: [0, 0],
            total: 0,
            user_choice: null,
            voters: [],
        };
    }

    function voterNames(votes, choiceIndex) {
        return (votes.voters || [])
            .filter(voter => voter.choice_index === choiceIndex)
            .map(voter => voter.name || 'Anonymous Visitor');
    }

    function renderResults(question) {
        const votes = voteData(question.id);
        return question.choices.map((choice, index) => {
            const percent = votes.percents[index] || 0;
            const count = votes.counts[index] || 0;
            const names = voterNames(votes, index);
            const selected = votes.user_choice === index;
            return `
                <div class="wyr-result-row${selected ? ' selected' : ''}">
                    <div class="wyr-result-label">
                        <strong>${escapeHtml(choice.text)}</strong>
                        <span>${percent}% - ${count} vote${count === 1 ? '' : 's'}</span>
                    </div>
                    <div class="wyr-bar"><span style="width:${percent}%"></span></div>
                    <div class="wyr-voters">
                        ${names.length ? names.map(name => `<span>${escapeHtml(name)}</span>`).join('') : '<em>No voters yet</em>'}
                    </div>
                </div>
            `;
        }).join('') + `<div class="wyr-total"><i class="fa-solid fa-chart-simple"></i>${votes.total || 0} total vote${votes.total === 1 ? '' : 's'}</div>`;
    }

    function renderQuestion(question, index) {
        const votes = voteData(question.id);
        const userChoice = votes.user_choice;
        const hasVoted = userChoice !== null && userChoice !== undefined;
        const meta = typeMeta[question.type] || {
            eyebrow: question.label,
            title: question.label,
            note: 'Choose one answer to reveal today\'s results.',
            icon: 'fa-circle-question',
        };
        const choices = question.choices.map(choice => {
            const selected = userChoice === choice.index;
            const percent = votes.percents[choice.index] || 0;
            return `
                <button class="wyr-choice${selected ? ' selected' : ''}${hasVoted ? ' revealed' : ''}" type="button" data-question-id="${escapeHtml(question.id)}" data-choice-index="${choice.index}">
                    <span class="wyr-choice-text">${escapeHtml(choice.text)}</span>
                    ${hasVoted ? `<span class="wyr-choice-score">${percent}%</span>` : '<span class="wyr-choice-action">Vote</span>'}
                </button>
            `;
        }).join('');

        return `
            <article class="wyr-card wyr-card-${escapeHtml(question.type)}${hasVoted ? ' has-voted' : ''}" data-question-id="${escapeHtml(question.id)}">
                <div class="wyr-card-header">
                    <div>
                        <span class="wyr-type"><i class="fa-solid ${meta.icon}"></i>${escapeHtml(meta.eyebrow)}</span>
                        <h2>${escapeHtml(meta.title)}</h2>
                    </div>
                    <span class="wyr-number">0${index + 1}</span>
                </div>
                <p class="wyr-card-note">${escapeHtml(meta.note)}</p>
                <h3 class="wyr-question">${escapeHtml(question.question)}</h3>
                <div class="wyr-choices">${choices}</div>
                ${hasVoted
                    ? `<div class="wyr-results">${renderResults(question)}</div>`
                    : '<div class="wyr-locked"><i class="fa-solid fa-lock"></i> Vote to reveal percentages and who picked each side.</div>'
                }
            </article>
        `;
    }

    function bindVoteButtons() {
        grid.querySelectorAll('.wyr-choice').forEach(button => {
            button.addEventListener('click', () => {
                if (isBusy) return;
                vote(button.dataset.questionId, Number.parseInt(button.dataset.choiceIndex, 10));
            });
        });
    }

    function renderDaily() {
        if (!dailyState || !Array.isArray(dailyState.questions) || !dailyState.questions.length) {
            renderEmpty('No daily questions found.', 'Try refreshing the page.');
            return;
        }

        if (dateText) dateText.textContent = prettyDay(dailyState.day);
        if (sourceText) sourceText.textContent = dailyState.source === 'ai' ? 'AI Daily Set' : 'Curated Daily Set';
        if (statusText) statusText.textContent = 'Vote on each card to unlock its results';
        grid.innerHTML = dailyState.questions.map(renderQuestion).join('');
        bindVoteButtons();
    }

    async function loadDaily() {
        setBusy(true);
        if (statusText) statusText.textContent = 'Loading today\'s questions';
        try {
            const response = await fetch('/api/would-you-rather/daily', {
                credentials: 'same-origin',
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load today\'s questions.');
            dailyState = data;
            renderDaily();
        } catch (error) {
            console.error('Would You Rather load failed:', error);
            if (statusText) statusText.textContent = 'Load failed';
            renderEmpty('Could not load Would You Rather.', error.message || 'The daily set is unavailable.');
        } finally {
            setBusy(false);
        }
    }

    async function vote(questionId, choiceIndex) {
        if (!questionId || !Number.isInteger(choiceIndex)) return;
        setBusy(true);
        if (statusText) statusText.textContent = 'Saving your pick';
        try {
            const response = await fetch('/api/would-you-rather/vote', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question_id: questionId,
                    choice_index: choiceIndex,
                }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not save your vote.');
            dailyState.votes = data.votes;
            renderDaily();
            if (statusText) statusText.textContent = 'Your pick is saved. Results are unlocked for that card.';
        } catch (error) {
            console.error('Would You Rather vote failed:', error);
            if (statusText) statusText.textContent = 'Vote failed';
        } finally {
            setBusy(false);
        }
    }

    if (refreshButton) refreshButton.addEventListener('click', loadDaily);
    loadDaily();
})();
