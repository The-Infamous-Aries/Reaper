class CasinoManager {
    constructor() {
        this.currentXP = 0;
        this.funMode = false;
        this.currentGame = null;
        this.slotsData = {
            difficulty: null,
            betAmount: 0,
            spinning: false,
            emojis: []
        };
    }

    async init() {
        this.setupEventListeners();
        await this.loadUserXP();
        this.updateFunModeDisplay();
    }

    setupEventListeners() {
        // Game selection buttons
        document.querySelectorAll('.play-game-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const game = e.target.dataset.game;
                this.openGame(game);
            });
        });

        // Fun mode toggle
        const funModeToggle = document.getElementById('fun-mode-toggle');
        if (funModeToggle) {
            funModeToggle.addEventListener('change', (e) => {
                this.funMode = e.target.checked;
                this.updateFunModeDisplay();
            });
        }

        // Slots specific listeners
        this.setupSlotsListeners();
    }

    setupSlotsListeners() {
        // Difficulty selection
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('difficulty-btn')) {
                document.querySelectorAll('.difficulty-btn').forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                this.slotsData.difficulty = e.target.dataset.difficulty;
                this.checkSlotsReady();
            }
        });

        // Bet presets
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('preset-btn')) {
                const amount = e.target.dataset.amount;
                const betInput = document.getElementById('slots-bet-amount');
                if (betInput) {
                    betInput.value = amount === '1K' ? '1000' : amount;
                    this.slotsData.betAmount = parseInt(betInput.value);
                    this.checkSlotsReady();
                }
            }
        });

        // Bet input
        document.addEventListener('input', (e) => {
            if (e.target.id === 'slots-bet-amount') {
                this.slotsData.betAmount = parseInt(e.target.value) || 0;
                this.checkSlotsReady();
            }
        });

        // Start slots button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'start-slots-btn') {
                this.startSlotsGame();
            }
        });

        // Spin button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'spin-slots-btn') {
                this.spinSlots();
            }
        });

        // Play again button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'slots-play-again') {
                this.resetSlots();
            }
        });
    }

    async loadUserXP() {
        try {
            // For now, we'll use a placeholder user ID
            // In a real implementation, this would come from authentication
            const userId = 'user123'; // This should be dynamic
            
            const response = await fetch(`/api/casino/user-xp/${userId}`);
            if (response.ok) {
                const data = await response.json();
                this.currentXP = data.total_xp;
            } else {
                this.currentXP = 1000; // Fallback for demo
            }
        } catch (error) {
            console.error('Error loading user XP:', error);
            this.currentXP = 1000; // Fallback for demo
        }
        
        this.updateXPDisplay();
    }

    updateXPDisplay() {
        const xpElement = document.getElementById('current-xp');
        if (xpElement) {
            xpElement.textContent = this.currentXP.toLocaleString();
        }

        const slotsXpElement = document.getElementById('slots-current-xp');
        if (slotsXpElement) {
            slotsXpElement.textContent = `XP: ${this.currentXP.toLocaleString()}`;
        }
    }

    updateFunModeDisplay() {
        const modeElements = document.querySelectorAll('#slots-current-mode');
        modeElements.forEach(element => {
            element.textContent = this.funMode ? 'Fun Mode' : 'Betting Mode';
        });

        // Update bet input visibility
        const betSections = document.querySelectorAll('.bet-input-section');
        betSections.forEach(section => {
            if (this.funMode) {
                section.style.display = 'none';
            } else {
                section.style.display = 'block';
            }
        });
    }

    openGame(gameType) {
        this.currentGame = gameType;
        const modal = new bootstrap.Modal(document.getElementById('gameModal'));
        const modalTitle = document.getElementById('gameModalTitle');
        const modalBody = document.getElementById('gameModalBody');

        // Set title
        const titles = {
            'slots': '🎰 Slot Machine',
            'blackjack': '🃏 Blackjack',
            'holdem': '♠️ Texas Hold\'em',
            'craps': '🎲 Craps',
            'races': '🏁 Pet Races'
        };
        modalTitle.textContent = titles[gameType] || 'Casino Game';

        // Load game content
        const template = document.getElementById(`${gameType}-game-template`);
        if (template) {
            modalBody.innerHTML = template.innerHTML;
            
            // Initialize game-specific logic
            if (gameType === 'slots') {
                this.initSlotsGame();
            }
        }

        modal.show();
    }

    initSlotsGame() {
        this.slotsData = {
            difficulty: null,
            betAmount: 0,
            spinning: false,
            emojis: []
        };
        
        this.updateFunModeDisplay();
        this.updateXPDisplay();
        this.checkSlotsReady();
    }

    checkSlotsReady() {
        const startBtn = document.getElementById('start-slots-btn');
        if (startBtn) {
            const ready = this.slotsData.difficulty && 
                         (this.funMode || (this.slotsData.betAmount > 0 && this.slotsData.betAmount <= this.currentXP));
            startBtn.disabled = !ready;
        }
    }

    async startSlotsGame() {
        const setupDiv = document.getElementById('slots-setup');
        const gameDiv = document.getElementById('slots-game');
        
        if (setupDiv && gameDiv) {
            setupDiv.classList.add('d-none');
            gameDiv.classList.remove('d-none');
        }

        // Update game info
        const currentBet = document.getElementById('current-bet');
        const currentDifficulty = document.getElementById('current-difficulty');
        
        if (currentBet) {
            currentBet.textContent = this.funMode ? '0' : this.slotsData.betAmount.toLocaleString();
        }
        if (currentDifficulty) {
            currentDifficulty.textContent = this.slotsData.difficulty;
        }

        // Setup reels based on difficulty
        await this.setupSlotsReels();
        
        // Show appropriate reel container
        const regularSlots = document.getElementById('regular-slots');
        const insanitySlots = document.getElementById('insanity-slots');
        
        if (this.slotsData.difficulty === 'Insanity') {
            regularSlots?.classList.add('d-none');
            insanitySlots?.classList.remove('d-none');
        } else {
            regularSlots?.classList.remove('d-none');
            insanitySlots?.classList.add('d-none');
        }
    }

    async setupSlotsReels() {
        try {
            const response = await fetch(`/api/casino/slots/emojis/${this.slotsData.difficulty}`);
            if (response.ok) {
                const data = await response.json();
                this.slotsData.emojis = data.emojis;
                this.populateReels();
            }
        } catch (error) {
            console.error('Error loading slot emojis:', error);
            // Fallback to basic emojis
            this.slotsData.emojis = [
                {name: 'Cat', path: '/static/Emojis/Pets/Cat.png'},
                {name: 'Dog', path: '/static/Emojis/Pets/Dog.png'},
                {name: 'Fire', path: '/static/Emojis/Pets/Deco/Fire.png'}
            ];
            this.populateReels();
        }
    }

    populateReels() {
        const emojis = this.slotsData.emojis;
        if (!emojis || emojis.length === 0) return;

        if (this.slotsData.difficulty === 'Insanity') {
            // Populate both element and pet reels
            for (let i = 1; i <= 3; i++) {
                const elementReel = document.getElementById(`element-reel-${i}`);
                const petReel = document.getElementById(`pet-reel-${i}`);
                
                if (elementReel) {
                    elementReel.innerHTML = this.generateReelContent(emojis);
                }
                if (petReel) {
                    petReel.innerHTML = this.generateReelContent(emojis);
                }
            }
        } else {
            // Populate regular reels
            for (let i = 1; i <= 3; i++) {
                const reel = document.getElementById(`reel-${i}`);
                if (reel) {
                    reel.innerHTML = this.generateReelContent(emojis);
                }
            }
        }
    }

    generateReelContent(emojis) {
        let html = '';
        for (let i = 0; i < 20; i++) {
            const randomEmoji = emojis[Math.floor(Math.random() * emojis.length)];
            html += `<img src="${randomEmoji.path}" alt="${randomEmoji.name}" style="width: 80px; height: 80px; object-fit: contain; display: block; margin-bottom: 10px;">`;
        }
        return html;
    }

    async spinSlots() {
        if (this.slotsData.spinning) return;
        
        this.slotsData.spinning = true;
        const spinBtn = document.getElementById('spin-slots-btn');
        const resultDiv = document.getElementById('slots-result-text');
        const winningsDiv = document.getElementById('slots-winnings');
        
        if (spinBtn) {
            spinBtn.disabled = true;
            spinBtn.textContent = '🎰 SPINNING...';
        }
        
        if (resultDiv) {
            resultDiv.textContent = '';
        }
        
        if (winningsDiv) {
            winningsDiv.classList.add('d-none');
        }

        // Start reel animations
        this.startReelAnimations();

        try {
            // Call API to get spin result
            const response = await fetch('/api/casino/slots/spin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    user_id: 'user123', // This should be dynamic
                    theme: this.slotsData.difficulty,
                    bet_amount: this.slotsData.betAmount,
                    fun_mode: this.funMode
                })
            });

            if (response.ok) {
                const result = await response.json();
                
                // Wait for animation then show results
                setTimeout(() => {
                    this.showSlotsResult(result);
                }, 3000);
            } else {
                throw new Error('Spin failed');
            }
        } catch (error) {
            console.error('Error spinning slots:', error);
            // Fallback result
            setTimeout(() => {
                this.showSlotsResult({
                    result_text: 'Better luck next time!',
                    winnings: 0,
                    insanity_mode: false
                });
            }, 3000);
        }
    }

    startReelAnimations() {
        const reels = document.querySelectorAll('.slots-reel');
        reels.forEach((reel, index) => {
            setTimeout(() => {
                reel.classList.add('spinning');
            }, index * 200);
        });
    }

    showSlotsResult(result) {
        // Stop animations
        const reels = document.querySelectorAll('.slots-reel');
        reels.forEach(reel => {
            reel.classList.remove('spinning');
        });

        // Show result text
        const resultDiv = document.getElementById('slots-result-text');
        if (resultDiv) {
            resultDiv.textContent = result.result_text;
        }

        // Show winnings if any
        if (result.winnings > 0) {
            const winningsDiv = document.getElementById('slots-winnings');
            const winningsAmount = document.getElementById('winnings-amount');
            
            if (winningsDiv && winningsAmount) {
                winningsAmount.textContent = `${result.winnings.toLocaleString()} XP`;
                winningsDiv.classList.remove('d-none');
            }

            // Update user XP
            if (!this.funMode) {
                this.currentXP += result.winnings;
                this.updateXPDisplay();
            }
        }

        // Show play again button
        const playAgainBtn = document.getElementById('slots-play-again');
        if (playAgainBtn) {
            playAgainBtn.classList.remove('d-none');
        }

        // Reset spin button
        const spinBtn = document.getElementById('spin-slots-btn');
        if (spinBtn) {
            spinBtn.disabled = false;
            spinBtn.textContent = '🎰 SPIN';
            spinBtn.classList.add('d-none');
        }

        this.slotsData.spinning = false;
    }

    resetSlots() {
        const setupDiv = document.getElementById('slots-setup');
        const gameDiv = document.getElementById('slots-game');
        
        if (setupDiv && gameDiv) {
            setupDiv.classList.remove('d-none');
            gameDiv.classList.add('d-none');
        }

        // Reset slots data
        this.slotsData = {
            difficulty: null,
            betAmount: 0,
            spinning: false,
            emojis: []
        };

        // Reset form
        document.querySelectorAll('.difficulty-btn').forEach(btn => btn.classList.remove('active'));
        const betInput = document.getElementById('slots-bet-amount');
        if (betInput) {
            betInput.value = '';
        }

        this.checkSlotsReady();
    }
}

// Initialize casino when page loads
document.addEventListener('DOMContentLoaded', () => {
    const casino = new CasinoManager();
    casino.init();
});

// Make casino globally available for debugging
window.casino = new CasinoManager();