'use strict';

(function() {
    var pollId = null;
    var countdownId = null;
    var state = null;

    function el(id) { return document.getElementById(id); }
    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function setHidden(id, hidden) {
        var node = el(id);
        if (node) node.hidden = !!hidden;
    }

    function toast(message) {
        var node = el('zombie-toast');
        if (!node) return;
        node.textContent = message;
        node.hidden = false;
        clearTimeout(node._hideTimer);
        node._hideTimer = setTimeout(function() { node.hidden = true; }, 4200);
    }

    function fmtTime(seconds) {
        seconds = Math.max(0, Math.floor(seconds || 0));
        var h = Math.floor(seconds / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        var s = seconds % 60;
        if (h > 0) return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
        return m + ':' + String(s).padStart(2, '0');
    }

    function statBar(label, value, cls) {
        value = Math.max(0, Math.min(100, Number(value || 0)));
        return [
            '<div class="zombie-stat-line"><span>', esc(label), '</span><strong>', value, '/100</strong></div>',
            '<div class="zombie-bar ', cls, '"><span style="width:', value, '%"></span></div>'
        ].join('');
    }

    function renderCharacter(data) {
        var node = el('zombie-character');
        if (!node) return;
        var character = data.my_character;
        if (!character) {
            node.innerHTML = '<div class="zombie-empty-panel">Your survivor appears here once you join or vote.</div>';
            return;
        }
        var user = data.user || {};
        var status = character.status || 'Normal';
        node.innerHTML = [
            '<div class="zombie-character-head">',
                '<div><div class="zombie-character-name">', esc(user.display_name || user.username || 'You'), '</div>',
                '<div class="zombie-status">', esc(status), data.has_voted ? ' - Voted' : ' - Not voted', '</div></div>',
            '</div>',
            statBar('Health', character.health, 'zombie-bar-health'),
            statBar('Stamina', character.stamina, 'zombie-bar-stamina'),
            statBar('Morale', character.morale, 'zombie-bar-morale'),
            statBar('Melee condition', character.melee_condition, 'zombie-bar-melee'),
            '<div class="zombie-gear">',
                '<div class="zombie-gear-item"><strong>Revolver</strong>', esc(character.revolver_loaded || 0), '/6 loaded +', esc(character.revolver_spare || 0), ' spare</div>',
                '<div class="zombie-gear-item"><strong>Rifle</strong>', esc(character.rifle_loaded || 0), '/12 loaded +', esc(character.rifle_spare || 0), ' spare</div>',
                '<div class="zombie-gear-item" style="grid-column:1/-1"><strong>Melee</strong>', esc(character.melee || 'Crowbar'), '</div>',
            '</div>'
        ].join('');
    }

    function renderChoices(data) {
        var node = el('zombie-choices');
        if (!node) return;
        if (!data.active || !data.choices || !data.choices.length) {
            node.innerHTML = '<div class="zombie-panel zombie-empty-panel">No active round is available.</div>';
            return;
        }

        var myVote = data.my_vote;
        var dead = data.my_character && data.my_character.status === 'Deceased';
        node.innerHTML = data.choices.map(function(choice) {
            var voted = Number(myVote) === Number(choice.index);
            var disabled = data.has_voted || dead;
            return [
                '<button class="zombie-choice ', voted ? 'voted' : '', '" type="button" data-choice="', choice.index, '" ', disabled ? 'disabled' : '', '>',
                    '<div class="zombie-choice-top">',
                        '<span class="zombie-choice-label">', esc(choice.label), '</span>',
                        '<img src="', esc(choice.image), '" alt="', esc(choice.label), '">',
                    '</div>',
                    '<div class="zombie-choice-text">', esc(choice.text), '</div>',
                    '<div class="zombie-preview">', esc(choice.preview), '</div>',
                    '<div class="zombie-vote-count">', choice.votes, ' vote', choice.votes === 1 ? '' : 's', voted ? ' - yours' : '', '</div>',
                '</button>'
            ].join('');
        }).join('');

        Array.prototype.forEach.call(node.querySelectorAll('.zombie-choice:not(:disabled)'), function(btn) {
            btn.addEventListener('click', function() {
                vote(Number(btn.getAttribute('data-choice')));
            });
        });
    }

    function renderSurvivors(data) {
        var node = el('zombie-survivors');
        var count = el('zombie-survivor-count');
        if (!node) return;
        var survivors = data.survivors || [];
        if (count) count.textContent = String(survivors.length);
        if (!survivors.length) {
            node.innerHTML = '<div class="zombie-empty-panel">No survivors have joined yet.</div>';
            return;
        }
        node.innerHTML = survivors.map(function(s) {
            var dead = s.status === 'Deceased';
            return [
                '<div class="zombie-survivor ', s.is_me ? 'me' : '', ' ', dead ? 'dead' : '', '">',
                    '<strong>', esc(s.display_name), '</strong>',
                    '<div>', esc(s.status), '</div>',
                    '<div>HP ', s.health, ' - ST ', s.stamina, ' - MO ', s.morale, '</div>',
                    '<div>Rev ', s.revolver_loaded, '/6 +', s.revolver_spare, ' - Rifle ', s.rifle_loaded, '/12 +', s.rifle_spare, '</div>',
                    '<div>', esc(s.melee), ' ', s.melee_condition, '/100</div>',
                '</div>'
            ].join('');
        }).join('');
    }

    function renderHistory(data) {
        var node = el('zombie-history');
        if (!node) return;
        var history = data.history || [];
        if (!history.length) {
            node.innerHTML = '<div class="zombie-empty-panel">No resolved rounds yet.</div>';
            return;
        }
        node.innerHTML = history.slice().reverse().map(function(item) {
            return [
                '<div class="zombie-history-item">',
                    '<strong>Round ', esc(item.round), '</strong><br>',
                    esc(item.outcome_text || item.event || ''),
                '</div>'
            ].join('');
        }).join('');
    }

    function updateCountdown() {
        if (!state) return;
        var node = el('zombie-timer');
        if (!node) return;
        if (!state.active || !state.deadline_ts) {
            node.textContent = '--:--';
            return;
        }
        var remaining = Math.max(0, Number(state.deadline_ts) - Math.floor(Date.now() / 1000));
        node.textContent = fmtTime(remaining);
    }

    function render(data) {
        state = data;
        setHidden('zombie-login', true);
        setHidden('zombie-admin', !data.is_admin);

        var status = el('zombie-status-line');
        if (status) {
            status.textContent = data.active
                ? 'Live in Discord - round ' + data.round
                : 'No active Discord game';
        }

        var pill = el('zombie-user-pill');
        if (pill) pill.textContent = data.user && data.user.display_name ? data.user.display_name : 'Discord synced';

        var adminText = el('zombie-admin-text');
        if (adminText) adminText.textContent = data.active ? 'Game running' : 'Ready to start';

        var round = el('zombie-round-label');
        if (round) round.textContent = data.active ? 'Round ' + data.round : 'Inactive';

        var story = el('zombie-story');
        if (story) story.textContent = data.active
            ? (data.current_event || 'The story is waiting for the next Discord update.')
            : 'No Zombie Survival game is currently running.';

        var channel = el('zombie-channel-label');
        if (channel) channel.textContent = data.channel_id ? 'Channel: ' + data.channel_id : 'Channel: --';

        var votes = el('zombie-vote-label');
        if (votes) votes.textContent = 'Votes: ' + (data.voters_total || 0);

        var channelInput = el('zombie-channel-input');
        if (channelInput && data.channel_id && !channelInput.value) channelInput.value = data.channel_id;

        renderCharacter(data);
        renderChoices(data);
        renderSurvivors(data);
        renderHistory(data);
        updateCountdown();
    }

    function parseError(resp) {
        return resp.json().then(function(body) {
            return body.detail || body.message || 'Request failed';
        }).catch(function() {
            return 'Request failed';
        });
    }

    function loadState() {
        return fetch('/api/zombie/state', { credentials: 'same-origin' })
            .then(function(resp) {
                if (resp.status === 401) {
                    setHidden('zombie-login', false);
                    var status = el('zombie-status-line');
                    if (status) status.textContent = 'Discord login required';
                    throw new Error('login');
                }
                if (!resp.ok) return parseError(resp).then(function(msg) { throw new Error(msg); });
                return resp.json();
            })
            .then(render)
            .catch(function(err) {
                if (err.message !== 'login') toast(err.message || 'Could not sync Zombie Survival.');
            });
    }

    function vote(choiceIndex) {
        fetch('/api/zombie/vote', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ choice_index: choiceIndex })
        })
            .then(function(resp) {
                if (!resp.ok) return parseError(resp).then(function(msg) { throw new Error(msg); });
                return resp.json();
            })
            .then(function(data) {
                render(data);
                toast(data.message || 'Vote recorded.');
            })
            .catch(function(err) { toast(err.message || 'Vote failed.'); });
    }

    function startGame() {
        var input = el('zombie-channel-input');
        var channelId = input ? input.value.trim() : '';
        if (!channelId) {
            toast('Enter the Discord channel ID for the story message.');
            return;
        }
        fetch('/api/zombie/start', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: channelId })
        })
            .then(function(resp) {
                if (!resp.ok) return parseError(resp).then(function(msg) { throw new Error(msg); });
                return resp.json();
            })
            .then(function(data) {
                render(data);
                toast(data.message || 'Zombie Survival started.');
            })
            .catch(function(err) { toast(err.message || 'Start failed.'); });
    }

    function stopGame() {
        fetch('/api/zombie/stop', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: '{}'
        })
            .then(function(resp) {
                if (!resp.ok) return parseError(resp).then(function(msg) { throw new Error(msg); });
                return resp.json();
            })
            .then(function(data) {
                render(data);
                toast(data.message || 'Zombie Survival stopped.');
            })
            .catch(function(err) { toast(err.message || 'Stop failed.'); });
    }

    function cleanup() {
        if (pollId) clearInterval(pollId);
        if (countdownId) clearInterval(countdownId);
        pollId = null;
        countdownId = null;
    }

    function init() {
        cleanup();
        var start = el('zombie-start-btn');
        var stop = el('zombie-stop-btn');
        if (start) start.addEventListener('click', startGame);
        if (stop) stop.addEventListener('click', stopGame);
        loadState();
        pollId = setInterval(loadState, 10000);
        countdownId = setInterval(updateCountdown, 1000);
    }

    document.addEventListener('dashboardPageLoaded', function(e) {
        if (e.detail && e.detail.page === 'zombie.html') {
            init();
        } else {
            cleanup();
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
