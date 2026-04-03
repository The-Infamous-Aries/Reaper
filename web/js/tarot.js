// CRYSTAL BALL IMPLEMENTATION - Enhanced Version

class CrystalBall {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.animationId = null;
        this.skullEmojis = [];
        this.currentSkullIndex = 0;
        this.time = 0;
        this.particles = [];
        
        // Don't call init() here - let it be called after DOM is ready
        console.log('CrystalBall constructor called');
    }
    
    async init() {
        console.log('Enhanced CrystalBall.init() called');
        try {
            // DOM should already be ready when this is called
            await this.initializeComponents();
        } catch (error) {
            console.error('Crystal Ball initialization failed:', error);
            this.showEnhancedFallback();
        }
    }
    
    async initializeComponents() {
        console.log('Initializing crystal ball components...');
        
        // Check if canvas element exists
        const canvas = document.getElementById('crystal-canvas');
        if (!canvas) {
            console.error('Canvas element not found!');
            this.showEnhancedFallback();
            return;
        }
        
        await this.loadSkullEmojis();
        this.setupCanvas();
        this.createParticles();
        this.animate();
        
        // Change skull every 5 seconds
        setInterval(() => this.changeSkull(), 5000);
        
        console.log('Crystal ball initialization completed successfully');
    }
    
    async loadSkullEmojis() {
        console.log('Starting to load skull emojis...');
        
        // Load all skull emoji images with better error handling
        const skullPromises = [];
        for (let i = 1; i <= 16; i++) {
            const imagePath = `/static/Emojis/Skulls/${i}.png`;
            console.log(`Loading skull emoji: ${imagePath}`);
            skullPromises.push(this.loadImageSafely(imagePath));
        }
        
        try {
            const results = await Promise.allSettled(skullPromises);
            console.log('Skull emoji loading results:', results.map(r => r.status));
            
            this.skullEmojis = results
                .filter(result => result.status === 'fulfilled' && result.value)
                .map(result => result.value);
            
            if (this.skullEmojis.length === 0) {
                console.warn('No skull emojis loaded, using fallback');
                this.skullEmojis = [this.createFallbackSkull()];
            } else {
                console.log(`Successfully loaded ${this.skullEmojis.length} skull emojis`);
            }
        } catch (error) {
            console.error('Error loading skull emojis:', error);
            this.skullEmojis = [this.createFallbackSkull()];
        }
        
        // Ensure we have at least one skull emoji
        if (this.skullEmojis.length === 0) {
            this.skullEmojis = [this.createFallbackSkull()];
        }
        
        console.log('Final skull emoji count:', this.skullEmojis.length);
    }
    
    loadImageSafely(src) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            
            // Set a timeout for image loading
            const timeout = setTimeout(() => {
                console.warn(`Image load timeout for: ${src}`);
                reject(new Error('Image load timeout'));
            }, 10000); // Increased timeout to 10 seconds
            
            img.onload = () => {
                clearTimeout(timeout);
                // Verify the image has valid dimensions
                if (img.width > 0 && img.height > 0) {
                    console.log(`Successfully loaded image: ${src} (${img.width}x${img.height})`);
                    resolve(img);
                } else {
                    console.warn(`Image has invalid dimensions: ${src}`);
                    reject(new Error('Image has invalid dimensions'));
                }
            };
            
            img.onerror = () => {
                clearTimeout(timeout);
                console.warn(`Failed to load image: ${src}`);
                reject(new Error('Image load error'));
            };
            
            img.onabort = () => {
                clearTimeout(timeout);
                console.warn(`Image load aborted: ${src}`);
                reject(new Error('Image load aborted'));
            };
            
            // Start loading
            console.log(`Starting to load image: ${src}`);
            img.src = src;
        });
    }
    
    createFallbackSkull() {
        const canvas = document.createElement('canvas');
        canvas.width = 64;
        canvas.height = 64;
        const ctx = canvas.getContext('2d');
        
        // Draw a simple skull
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, 64, 64);
        ctx.fillStyle = '#000000';
        ctx.fillRect(20, 15, 8, 8); // Left eye
        ctx.fillRect(36, 15, 8, 8); // Right eye
        ctx.fillRect(24, 30, 16, 4); // Nose
        ctx.fillRect(16, 40, 32, 4); // Mouth
        
        return canvas;
    }
    
    setupCanvas() {
        const container = document.getElementById('crystal-ball-container');
        this.canvas = document.getElementById('crystal-canvas');
        
        if (!this.canvas) {
            console.error('Canvas element not found in setupCanvas!');
            throw new Error('Canvas element not found');
        }
        
        this.ctx = this.canvas.getContext('2d');
        
        if (!this.ctx) {
            console.error('Could not get 2D context from canvas!');
            throw new Error('Canvas 2D context not available');
        }
        
        // Set canvas size
        this.canvas.width = 120;
        this.canvas.height = 120;
        
        console.log('Canvas setup completed:', this.canvas.width, 'x', this.canvas.height);
        
        // Create radial gradient for crystal effect
        this.createCrystalGradient();
    }
    
    createCrystalGradient() {
        // Create a radial gradient that simulates crystal refraction
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        const radius = this.canvas.width / 2;
        
        this.crystalGradient = this.ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
        this.crystalGradient.addColorStop(0, 'rgba(255, 255, 255, 0.8)');
        this.crystalGradient.addColorStop(0.3, 'rgba(255, 215, 0, 0.4)');
        this.crystalGradient.addColorStop(0.6, 'rgba(68, 34, 102, 0.6)');
        this.crystalGradient.addColorStop(1, 'rgba(25, 0, 50, 0.8)');
    }
    
    createParticles() {
        // Create mystical particles for the crystal ball
        for (let i = 0; i < 20; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5,
                size: Math.random() * 3 + 1,
                opacity: Math.random() * 0.5 + 0.3,
                color: Math.random() > 0.5 ? '#ffd700' : '#ffffff'
            });
        }
    }
    
    animate() {
        this.animationId = requestAnimationFrame(() => this.animate());
        this.time += 0.016; // ~60fps
        
        this.clearCanvas();
        this.drawCrystalBall();
        this.drawSmokeEffect();
        this.drawSkull();
        this.drawParticles();
        this.drawGlowEffect();
    }
    
    clearCanvas() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
    
    drawCrystalBall() {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        const radius = this.canvas.width / 2 - 4; // Account for border
        
        // Draw the main crystal ball
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.clip();
        
        // Fill with gradient
        this.ctx.fillStyle = this.crystalGradient;
        this.ctx.fill();
        
        // Add subtle animation by scaling the gradient
        const scale = 1 + Math.sin(this.time * 2) * 0.05;
        this.ctx.save();
        this.ctx.translate(centerX, centerY);
        this.ctx.scale(scale, scale);
        this.ctx.translate(-centerX, -centerY);
        
        // Redraw gradient with animation
        this.createCrystalGradient();
        this.ctx.fillStyle = this.crystalGradient;
        this.ctx.fill();
        this.ctx.restore();
        
        this.ctx.restore();
    }
    
    drawSmokeEffect() {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        const radius = this.canvas.width / 2 - 10;
        
        // Draw swirling smoke effect
        this.ctx.save();
        this.ctx.globalCompositeOperation = 'source-atop';
        
        for (let i = 0; i < 3; i++) {
            const angle = this.time * (0.5 + i * 0.3);
            const smokeRadius = radius * (0.3 + i * 0.2);
            const x = centerX + Math.cos(angle) * smokeRadius * 0.5;
            const y = centerY + Math.sin(angle) * smokeRadius * 0.3;
            
            const gradient = this.ctx.createRadialGradient(x, y, 0, x, y, smokeRadius);
            gradient.addColorStop(0, `rgba(68, 34, 102, ${0.3 - i * 0.1})`);
            gradient.addColorStop(1, 'rgba(68, 34, 102, 0)');
            
            this.ctx.fillStyle = gradient;
            this.ctx.beginPath();
            this.ctx.arc(x, y, smokeRadius, 0, Math.PI * 2);
            this.ctx.fill();
        }
        
        this.ctx.restore();
    }
    
    drawSkull() {
        if (this.skullEmojis.length === 0) {
            console.log('No skull emojis available for drawing');
            return;
        }
        
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        const skullSize = 40;
        
        // Get current skull
        const currentSkull = this.skullEmojis[this.currentSkullIndex];
        
        if (!currentSkull) {
            console.log('No current skull available');
            return;
        }
        
        // Add floating animation
        const floatY = Math.sin(this.time * 1.5) * 3;
        const floatX = Math.cos(this.time * 0.8) * 2;
        
        this.ctx.save();
        this.ctx.globalCompositeOperation = 'source-atop';
        this.ctx.globalAlpha = 0.8;
        
        // Draw skull with animation
        try {
            this.ctx.drawImage(
                currentSkull,
                centerX - skullSize/2 + floatX,
                centerY - skullSize/2 + floatY,
                skullSize,
                skullSize
            );
            console.log('Drew skull at position:', centerX - skullSize/2 + floatX, centerY - skullSize/2 + floatY);
        } catch (error) {
            console.error('Error drawing skull image:', error);
        }
        
        // Add glowing eyes effect
        this.ctx.globalAlpha = 0.6 + Math.sin(this.time * 3) * 0.3;
        this.ctx.fillStyle = '#ff0000';
        this.ctx.shadowColor = '#ff0000';
        this.ctx.shadowBlur = 5;
        
        // Left eye glow
        this.ctx.beginPath();
        this.ctx.arc(centerX - 8 + floatX, centerY - 5 + floatY, 2, 0, Math.PI * 2);
        this.ctx.fill();
        
        // Right eye glow
        this.ctx.beginPath();
        this.ctx.arc(centerX + 8 + floatX, centerY - 5 + floatY, 2, 0, Math.PI * 2);
        this.ctx.fill();
        
        this.ctx.restore();
    }
    
    drawParticles() {
        this.ctx.save();
        this.ctx.globalCompositeOperation = 'source-over';
        
        this.particles.forEach(particle => {
            // Update particle position
            particle.x += particle.vx;
            particle.y += particle.vy;
            
            // Bounce off edges
            if (particle.x <= 0 || particle.x >= this.canvas.width) {
                particle.vx *= -1;
            }
            if (particle.y <= 0 || particle.y >= this.canvas.height) {
                particle.vy *= -1;
            }
            
            // Keep particles within bounds
            particle.x = Math.max(0, Math.min(this.canvas.width, particle.x));
            particle.y = Math.max(0, Math.min(this.canvas.height, particle.y));
            
            // Draw particle with pulsing effect
            const pulse = 0.5 + Math.sin(this.time * 4 + particle.x * 0.1) * 0.3;
            this.ctx.globalAlpha = particle.opacity * pulse;
            this.ctx.fillStyle = particle.color;
            this.ctx.shadowColor = particle.color;
            this.ctx.shadowBlur = particle.size;
            
            this.ctx.beginPath();
            this.ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
            this.ctx.fill();
        });
        
        this.ctx.restore();
    }
    
    drawGlowEffect() {
        // Add outer glow effect
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        const radius = this.canvas.width / 2;
        
        this.ctx.save();
        this.ctx.globalCompositeOperation = 'source-over';
        
        // Pulsing outer glow
        const glowIntensity = 0.3 + Math.sin(this.time * 2) * 0.2;
        const gradient = this.ctx.createRadialGradient(centerX, centerY, radius * 0.8, centerX, centerY, radius);
        gradient.addColorStop(0, `rgba(255, 215, 0, 0)`);
        gradient.addColorStop(1, `rgba(255, 215, 0, ${glowIntensity})`);
        
        this.ctx.fillStyle = gradient;
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.fill();
        
        this.ctx.restore();
    }
    
    changeSkull() {
        if (this.skullEmojis.length <= 1) return;
        
        // Move to a new random skull emoji, ensuring it's different from the current one
        let newIndex;
        do {
            newIndex = Math.floor(Math.random() * this.skullEmojis.length);
        } while (newIndex === this.currentSkullIndex);
        
        this.currentSkullIndex = newIndex;
        console.log(`Changed skull to emoji ${this.currentSkullIndex + 1}`);
    }
    
    startTalking() {
        const container = document.getElementById('crystal-ball-container');
        if (container) {
            container.classList.add('talking');
        }
    }

    stopTalking() {
        const container = document.getElementById('crystal-ball-container');
        if (container) {
            container.classList.remove('talking');
        }
    }
    
    showEnhancedFallback() {
        const container = document.getElementById('crystal-ball-container');
        
        // Create a more visually appealing fallback
        container.innerHTML = `
            <div style="
                width: 100%; 
                height: 100%; 
                background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.4) 0%, rgba(255,215,0,0.3) 20%, rgba(68,34,102,0.6) 60%, rgba(25,0,50,0.8) 100%);
                border-radius: 50%;
                display: flex; 
                align-items: center; 
                justify-content: center; 
                color: #fff; 
                font-size: 24px;
                position: relative;
                overflow: hidden;
                animation: crystalPulse 3s ease-in-out infinite;
            ">
                <div style="
                    position: absolute;
                    width: 80%;
                    height: 80%;
                    background: radial-gradient(circle, rgba(255,215,0,0.2) 0%, transparent 70%);
                    border-radius: 50%;
                    animation: innerGlow 2s ease-in-out infinite alternate;
                "></div>
                🔮
                <div style="
                    position: absolute;
                    top: 10%;
                    left: 20%;
                    width: 4px;
                    height: 4px;
                    background: rgba(255,255,255,0.8);
                    border-radius: 50%;
                    animation: sparkle 1.5s ease-in-out infinite;
                "></div>
                <div style="
                    position: absolute;
                    bottom: 15%;
                    right: 25%;
                    width: 3px;
                    height: 3px;
                    background: rgba(255,215,0,0.9);
                    border-radius: 50%;
                    animation: sparkle 2s ease-in-out infinite 0.5s;
                "></div>
            </div>
        `;
        
        // Add CSS animations for the fallback
        const style = document.createElement('style');
        style.textContent = `
            @keyframes crystalPulse {
                0%, 100% { 
                    transform: scale(1);
                    box-shadow: 0 0 25px var(--gold-glow), 0 0 50px var(--gold-glow); 
                }
                50% { 
                    transform: scale(1.03);
                    box-shadow: 0 0 35px var(--gold-glow), 0 0 70px var(--gold-glow), 0 0 100px rgba(255, 215, 0, 0.3); 
                }
            }
            
            @keyframes innerGlow {
                0% { opacity: 0.3; }
                100% { opacity: 0.7; }
            }
            
            @keyframes sparkle {
                0%, 100% { opacity: 0; transform: scale(0); }
                50% { opacity: 1; transform: scale(1); }
            }
        `;
        document.head.appendChild(style);
    }
    
    destroy() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
    }
}

class TarotReading {
    constructor(crystalBall) {
        this.crystalBall = crystalBall;
        this.currentSpread = null;
        this.cards = [];
        this.tarotData = null;
        this.isDealing = false;
        this.dealerMessages = {
            start: "The universe whispers... let me reveal your path.",
            dealing: "Feel the energy of each card as it falls...",
            summary: "The cosmos has spoken. Listen carefully to this wisdom."
        };
        
        // Get GROQ API key from global config
        this.groqApiKey = window.botInfo?.groq_api_key || '';
        this.groqApiAvailable = window.botInfo?.groq_api_available || false;
        
        this.init();
    }
    
    async init() {
        await this.loadTarotData();
        this.setupEventListeners();
        this.loadBotAvatar();
    }
    
    async loadTarotData() {
        try {
            const response = await fetch('/Systems/Astrology/Tarot/tarot-images.json');
            const data = await response.json();
            // Convert the cards array to an object for easier access
            this.tarotData = {};
            data.cards.forEach(card => {
                // Use the image filename as the key (without .jpg extension)
                const key = card.img.replace('.jpg', '');
                this.tarotData[key] = card;
            });
            console.log('Tarot data loaded:', Object.keys(this.tarotData).length, 'cards');
        } catch (error) {
            console.error('Error loading tarot data:', error);
            this.tarotData = {};
        }
    }
    
    setupEventListeners() {
        // Thought bubble clicks
        document.querySelectorAll('.thought-bubble').forEach(bubble => {
            bubble.addEventListener('click', (e) => {
                const spread = e.currentTarget.dataset.spread;
                this.startReading(spread);
            });
        });
        
        // Restart button
        document.getElementById('restart-reading').addEventListener('click', () => {
            this.restartReading();
        });
    }
    
    loadBotAvatar() {
        const loadingElement = document.getElementById('dealer-avatar-loading');
        const summaryAvatar = document.getElementById('summary-avatar');
        
        // Hide loading, as the crystal ball is now handled by canvas
        if (loadingElement) {
            loadingElement.style.display = 'none';
        }
        
        // Update summary avatar with a random skull emoji
        if (summaryAvatar) {
            const randomSkullIndex = Math.floor(Math.random() * 16) + 1;
            summaryAvatar.style.backgroundImage = `url('/static/Emojis/Skulls/${randomSkullIndex}.png')`;
            summaryAvatar.style.backgroundSize = 'cover';
            summaryAvatar.style.backgroundPosition = 'center';
            summaryAvatar.style.backgroundRepeat = 'no-repeat';
        }
    }
    
    async startReading(spread) {
        this.currentSpread = spread;
        
        // Hide selection, show card table
        document.getElementById('reading-selection').classList.add('d-none');
        document.getElementById('card-table').classList.remove('d-none');
        document.getElementById('reading-results').classList.add('d-none');
        
        // Show dealer message
        this.showDealerMessage(this.dealerMessages.start);
        
        // Wait a moment then start dealing
        await this.delay(2000);
        await this.dealCards();
    }
    
    async dealCards() {
        this.isDealing = true;
        const cardCount = this.getCardCountForSpread(this.currentSpread);
        const cardSlots = document.getElementById('card-slots');
        
        // Shuffle the deck
        const cardKeys = Object.keys(this.tarotData);
        this.shuffledDeck = cardKeys.sort(() => 0.5 - Math.random());
        
        // Create card slots
        cardSlots.innerHTML = '';
        for (let i = 0; i < cardCount; i++) {
            const slot = document.createElement('div');
            slot.className = 'card-slot';
            slot.id = `slot-${i}`;
            cardSlots.appendChild(slot);
        }
        
        // Deal cards one by one
        for (let i = 0; i < cardCount; i++) {
            await this.dealSingleCard(i);
            await this.delay(3000); // Wait between cards for reading
        }
        
        // Show summary
        await this.delay(1000);
        await this.generateSummary();
    }
    
    async dealSingleCard(index) {
        const slot = document.getElementById(`slot-${index}`);
        
        // Get the next card from the shuffled deck
        const cardKey = this.shuffledDeck.pop();
        const cardData = this.tarotData[cardKey];
        
        if (!cardData) {
            console.error('No card data found for key:', cardKey);
            this.showDealerMessage('Error: Could not load card data');
            return;
        }
        
        console.log('Dealing card:', cardData.name, 'Key:', cardKey);
        
        // Determine if card is reversed (50% chance)
        const isReversed = Math.random() < 0.5;
        const orientation = isReversed ? ' (Reversed)' : '';
        
        // Get meanings based on orientation
        const meanings = isReversed ? cardData.meanings.shadow : cardData.meanings.light;
        const meaning = Array.isArray(meanings) ? meanings.slice(0, 3).join(', ') : meanings;
        
        // Get fortune telling message
        const fortune = Array.isArray(cardData.fortune_telling) ? 
            cardData.fortune_telling[Math.floor(Math.random() * cardData.fortune_telling.length)] : 
            cardData.fortune_telling;
        
        // Store enhanced card data
        const enhancedCardData = {
            ...cardData,
            name: cardData.name + orientation,
            isReversed: isReversed,
            meaning: meaning,
            fortune: fortune,
            imageKey: cardKey
        };
        
        this.cards.push(enhancedCardData);
        
        // Show dealer message
        this.showDealerMessage(`${this.dealerMessages.dealing} ${enhancedCardData.name}...`);
        
        // Create and animate card
        const card = document.createElement('div');
        card.className = 'tarot-card dealing' + (isReversed ? ' reversed' : '');
        
        // Create card HTML with proper image handling
        const cardImageUrl = `/Systems/Astrology/Tarot/cards/${cardKey}.jpg`;
        card.innerHTML = `
            <div class="card-front">
                <img src="${cardImageUrl}" alt="${enhancedCardData.name}" class="card-image" 
                     onerror="this.onerror=null; this.src='https://via.placeholder.com/100x150?text=Card+${cardKey}';">
                <div class="card-name">${enhancedCardData.name}</div>
                ${isReversed ? '<div class="card-reversed-indicator">REVERSED</div>' : ''}
            </div>
        `;
        
        slot.appendChild(card);
        
        // Wait for animation to complete
        await this.delay(1500);
        
        // Reveal meaning
        this.showDealerMessage(meaning);
        
        // Add a subtle glow effect for major arcana cards
        if (cardData.arcana && (cardData.arcana.toLowerCase().includes('major') || cardData.arcana === 'Major Arcana')) {
            card.classList.add('major-arcana');
        }
    }
    
    async generateSummary() {
        this.showDealerMessage(this.dealerMessages.summary);
        
        // Show loading state
        const summaryContent = document.getElementById('ai-summary-content');
        summaryContent.innerHTML = '<div class="text-center"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Generating AI reading...</span></div><p class="mt-2">The universe is channeling wisdom...</p></div>';
        
        // Generate AI-powered summary
        const aiSummary = await this.generateAISummary();
        
        // Display the summary with rich formatting
        summaryContent.innerHTML = this.formatAISummary(aiSummary);
        
        await this.delay(2000);
        
        // Show results
        document.getElementById('reading-results').classList.remove('d-none');
        document.getElementById('reading-results').classList.add('fade-in');
        
        this.hideDealerMessage();
    }
    
    async generateAISummary() {
        if (!this.groqApiAvailable || !this.groqApiKey) {
            // Fallback to basic summary if API not available
            console.log('GROQ API not available, using basic summary');
            return this.generateBasicSummary();
        }
        
        console.log('Generating AI-powered tarot summary...');
        
        try {
            const spread_config = {
                "1 Card": ["The Message"],
                "3 Card (Past/Present/Future)": ["Past", "Present", "Future"],
                "5 Card (Traditional)": ["Theme", "Obstacle", "Advice", "Hidden Influence", "Outcome"]
            };
            
            const positions = spread_config[this.currentSpread];
            
            // Prepare card information for AI
            const cardInfo = this.cards.map((card, index) => ({
                name: card.name,
                position: positions[index],
                meaning: card.meaning,
                fortune: card.fortune,
                arcana: card.arcana || 'Minor'
            }));
            
            let prompt = '';
            
            if (this.currentSpread === "1 Card") {
                prompt = `You are a wise and intuitive tarot reader. The universe has drawn one card for a seeker.

Card: ${cardInfo[0].name}
Position: ${cardInfo[0].position}
Core Meaning: ${cardInfo[0].meaning}
Fortune: ${cardInfo[0].fortune}

Provide a profound and personalized message from the universe to the seeker. The message should be encouraging, insightful, and directly related to the card's energy. Keep the response under 150 words.`;
            } else if (this.currentSpread === "3 Card (Past/Present/Future)") {
                prompt = `You are an experienced tarot reader interpreting a three-card spread for a seeker.

**Past**: ${cardInfo[0].name} - ${cardInfo[0].meaning}
**Present**: ${cardInfo[1].name} - ${cardInfo[1].meaning}  
**Future**: ${cardInfo[2].name} - ${cardInfo[2].meaning}

First, explain what each card in its position (Past, Present, Future) means for the seeker's situation. Then, provide a combined interpretation of how these three cards work together to tell a cohesive story about the seeker's journey. The reading should be insightful, clear, and offer practical guidance. Use warm, mystical language that connects the cards' energies. Keep the total response under 250 words.`;
            } else if (this.currentSpread === "5 Card (Traditional)") {
                prompt = `You are a master tarot reader providing a detailed five-card spread reading for a seeker.

**Theme**: ${cardInfo[0].name} - ${cardInfo[0].meaning}
**Obstacle**: ${cardInfo[1].name} - ${cardInfo[1].meaning}
**Advice**: ${cardInfo[2].name} - ${cardInfo[2].meaning}
**Hidden Influence**: ${cardInfo[3].name} - ${cardInfo[3].meaning}
**Outcome**: ${cardInfo[4].name} - ${cardInfo[4].meaning}

Provide a comprehensive tarot reading that weaves these five cards into a cohesive narrative. Address:
- The core theme or energy surrounding the seeker's inquiry
- The main obstacle or challenge they face
- The advice or guidance from the universe
- The hidden influence affecting the situation
- The likely outcome if the seeker follows the guidance

Make connections between the cards and tell a compelling story. Use mystical, encouraging language while being practical and actionable. Keep the response under 300 words.`;
            }
            
            const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.groqApiKey}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    model: 'llama-3.1-8b-instant',
                    messages: [
                        {
                            role: 'system',
                            content: 'You are a wise and intuitive tarot reader. Provide profound, insightful, and personalized messages from the universe based on the cards drawn. Use mystical language, make connections between cards, and offer practical guidance. Format your response with clear sections and engaging language.'
                        },
                        {
                            role: 'user',
                            content: prompt
                        }
                    ],
                    temperature: 0.8,
                    max_tokens: 500,
                    top_p: 0.9,
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                return data.choices[0].message.content.trim();
            } else {
                console.error('Groq API error:', response.status, response.statusText);
                const errorData = await response.text();
                console.error('Error details:', errorData);
                return this.generateBasicSummary();
            }
        } catch (error) {
            console.error('Error generating AI summary:', error);
            return this.generateBasicSummary();
        }
    }
    
    formatAISummary(summary) {
        // Enhanced formatting for AI summary
        let formatted = summary
            // Convert markdown-style headers to HTML
            .replace(/^### (.+)$/gm, '<h6 class="text-primary mb-2">$1</h6>')
            .replace(/^## (.+)$/gm, '<h5 class="text-info mb-3">$1</h5>')
            .replace(/^# (.+)$/gm, '<h4 class="text-warning mb-4">$1</h4>')
            // Convert **bold** to <strong>
            .replace(/\*\*(.+?)\*\*/g, '<strong class="text-light">$1</strong>')
            // Convert *italic* to <em>
            .replace(/\*(.+?)\*/g, '<em class="text-muted">$1</em>')
            // Convert bullet points
            .replace(/^[-•] (.+)$/gm, '<li class="mb-1">$1</li>')
            // Convert numbered lists
            .replace(/^\d+\. (.+)$/gm, '<li class="mb-1">$1</li>')
            // Add spacing between paragraphs
            .replace(/\n\n/g, '</p><p class="mb-4">')
            // Handle single newlines
            .replace(/\n/g, '<br>')
            // Wrap in paragraphs
            .replace(/^(<[^>]+>.*<\/[^>]+>)$/gm, '$1')
            .replace(/^([^<].*[^>])$/gm, '<p class="mb-3">$1</p>');
        
        // Wrap lists in proper HTML
        if (formatted.includes('<li')) {
            formatted = formatted.replace(/(<li>.*<\/li>)/s, '<ul class="list-unstyled ms-3">$1</ul>');
        }
        
        // Add mystical styling classes
        formatted = `<div class="ai-summary-text">${formatted}</div>`;
        
        return formatted;
    }
    
    generateBasicSummary() {
        const spread_config = {
            "1 Card": ["The Message"],
            "3 Card (Past/Present/Future)": ["Past", "Present", "Future"],
            "5 Card (Traditional)": ["Theme", "Obstacle", "Advice", "Hidden Influence", "Outcome"]
        };
        
        const positions = spread_config[this.currentSpread];
        let summary = `For your ${this.currentSpread} reading, the cards reveal the following insights:\n\n`;
        
        this.cards.forEach((card, index) => {
            summary += `**${positions[index]}: ${card.name}**\n`;
            summary += `${card.meaning}\n\n`;
        });
        
        return summary;
    }
    
    restartReading() {
        // Reset everything
        this.currentSpread = null;
        this.cards = [];
        this.isDealing = false;
        
        // Show selection, hide everything else
        document.getElementById('reading-selection').classList.remove('d-none');
        document.getElementById('card-table').classList.add('d-none');
        document.getElementById('reading-results').classList.add('d-none');
        
        this.hideDealerMessage();
    }
    
    showDealerMessage(message) {
        const speechBubble = document.getElementById('dealer-speech');
        const speechContent = speechBubble.querySelector('.speech-content');
        
        speechContent.textContent = message;
        speechBubble.classList.remove('d-none');
        
        // Add talking animation to crystal ball
        this.crystalBall.startTalking();
    }
    
    hideDealerMessage() {
        document.getElementById('dealer-speech').classList.add('d-none');
        this.crystalBall.stopTalking();
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

// Initialize crystal ball and tarot reading when page loads
document.addEventListener('DOMContentLoaded', async () => {
    console.log('DOM Content Loaded - Starting crystal ball initialization');
    
    // Check if crystal ball container exists
    const container = document.getElementById('crystal-ball-container');
    if (!container) {
        console.error('Crystal ball container not found in DOM!');
        return;
    }
    
    console.log('Crystal ball container found:', container);
    
    try {
        // Use the simplified crystal ball that should definitely work
        const crystalBall = new SimpleCrystalBall();
        console.log('SimpleCrystalBall instance created');
        
        // Initialize the crystal ball
        await crystalBall.init();
        console.log('Simple crystal ball initialized successfully');
        
        // Initialize the tarot reading with the crystal ball instance
        window.tarotInstance = new TarotReading(crystalBall);
        console.log('Tarot reading initialized successfully');
        
    } catch (error) {
        console.error('Failed to initialize crystal ball or tarot reading:', error);
        // Show fallback if everything fails
        if (container) {
            container.innerHTML = `
                <div style="
                    width: 100%; 
                    height: 100%; 
                    background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.4) 0%, rgba(255,215,0,0.3) 20%, rgba(68,34,102,0.6) 60%, rgba(25,0,50,0.8) 100%);
                    border-radius: 50%;
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    color: #fff; 
                    font-size: 24px;
                    animation: crystalPulse 3s ease-in-out infinite;
                ">
                    🔮
                </div>
            `;
        }
    }
});
