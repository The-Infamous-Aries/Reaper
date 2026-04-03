class FunFeatures {
    constructor() {
        this.emojiData = null;
        this.coinTheme = null;
        this.cardAmount = null;
        
        // RPS properties
        this.rpsTheme = null;
        this.rpsPlayerScore = 0;
        this.rpsAiScore = 0;
        this.rpsPlayerHistory = [];
        
        // Slots properties
        this.slotsTheme = null;
        this.slotsReels = [];
        this.slotsSpinning = false;
        
        this.coinThemes = {
            'Raider': { heads: 'Pirate', tails: 'Poop', headsEmoji: '/static/Emojis/Coins/Pirate.png', tailsEmoji: '/static/Emojis/Coins/Poop.png' },
            'Time': { heads: 'Future', tails: 'Retro', headsEmoji: '/static/Emojis/Coins/Future.png', tailsEmoji: '/static/Emojis/Coins/Retro.png' },
            'Battery': { heads: 'Full', tails: 'Empty', headsEmoji: '/static/Emojis/Coins/Full.png', tailsEmoji: '/static/Emojis/Coins/Empty.png' },
            'Electric': { heads: 'Plug', tails: 'Socket', headsEmoji: '/static/Emojis/Coins/Plug.png', tailsEmoji: '/static/Emojis/Coins/Socket.png' },
            'Business': { heads: 'Open', tails: 'Close', headsEmoji: '/static/Emojis/Coins/Open.png', tailsEmoji: '/static/Emojis/Coins/Close.png' },
            'Sky': { heads: 'Day', tails: 'Night', headsEmoji: '/static/Emojis/Coins/Day.png', tailsEmoji: '/static/Emojis/Coins/Night.png' },
            'Tempature': { heads: 'Heat', tails: 'Cold', headsEmoji: '/static/Emojis/Coins/Hot.png', tailsEmoji: '/static/Emojis/Coins/Cold.png' }
        };
        
        this.cardSuits = {
            'Hearts': { cards: ['H1','H2','H3','H4','H5','H6','H7','H8','H9','H10','HJ','HQ','HK'], color: 'red', symbol: '♥️' },
            'Diamonds': { cards: ['D1','D2','D3','D4','D5','D6','D7','D8','D9','D10','DJ','DQ','DK'], color: 'red', symbol: '♦️' },
            'Clubs': { cards: ['C1','C2','C3','C4','C5','C6','C7','C8','C9','C10','CJ','CQ','CK'], color: 'black', symbol: '♣️' },
            'Spades': { cards: ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','SJ','SQ','SK'], color: 'black', symbol: '♠️' },
            'Jokers': { cards: ['LJ','BJ'], color: 'red', symbol: '🃏' }
        };
    }

    async init() {
        this.setupEventListeners();
        // Check if GSAP is loaded with retry mechanism
        let gsapCheckAttempts = 0;
        const maxGsapChecks = 5;
        const gsapCheckDelay = 200; // 200ms delay between checks
        
        while (gsapCheckAttempts < maxGsapChecks) {
            if (typeof gsap !== 'undefined') {
                console.log('GSAP library loaded successfully!');
                this.gsapAvailable = true;
                
                // Register MotionPathPlugin if available
                if (typeof MotionPathPlugin !== 'undefined') {
                    gsap.registerPlugin(MotionPathPlugin);
                    console.log('MotionPathPlugin registered successfully!');
                } else {
                    console.warn('MotionPathPlugin not found, some animations may not work properly.');
                }
                break;
            } else {
                gsapCheckAttempts++;
                console.log(`GSAP not found, attempt ${gsapCheckAttempts}/${maxGsapChecks}`);
                
                if (gsapCheckAttempts < maxGsapChecks) {
                    await new Promise(resolve => setTimeout(resolve, gsapCheckDelay));
                } else {
                    console.error('GSAP library not loaded after all attempts! Falling back to CSS animations.');
                    this.gsapAvailable = false;
                }
            }
        }
        
        await this.loadEmojiData();
    }
    
    async loadEmojiData() {
        try {
            console.log('Loading emoji data from server...');
            // Load emoji data from the server
            const response = await fetch('/api/emoji-data');
            if (response.ok) {
                const data = await response.json();
                console.log('API emoji data response:', data);
                this.emojiData = data.emojis;
                this.emojiCategories = data.categories;
                console.log('Successfully loaded emoji data from API');
            } else {
                console.log(`API returned status ${response.status}, using fallback emoji data`);
                // Fallback to hardcoded emoji IDs if API not available
                this.emojiData = this.getFallbackEmojiData();
                this.emojiCategories = this.getFallbackCategories();
            }
        } catch (error) {
            console.log('Error loading emoji data from API, using fallback:', error.message);
            this.emojiData = this.getFallbackEmojiData();
            this.emojiCategories = this.getFallbackCategories();
        }
        
        // Verify emoji data is loaded
        if (this.emojiData) {
            console.log(`Loaded ${Object.keys(this.emojiData).length} custom emojis`);
            console.log('All available emojis:', Object.keys(this.emojiData).slice(0, 20));
            // Test a few key emojis
            console.log('Sample emojis loaded:', {
                'Pirate': this.emojiData['Pirate'] || 'not found',
                'Red1': this.emojiData['Red1'] || 'not found',
                'H1': this.emojiData['H1'] || 'not found',
                'D6': this.emojiData['D6'] || 'not found',
                'Heat': this.emojiData['Heat'] || 'not found'
            });
        } else {
            console.error('Failed to load any emoji data');
        }
    }
    
    getFallbackEmojiData() {
        return {};
    }
    
    getFallbackCategories() {
        return {
            'Military': ['soldier', 'tank', 'jet', 'ship'],
            'Stats': ['ATT', 'DEF', 'DEX', 'INT', 'HAP', 'ENE'],
            'Elements': ['Air', 'Basic', 'Electric', 'Fire', 'Holy', 'Ice', 'Magic', 'Necro', 'Plant', 'Rock', 'Water', 'Psychic', 'Fighting'],
            'Pets': [],
            'Pet Type': []
        };
    }
    
    setupEventListeners() {
        // Coin Flip Event Listeners
        const coinThemeBtns = document.querySelectorAll('.coin-theme-btn');
        if (coinThemeBtns) {
            coinThemeBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    coinThemeBtns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.coinTheme = btn.dataset.theme;
                    this.flipCoin();
                });
            });
        }
        
        const coinPlayAgainBtn = document.getElementById('coin-play-again');
        if (coinPlayAgainBtn) {
            coinPlayAgainBtn.addEventListener('click', () => {
                this.resetCoin();
            });
        }
        
        // Card Draw Event Listeners
        const cardAmountBtns = document.querySelectorAll('.card-amount-btn');
        if (cardAmountBtns) {
            cardAmountBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    cardAmountBtns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.cardAmount = parseInt(btn.dataset.amount);
                    const drawCardsBtn = document.getElementById('draw-cards-btn');
                    if (drawCardsBtn) {
                        drawCardsBtn.disabled = false;
                    }
                });
            });
        }
        
        const drawCardsBtn = document.getElementById('draw-cards-btn');
        if (drawCardsBtn) {
            drawCardsBtn.addEventListener('click', () => {
                this.drawCards();
            });
        }
        
        const cardPlayAgainBtn = document.getElementById('card-play-again');
        if (cardPlayAgainBtn) {
            cardPlayAgainBtn.addEventListener('click', () => {
                this.resetCards();
            });
        }
        
        // Rock Paper Scissors Event Listeners
        const rpsThemeBtns = document.querySelectorAll('.rps-theme-btn');
        if (rpsThemeBtns) {
            rpsThemeBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    rpsThemeBtns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.rpsTheme = btn.dataset.theme;
                    this.updateRPSTheme();
                    this.checkRPSReady();
                });
            });
        }
        
        const startRpsBtn = document.getElementById('start-rps-btn');
        if (startRpsBtn) {
            startRpsBtn.addEventListener('click', () => {
                this.startRPSGame();
            });
        }
        
        const changeThemeBtn = document.getElementById('change-theme-btn');
        if (changeThemeBtn) {
            changeThemeBtn.addEventListener('click', () => {
                this.showThemeSelection();
            });
        }
        
        const cancelThemeChangeBtn = document.getElementById('cancel-theme-change');
        if (cancelThemeChangeBtn) {
            cancelThemeChangeBtn.addEventListener('click', () => {
                this.hideThemeSelection();
            });
        }
        
        const rpsThemeChangeBtns = document.querySelectorAll('.rps-theme-change-btn');
        if (rpsThemeChangeBtns) {
            rpsThemeChangeBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    this.changeRPSTheme(btn.dataset.theme);
                });
            });
        }

        const resetGameBtn = document.getElementById('reset-game-btn');
        if (resetGameBtn) {
            resetGameBtn.addEventListener('click', () => {
                this.resetRPS();
            });
        }
        
        const rpsChoiceBtns = document.querySelectorAll('.rps-choice-btn');
        if (rpsChoiceBtns) {
            rpsChoiceBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    console.log('RPS choice button clicked:', btn.dataset.choice);
                    this.makeRPSMove(btn.dataset.choice);
                });
            });
        }
        
        const rpsPlayAgainBtn = document.getElementById('rps-play-again');
        if (rpsPlayAgainBtn) {
            rpsPlayAgainBtn.addEventListener('click', () => {
                this.resetRPSRound();
            });
        }
        
        const rpsNewRoundBtn = document.getElementById('rps-new-round');
        if (rpsNewRoundBtn) {
            rpsNewRoundBtn.addEventListener('click', () => {
                this.nextRPSRound();
            });
        }
        
        // Slots Event Listeners
        const slotsThemeBtns = document.querySelectorAll('.slots-theme-btn');
        if (slotsThemeBtns) {
            slotsThemeBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    slotsThemeBtns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.slotsTheme = btn.dataset.theme;
                    this.updateSlotsOdds(); // Update odds when theme changes
                    const startSlotsBtn = document.getElementById('start-slots-btn');
                    if (startSlotsBtn) {
                        startSlotsBtn.disabled = false;
                    }
                });
            });
        }
        
        this.loadSlotsOdds(); // Load odds on initialization
        
        const startSlotsBtn = document.getElementById('start-slots-btn');
        if (startSlotsBtn) {
            startSlotsBtn.addEventListener('click', () => {
                this.startSlotsGame();
            });
        }
        
        const spinSlotsBtn = document.getElementById('spin-slots-btn');
        if (spinSlotsBtn) {
            spinSlotsBtn.addEventListener('click', () => {
                this.spinSlots();
            });
        }
        
        const slotsPlayAgainBtn = document.getElementById('slots-play-again');
        if (slotsPlayAgainBtn) {
            slotsPlayAgainBtn.addEventListener('click', () => {
                this.resetSlots();
            });
        }
    }
    
    // Coin Flip Methods
    async flipCoin() {
        if (this.gsapAvailable) {
            return this.flipCoinEnhanced();
        } else {
            return this.flipCoinClassic();
        }
    }
    
    async flipCoinEnhanced() {
        const setup = document.getElementById('coin-setup');
        const animation = document.getElementById('coin-animation');
        const coin = document.getElementById('coin');
        const resultText = document.getElementById('coin-result-text');
        
        setup.classList.add('d-none');
        animation.classList.remove('d-none');
        
        const theme = this.coinThemes[this.coinTheme];
        
        // Set coin faces
        const headsFace = coin.querySelector('.coin-heads');
        const tailsFace = coin.querySelector('.coin-tails');
        
        if (this.emojiData) {
            const headsEmoji = this.emojiData[theme.heads] || `/static/Emojis/Coins/${theme.heads}.png`;
            const tailsEmoji = this.emojiData[theme.tails] || `/static/Emojis/Coins/${theme.tails}.png`;
            headsFace.innerHTML = `<img src="${headsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
            tailsFace.innerHTML = `<img src="${tailsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
        } else {
            headsFace.innerHTML = `<img src="${theme.headsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
            tailsFace.innerHTML = `<img src="${theme.tailsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
        }
        
        try {
            const response = await fetch(`/api/fun/coin-flip?theme=${encodeURIComponent(this.coinTheme)}`);
            let result;
            
            if (response.ok) {
                result = await response.json();
            } else {
                throw new Error('API error');
            }
            
            // Create enhanced 3D coin flip animation
            await this.animateCoinFlipEnhanced(coin, result.result);
            
            // Show result with enhanced effects
            resultText.innerHTML = `🎯 It landed on <strong>${result.result.toUpperCase()}</strong>!`;
            resultText.classList.add('fade-in');
            
            // Add celebration effect for the winner
            this.addCoinCelebration(result.result);
            
        } catch (error) {
            console.error('Error calling coin flip API:', error);
            // Fallback to client-side random with enhanced animation
            const isHeads = Math.random() < 0.5;
            const result = isHeads ? 'heads' : 'tails';
            
            await this.animateCoinFlipEnhanced(coin, result);
            
            resultText.innerHTML = `🎯 It landed on <strong>${result.toUpperCase()}</strong>!`;
            resultText.classList.add('fade-in');
            this.addCoinCelebration(result);
        }
    }
    
    async animateCoinFlipEnhanced(coin, finalResult) {
        // Reset any previous animations
        gsap.killTweensOf(coin);
        gsap.set(coin, { clearProps: "all" });
        
        // Create the enhanced coin flip timeline
        const flipTimeline = gsap.timeline();
        
        // Generate random number of full rotations (3-6 rotations)
        const fullRotations = Math.floor(Math.random() * 4) + 3; // 3-6 full rotations
        const totalRotation = fullRotations * 360;
        
        // Determine final rotation based on result
        const finalRotation = finalResult === 'heads' ? totalRotation : totalRotation + 180;
        
        // Phase 1: Launch (coin rises up with slight wobble)
        flipTimeline
            .to(coin, {
                duration: 0.3,
                y: -80,
                scale: 1.1,
                rotationY: 45,
                rotationX: 10,
                ease: "power2.out"
            })
            .to(coin, {
                duration: 0.2,
                rotationX: -5,
                ease: "sine.inOut"
            }, "-=0.1");
        
        // Phase 2: Mid-air spinning (multiple 360° rotations)
        flipTimeline
            .to(coin, {
                duration: 1.2,
                y: -120, // Peak height
                rotationY: finalRotation * 0.6, // 60% of total rotation
                rotationX: 15,
                scale: 1.0,
                ease: "power1.inOut"
            })
            .to(coin, {
                duration: 0.8,
                rotationY: finalRotation * 0.9, // 90% of total rotation
                rotationX: -10,
                ease: "sine.inOut"
            }, "-=0.4");
        
        // Phase 3: Landing (gravity effect with bounce)
        flipTimeline
            .to(coin, {
                duration: 0.4,
                y: 0,
                rotationY: finalRotation,
                rotationX: 0,
                scale: 1.0,
                ease: "bounce.out"
            })
            .to(coin, {
                duration: 0.1,
                scale: 1.05,
                ease: "power2.out"
            })
            .to(coin, {
                duration: 0.1,
                scale: 1.0,
                ease: "power2.in"
            });
        
        // Add motion blur effect during fast rotation
        // this.addMotionBlur(coin, flipTimeline); // Removed to eliminate reflection effect
        
        // Add whoosh sound effect (visual representation)
        // this.addWhooshEffect(coin, flipTimeline); // Removed to eliminate reflection effect
        
        return flipTimeline;
    }

    addMotionBlur(coin, timeline) {
        // Create motion blur effect during fast rotation
        const blurElement = coin.cloneNode(true);
        blurElement.style.position = 'absolute';
        blurElement.style.top = '0';
        blurElement.style.left = '0';
        blurElement.style.filter = 'blur(2px)';
        blurElement.style.opacity = '0.3';
        blurElement.style.pointerEvents = 'none';
        blurElement.id = '';
        
        coin.parentElement.appendChild(blurElement);
        
        // Sync the blur element with the original coin
        timeline.to(blurElement, {
            duration: 2.0,
            rotationY: "+=360",
            ease: "none"
        }, 0.5);
        
        // Fade out and remove blur element
        timeline.to(blurElement, {
            duration: 0.3,
            opacity: 0,
            onComplete: () => blurElement.remove()
        }, "-=0.5");
    }
    
    addWhooshEffect(coin, timeline) {
        // Create whoosh lines effect
        for (let i = 0; i < 3; i++) {
            const whooshLine = document.createElement('div');
            whooshLine.style.cssText = `
                position: absolute;
                width: 60px;
                height: 2px;
                background: linear-gradient(90deg, transparent, rgba(255,215,0,0.6), transparent);
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%) rotate(${i * 30 - 30}deg);
                pointer-events: none;
                opacity: 0;
            `;
            coin.parentElement.appendChild(whooshLine);
            
            timeline.to(whooshLine, {
                duration: 0.4,
                opacity: 1,
                scaleX: 1.5,
                ease: "power2.out"
            }, 0.2 + i * 0.1);
            
            timeline.to(whooshLine, {
                duration: 0.3,
                opacity: 0,
                x: (i - 1) * 20,
                onComplete: () => whooshLine.remove()
            }, "-=0.2");
        }
    }
    
    addCoinCelebration(result) {
        const coin = document.getElementById('coin');
        const celebrationTimeline = gsap.timeline();
        
        // Victory celebration effect
        celebrationTimeline
            .to(coin, {
                duration: 0.2,
                scale: 1.2,
                ease: "back.out(1.7)"
            })
            .to(coin, {
                duration: 0.3,
                y: "-=20",
                ease: "power2.out"
            })
            .to(coin, {
                duration: 0.4,
                y: "+=20",
                scale: 1.0,
                ease: "bounce.out"
            });
        
        // Add sparkle effects
        this.addSparkleEffects(coin, result);
    }
    
    addSparkleEffects(coin, result) {
        // Create sparkle particles
        for (let i = 0; i < 8; i++) {
            const sparkle = document.createElement('div');
            sparkle.style.cssText = `
                position: absolute;
                width: 4px;
                height: 4px;
                background: ${result === 'heads' ? 'var(--gold-primary)' : 'var(--danger)'};
                border-radius: 50%;
                pointer-events: none;
                box-shadow: 0 0 6px currentColor;
            `;
            
            coin.parentElement.appendChild(sparkle);
            
            const angle = (i / 8) * Math.PI * 2;
            const distance = 40 + Math.random() * 20;
            
            gsap.fromTo(sparkle,
                {
                    x: 0,
                    y: 0,
                    opacity: 1,
                    scale: 1
                },
                {
                    x: Math.cos(angle) * distance,
                    y: Math.sin(angle) * distance - 20,
                    opacity: 0,
                    scale: 0,
                    duration: 0.8,
                    delay: Math.random() * 0.3,
                    ease: "power2.out",
                    onComplete: () => sparkle.remove()
                }
            );
        }
    }
    
    // Classic coin flip method (fallback)
    async flipCoinClassic() {
        const setup = document.getElementById('coin-setup');
        const animation = document.getElementById('coin-animation');
        const coin = document.getElementById('coin');
        const resultText = document.getElementById('coin-result-text');
        
        setup.classList.add('d-none');
        animation.classList.remove('d-none');
        
        const theme = this.coinThemes[this.coinTheme];
        
        // Set coin faces
        const headsFace = coin.querySelector('.coin-heads');
        const tailsFace = coin.querySelector('.coin-tails');
        
        console.log('Setting coin faces:', {
            theme: theme,
            emojiDataAvailable: !!this.emojiData,
            headsEmoji: this.emojiData ? (this.emojiData[theme.heads] || theme.headsEmoji) : theme.headsEmoji,
            tailsEmoji: this.emojiData ? (this.emojiData[theme.tails] || theme.tailsEmoji) : theme.tailsEmoji
        });
        
        if (this.emojiData) {
            const headsEmoji = this.emojiData[theme.heads] || `/static/Emojis/Coins/${theme.heads}.png`;
        const tailsEmoji = this.emojiData[theme.tails] || `/static/Emojis/Coins/${theme.tails}.png`;
            
            // Check if it's an image URL (local or remote) or a Unicode emoji
            // All emojis are now image paths from the Emojis directory
            headsFace.innerHTML = `<img src="${headsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
            tailsFace.innerHTML = `<img src="${tailsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
        } else {
            // Fallback to theme emojis (which are now image paths)
            headsFace.innerHTML = `<img src="${theme.headsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
            tailsFace.innerHTML = `<img src="${theme.tailsEmoji}" style="width: 80px; height: 80px; object-fit: contain;">`;
        }
        
        // Animate coin flip
        coin.classList.add('flipping');
        
        // Call API for actual flip result
        try {
            const response = await fetch(`/api/fun/coin-flip?theme=${encodeURIComponent(this.coinTheme)}`);
            if (response.ok) {
                const result = await response.json();
                
                setTimeout(() => {
                    coin.classList.remove('flipping');
                    
                    // Show final result
                    if (result.result === 'heads') {
                        coin.style.transform = 'rotateY(0deg)';
                    } else {
                        coin.style.transform = 'rotateY(180deg)';
                    }
                    
                    resultText.innerHTML = `It landed on <strong>${result.result.toUpperCase()}</strong>!`;
                    resultText.classList.add('fade-in');
                }, 2000);
            } else {
                throw new Error('API error');
            }
        } catch (error) {
            console.error('Error calling coin flip API:', error);
            // Fallback to client-side random
            const isHeads = Math.random() < 0.5;
            const result = isHeads ? 'heads' : 'tails';
            
            setTimeout(() => {
                coin.classList.remove('flipping');
                
                // Show final result
                if (isHeads) {
                    coin.style.transform = 'rotateY(0deg)';
                } else {
                    coin.style.transform = 'rotateY(180deg)';
                }
                
                resultText.innerHTML = `It landed on <strong>${result.toUpperCase()}</strong>!`;
                resultText.classList.add('fade-in');
            }, 2000);
        }
    }
    
    resetCoin() {
        document.getElementById('coin-setup').classList.remove('d-none');
        document.getElementById('coin-animation').classList.add('d-none');
        document.getElementById('coin').style.transform = 'rotateY(0deg)';
        document.getElementById('coin-result-text').classList.remove('fade-in');
        this.coinTheme = null;
        document.querySelectorAll('.coin-theme-btn').forEach(b => b.classList.remove('active'));
    }
    
    // Helper method to get dice face content
    getDiceFace(value, color) {
        const emojiName = `${color}${value}`;
        if (this.emojiData && this.emojiData[emojiName]) {
            const emoji = this.emojiData[emojiName];
            if (emoji.includes('.png') || emoji.includes('/')) {
                return `<img src="${emoji}" style="width: 70px; height: 70px; object-fit: contain;">`;
            } else {
                return emoji;
            }
        } else {
            return value;
        }
    }
    
    // Dice Roll Methods
    checkDiceReady() {
        if (this.diceColor && this.diceAmount) {
            document.getElementById('roll-dice-btn').disabled = false;
        }
    }
    
    async rollDice() {
        const setup = document.getElementById('dice-setup');
        const animation = document.getElementById('dice-animation');
        const container = document.getElementById('dice-container');
        const resultText = document.getElementById('dice-result-text');
        
        setup.classList.add('d-none');
        animation.classList.remove('d-none');
        
        container.innerHTML = '';
        
        // Call API for dice roll
        try {
            const response = await fetch(`/api/fun/dice-roll?color=${encodeURIComponent(this.diceColor)}&amount=${this.diceAmount}`);
            if (response.ok) {
                const result = await response.json();
                
                console.log('Dice API response:', result);
                
                // Create dice with API results
                result.rolls.forEach((roll, index) => {
                    console.log('Processing dice roll:', roll);
                    const dice = document.createElement('div');
                    dice.className = 'dice rolling';
                    
                    const face = document.createElement('div');
                    face.className = 'dice-face';
                    
                    // Start with random face for rolling effect
                    const startValue = Math.floor(Math.random() * 6) + 1;
                    face.innerHTML = this.getDiceFace(startValue, this.diceColor);
                    
                    dice.appendChild(face);
                    container.appendChild(dice);
                    
                    // Cycle through faces during rolling
                    let rollCount = 0;
                    const rollInterval = setInterval(() => {
                        rollCount++;
                        const currentValue = Math.floor(Math.random() * 6) + 1;
                        face.innerHTML = this.getDiceFace(currentValue, this.diceColor);
                        
                        if (rollCount >= 8) { // Show 8 different faces during roll
                            clearInterval(rollInterval);
                            // Show final result
                            if (roll.emoji) {
                                if (roll.emoji.includes('.png') || roll.emoji.includes('/')) {
                                    face.innerHTML = `<img src="${roll.emoji}" style="width: 70px; height: 70px; object-fit: contain;">`;
                                } else {
                                    face.innerHTML = roll.emoji;
                                }
                            } else {
                                face.innerHTML = roll.value;
                            }
                        }
                    }, 150);
                    
                    // Stagger animation - wait for face cycling to complete
                setTimeout(() => {
                    dice.classList.remove('rolling');
                    // Add bounce effect
                    dice.style.transform = 'scale(1.1)';
                    setTimeout(() => {
                        dice.style.transform = 'scale(0.95)';
                        setTimeout(() => {
                            dice.style.transform = 'scale(1)';
                        }, 100);
                    }, 100);
                }, 1500 + (index * 200) + 1200); // Extra 1200ms for face cycling (8 * 150ms)
                });
                
                // Show result after all dice have finished cycling faces
                setTimeout(() => {
                    const rollValues = result.rolls.map(r => r.value);
                    resultText.innerHTML = `You rolled: ${rollValues.join(', ')}<br><strong>Total: ${result.total}</strong>`;
                    resultText.classList.add('fade-in');
                }, 1500 + (result.rolls.length * 200) + 1200); // Extra 1200ms for face cycling
            } else {
                throw new Error('API error');
            }
        } catch (error) {
            console.error('Error calling dice roll API:', error);
            console.log('Falling back to client-side dice roll with local emoji data');
            // Fallback to client-side random
            const rolls = [];
            for (let i = 0; i < this.diceAmount; i++) {
                const roll = Math.floor(Math.random() * 6) + 1;
                rolls.push(roll);
                
                const dice = document.createElement('div');
                dice.className = 'dice rolling';
                
                const face = document.createElement('div');
                face.className = 'dice-face';
                
                // Start with random face for rolling effect
                const startValue = Math.floor(Math.random() * 6) + 1;
                face.innerHTML = this.getDiceFace(startValue, this.diceColor);
                
                dice.appendChild(face);
                container.appendChild(dice);
                
                // Cycle through faces during rolling
                let rollCount = 0;
                const rollInterval = setInterval(() => {
                    rollCount++;
                    const currentValue = Math.floor(Math.random() * 6) + 1;
                    face.innerHTML = this.getDiceFace(currentValue, this.diceColor);
                    
                    if (rollCount >= 8) { // Show 8 different faces during roll
                        clearInterval(rollInterval);
                        // Show final result
                        face.innerHTML = this.getDiceFace(roll, this.diceColor);
                    }
                }, 150);
                
                // Stagger animation
                setTimeout(() => {
                    dice.classList.remove('rolling');
                    // Add bounce effect
                    dice.style.transform = 'scale(1.1)';
                    setTimeout(() => {
                        dice.style.transform = 'scale(0.95)';
                        setTimeout(() => {
                            dice.style.transform = 'scale(1)';
                        }, 100);
                    }, 100);
                }, 1500 + (i * 200) + 1200); // Extra 1200ms for face cycling
            }
            
            // Show result after all dice have finished cycling faces
            setTimeout(() => {
                const total = rolls.reduce((a, b) => a + b, 0);
                resultText.innerHTML = `You rolled: ${rolls.join(', ')}<br><strong>Total: ${total}</strong>`;
                resultText.classList.add('fade-in');
            }, 1500 + (this.diceAmount * 200) + 1200); // Extra 1200ms for face cycling
        }
    }
    
    resetDice() {
        document.getElementById('dice-setup').classList.remove('d-none');
        document.getElementById('dice-animation').classList.add('d-none');
        document.getElementById('dice-result-text').classList.remove('fade-in');
        this.diceColor = null;
        this.diceAmount = null;
        document.getElementById('roll-dice-btn').disabled = true;
        document.querySelectorAll('.dice-color-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.dice-amount-btn').forEach(b => b.classList.remove('active'));
    }
    
    // Card Draw Methods
    async drawCards() {
        const setup = document.getElementById('card-setup');
        const animation = document.getElementById('card-animation');
        const drawnCards = document.getElementById('drawn-cards');
        const resultText = document.getElementById('card-result-text');
        
        setup.classList.add('d-none');
        animation.classList.remove('d-none');
        
        drawnCards.innerHTML = '';
        
        // Call API for card draw
        try {
            const response = await fetch(`/api/fun/card-draw?count=${this.cardAmount}`);
            if (response.ok) {
                const result = await response.json();
                
                // Draw cards with API results
                result.cards.forEach((card, index) => {
                    setTimeout(() => {
                        console.log('Drawing card from API:', {
                            card: card.card,
                            suit: card.suit,
                            emojiDataAvailable: !!this.emojiData,
                            emojiFound: this.emojiData ? this.emojiData[card.card] : 'not found'
                        });
                        
                        const cardElement = document.createElement('div');
                        cardElement.className = `playing-card ${this.getCardColor(card.card)} drawing`;
                        
                        // Get card value
                        let value = card.card.substring(1);
                        if (value === 'J') value = 'J';
                        else if (value === 'Q') value = 'Q';
                        else if (value === 'K') value = 'K';
                        else if (value === 'LJ') value = '🃏';
                        else if (value === 'BJ') value = '🃏';
                        
                        // Get emoji if available
                        if (this.emojiData && this.emojiData[card.card]) {
                            const emoji = this.emojiData[card.card] || `/static/Emojis/Cards/${card.card}.png`;
                            cardElement.innerHTML = `<img src="${emoji}" style="width: 50px; height: 50px; object-fit: contain;">`;
                        } else {
                            const symbol = this.getCardSymbol(card.suit);
                            cardElement.innerHTML = `${value}<br><small>${symbol}</small>`;
                        }
                        
                        drawnCards.appendChild(cardElement);
                    }, index * 300);
                });
                
                // Show result
                setTimeout(() => {
                    const cardNames = result.cards.map(card => {
                        let name = card.card;
                        if (name.startsWith('H')) return name.replace('H', '♥️');
                        if (name.startsWith('D')) return name.replace('D', '♦️');
                        if (name.startsWith('C')) return name.replace('C', '♣️');
                        if (name.startsWith('S')) return name.replace('S', '♠️');
                        return name;
                    });
                    
                    resultText.innerHTML = `You drew ${this.cardAmount} card${this.cardAmount > 1 ? 's' : ''}:<br><strong>${cardNames.join(', ')}</strong>`;
                    resultText.classList.add('fade-in');
                }, result.cards.length * 300 + 500);
            } else {
                throw new Error('API error');
            }
        } catch (error) {
            console.error('Error calling card draw API:', error);
            console.log('Falling back to client-side card draw with local emoji data');
            // Fallback to client-side random
            this.drawCardsFallback();
        }
    }
    
    getCardColor(cardName) {
        if (cardName.startsWith('H') || cardName.startsWith('D')) return 'red';
        return 'black';
    }
    
    getCardSymbol(suit) {
        const symbols = {
            'Hearts': '♥️',
            'Diamonds': '♦️',
            'Clubs': '♣️',
            'Spades': '♠️',
            'Jokers': '🃏'
        };
        return symbols[suit] || '';
    }
    
    testEmojiData() {
        console.log('Testing emoji data...');
        console.log('Emoji data available:', !!this.emojiData);
        if (this.emojiData) {
            console.log('Testing dice emojis:');
            ['Red', 'Blue', 'Green'].forEach(color => {
                for (let i = 1; i <= 6; i++) {
                    const emojiName = `${color}${i}`;
                    const emoji = this.emojiData[emojiName];
                    console.log(`${emojiName}:`, emoji || 'NOT FOUND');
                }
            });
            
            console.log('Testing card emojis:');
            ['H1', 'D1', 'C1', 'S1', 'HJ', 'HQ', 'HK'].forEach(card => {
                const emoji = this.emojiData[card];
                console.log(`${card}:`, emoji || 'NOT FOUND');
            });
        }
    }
    
    drawCardsFallback() {
        const drawnCards = document.getElementById('drawn-cards');
        const resultText = document.getElementById('card-result-text');
        
        // Get all available cards
        const allCards = [];
        Object.keys(this.cardSuits).forEach(suit => {
            this.cardSuits[suit].cards.forEach(card => {
                allCards.push({ card, suit, ...this.cardSuits[suit] });
            });
        });
        
        // Shuffle and draw
        const shuffled = allCards.sort(() => 0.5 - Math.random());
        const drawn = shuffled.slice(0, this.cardAmount);
        
        drawn.forEach((card, index) => {
            setTimeout(() => {
                console.log('Drawing fallback card:', {
                    card: card.card,
                    suit: card.suit,
                    emojiDataAvailable: !!this.emojiData,
                    emojiFound: this.emojiData ? this.emojiData[card.card] : 'not available'
                });
                
                const cardElement = document.createElement('div');
                cardElement.className = `playing-card ${card.color} drawing`;
                
                // Get card value
                let value = card.card.substring(1);
                if (value === 'J') value = 'J';
                else if (value === 'Q') value = 'Q';
                else if (value === 'K') value = 'K';
                else if (value === 'LJ') value = '🃏';
                else if (value === 'BJ') value = '🃏';
                
                // Get emoji if available
                if (this.emojiData && this.emojiData[card.card]) {
                    const emoji = this.emojiData[card.card];
                    // All emojis are now image paths from the Emojis directory
                    cardElement.innerHTML = `<img src="${emoji}" style="width: 40px; height: 40px; object-fit: contain;">`;
                } else {
                    cardElement.innerHTML = `${value}<br><small>${card.symbol}</small>`;
                }
                
                drawnCards.appendChild(cardElement);
            }, index * 300);
        });
        
        // Show result
        setTimeout(() => {
            const cardNames = drawn.map(card => {
                let name = card.card;
                if (name.startsWith('H')) return name.replace('H', '♥️');
                if (name.startsWith('D')) return name.replace('D', '♦️');
                if (name.startsWith('C')) return name.replace('C', '♣️');
                if (name.startsWith('S')) return name.replace('S', '♠️');
                return name;
            });
            
            resultText.innerHTML = `You drew ${this.cardAmount} card${this.cardAmount > 1 ? 's' : ''}:<br><strong>${cardNames.join(', ')}</strong>`;
            resultText.classList.add('fade-in');
        }, this.cardAmount * 300 + 500);
    }
    
    resetCards() {
        document.getElementById('card-setup').classList.remove('d-none');
        document.getElementById('card-animation').classList.add('d-none');
        document.getElementById('card-result-text').classList.remove('fade-in');
        this.cardAmount = null;
        document.getElementById('draw-cards-btn').disabled = true;
        document.querySelectorAll('.card-amount-btn').forEach(b => b.classList.remove('active'));
    }
    
    // Rock Paper Scissors Methods
    showThemeSelection() {
        document.getElementById('rps-choices-div').classList.add('d-none');
        document.getElementById('rps-theme-selection').classList.remove('d-none');
    }
    
    hideThemeSelection() {
        document.getElementById('rps-theme-selection').classList.add('d-none');
        document.getElementById('rps-choices-div').classList.remove('d-none');
    }
    
    changeRPSTheme(newTheme) {
        this.rpsTheme = newTheme;
        this.updateRPSTheme();
        this.hideThemeSelection();
    }

    updateRPSTheme() {
        const gameDiv = document.getElementById('rps-game');
        if (gameDiv) {
            gameDiv.className = `rps-game rps-theme-${this.rpsTheme.toLowerCase()}`;
        }

        const choices = {
            Traditional: [
                { name: 'Rock', choice: 'rock_1', beats: 'Scissors', emoji: 'rock_1.png' },
                { name: 'Paper', choice: 'paper', beats: 'Rock', emoji: 'paper.png' },
                { name: 'Scissors', choice: 'scissor', beats: 'Paper', emoji: 'scissor.png' },
            ],
            Fantasy: [
                { name: 'Knight', choice: 'knights', beats: 'Archer', emoji: 'knights.png' },
                { name: 'Archer', choice: 'archer', beats: 'Necromancer', emoji: 'archer.png' },
                { name: 'Necromancer', choice: 'necromancer', beats: 'Knight', emoji: 'necromancer.png' },
            ],
            War: [
                { name: 'Tank', choice: 'tank', beats: 'Ship', emoji: 'tank.png' },
                { name: 'Jet', choice: 'jet', beats: 'Tank', emoji: 'jet.png' },
                { name: 'Ship', choice: 'ship', beats: 'Jet', emoji: 'ship.png' },
            ],
        };

        const themeChoices = choices[this.rpsTheme];
        if (themeChoices) {
            const choiceButtons = document.querySelectorAll('.rps-choice-btn');
            choiceButtons.forEach((btn, index) => {
                if (index < themeChoices.length) {
                    const choiceData = themeChoices[index];
                    try {
                        btn.dataset.choice = choiceData.choice;
                        
                        const nameElement = btn.querySelector('small');
                        if (nameElement) nameElement.textContent = choiceData.name;
                        
                        const beatsElement = btn.querySelector('.beats-text');
                        if (beatsElement) beatsElement.textContent = `Beats ${choiceData.beats}`;
                        
                        const imgElement = btn.querySelector('img');
                        if (imgElement) imgElement.src = `/static/Emojis/RPS/${choiceData.emoji}`;
                        
                        // Enable the button
                        btn.disabled = false;
                        btn.style.pointerEvents = 'auto';
                        btn.style.opacity = '1';
                    } catch (error) {
                        console.error('Error updating choice button:', error);
                    }
                }
            });
        }
    }
    
    checkRPSReady() {
        if (this.rpsTheme) {
            document.getElementById('start-rps-btn').disabled = false;
        }
    }
    
    startRPSGame() {
        this.rpsPlayerScore = 0;
        this.rpsAiScore = 0;
        this.rpsPlayerHistory = [];
        
        document.getElementById('rps-setup').classList.add('d-none');
        document.getElementById('rps-game').classList.remove('d-none');
        
        // Ensure theme is applied
        this.updateRPSTheme();
        
        this.updateRPSScore();
        this.nextRPSRound();
    }
    
    nextRPSRound() {
        document.getElementById('rps-round-result').innerHTML = `Choose your move!`;
        
        // Show choices div
        document.getElementById('rps-choices-div').classList.remove('d-none');

        // Enable choice buttons and ensure they're clickable
        document.querySelectorAll('.rps-choice-btn').forEach((btn, index) => {
            btn.disabled = false;
            btn.style.pointerEvents = 'auto';
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
            console.log(`Choice button ${index} enabled with choice:`, btn.dataset.choice);
        });
        
        // Hide arena and reset animations
        const arena = document.getElementById('rps-arena');
        arena.classList.add('d-none');
        arena.classList.remove('show-result', 'battle-impact', 'battle-collision');
        
        // Clear winner/loser classes
        const playerAnimation = document.querySelector('.rps-player-choice-animation');
        const aiAnimation = document.querySelector('.rps-ai-choice-animation');
        playerAnimation.classList.remove('winner', 'loser', 'tie');
        aiAnimation.classList.remove('winner', 'loser', 'tie');
        
        // Hide action buttons
        document.getElementById('rps-result-actions').classList.add('d-none');
        
        console.log('RPS round started, buttons should be clickable');
    }
    
    resetRPSRound() {
        console.log('Resetting current RPS round');
        
        // Clear the current round result but keep scores
        this.nextRPSRound();
    }
    
    async makeRPSMove(playerChoice) {
        console.log('makeRPSMove called with choice:', playerChoice);

        document.getElementById('rps-choices-div').classList.add('d-none');

        document.querySelectorAll('.rps-choice-btn').forEach(btn => {
            btn.disabled = true;
        });

        const arena = document.getElementById('rps-arena');
        const playerAnimation = document.querySelector('.rps-player-choice-animation');
        const aiAnimation = document.querySelector('.rps-ai-choice-animation');

        playerAnimation.style.backgroundImage = `url(/static/Emojis/RPS/${this.getChoiceEmoji(playerChoice)})`;
        arena.classList.remove('d-none');

        try {
            const response = await fetch('/api/fun/rps-play', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    theme: this.rpsTheme,
                    playerChoice: playerChoice,
                    playerHistory: this.rpsPlayerHistory
                })
            });

            if (response.ok) {
                const result = await response.json();
                aiAnimation.style.backgroundImage = `url(/static/Emojis/RPS/${this.getChoiceEmoji(result.aiChoice)})`;
                
                if (this.gsapAvailable) {
                    // Use enhanced GSAP animations
                    await this.animateRPSFightEnhanced(playerChoice, result.aiChoice, result.winner);
                    this.processRPSResultEnhanced(result, playerChoice);
                } else {
                    // Fallback to original CSS animations
                    this.processRPSResult(result, playerChoice, playerAnimation, aiAnimation);
                }
            } else {
                throw new Error('API error');
            }
        } catch (error) {
            console.error('Error calling RPS API:', error);
            this.processRPSResultFallback(playerChoice);
        }
    }

    processRPSResult(result, playerChoice, playerAnimation, aiAnimation) {
        this.rpsPlayerHistory.push(playerChoice);

        setTimeout(() => {
            let resultText = '';
            const arena = document.getElementById('rps-arena');
            
            if (result.winner === 'player') {
                this.rpsPlayerScore++;
                resultText = `You win! ${this.getChoiceDisplayName(playerChoice)} beats ${this.getChoiceDisplayName(result.aiChoice)}`;
                playerAnimation.classList.add('winner');
                aiAnimation.classList.add('loser');
            } else if (result.winner === 'ai') {
                this.rpsAiScore++;
                resultText = `AI wins! ${this.getChoiceDisplayName(result.aiChoice)} beats ${this.getChoiceDisplayName(playerChoice)}`;
                aiAnimation.classList.add('winner');
                playerAnimation.classList.add('loser');
            } else {
                resultText = `It's a tie!`;
                playerAnimation.classList.add('tie');
                aiAnimation.classList.add('tie');
            }

            // Add battle impact and collision effects
            arena.classList.add('battle-impact', 'battle-collision');
            
            document.getElementById('rps-round-result').innerHTML = resultText;
            this.updateRPSScore();

            // Show result text and action buttons
            arena.classList.add('show-result');
            
            // Show action buttons
            document.getElementById('rps-result-actions').classList.remove('d-none');

            // Don't automatically continue - wait for user action
            // The winner will stay in the center until Play Again or Reset is clicked
        }, 1800); // Wait for dancing and collision animation to complete
    }
    
    async processRPSResultFallback(playerChoice) {
        // Enhanced fallback logic with GSAP animations
        const choices = this.getRPSChoices();
        const aiChoice = choices[Math.floor(Math.random() * choices.length)];
        
        this.rpsPlayerHistory.push(playerChoice);
        
        let result = this.getRPSWinner(playerChoice, aiChoice);
        
        const arena = document.getElementById('rps-arena');
        const playerAnimation = document.querySelector('.rps-player-choice-animation');
        const aiAnimation = document.querySelector('.rps-ai-choice-animation');
        
        // Set AI choice image for animation
        aiAnimation.style.backgroundImage = `url(/static/Emojis/RPS/${this.getChoiceEmoji(aiChoice)})`;
        
        if (this.gsapAvailable) {
            // Use enhanced GSAP animations for fallback
            await this.animateRPSFightEnhanced(playerChoice, aiChoice, result);
            this.processRPSResultEnhanced({ winner: result, aiChoice: aiChoice }, playerChoice);
        } else {
            // Fallback to original CSS animations
            this.processRPSResult({ winner: result, aiChoice: aiChoice }, playerChoice, playerAnimation, aiAnimation);
        }
    }
    
    getRPSChoices() {
        const themes = {
            'Traditional': ['rock', 'paper', 'scissors'],
            'Fantasy': ['knights', 'archer', 'necromancer'],
            'War': ['tank', 'jet', 'ship']
        };
        return themes[this.rpsTheme] || ['rock', 'paper', 'scissors'];
    }
    
    getRPSWinner(player, ai) {
        if (player === ai) return 'tie';
        
        const beats = {
            'rock': 'scissors',
            'paper': 'rock',
            'scissors': 'paper',
            'knights': 'archer',
            'archer': 'necromancer',
            'necromancer': 'knights',
            'tank': 'ship',
            'jet': 'tank',
            'ship': 'jet'
        };
        
        return beats[player] === ai ? 'player' : 'ai';
    }

    getChoiceDisplayName(choice) {
        const choiceNames = {
            'rock_1': 'Rock',
            'paper': 'Paper', 
            'scissor': 'Scissors',
            'knights': 'Knight',
            'archer': 'Archer',
            'necromancer': 'Necromancer',
            'tank': 'Tank',
            'jet': 'Jet',
            'ship': 'Ship'
        };
        return choiceNames[choice] || choice;
    }

    getChoiceEmoji(choice) {
        const choices = {
            rock_1: 'rock_1.png',
            paper: 'paper.png',
            scissor: 'scissor.png',
            knights: 'knights.png',
            archer: 'archer.png',
            necromancer: 'necromancer.png',
            tank: 'tank.png',
            jet: 'jet.png',
            ship: 'ship.png',
        };
        return choices[choice] || '';
    }
    
    updateRPSScore() {
        document.getElementById('player-score').textContent = `Player: ${this.rpsPlayerScore}`;
        document.getElementById('ai-score').textContent = `AI: ${this.rpsAiScore}`;
    }
    

    
    resetRPS() {
        document.getElementById('rps-setup').classList.remove('d-none');
        document.getElementById('rps-game').classList.add('d-none');
        
        this.rpsTheme = null;
        this.rpsPlayerScore = 0;
        this.rpsAiScore = 0;
        this.rpsPlayerHistory = [];
        
        document.getElementById('start-rps-btn').disabled = true;
        document.querySelectorAll('.rps-theme-btn').forEach(b => b.classList.remove('active'));
        
        // Clear any remaining animation states
        const arena = document.getElementById('rps-arena');
        arena.classList.add('d-none');
        arena.classList.remove('show-result', 'battle-impact', 'battle-collision');
        
        const playerAnimation = document.querySelector('.rps-player-choice-animation');
        const aiAnimation = document.querySelector('.rps-ai-choice-animation');
        if (playerAnimation) playerAnimation.classList.remove('winner', 'loser', 'tie');
        if (aiAnimation) aiAnimation.classList.remove('winner', 'loser', 'tie');
        
        document.getElementById('rps-result-actions').classList.add('d-none');
    }
    
    processRPSResultEnhanced(result, playerChoice) {
        this.rpsPlayerHistory.push(playerChoice);
        
        let resultText = '';
        const arena = document.getElementById('rps-arena');
        
        if (result.winner === 'player') {
            this.rpsPlayerScore++;
            resultText = `🎉 You win! ${this.getChoiceDisplayName(playerChoice)} beats ${this.getChoiceDisplayName(result.aiChoice)}`;
        } else if (result.winner === 'ai') {
            this.rpsAiScore++;
            resultText = `🤖 AI wins! ${this.getChoiceDisplayName(result.aiChoice)} beats ${this.getChoiceDisplayName(playerChoice)}`;
        } else {
            resultText = `🤝 It's a tie! Both chose ${this.getChoiceDisplayName(playerChoice)}`;
        }
        
        // Show result with enhanced styling
        document.getElementById('rps-round-result').innerHTML = resultText;
        this.updateRPSScore();
        
        // Add visual effects to the arena
        arena.classList.add('show-result');
        
        // Show action buttons
        document.getElementById('rps-result-actions').classList.remove('d-none');
    }
    
    // Enhanced GSAP Animation Methods for RPS
    async animateRPSFightEnhanced(playerChoice, aiChoice, result) {
        const playerAnimation = document.querySelector('.rps-player-choice-animation');
        const aiAnimation = document.querySelector('.rps-ai-choice-animation');
        const arena = document.getElementById('rps-arena');
        
        // Reset any previous animations
        gsap.killTweensOf([playerAnimation, aiAnimation]);
        
        // Set initial positions
        gsap.set(playerAnimation, { left: 0, x: 0, y: 0, rotation: 0, scale: 1 });
        gsap.set(aiAnimation, { right: 0, x: 0, y: 0, rotation: 0, scale: 1 });
        
        // Create the fight animation timeline
        const fightTimeline = gsap.timeline();
        
        // Phase 1: Approach with circling movement (looking for advantage)
        fightTimeline
            .to(playerAnimation, {
                duration: 1.2,
                x: 120,
                y: "+=15",
                rotation: -15,
                scale: 1.1,
                ease: "power2.inOut",
                onUpdate: function() {
                    // Add subtle up/down movement during approach
                    const progress = this.progress();
                    const bobAmount = Math.sin(progress * Math.PI * 4) * 8;
                    gsap.set(playerAnimation, { y: bobAmount });
                }
            })
            .to(aiAnimation, {
                duration: 1.2,
                x: -120,
                y: "+=15",
                rotation: 15,
                scale: 1.1,
                ease: "power2.inOut",
                onUpdate: function() {
                    const progress = this.progress();
                    const bobAmount = Math.sin(progress * Math.PI * 4 + Math.PI) * 8;
                    gsap.set(aiAnimation, { y: bobAmount });
                }
            }, "<"); // Run simultaneously
        
        // Phase 2: Lunge towards center with anticipation
        fightTimeline
            .to(playerAnimation, {
                duration: 0.15,
                x: 100,
                scale: 0.9,
                rotation: -25,
                ease: "power2.in"
            }, "+=0.2") // Small pause before lunge
            .to(playerAnimation, {
                duration: 0.4,
                x: 180,
                scale: 1.3,
                rotation: -5,
                ease: "power3.out"
            })
            .to(aiAnimation, {
                duration: 0.15,
                x: -100,
                scale: 0.9,
                rotation: 25,
                ease: "power2.in"
            }, "<")
            .to(aiAnimation, {
                duration: 0.4,
                x: -180,
                scale: 1.3,
                rotation: 5,
                ease: "power3.out"
            }, "<");
        
        // Phase 3: Impact and result based on winner
        if (result === 'player') {
            // Player wins - AI flies off dramatically
            fightTimeline
                .to(aiAnimation, {
                    duration: 1.5,
                    x: 400,
                    y: -200,
                    rotation: 720,
                    scale: 0.2,
                    opacity: 0.3,
                    ease: "power4.out"
                })
                .to(playerAnimation, {
                    duration: 0.3,
                    scale: 1.4,
                    rotation: 0,
                    ease: "back.out(1.7)"
                }, "<")
                .to(playerAnimation, {
                    duration: 0.8,
                    scale: 1.2,
                    y: "+=10",
                    ease: "elastic.out(1, 0.3)"
                });
        } else if (result === 'ai') {
            // AI wins - Player flies off dramatically
            fightTimeline
                .to(playerAnimation, {
                    duration: 1.5,
                    x: -400,
                    y: -200,
                    rotation: -720,
                    scale: 0.2,
                    opacity: 0.3,
                    ease: "power4.out"
                })
                .to(aiAnimation, {
                    duration: 0.3,
                    scale: 1.4,
                    rotation: 0,
                    ease: "back.out(1.7)"
                }, "<")
                .to(aiAnimation, {
                    duration: 0.8,
                    scale: 1.2,
                    y: "+=10",
                    ease: "elastic.out(1, 0.3)"
                });
        } else {
            // Tie - both bounce back
            fightTimeline
                .to([playerAnimation, aiAnimation], {
                    duration: 0.2,
                    scale: 1.2,
                    ease: "power2.out"
                })
                .to([playerAnimation, aiAnimation], {
                    duration: 0.3,
                    x: 0,
                    scale: 1,
                    rotation: 0,
                    ease: "power2.inOut"
                })
                .to([playerAnimation, aiAnimation], {
                    duration: 0.5,
                    y: "+=5",
                    ease: "sine.inOut",
                    yoyo: true,
                    repeat: 2
                });
        }
        
        // Add particle effects for impact
        this.createImpactEffect(arena, result);
        
        return fightTimeline;
    }
    
    createImpactEffect(arena, result) {
        // Create impact particles
        const impactDiv = document.createElement('div');
        impactDiv.className = 'impact-effect';
        impactDiv.style.cssText = `
            position: absolute;
            left: 50%;
            top: 50%;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            transform: translate(-50%, -50%);
            pointer-events: none;
        `;
        
        // Set color based on result
        if (result === 'player') {
            impactDiv.style.background = 'radial-gradient(circle, var(--gold-primary), transparent)';
        } else if (result === 'ai') {
            impactDiv.style.background = 'radial-gradient(circle, var(--danger), transparent)';
        } else {
            impactDiv.style.background = 'radial-gradient(circle, var(--warning), transparent)';
        }
        
        arena.appendChild(impactDiv);
        
        // Animate the impact effect
        gsap.fromTo(impactDiv, 
            { scale: 0, opacity: 1 },
            { 
                scale: 3, 
                opacity: 0, 
                duration: 0.6,
                ease: "power2.out",
                onComplete: () => impactDiv.remove()
            }
        );
        
        // Create multiple smaller particles
        for (let i = 0; i < 8; i++) {
            const particle = document.createElement('div');
            particle.style.cssText = `
                position: absolute;
                left: 50%;
                top: 50%;
                width: 4px;
                height: 4px;
                border-radius: 50%;
                background: ${result === 'player' ? 'var(--gold-primary)' : result === 'ai' ? 'var(--danger)' : 'var(--warning)'};
                pointer-events: none;
            `;
            arena.appendChild(particle);
            
            const angle = (i / 8) * Math.PI * 2;
            const distance = 50 + Math.random() * 30;
            
            gsap.fromTo(particle,
                { x: 0, y: 0, opacity: 1, scale: 1 },
                {
                    x: Math.cos(angle) * distance,
                    y: Math.sin(angle) * distance,
                    opacity: 0,
                    scale: 0,
                    duration: 0.8,
                    ease: "power2.out",
                    delay: Math.random() * 0.2,
                    onComplete: () => particle.remove()
                }
            );
        }
        
        // Add screen shake effect for impact
        this.addScreenShake(result);
    }
    
    addScreenShake(result) {
        const arena = document.getElementById('rps-arena');
        const shakeIntensity = result === 'tie' ? 3 : 5;
        
        gsap.to(arena, {
            x: "+=5",
            duration: 0.1,
            ease: "power2.inOut",
            yoyo: true,
            repeat: 5,
            onComplete: () => gsap.set(arena, { x: 0 })
        });
        
        // Add vibration for mobile devices (if supported)
        if ('vibrate' in navigator) {
            const vibrationPattern = result === 'tie' ? 100 : [100, 50, 100];
            navigator.vibrate(vibrationPattern);
        }
    }
    
    // Slots Methods
    startSlotsGame() {
        document.getElementById('slots-setup').classList.add('d-none');
        document.getElementById('slots-game').classList.remove('d-none');
        this.prepareSlots();
    }
    
    prepareSlots() {
        const reels = document.querySelectorAll('.slots-reel');
        const theme = this.slotsTheme.replace(/ /g, '');
        const emojiCategory = this.getEmojiCategoryForTheme(theme);
        let emojis = [];
        
        // For Insanity theme, combine only emojis from other slots themes (Pets and such)
        if (Array.isArray(emojiCategory)) {
            // For Insanity theme, combine emojis from the specified categories
            for (const category of emojiCategory) {
                if (this.emojiCategories[category]) {
                    emojis = emojis.concat(this.emojiCategories[category]);
                }
            }
            
            // Ensure we have emojis from the other slots themes
            if (emojis.length === 0) {
                console.error('No emojis found for Insanity theme from other slots categories');
                return;
            }
            
            console.log(`Insanity theme loaded ${emojis.length} emojis from other slots themes:`, emojis.slice(0, 10));
        } else {
            emojis = this.emojiCategories[emojiCategory] || [];
            console.log(`${this.slotsTheme} theme loaded ${emojis.length} emojis from category: ${emojiCategory}`);
        }
        
        if (emojis.length === 0) {
            console.error(`No emojis found for category: ${emojiCategory}`);
            return;
        }

        reels.forEach(reel => {
            let reelHtml = '';
            for (let i = 0; i < 20; i++) { // Populate with 20 emojis for a good visual
                const randomEmojiName = emojis[Math.floor(Math.random() * emojis.length)];
                let emojiUrl = this.emojiData[randomEmojiName];
                    if (!emojiUrl) {
                        // Determine the correct path based on emoji type and theme
                        let basePath = '/static/Emojis/Pets/';
                        if (this.slotsTheme === 'Easy') {
                            basePath = '/static/Emojis/Military/';
                        } else if (this.slotsTheme === 'Very Easy' || this.slotsTheme === 'Medium' || this.slotsTheme === 'Hard') {
                            basePath = '/static/Emojis/Pets/Deco/';
                        } else if (this.slotsTheme === 'Insanity') {
                            // For Insanity theme, determine path based on emoji category from other slots themes
                            if (['soldier', 'tank', 'jet', 'ship'].includes(randomEmojiName)) {
                                basePath = '/static/Emojis/Military/';
                            } else if (['ATT', 'DEF', 'DEX', 'INT', 'HAP', 'ENE'].includes(randomEmojiName)) {
                                basePath = '/static/Emojis/Pets/Deco/'; // Stats emojis
                            } else if (['Air', 'Basic', 'Electric', 'Fire', 'Holy', 'Ice', 'Magic', 'Necro', 'Plant', 'Rock', 'Water', 'Psychic', 'Fighting'].includes(randomEmojiName)) {
                                basePath = '/static/Emojis/Pets/Deco/'; // Elements emojis
                            } else {
                                basePath = '/static/Emojis/Pets/'; // Default to Pets for pet emojis
                            }
                        } else if (['soldier', 'tank', 'jet', 'ship'].includes(randomEmojiName)) {
                            basePath = '/static/Emojis/Military/'; // Military units
                        }
                        emojiUrl = `${basePath}${randomEmojiName}.png`;
                    }
                reelHtml += `<img src="${emojiUrl}" style="width: 70px; height: 70px; object-fit: contain; display: block; margin-bottom: 10px;">`;
            }
            reel.innerHTML = reelHtml;
        });
    }

    getEmojiCategoryForTheme(theme) {
        const themeMap = {
            'VeryEasy': 'Pet Type',
            'Easy': 'Military',
            'Medium': 'Stats',
            'Hard': 'Elements',
            'VeryHard': 'Pets',
            'Insanity': ['Pets', 'Pet Type', 'Military', 'Stats', 'Elements'] // Corrected to return an array of categories
        };
        return themeMap[theme];
    }

    async spinSlots() {
        if (this.slotsSpinning) {
            // Stop the spinning with decision animation
            this.stopSpinningWithDecision();
            return;
        }
        
        this.slotsSpinning = true;
        const spinBtn = document.getElementById('spin-slots-btn');
        spinBtn.textContent = 'Stop Spin';
        spinBtn.classList.remove('btn-primary');
        spinBtn.classList.add('btn-danger');

        const reels = document.querySelectorAll('.slots-reel');
        const resultText = document.getElementById('slots-result-text');
        resultText.innerHTML = '';

        // Start spinning animation
        reels.forEach((reel, index) => {
            setTimeout(() => {
                reel.classList.add('spinning');
            }, index * 200);
        });

        // Store the spin result for when user stops
        try {
            const response = await fetch('/api/fun/slots-spin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme: this.slotsTheme })
            });

            if (response.ok) {
                this.pendingResult = await response.json();
            } else {
                throw new Error('API error');
            }
        } catch (error) {
            console.error('Error calling slots API:', error);
            // Fallback to client-side random
            this.pendingResult = null;
        }
    }
    
    stopSpinningWithDecision() {
        if (!this.slotsSpinning) return;
        
        const spinBtn = document.getElementById('spin-slots-btn');
        spinBtn.textContent = 'Start Spin';
        spinBtn.classList.remove('btn-danger');
        spinBtn.classList.add('btn-primary');
        
        this.stopSlotsWithDecision(this.pendingResult);
    }
    
    stopSlotsWithDecision(result) {
        const reels = document.querySelectorAll('.slots-reel');
        const finalPositions = [];
        const finalReels = result ? result.reels : [];

        reels.forEach((reel, index) => {
            setTimeout(() => {
                reel.classList.remove('spinning');
                const children = Array.from(reel.children);
                let finalEmojiData = finalReels[index] || null;
                let finalIndex = -1;

                if (finalEmojiData) {
                    const emojiPath = finalEmojiData.path;
                    finalIndex = children.findIndex(child => child.src.includes(emojiPath));
                }

                if (finalIndex === -1) {
                    finalIndex = Math.floor(Math.random() * children.length);
                }

                const target = children[finalIndex];
                const reelContainer = reel.parentElement;
                const reelContainerHeight = reelContainer.clientHeight;
                const emojiHeight = target.clientHeight;
                
                // Calculate the exact position to center the emoji
                const targetTop = target.offsetTop;
                const centerPosition = (reelContainerHeight / 2) - (emojiHeight / 2);
                const finalPosition = targetTop - centerPosition;

                // Create decision animation - back and forth before settling
                const decisionAnimation = () => {
                    // First, overshoot slightly
                    reel.style.transition = 'transform 0.3s ease-out';
                    reel.style.transform = `translateY(-${finalPosition - 10}px)`;
                    
                    setTimeout(() => {
                        // Then go back a bit
                        reel.style.transform = `translateY(-${finalPosition + 5}px)`;
                        
                        setTimeout(() => {
                            // Finally settle in the center
                            reel.style.transition = 'transform 0.4s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
                            reel.style.transform = `translateY(-${finalPosition}px)`;
                            
                            // Add a small bounce effect after landing
                            setTimeout(() => {
                                reel.style.transition = 'transform 0.2s ease-out';
                                reel.style.transform = `translateY(-${finalPosition - 3}px)`;
                                setTimeout(() => {
                                    reel.style.transform = `translateY(-${finalPosition}px)`;
                                }, 200);
                            }, 400);
                        }, 300);
                    }, 300);
                };
                
                // Start the decision animation
                decisionAnimation();
                
                finalPositions.push(children[finalIndex].src);

                if (index === reels.length - 1) {
                    this.checkSlotsResult(result, finalPositions);
                }
            }, index * 600); // Slightly longer delay for decision animation
        });
    }
    
    stopSpinning() {
        if (!this.slotsSpinning) return;
        
        const spinBtn = document.getElementById('spin-slots-btn');
        spinBtn.textContent = 'Start Spin';
        spinBtn.classList.remove('btn-danger');
        spinBtn.classList.add('btn-primary');
        
        this.stopSlots(this.pendingResult);
    }

    stopSlots(result) {
        const reels = document.querySelectorAll('.slots-reel');
        const finalPositions = [];
        const finalReels = result ? result.reels : [];

        reels.forEach((reel, index) => {
            setTimeout(() => {
                reel.classList.remove('spinning');
                const children = Array.from(reel.children);
                let finalEmojiData = finalReels[index] || null;
                let finalIndex = -1;

                if (finalEmojiData) {
                    const emojiPath = finalEmojiData.path;
                    finalIndex = children.findIndex(child => child.src.includes(emojiPath));
                }

                if (finalIndex === -1) {
                    finalIndex = Math.floor(Math.random() * children.length);
                }

                const target = children[finalIndex];
                const reelContainer = reel.parentElement;
                const reelContainerHeight = reelContainer.clientHeight;
                const emojiHeight = target.clientHeight;
                
                // Calculate the exact position to center the emoji
                const targetTop = target.offsetTop;
                const centerPosition = (reelContainerHeight / 2) - (emojiHeight / 2);
                const finalPosition = targetTop - centerPosition;

                // Add a subtle bounce animation when stopping
                reel.style.transition = 'transform 0.8s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
                reel.style.transform = `translateY(-${finalPosition}px)`;
                
                // Add a small bounce effect after landing
                setTimeout(() => {
                    reel.style.transition = 'transform 0.2s ease-out';
                    reel.style.transform = `translateY(-${finalPosition - 5}px)`;
                    setTimeout(() => {
                        reel.style.transform = `translateY(-${finalPosition}px)`;
                    }, 200);
                }, 800);
                
                finalPositions.push(children[finalIndex].src);

                if (index === reels.length - 1) {
                    this.checkSlotsResult(result, finalPositions);
                }
            }, index * 500);
        });
    }

    checkSlotsResult(result, finalPositions) {
        const resultText = document.getElementById('slots-result-text');
        
        if (result) {
            resultText.innerHTML = `<strong>${result.result_text}</strong>`;
        } else {
            const allSame = finalPositions.every(val => val === finalPositions[0]);
            const twoSame = new Set(finalPositions).size === 2;

            if (allSame) {
                resultText.innerHTML = '<strong>JACKPOT! 3 in a row!</strong>';
            } else if (twoSame) {
                resultText.innerHTML = '<strong>WIN! 2 in a row!</strong>';
            } else {
                resultText.innerHTML = 'Better luck next time!';
            }
        }

        // Show final combination odds if available
        if (this.slotsOdds && this.slotsTheme) {
            const odds = this.slotsOdds[this.slotsTheme];
            if (odds) {
                setTimeout(() => {
                    resultText.innerHTML += `<br><small class="text-muted" style="opacity: 0.8;">Odds: ${odds.three_match_odds} (3-match) | ${odds.two_match_odds} (2-match)</small>`;
                }, 1000);
            }
        }

        document.getElementById('spin-slots-btn').classList.add('d-none');
        document.getElementById('slots-play-again').classList.remove('d-none');
        this.slotsSpinning = false;
    }

    resetSlots() {
        document.getElementById('slots-setup').classList.remove('d-none');
        document.getElementById('slots-game').classList.add('d-none');
        
        const spinBtn = document.getElementById('spin-slots-btn');
        spinBtn.classList.remove('d-none');
        spinBtn.textContent = 'Start Spin';
        spinBtn.classList.remove('btn-danger');
        spinBtn.classList.add('btn-primary');

        document.getElementById('slots-play-again').classList.add('d-none');
        document.getElementById('slots-result-text').innerHTML = '';
        this.slotsTheme = null;
        this.slotsSpinning = false;
        this.pendingResult = null;
        document.querySelectorAll('.slots-theme-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('start-slots-btn').disabled = true;
    }

    // Slots odds methods
    async loadSlotsOdds() {
        try {
            const response = await fetch('/api/fun/slots-odds');
            if (response.ok) {
                this.slotsOdds = await response.json();
            }
        } catch (error) {
            console.error('Error loading slots odds:', error);
            // Fallback odds
            this.slotsOdds = {
                "Very Easy": {"total_emojis": 3, "three_match_odds": "1 in 9", "two_match_odds": "1 in 3"},
                "Easy": {"total_emojis": 4, "three_match_odds": "1 in 16", "two_match_odds": "1 in 4"},
                "Medium": {"total_emojis": 6, "three_match_odds": "1 in 36", "two_match_odds": "1 in 6"},
                "Hard": {"total_emojis": 13, "three_match_odds": "1 in 169", "two_match_odds": "1 in 13"},
                "Very Hard": {"total_emojis": 95, "three_match_odds": "1 in 9,025", "two_match_odds": "1 in 95"},
                "Insanity": {"total_emojis": "100+", "three_match_odds": "1 in 10,000+", "two_match_odds": "1 in 100+"}
            };
        }
    }

    updateSlotsOdds() {
        if (!this.slotsOdds || !this.slotsTheme) return;
        
        const odds = this.slotsOdds[this.slotsTheme];
        if (odds) {
            const oddsInfo = document.getElementById('slots-odds-info');
            oddsInfo.innerHTML = `Odds: ${odds.three_match_odds} (3-match) | ${odds.two_match_odds} (2-match)`;
        }
    }
}

// This function will be called from the main dashboard
window.initializeFun = async () => {
    if (!window.funFeaturesInstance) {
        console.log("Initializing Fun page features...");
        window.funFeaturesInstance = new FunFeatures();
        await window.funFeaturesInstance.init();
        console.log("Fun page features initialized with emoji data.");
    } else {
        console.log("Fun page features already initialized.");
    }
};

// Self-initialize if the page is loaded directly
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.initializeFun);
} else {
    // If loaded dynamically, dashboard.html will call initializeFun()
    window.initializeFun();
}