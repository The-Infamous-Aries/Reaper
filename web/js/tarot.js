class TarotReading {
    constructor() {
        this.currentSpread = null;
        this.cards = [];
        this.tarotData = null;
        this.isDealing = false;
        this.dealerMessages = {
            start: "The universe whispers... let me reveal your path.",
            dealing: "Feel the energy of each card as it falls...",
            summary: "The cosmos has spoken. Listen carefully to this wisdom."
        };

        this.groqApiKey = window.botInfo?.groq_api_key || '';
        this.groqApiAvailable = window.botInfo?.groq_api_available || false;

        this.init();
    }

    async init() {
        // Set up event listeners immediately so clicks are never missed
        this.setRandomSkull();
        this.setupEventListeners();

        // Fetch bot info and tarot data in the background
        try {
            const res = await fetch('/api/bot-info');
            if (res.ok) {
                const info = await res.json();
                window.botInfo = info;
                this.groqApiKey = info.groq_api_key || '';
                this.groqApiAvailable = info.groq_api_available || false;
            }
        } catch (_) {}

        await this.loadTarotData();
    }

    setRandomSkull() {
        const skullIndex = Math.floor(Math.random() * 16) + 1;
        const skullUrl = `/static/Emojis/Skulls/${skullIndex}.png`;

        const skullImage = document.getElementById('skull-image');
        if (skullImage) {
            skullImage.style.display = 'none';
            skullImage.onload = () => { skullImage.style.display = ''; };
            skullImage.onerror = () => {
                skullImage.src = `/static/Emojis/Skulls/1.png`;
                skullImage.style.display = '';
            };
            skullImage.src = skullUrl;
        }

        const summaryAvatar = document.getElementById('summary-avatar');
        if (summaryAvatar) {
            summaryAvatar.style.backgroundImage = `url('${skullUrl}')`;
            summaryAvatar.style.backgroundSize = 'cover';
            summaryAvatar.style.backgroundPosition = 'center';
        }
    }

    setupEventListeners() {
        const bubbles = document.querySelectorAll('.thought-bubble');
        if (!bubbles.length) {
            console.warn('[TarotReading] No .thought-bubble elements found in DOM');
        }
        bubbles.forEach(bubble => {
            bubble.addEventListener('click', (e) => {
                e.stopPropagation();
                if (this.isDealing) return;
                const spread = bubble.dataset.spread;
                if (!spread) return;
                document.querySelectorAll('.thought-bubble').forEach(b => b.classList.remove('selected'));
                bubble.classList.add('selected');
                this.startReading(spread);
            });
        });

        const restartBtn = document.getElementById('restart-reading');
        if (restartBtn) {
            restartBtn.addEventListener('click', () => this.restartReading());
        }
    }

    async loadTarotData() {
        try {
            const response = await fetch('/Systems/Astrology/Tarot/tarot-images.json');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            this.tarotData = {};
            data.cards.forEach(card => {
                const key = card.img.replace('.jpg', '');
                this.tarotData[key] = card;
            });
        } catch (error) {
            console.error('Error loading tarot data:', error);
            this.tarotData = {};
        }
    }

    async startReading(spread) {
        this.currentSpread = spread;
        this.isDealing = true;

        document.getElementById('reading-selection').classList.add('d-none');
        document.getElementById('card-table').classList.remove('d-none');
        document.getElementById('reading-results').classList.add('d-none');

        this.showDealerMessage(this.dealerMessages.start);

        // If tarot data hasn't loaded yet, wait up to 5 seconds
        if (!this.tarotData || Object.keys(this.tarotData).length === 0) {
            this.showDealerMessage('Loading the cards from the cosmos...');
            await this.loadTarotData();
        }

        if (!this.tarotData || Object.keys(this.tarotData).length === 0) {
            document.getElementById('card-table').classList.add('d-none');
            document.getElementById('reading-selection').classList.remove('d-none');
            this.showDealerMessage('The cards are unavailable. Please try again.');
            this.isDealing = false;
            return;
        }

        await this.delay(1500);
        await this.dealCards();
    }

    async dealCards() {
        const cardCount = this.getCardCountForSpread(this.currentSpread);
        const cardSlots = document.getElementById('card-slots');

        // Fisher-Yates shuffle for unbiased randomness
        const cardKeys = Object.keys(this.tarotData);
        for (let i = cardKeys.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [cardKeys[i], cardKeys[j]] = [cardKeys[j], cardKeys[i]];
        }
        this.shuffledDeck = cardKeys;

        const positions = this.getPositionsForSpread(this.currentSpread);

        // Create slots
        cardSlots.innerHTML = '';
        for (let i = 0; i < cardCount; i++) {
            const slot = document.createElement('div');
            slot.className = 'card-slot';
            slot.id = `slot-${i}`;
            // Position label above the slot
            const label = document.createElement('div');
            label.className = 'card-position-label';
            label.textContent = positions[i];
            slot.appendChild(label);
            cardSlots.appendChild(slot);
        }

        // Deal cards one by one
        this.cards = [];
        for (let i = 0; i < cardCount; i++) {
            await this.dealSingleCard(i, positions[i]);
            await this.delay(2500);
        }

        await this.delay(800);
        await this.generateSummary();
    }

    async dealSingleCard(index, position) {
        const slot = document.getElementById(`slot-${index}`);
        const cardKey = this.shuffledDeck.pop();
        const cardData = this.tarotData[cardKey];

        if (!cardData) {
            console.error('No card data for:', cardKey);
            return;
        }

        const isReversed = Math.random() < 0.3; // 30% chance reversed
        const meanings = isReversed ? cardData.meanings.shadow : cardData.meanings.light;
        const meaning = Array.isArray(meanings) ? meanings.slice(0, 3).join(', ') : (meanings || 'Unknown');
        const displayName = cardData.name + (isReversed ? ' (Reversed)' : '');
        const isMajor = cardData.arcana === 'Major Arcana';

        const enhancedCardData = {
            ...cardData,
            name: displayName,
            isReversed,
            meaning,
            imageKey: cardKey,
            position
        };

        this.cards.push(enhancedCardData);
        this.showDealerMessage(`${cardData.name}${isReversed ? ' — Reversed' : ''}: ${meaning.split(',')[0]}`);

        const card = document.createElement('div');
        card.className = 'tarot-card dealing' + (isReversed ? ' reversed' : '') + (isMajor ? ' major-arcana' : '');

        const cardImageUrl = `/Systems/Astrology/Tarot/cards/${cardKey}.jpg`;
        card.innerHTML = `
            <div class="card-front">
                <img src="${cardImageUrl}" alt="${cardData.name}" class="card-image"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                <div class="card-image-fallback" style="display:none">${cardData.name.charAt(0)}</div>
                <div class="card-name">${displayName}</div>
                ${isReversed ? '<div class="card-reversed-indicator">↓ REVERSED</div>' : ''}
            </div>
        `;

        slot.appendChild(card);

        // Remove dealing class after animation completes so reversed transform sticks
        card.addEventListener('animationend', () => {
            card.classList.remove('dealing');
        }, { once: true });

        await this.delay(1200);
    }

    async generateSummary() {
        this.showDealerMessage(this.dealerMessages.summary);

        const summaryContent = document.getElementById('ai-summary-content');
        summaryContent.innerHTML = `
            <div class="text-center py-3">
                <div class="spinner-border" style="color:var(--gold-primary)">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2" style="color:var(--text-secondary)">The universe is channeling wisdom...</p>
            </div>`;

        const summary = await this.generateAISummary();
        summaryContent.innerHTML = this.formatAISummary(summary);

        await this.delay(1000);

        const results = document.getElementById('reading-results');
        results.classList.remove('d-none');
        results.classList.add('fade-in');

        this.hideDealerMessage();
        this.isDealing = false;
    }

    async generateAISummary() {
        try {
            const cardPayload = this.cards.map(card => ({
                name: card.name,
                position: card.position,
                meaning: card.meaning,
                isReversed: card.isReversed,
                imageKey: card.imageKey
            }));

            const response = await fetch('/api/tarot/reading', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    spread: this.currentSpread,
                    cards: cardPayload
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.summary) return data.summary;
            } else {
                console.error('Tarot API error:', response.status);
            }
        } catch (error) {
            console.error('AI summary error:', error);
        }

        return this.generateBasicSummary();
    }

    generateBasicSummary() {
        const positions = this.getPositionsForSpread(this.currentSpread);
        let summary = `**Your ${this.currentSpread} Reading**\n\n`;

        this.cards.forEach((card, index) => {
            summary += `**${positions[index]}: ${card.name}**\n${card.meaning}\n\n`;
        });

        return summary;
    }

    formatAISummary(summary) {
        const html = summary
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');
        return `<div class="ai-summary-text"><p>${html}</p></div>`;
    }

    restartReading() {
        this.currentSpread = null;
        this.cards = [];
        this.isDealing = false;

        document.querySelectorAll('.thought-bubble').forEach(b => b.classList.remove('selected'));
        document.getElementById('reading-selection').classList.remove('d-none');
        document.getElementById('card-table').classList.add('d-none');
        document.getElementById('reading-results').classList.add('d-none');

        this.hideDealerMessage();
        this.setRandomSkull();
    }

    showDealerMessage(message) {
        const speechBubble = document.getElementById('dealer-speech');
        if (!speechBubble) return;
        const speechContent = speechBubble.querySelector('.speech-content');
        if (speechContent) {
            speechContent.textContent = message;
            speechBubble.classList.remove('d-none');
        }
    }

    hideDealerMessage() {
        const speechBubble = document.getElementById('dealer-speech');
        if (speechBubble) speechBubble.classList.add('d-none');
    }

    getPositionsForSpread(spread) {
        const config = {
            "1 Card": ["The Message"],
            "3 Card (Past/Present/Future)": ["Past", "Present", "Future"],
            "5 Card (Traditional)": ["Theme", "Obstacle", "Advice", "Hidden Influence", "Outcome"]
        };
        return config[spread] || ["Card"];
    }

    getCardCountForSpread(spread) {
        if (spread.includes('1 Card')) return 1;
        if (spread.includes('3 Card')) return 3;
        if (spread.includes('5 Card')) return 5;
        return 1;
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Initialize when the dashboard loads this page.
// Use a named handler so we can remove any previously registered copy before
// adding a new one — prevents stacking duplicate listeners across page visits.
function _tarotPageLoadedHandler(event) {
    if (event.detail && event.detail.page === 'tarot.html') {
        // Destroy any previous instance so its state doesn't bleed in
        if (window.tarotInstance) {
            window.tarotInstance = null;
        }
        window.tarotInstance = new TarotReading();
    }
}

// Remove any stale listener from a previous script load, then re-register
document.removeEventListener('dashboardPageLoaded', _tarotPageLoadedHandler);
document.addEventListener('dashboardPageLoaded', _tarotPageLoadedHandler);

// Handle direct page load (no dashboard wrapper)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.getElementById('reading-selection')) {
            window.tarotInstance = new TarotReading();
        }
    });
} else if (document.getElementById('reading-selection')) {
    window.tarotInstance = new TarotReading();
}
