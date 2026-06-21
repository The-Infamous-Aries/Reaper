(function () {
    const root = document.getElementById('quiz-page');
    if (!root) return;

    const list = document.getElementById('quiz-list');
    const stage = document.getElementById('quiz-stage');
    const reload = document.getElementById('quiz-reload');

    const state = {
        quizzes: [],
        activeQuiz: null,
        activeIndex: 0,
        answers: {},
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

    function roleLabel(roleId) {
        return state.activeQuiz?.roles?.[roleId]?.label || roleId;
    }

    function titleCase(value) {
        return String(value || '').replace(/\b\w/g, char => char.toUpperCase());
    }

    function renderEmpty(title, message) {
        stage.innerHTML = `
            <article class="quiz-empty">
                <span class="quiz-emoji" aria-hidden="true">❓</span>
                <h2>${escapeHtml(title)}</h2>
                ${message ? `<p>${escapeHtml(message)}</p>` : ''}
            </article>
        `;
    }

    function validateQuiz(quiz) {
        if (!quiz || !quiz.id || !Array.isArray(quiz.questions)) return false;
        if (!quiz.roles || typeof quiz.roles !== 'object') return false;
        return quiz.questions.every(question => (
            question.id &&
            question.prompt &&
            Array.isArray(question.answers) &&
            question.answers.length >= 2 &&
            question.answers.length <= 4 &&
            question.answers.every(answer => answer.text && answer.scores && typeof answer.scores === 'object')
        ));
    }

    function renderQuizList() {
        if (!state.quizzes.length) {
            list.innerHTML = `
                <article class="quiz-empty">
                    <span class="quiz-emoji" aria-hidden="true">❓</span>
                    <h2>No quizzes found.</h2>
                    <p>Add quiz JSON files under web/data/quizzes.</p>
                </article>
            `;
            return;
        }

        function quizOutcomeText(quiz) {
            if (quiz.resultMode === 'pet_match') {
                const petCount = Object.keys(quiz.petSystem?.petCatalog || {}).length;
                const elementCount = Object.keys(quiz.petSystem?.elements || {}).length;
                const typeCount = Object.keys(quiz.petSystem?.types || {}).length;
                return `${quiz.questions.length} questions / ${petCount} pets / ${elementCount} elements / ${typeCount} types`;
            }
            return `${quiz.questions.length} questions / ${Object.keys(quiz.roles).length} outcomes`;
        }

        list.innerHTML = state.quizzes.map(quiz => `
            <button class="quiz-card${state.activeQuiz?.id === quiz.id ? ' active' : ''}" type="button" data-quiz-id="${escapeHtml(quiz.id)}">
                <h2>${escapeHtml(quiz.title)}</h2>
                <p>${escapeHtml(quiz.description)}</p>
                <span>${escapeHtml(quizOutcomeText(quiz))}</span>
            </button>
        `).join('');

        list.querySelectorAll('.quiz-card').forEach(card => {
            card.addEventListener('click', () => selectQuiz(card.dataset.quizId));
        });
    }

    function selectQuiz(id) {
        const quiz = state.quizzes.find(item => item.id === id);
        if (!quiz) return;
        state.activeQuiz = quiz;
        state.activeIndex = 0;
        state.answers = {};
        renderQuizList();
        renderActiveQuestion();
    }

    function answeredCount() {
        return Object.keys(state.answers).length;
    }

    function currentQuestion() {
        return state.activeQuiz?.questions?.[state.activeIndex] || null;
    }

    function answerLetter(index) {
        return String.fromCharCode(65 + index);
    }

    function renderActiveQuestion() {
        const quiz = state.activeQuiz;
        if (!quiz) {
            renderEmpty('Select a quiz.', 'The Alliance Role quiz will decide the strongest match across 1ic, 2ic, MA, FA, IA, EI, TA, and JA.');
            return;
        }

        const question = currentQuestion();
        if (!question) {
            renderResults();
            return;
        }

        const total = quiz.questions.length;
        const progress = Math.round((answeredCount() / total) * 100);
        const selectedAnswer = state.answers[question.id];
        const answers = question.answers.map((answer, index) => `
            <button class="quiz-answer${selectedAnswer === answer.id ? ' selected' : ''}" type="button" data-answer-id="${escapeHtml(answer.id)}">
                <span class="quiz-answer-letter">${answerLetter(index)}</span>
                <span>${escapeHtml(answer.text)}</span>
            </button>
        `).join('');

        stage.innerHTML = `
            <section class="quiz-intro">
                <div class="quiz-title-block">
                    <h2>${escapeHtml(quiz.title)}</h2>
                    <p>${escapeHtml(quiz.description)}</p>
                </div>
                <div class="quiz-actions">
                    <button class="quiz-button" type="button" id="quiz-reset"><i class="fa-solid fa-arrow-rotate-left"></i> Reset</button>
                    <button class="quiz-button primary" type="button" id="quiz-finish" ${answeredCount() < total ? 'disabled' : ''}>
                        <i class="fa-solid fa-square-poll-vertical"></i> Results
                    </button>
                </div>
            </section>
            <div class="quiz-progress-bar" aria-label="${progress}% complete"><span class="quiz-progress-fill" style="width:${progress}%"></span></div>
            <article class="quiz-question-card">
                <div class="quiz-question-top">
                    <span class="quiz-question-number">Question ${state.activeIndex + 1} of ${total}</span>
                    <span class="quiz-question-meta">${escapeHtml(question.type === 'true_false' ? 'True / False' : 'Multiple Choice')}</span>
                </div>
                <h3>${escapeHtml(question.prompt)}</h3>
                <div class="quiz-answer-grid">${answers}</div>
                <div class="quiz-nav">
                    <button class="quiz-button" type="button" id="quiz-prev" ${state.activeIndex === 0 ? 'disabled' : ''}>
                        <i class="fa-solid fa-arrow-left"></i> Back
                    </button>
                    <button class="quiz-button primary" type="button" id="quiz-next" ${selectedAnswer ? '' : 'disabled'}>
                        ${state.activeIndex === total - 1 ? 'Finish' : 'Next'} <i class="fa-solid fa-arrow-right"></i>
                    </button>
                </div>
            </article>
        `;

        stage.querySelectorAll('.quiz-answer').forEach(button => {
            button.addEventListener('click', () => {
                state.answers[question.id] = button.dataset.answerId;
                renderActiveQuestion();
            });
        });

        document.getElementById('quiz-reset')?.addEventListener('click', () => {
            state.activeIndex = 0;
            state.answers = {};
            renderActiveQuestion();
        });
        document.getElementById('quiz-finish')?.addEventListener('click', renderResults);
        document.getElementById('quiz-prev')?.addEventListener('click', () => {
            state.activeIndex = Math.max(0, state.activeIndex - 1);
            renderActiveQuestion();
        });
        document.getElementById('quiz-next')?.addEventListener('click', () => {
            if (!state.answers[question.id]) return;
            if (state.activeIndex >= total - 1) {
                renderResults();
                return;
            }
            state.activeIndex += 1;
            renderActiveQuestion();
        });
    }

    function calculateScores() {
        const quiz = state.activeQuiz;
        const scores = {};
        const possible = {};
        Object.keys(quiz.roles).forEach(role => {
            scores[role] = 0;
            possible[role] = 0;
        });

        quiz.questions.forEach(question => {
            const maximums = {};
            Object.keys(quiz.roles).forEach(role => { maximums[role] = 0; });

            question.answers.forEach(answer => {
                Object.entries(answer.scores || {}).forEach(([role, value]) => {
                    maximums[role] = Math.max(maximums[role] || 0, Number(value) || 0);
                });
            });

            Object.entries(maximums).forEach(([role, value]) => {
                possible[role] += value;
            });

            const selected = question.answers.find(answer => answer.id === state.answers[question.id]);
            if (!selected) return;
            Object.entries(selected.scores || {}).forEach(([role, value]) => {
                scores[role] = (scores[role] || 0) + (Number(value) || 0);
            });
        });

        const normalized = Object.keys(scores).map(role => {
            const percent = possible[role] > 0 ? Math.round((scores[role] / possible[role]) * 100) : 0;
            return {
                role,
                raw: scores[role],
                possible: possible[role],
                percent,
                priority: state.activeQuiz.roles[role]?.priority || 999,
            };
        }).sort((a, b) => b.percent - a.percent || b.raw - a.raw || a.priority - b.priority || a.role.localeCompare(b.role));

        return normalized;
    }

    function calculatePetMatch() {
        const quiz = state.activeQuiz;
        const petSystem = quiz.petSystem || {};
        const catalog = petSystem.petCatalog || {};
        const statKeys = Object.keys(petSystem.statLabels || {
            ATT: 'Attack',
            DEF: 'Defense',
            INT: 'Intelligence',
            DEX: 'Dexterity',
            HAP: 'Happiness',
            ENE: 'Energy',
        });
        const desiredStats = Object.fromEntries(statKeys.map(stat => [stat, 0]));
        const elementScores = {};
        const typeScores = {};
        const petBoosts = {};

        quiz.questions.forEach(question => {
            const selected = question.answers.find(answer => answer.id === state.answers[question.id]);
            if (!selected || !selected.petProfile) return;
            Object.entries(selected.petProfile.stats || {}).forEach(([stat, value]) => {
                desiredStats[stat] = (desiredStats[stat] || 0) + (Number(value) || 0);
            });
            Object.entries(selected.petProfile.elements || {}).forEach(([element, value]) => {
                elementScores[element] = (elementScores[element] || 0) + (Number(value) || 0);
            });
            Object.entries(selected.petProfile.types || {}).forEach(([type, value]) => {
                typeScores[type] = (typeScores[type] || 0) + (Number(value) || 0);
            });
            Object.entries(selected.petProfile.pets || {}).forEach(([species, value]) => {
                petBoosts[species] = (petBoosts[species] || 0) + (Number(value) || 0);
            });
        });

        const desiredTotal = Object.values(desiredStats).reduce((sum, value) => sum + value, 0) || 1;
        const desiredVector = Object.fromEntries(statKeys.map(stat => [stat, (desiredStats[stat] || 0) / desiredTotal]));
        const desiredSpecs = Object.entries(desiredStats)
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .slice(0, 2)
            .map(([stat]) => stat);

        const petResults = Object.entries(catalog).map(([species, pet]) => {
            const stats = pet.stats || {};
            const petTotal = statKeys.reduce((sum, stat) => sum + (Number(stats[stat]) || 0), 0) || 1;
            let distance = 0;
            statKeys.forEach(stat => {
                const petShare = (Number(stats[stat]) || 0) / petTotal;
                distance += Math.abs((desiredVector[stat] || 0) - petShare);
            });
            const petSpecs = pet.spec || [];
            const specMatches = desiredSpecs.filter(stat => petSpecs.includes(stat)).length;
            const exactSpecPair = specMatches === 2 ? 35 : 0;
            const specMatchBonus = specMatches * 22;
            const statShapeScore = Math.max(0, 100 - (distance * 100));
            const score = statShapeScore + specMatchBonus + exactSpecPair + (petBoosts[species] || 0);
            return { species, pet, score };
        }).sort((a, b) => b.score - a.score || a.species.localeCompare(b.species));

        const typeRank = Object.entries(typeScores)
            .map(([type, score]) => ({ type, score }))
            .sort((a, b) => b.score - a.score || a.type.localeCompare(b.type));
        const elementRank = Object.entries(elementScores)
            .map(([element, score]) => ({ element, score }))
            .sort((a, b) => b.score - a.score || a.element.localeCompare(b.element));

        const topElement = elementRank[0] || { element: 'Basic', score: 1 };
        const secondElement = elementRank[1];
        const basicIsInResult = topElement.element === 'Basic' || secondElement?.element === 'Basic';
        const useSecondElement = !basicIsInResult && secondElement && secondElement.score >= Math.max(8, topElement.score * 0.5);

        return {
            pet: petResults[0],
            alternates: petResults.slice(1, 4),
            type: typeRank[0] || { type: 'Land', score: 1 },
            elements: useSecondElement ? [topElement, secondElement] : [topElement],
            desiredStats,
            petResults,
        };
    }

    function renderPetMatchResults() {
        const quiz = state.activeQuiz;
        const petSystem = quiz.petSystem || {};
        const match = calculatePetMatch();
        const pet = match.pet?.pet || {};
        const species = match.pet?.species || 'Unknown';
        const typeMeta = petSystem.types?.[match.type.type] || { label: titleCase(match.type.type), image: '' };
        const elementChips = match.elements.map(item => {
            const meta = petSystem.elements?.[item.element] || { label: titleCase(item.element), image: '' };
            return `
                <span class="quiz-pet-chip">
                    ${meta.image ? `<img src="${escapeHtml(meta.image)}" alt="">` : ''}
                    ${escapeHtml(meta.label)}
                </span>
            `;
        }).join('');
        const stats = Object.entries(petSystem.statLabels || {}).map(([stat, label]) => {
            const value = Number(pet.stats?.[stat]) || 0;
            return `
                <div class="quiz-pet-stat">
                    <span>${escapeHtml(label)}</span>
                    <strong>${value}</strong>
                    <em style="width:${Math.min(100, value * 4)}%"></em>
                </div>
            `;
        }).join('');
        const alternates = match.alternates.map(item => `
            <span class="quiz-pet-alt">
                <img src="${escapeHtml(item.pet.image)}" alt="">
                ${escapeHtml(item.species)}
            </span>
        `).join('');

        stage.innerHTML = `
            <section class="quiz-intro">
                <div class="quiz-title-block">
                    <h2>${escapeHtml(quiz.title)}</h2>
                    <p>${quiz.questions.length} answers matched against ${Object.keys(petSystem.petCatalog || {}).length} Pet System species.</p>
                </div>
                <div class="quiz-actions">
                    <button class="quiz-button" type="button" id="quiz-review"><i class="fa-solid fa-list-check"></i> Review</button>
                    <button class="quiz-button primary" type="button" id="quiz-retake"><i class="fa-solid fa-arrow-rotate-left"></i> Retake</button>
                </div>
            </section>
            <article class="quiz-result-card quiz-pet-result">
                <span class="quiz-result-label">${escapeHtml(quiz.resultLabel || 'Perfect Pet Match')}</span>
                <div class="quiz-pet-hero">
                    <img class="quiz-pet-image" src="${escapeHtml(pet.image || '')}" alt="${escapeHtml(species)}">
                    <div>
                        <h2>${escapeHtml(species)}</h2>
                        <p class="quiz-result-detail">${escapeHtml(pet.description || 'A perfectly matched companion from the Pet System.')}</p>
                        <div class="quiz-pet-chips">
                            <span class="quiz-pet-chip">
                                ${typeMeta.image ? `<img src="${escapeHtml(typeMeta.image)}" alt="">` : ''}
                                ${escapeHtml(typeMeta.label)}
                            </span>
                            ${elementChips}
                        </div>
                    </div>
                </div>
                <div class="quiz-pet-grid">
                    <section>
                        <h3>Pet Stats</h3>
                        <div class="quiz-pet-stats">${stats}</div>
                    </section>
                    <section>
                        <h3>Battle Style</h3>
                        <p><strong>Attack:</strong> ${escapeHtml(pet.actions?.Attack || 'Attack')}</p>
                        <p><strong>Defense:</strong> ${escapeHtml(pet.actions?.Defense || 'Defend')}</p>
                        <p><strong>Charge:</strong> ${escapeHtml(pet.actions?.Charge || 'Charge')}</p>
                    </section>
                </div>
                <div class="quiz-pet-alts">
                    <span>Close matches</span>
                    ${alternates}
                </div>
            </article>
        `;

        document.getElementById('quiz-review')?.addEventListener('click', () => {
            state.activeIndex = 0;
            renderActiveQuestion();
        });
        document.getElementById('quiz-retake')?.addEventListener('click', () => {
            state.activeIndex = 0;
            state.answers = {};
            renderActiveQuestion();
        });
    }

    function renderResults() {
        const quiz = state.activeQuiz;
        if (!quiz) return;
        if (answeredCount() < quiz.questions.length) {
            renderActiveQuestion();
            return;
        }

        if (quiz.resultMode === 'pet_match') {
            renderPetMatchResults();
            return;
        }

        const results = calculateScores();
        const winner = results[0];
        const role = quiz.roles[winner.role];
        const rows = results.map(result => `
            <div class="quiz-score-row">
                <strong>${escapeHtml(roleLabel(result.role))}</strong>
                <span class="quiz-score-bar"><span style="width:${result.percent}%"></span></span>
                <span>${result.percent}%</span>
            </div>
        `).join('');

        stage.innerHTML = `
            <section class="quiz-intro">
                <div class="quiz-title-block">
                    <h2>${escapeHtml(quiz.title)}</h2>
                    <p>${quiz.questions.length} answers scored with weighted role matching.</p>
                </div>
                <div class="quiz-actions">
                    <button class="quiz-button" type="button" id="quiz-review"><i class="fa-solid fa-list-check"></i> Review</button>
                    <button class="quiz-button primary" type="button" id="quiz-retake"><i class="fa-solid fa-arrow-rotate-left"></i> Retake</button>
                </div>
            </section>
            <article class="quiz-result-card">
                <span class="quiz-result-label">${escapeHtml(quiz.resultLabel || 'Best Quiz Match')}</span>
                <h2>${escapeHtml(role.label)}</h2>
                <p class="quiz-result-detail">${escapeHtml(role.summary)}</p>
                <div class="quiz-score-list">${rows}</div>
            </article>
        `;

        document.getElementById('quiz-review')?.addEventListener('click', () => {
            state.activeIndex = 0;
            renderActiveQuestion();
        });
        document.getElementById('quiz-retake')?.addEventListener('click', () => {
            state.activeIndex = 0;
            state.answers = {};
            renderActiveQuestion();
        });
    }

    async function loadQuizzes() {
        list.innerHTML = `
            <article class="quiz-empty">
                <span class="quiz-emoji" aria-hidden="true">❓</span>
                <h2>Loading quizzes.</h2>
            </article>
        `;
        try {
            const response = await fetch('/quiz-data/quizzes/index.json', { credentials: 'same-origin', cache: 'no-cache' });
            if (!response.ok) throw new Error(`Index HTTP ${response.status}`);
            const index = await response.json();
            const files = Array.isArray(index.quizzes) ? index.quizzes : [];
            const loaded = await Promise.all(files.map(async file => {
                const quizResponse = await fetch(`/quiz-data/quizzes/${file}`, { credentials: 'same-origin', cache: 'no-cache' });
                if (!quizResponse.ok) throw new Error(`${file} HTTP ${quizResponse.status}`);
                return quizResponse.json();
            }));
            state.quizzes = loaded.filter(validateQuiz);
            state.activeQuiz = state.quizzes[0] || null;
            state.activeIndex = 0;
            state.answers = {};
            renderQuizList();
            renderActiveQuestion();
        } catch (error) {
            console.error('Quiz Hub load failed:', error);
            list.innerHTML = `
                <article class="quiz-empty">
                    <span class="quiz-emoji" aria-hidden="true">❓</span>
                    <h2>Could not load quizzes.</h2>
                    <p>${escapeHtml(error.message || 'Quiz data is unavailable.')}</p>
                </article>
            `;
            renderEmpty('Could not load Quiz Hub.', 'Check web/data/quizzes/index.json and the quiz JSON files.');
        }
    }

    reload?.addEventListener('click', loadQuizzes);
    loadQuizzes();
})();
