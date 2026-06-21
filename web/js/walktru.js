'use strict';

(function() {
    var root = document.getElementById('walktru-root');
    if (!root) return;

    var state = {
        stories: [],
        selected: null,
        currentStage: null,
        primaryValue: 0,
        secondaryStats: {},
        originAlignment: null,
        stageCache: {},
        history: [],
        busy: false,
        finished: false,
    };

    var DANGER_HIGH = { ganster: true, horror: true, cyberpunk: true };
    var DANGER_LOW = { robot: true, western: true, wizard: true, spy: true, carnival: true, deepsea: true };

    function el(id) { return document.getElementById(id); }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function titleCase(value) {
        return String(value || '')
            .replace(/_/g, ' ')
            .replace(/\b\w/g, function(ch) { return ch.toUpperCase(); });
    }

    function clamp(value, bounds) {
        var min = Number(bounds && bounds.min != null ? bounds.min : 0);
        var max = Number(bounds && bounds.max != null ? bounds.max : 100);
        value = Number(value || 0);
        return Math.max(min, Math.min(max, value));
    }

    function percent(value, bounds) {
        var min = Number(bounds && bounds.min != null ? bounds.min : 0);
        var max = Number(bounds && bounds.max != null ? bounds.max : 100);
        if (max === min) return 0;
        return Math.max(0, Math.min(100, ((Number(value || 0) - min) / (max - min)) * 100));
    }

    function toast(message) {
        var node = el('walktru-toast');
        if (!node) return;
        node.textContent = message;
        node.hidden = false;
        clearTimeout(node._hideTimer);
        node._hideTimer = setTimeout(function() { node.hidden = true; }, 3800);
    }

    function setStatus(message) {
        var node = el('walktru-status');
        if (node) node.textContent = message;
    }

    function storyIcon(story) {
        if (story && story.key === 'origin') {
            return '/static/Emojis/Walkthru/origin.png';
        }
        return story && story.icon ? story.icon : '/static/Emojis/Walkthru/knight.png';
    }

    function getStageNumber(stage) {
        return Number(stage && stage.stage ? stage.stage : 0);
    }

    function cacheKey(storyKey, stageId, alignment) {
        return storyKey + '::' + stageId + '::' + (alignment || 'base');
    }

    function apiError(resp) {
        return resp.json().then(function(body) {
            return body.detail || body.message || 'Request failed';
        }).catch(function() {
            return 'Request failed';
        });
    }

    function renderStories() {
        var list = el('walktru-story-list');
        if (!list) return;

        if (!state.stories.length) {
            list.innerHTML = '<div class="walktru-empty">Loading stories...</div>';
            return;
        }

        list.innerHTML = state.stories.map(function(story) {
            var active = state.selected && state.selected.key === story.key;
            return [
                '<button class="walktru-story-card ', active ? 'active' : '', '" type="button" data-story="', esc(story.key), '">',
                    '<div class="walktru-card-top">',
                        '<img src="', esc(storyIcon(story)), '" alt="">',
                        '<div>',
                            '<div class="walktru-card-title">', esc(story.title || titleCase(story.key)), '</div>',
                            '<div class="walktru-card-stat">', esc(titleCase(story.mechanic)), '</div>',
                        '</div>',
                    '</div>',
                    '<p class="walktru-card-description">', esc(story.description || ''), '</p>',
                '</button>'
            ].join('');
        }).join('');

        Array.prototype.forEach.call(list.querySelectorAll('[data-story]'), function(button) {
            button.addEventListener('click', function() {
                startStory(button.getAttribute('data-story'));
            });
        });
    }

    function statClass(storyKey, value, bounds) {
        var pct = percent(value, bounds);
        if (DANGER_HIGH[storyKey] && pct >= 75) return 'bad';
        if (DANGER_HIGH[storyKey] && pct <= 35) return 'good';
        if (DANGER_LOW[storyKey] && pct <= 25) return 'bad';
        if (DANGER_LOW[storyKey] && pct >= 70) return 'good';
        if (storyKey === 'pirate' && titleCase(state.selected && state.selected.mechanic) === 'Infamy') return 'good';
        if (storyKey === 'origin') {
            if (value >= 50 || value <= -50) return 'good';
            if (value === 0) return 'bad';
        }
        return '';
    }

    function renderStat(label, value, bounds, rangeText, cssClass) {
        var pct = percent(value, bounds);
        return [
            '<div class="walktru-stat">',
                '<div class="walktru-stat-head">',
                    '<span class="walktru-stat-name">', esc(label), '</span>',
                    '<span class="walktru-stat-value">', esc(value), '</span>',
                '</div>',
                '<div class="walktru-bar ', esc(cssClass || ''), '"><span style="width:', pct.toFixed(1), '%"></span></div>',
                '<span class="walktru-stat-range">', esc(rangeText), ' - ', pct.toFixed(0), '%</span>',
            '</div>'
        ].join('');
    }

    function renderStats() {
        var node = el('walktru-stats');
        if (!node || !state.selected) {
            if (node) node.innerHTML = '';
            return;
        }

        var story = state.selected;
        var bounds = story.bounds || { min: 0, max: 100 };
        var html = renderStat(
            titleCase(story.mechanic),
            state.primaryValue,
            bounds,
            'Range ' + bounds.min + ' to ' + bounds.max,
            statClass(story.key, state.primaryValue, bounds)
        );

        Object.keys(state.secondaryStats).forEach(function(statKey) {
            var stat = state.secondaryStats[statKey];
            var statBounds = { min: stat.min_value, max: stat.max_value };
            var cls = stat.value <= statBounds.min + 10 ? 'bad' : (stat.value >= 60 ? 'good' : '');
            html += renderStat(
                stat.label || titleCase(statKey),
                stat.value,
                statBounds,
                'Range ' + statBounds.min + ' to ' + statBounds.max,
                cls
            );
        });

        node.innerHTML = html;
    }

    function renderHistory() {
        var node = el('walktru-history');
        var count = el('walktru-path-count');
        if (count) count.textContent = state.history.length + ' choice' + (state.history.length === 1 ? '' : 's');
        if (!node) return;

        if (!state.history.length) {
            node.innerHTML = '<div class="walktru-empty">Your choices and outcomes will appear here.</div>';
            return;
        }

        node.innerHTML = state.history.slice().reverse().map(function(item) {
            return [
                '<div class="walktru-history-item ', esc(item.cls), '">',
                    '<strong>Stage ', esc(item.stage), ': ', esc(item.choice), '</strong><br>',
                    esc(item.result), ' - ', esc(item.statText),
                '</div>'
            ].join('');
        }).join('');
    }

    function renderStage() {
        var story = state.selected;
        var stage = state.currentStage;
        var result = el('walktru-result');
        if (result) {
            result.hidden = true;
            result.innerHTML = '';
            result.className = 'walktru-result';
        }

        renderStories();
        renderStats();
        renderHistory();

        var icon = el('walktru-story-icon');
        if (icon) icon.src = storyIcon(story);

        var title = el('walktru-stage-title');
        var text = el('walktru-stage-text');
        var kicker = el('walktru-stage-kicker');
        var count = el('walktru-stage-count');
        var choices = el('walktru-choices');

        if (!story || !stage) {
            if (title) title.textContent = 'Pick a Walkthru story';
            if (text) text.textContent = 'Select a story to begin a fully branching eight-stage run.';
            if (kicker) kicker.textContent = 'No Story Selected';
            if (count) count.textContent = 'Stage --/8';
            if (choices) choices.innerHTML = '';
            return;
        }

        var stageNo = getStageNumber(stage);
        if (title) title.textContent = stage.title || 'Untitled Stage';
        if (text) text.textContent = stage.description || '';
        if (kicker) kicker.textContent = (story.title || titleCase(story.key)) + (state.originAlignment ? ' - ' + titleCase(state.originAlignment) : '');
        if (count) count.textContent = 'Stage ' + (stageNo || '--') + '/8';
        setStatus((story.title || titleCase(story.key)) + ' loaded.');

        var stageChoices = Array.isArray(stage.choices) ? stage.choices : [];
        if (!choices) return;
        choices.innerHTML = stageChoices.map(function(choice, index) {
            return [
                '<button class="walktru-choice" type="button" data-choice="', index, '">',
                    '<div class="walktru-choice-top">',
                        '<span class="walktru-choice-label">', esc(choice.label || 'Continue'), '</span>',
                        '<span class="walktru-choice-number">', index + 1, '</span>',
                    '</div>',
                '</button>'
            ].join('');
        }).join('');

        Array.prototype.forEach.call(choices.querySelectorAll('[data-choice]'), function(button) {
            button.addEventListener('click', function() {
                choose(Number(button.getAttribute('data-choice')));
            });
        });
    }

    async function loadStories() {
        renderStories();
        var resp = await fetch('/api/walktru/stories', { credentials: 'same-origin' });
        if (!resp.ok) throw new Error(await apiError(resp));
        var data = await resp.json();
        state.stories = Array.isArray(data.stories) ? data.stories.filter(function(story) { return !story.error; }) : [];
        renderStories();
        if (state.stories.length) {
            await startStory(state.stories[0].key);
        } else {
            setStatus('No Walkthru stories are available.');
        }
    }

    async function fetchStage(storyKey, stageId, alignment) {
        var key = cacheKey(storyKey, stageId, alignment);
        if (state.stageCache[key]) return state.stageCache[key];

        var url = '/api/walktru/stories/' + encodeURIComponent(storyKey) + '/stage/' + encodeURIComponent(stageId);
        if (alignment) url += '?alignment=' + encodeURIComponent(alignment);
        var resp = await fetch(url, { credentials: 'same-origin' });
        if (!resp.ok) throw new Error(await apiError(resp));
        var data = await resp.json();
        state.stageCache[key] = data.stage;
        if (data.story && state.selected && state.selected.key === storyKey) {
            state.selected = Object.assign({}, state.selected, data.story);
        }
        return data.stage;
    }

    async function startStory(storyKey) {
        if (state.busy) return;
        var story = state.stories.find(function(item) { return item.key === storyKey; });
        if (!story) return;

        state.busy = true;
        try {
            state.selected = story;
            state.primaryValue = clamp(story.starting_value || 0, story.bounds);
            state.secondaryStats = {};
            var secondary = story.secondary_stats || {};
            Object.keys(secondary).forEach(function(statKey) {
                var config = secondary[statKey] || {};
                state.secondaryStats[statKey] = {
                    label: config.label || titleCase(statKey),
                    value: clamp(config.starting_value || 0, { min: config.min_value || 0, max: config.max_value || 100 }),
                    min_value: config.min_value == null ? 0 : config.min_value,
                    max_value: config.max_value == null ? 100 : config.max_value,
                };
            });
            state.originAlignment = null;
            state.history = [];
            state.finished = false;
            state.currentStage = await fetchStage(story.key, story.start_stage || 'event_start', null);
            renderStage();
        } catch (error) {
            console.error('Walkthru start failed:', error);
            toast(error.message || 'Could not start this Walkthru.');
        } finally {
            state.busy = false;
        }
    }

    function applyOutcome(outcome) {
        var story = state.selected;
        var mechanicChange = Number(outcome.mechanic_change || 0);
        state.primaryValue = clamp(state.primaryValue + mechanicChange, story.bounds);

        var extra = outcome.extra_stat_changes || {};
        Object.keys(extra).forEach(function(statKey) {
            var stat = state.secondaryStats[statKey];
            if (!stat) return;
            stat.value = clamp(
                stat.value + Number(extra[statKey] || 0),
                { min: stat.min_value, max: stat.max_value }
            );
        });

        return mechanicChange;
    }

    function getStatGameOver() {
        var story = state.selected;
        if (!story) return null;
        var mechanic = story.mechanic;
        var value = state.primaryValue;
        if (story.key === 'ganster' && mechanic === 'heat' && value >= 100) {
            return {
                title: 'Adventure Ended - The Heat Burns You',
                text: 'Heat reached 100. Federal agents, city detectives, and courthouse witnesses finally lock the city around you. Your empire is seized, your crews scatter, and your name becomes an evidence label.'
            };
        }
        if (story.key === 'horror' && mechanic === 'fear' && value >= 100) {
            return {
                title: 'Adventure Ended - Fear Overwhelmed You',
                text: 'Fear reached 100. Terror takes over completely, and the nightmare claims you.'
            };
        }
        if (story.key === 'cyberpunk' && mechanic === 'trace' && value >= 100) {
            return {
                title: 'Adventure Ended - Corp Security Found You',
                text: 'Trace reached 100. Megacorp security triangulates your safehouse, burns your aliases, and floods the block with drones before your deck can finish wiping itself.'
            };
        }
        if (story.key === 'spy' && mechanic === 'cover' && value <= 0) {
            return {
                title: 'Adventure Ended - Identity Exposed',
                text: 'Cover reached 0. Enemy counterintelligence connects your aliases, photographs, and dead drops; your diplomatic passport is revoked before the extraction team can find you.'
            };
        }
        if (story.key === 'carnival' && mechanic === 'sanity' && value <= 0) {
            return {
                title: 'Adventure Ended - Part of the Attraction',
                text: 'Sanity reached 0. The midway remembers you as decoration, your voice joins the calliope, and tomorrow visitors laugh at the new attraction wearing your face.'
            };
        }
        if (story.key === 'deepsea' && mechanic === 'oxygen' && value <= 0) {
            return {
                title: 'Adventure Ended - Lost in the Trench',
                text: 'Oxygen reached 0. The submersible lights gutter, pressure folds the hull inward, and something vast in the black water finds you before the surface can.'
            };
        }
        if (story.key === 'wizard' && mechanic === 'mana' && value <= 0) {
            return {
                title: 'Adventure Ended - Mana Extinguished',
                text: 'Mana reached 0. The spell holding your name together collapses, reality forgets your outline, and you cease to exist.'
            };
        }
        if (story.key === 'pirate' && state.secondaryStats.crew_loyalty && state.secondaryStats.crew_loyalty.value <= 0) {
            return {
                title: 'Adventure Ended - Mutiny on Your Deck',
                text: 'Crew Loyalty reached 0. The crew lowers your black flag, locks the powder room, and chooses a new captain before dawn. Your rise ends with your own ship turned against you.'
            };
        }
        if ((story.key === 'western' || story.key === 'robot') && value <= 0) {
            return {
                title: 'Adventure Ended',
                text: titleCase(mechanic) + ' reached 0. You can no longer continue.'
            };
        }
        return null;
    }

    function updateOriginAlignment(nextStage) {
        if (!state.selected || state.selected.key !== 'origin' || !nextStage) return false;
        var currentStage = state.currentStage || {};
        if (getStageNumber(currentStage) === 5 && getStageNumber(nextStage) === 6) {
            if (state.primaryValue > 0) {
                state.originAlignment = 'hero';
                return true;
            }
            if (state.primaryValue < 0) {
                state.originAlignment = 'villain';
                return true;
            }
        }
        return false;
    }

    function getCheckpointGameOver(nextStage) {
        if (!nextStage || !state.selected) return null;
        var story = state.selected;
        var currentNo = getStageNumber(state.currentStage);
        var nextNo = getStageNumber(nextStage);

        if (story.key === 'robot' && currentNo === 5 && nextNo === 6 && state.primaryValue < 100) {
            return {
                title: 'Adventure Ended - Robot Incomplete',
                text: 'Power reached only ' + state.primaryValue + '/100 by the end of stage 5. The helper frame never fully boots, the docking deck loses pressure, and you have no working robot to carry you through the station escape.'
            };
        }

        if (story.key === 'origin' && currentNo === 5 && nextNo === 6 && state.primaryValue === 0) {
            return {
                title: 'Adventure Ended - The City Never Chose',
                text: 'Public Trust ended stage 5 at exactly 0. The city sees neither hero nor villain, only a dangerous unknown, and your origin collapses before it becomes a symbol.'
            };
        }

        if (story.key === 'origin' && currentNo === 7 && nextNo === 8) {
            if (state.originAlignment === 'hero' && state.primaryValue < 50) {
                return {
                    title: 'Adventure Ended - Not Enough Trust to Become a Hero',
                    text: 'Public Trust reached only ' + state.primaryValue + '. The city will not follow you into the final battle until you have at least 50 Public Trust.'
                };
            }
            if (state.originAlignment === 'villain' && state.primaryValue > -50) {
                return {
                    title: 'Adventure Ended - Not Feared Enough to Become a Villain',
                    text: 'Public Trust reached only ' + state.primaryValue + '. The underworld will not crown you until the city has fallen to -50 Public Trust or worse.'
                };
            }
        }

        return null;
    }

    function statChangeText(mechanicChange, extraChanges) {
        var parts = [];
        if (mechanicChange) {
            parts.push(titleCase(state.selected.mechanic) + ' ' + (mechanicChange > 0 ? '+' : '') + mechanicChange);
        }
        Object.keys(extraChanges || {}).forEach(function(statKey) {
            var amount = Number(extraChanges[statKey] || 0);
            if (!amount) return;
            var stat = state.secondaryStats[statKey] || {};
            parts.push((stat.label || titleCase(statKey)) + ' ' + (amount > 0 ? '+' : '') + amount);
        });
        return parts.length ? parts.join(', ') : 'No stat change';
    }

    function disableChoices(disabled) {
        var choices = el('walktru-choices');
        if (!choices) return;
        Array.prototype.forEach.call(choices.querySelectorAll('button'), function(button) {
            button.disabled = !!disabled;
        });
    }

    async function choose(index) {
        if (state.busy || state.finished || !state.currentStage || !state.selected) return;
        var choices = Array.isArray(state.currentStage.choices) ? state.currentStage.choices : [];
        var choice = choices[index];
        if (!choice) return;

        state.busy = true;
        disableChoices(true);

        try {
            var chance = Number(choice.success_chance == null ? 100 : choice.success_chance);
            var roll = Math.floor(Math.random() * 100) + 1;
            var success = roll <= chance;
            var outcome = choice[success ? 'success' : 'failure'] || {};
            var mechanicChange = applyOutcome(outcome);
            var nextStageId = outcome.next_stage;
            var statGameOver = getStatGameOver();
            var nextStage = null;

            if (nextStageId && nextStageId !== 'end' && !outcome.ending) {
                nextStage = await fetchStage(state.selected.key, nextStageId, null);
                var alignmentChanged = updateOriginAlignment(nextStage);
                if (alignmentChanged && nextStage.alignment_variants) {
                    nextStage = await fetchStage(state.selected.key, nextStageId, state.originAlignment);
                }
            }

            var checkpointGameOver = getCheckpointGameOver(nextStage);
            var gameOver = statGameOver || checkpointGameOver || null;
            var finished = !!(outcome.ending || gameOver || !nextStageId || nextStageId === 'end');
            var cls = gameOver ? 'game-over' : (success ? 'success' : 'failure');
            var statText = statChangeText(mechanicChange, outcome.extra_stat_changes || {});

            state.history.push({
                stage: getStageNumber(state.currentStage) || '--',
                choice: choice.label || 'Choice ' + (index + 1),
                result: gameOver ? gameOver.title : (success ? 'Success' : 'Failure'),
                statText: statText,
                cls: cls,
            });

            renderStats();
            renderHistory();
            renderResult({
                success: success,
                roll: roll,
                chance: chance,
                outcome: outcome,
                gameOver: gameOver,
                finished: finished,
                cls: cls,
                statText: statText,
                nextStage: nextStage,
            });

            if (!finished) {
                state._pendingStage = nextStage;
            } else {
                state.finished = true;
            }
        } catch (error) {
            console.error('Walkthru choice failed:', error);
            toast(error.message || 'Choice failed.');
            disableChoices(false);
        } finally {
            state.busy = false;
        }
    }

    function renderResult(data) {
        var result = el('walktru-result');
        var choices = el('walktru-choices');
        if (!result) return;

        var title = data.gameOver ? data.gameOver.title : (data.outcome.ending_title || (data.success ? 'Choice Result - Success' : 'Choice Result - Failure'));
        var text = data.gameOver ? data.gameOver.text : (data.outcome.text || 'You move forward.');
        var ending = data.outcome.ending_status ? '<p><strong>Ending:</strong> ' + esc(data.outcome.ending_status) + '</p>' : '';

        result.className = 'walktru-result ' + data.cls;
        result.hidden = false;
        result.innerHTML = [
            '<h5>', esc(title), '</h5>',
            '<p>', esc(text), '</p>',
            ending,
            '<div class="walktru-result-meta">',
                '<span>', esc(data.success ? 'Success' : 'Failure'), '</span>',
                '<span>', esc(data.statText), '</span>',
            '</div>',
            '<div class="walktru-result-actions">',
                data.finished
                    ? '<button class="walktru-btn walktru-btn-primary" id="walktru-result-restart" type="button">Start Over</button><button class="walktru-btn walktru-btn-ghost" id="walktru-result-stories" type="button">Choose Story</button>'
                    : '<button class="walktru-btn walktru-btn-primary" id="walktru-result-continue" type="button">Continue</button>',
            '</div>'
        ].join('');

        if (choices) choices.innerHTML = '';

        var continueBtn = el('walktru-result-continue');
        if (continueBtn) {
            continueBtn.addEventListener('click', function() {
                if (!state._pendingStage) return;
                state.currentStage = state._pendingStage;
                state._pendingStage = null;
                renderStage();
            });
        }

        var restartBtn = el('walktru-result-restart');
        if (restartBtn) {
            restartBtn.addEventListener('click', function() {
                if (state.selected) startStory(state.selected.key);
            });
        }

        var storiesBtn = el('walktru-result-stories');
        if (storiesBtn) {
            storiesBtn.addEventListener('click', function() {
                root.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        }
    }

    function bindStaticActions() {
        var restart = el('walktru-new-run');
        if (restart) {
            restart.addEventListener('click', function() {
                if (state.selected) startStory(state.selected.key);
                else toast('Choose a story first.');
            });
        }

        var stories = el('walktru-change-story');
        if (stories) {
            stories.addEventListener('click', function() {
                var list = el('walktru-story-list');
                if (list) list.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        }
    }

    bindStaticActions();
    loadStories().catch(function(error) {
        console.error('Walkthru init failed:', error);
        setStatus('Could not load Walkthru stories.');
        toast(error.message || 'Could not load Walkthru.');
    });
})();
