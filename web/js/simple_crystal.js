// Simplified Crystal Ball Implementation for Testing

class SimpleCrystalBall {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.skullImages = [];
        this.currentSkullIndex = 0;
        this.time = 0;
        this.animationId = null;
        
        console.log('SimpleCrystalBall constructor called');
    }
    
    async init() {
        console.log('SimpleCrystalBall.init() called');
        try {
            this.setupCanvas();
            await this.loadSkullImages();
            this.startAnimation();
            console.log('SimpleCrystalBall initialized successfully');
        } catch (error) {
            console.error('SimpleCrystalBall initialization failed:', error);
            this.drawFallback();
        }
    }
    
    setupCanvas() {
        console.log('Setting up canvas...');
        this.canvas = document.getElementById('crystal-canvas');
        if (!this.canvas) {
            throw new Error('Canvas element not found');
        }
        
        this.ctx = this.canvas.getContext('2d');
        if (!this.ctx) {
            throw new Error('Could not get 2D context');
        }
        
        console.log('Canvas setup completed');
    }
    
    async loadSkullImages() {
        console.log('Loading skull images...');
        const imagePromises = [];
        
        for (let i = 1; i <= 16; i++) {
            const imagePath = `/static/Emojis/Skulls/${i}.png`;
            console.log(`Loading: ${imagePath}`);
            imagePromises.push(this.loadImage(imagePath));
        }
        
        const results = await Promise.allSettled(imagePromises);
        this.skullImages = results
            .filter(result => result.status === 'fulfilled' && result.value)
            .map(result => result.value)
            .filter(img => img.width > 0 && img.height > 0);
        
        if (this.skullImages.length === 0) {
            console.warn('No skull images loaded, using fallback');
            this.createFallbackImages();
        } else {
            console.log(`Successfully loaded ${this.skullImages.length} skull images`);
        }
        
        // Select a random skull for this page load (fixed until page refresh)
        this.currentSkullIndex = Math.floor(Math.random() * this.skullImages.length);
        console.log(`Selected random skull ${this.currentSkullIndex + 1} for this page load`);
    }
    
    loadImage(src) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                console.log(`Image loaded: ${src} (${img.width}x${img.height})`);
                resolve(img);
            };
            img.onerror = () => {
                console.warn(`Failed to load image: ${src}`);
                reject(new Error(`Failed to load ${src}`));
            };
            img.src = src;
        });
    }
    
    createFallbackImages() {
        // Create simple fallback skull using canvas
        const canvas = document.createElement('canvas');
        canvas.width = 64;
        canvas.height = 64;
        const ctx = canvas.getContext('2d');
        
        // Draw a simple skull
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, 64, 64);
        ctx.fillStyle = '#000000';
        
        // Eyes
        ctx.fillRect(20, 15, 8, 8);
        ctx.fillRect(36, 15, 8, 8);
        
        // Nose
        ctx.fillRect(28, 28, 8, 4);
        
        // Mouth
        ctx.fillRect(16, 40, 32, 4);
        
        this.skullImages = [canvas];
        console.log('Fallback skull image created');
    }
    
    startAnimation() {
        console.log('Starting animation...');
        this.animate();
        
        // No more automatic skull changing - skull is now fixed per page load
    }
    
    animate() {
        this.animationId = requestAnimationFrame(() => this.animate());
        this.time += 0.016; // ~60fps
        this.draw();
    }
    
    draw() {
        if (!this.ctx || !this.canvas) return;
        
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        const radius = this.canvas.width / 2 - 4;
        
        // Save the context state
        this.ctx.save();

        // Create the circular path and clip to it
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.clip();

        // Fill the circle with a solid black color
        this.ctx.fillStyle = '#000000';
        this.ctx.fill();
        
        // Draw the skull inside the clipped circle
        if (this.skullImages.length > 0) {
            const currentSkull = this.skullImages[this.currentSkullIndex];
            if (currentSkull) {
                const skullSize = 50;
                const floatY = Math.sin(this.time * 0.5) * 15; // Slower speed, wider range
                const floatX = Math.cos(this.time * 0.3) * 15; // Slower speed, wider range
                
                // The 'source-atop' operation ensures the skull is only drawn inside the black circle
                this.ctx.globalCompositeOperation = 'source-atop';
                this.ctx.globalAlpha = 0.9;
                
                try {
                    this.ctx.drawImage(
                        currentSkull,
                        centerX - skullSize/2 + floatX,
                        centerY - skullSize/2 + floatY - 5, // Slightly higher center
                        skullSize,
                        skullSize
                    );
                } catch (error) {
                    console.error('Error drawing skull:', error);
                }
            }
        }
        
        // Restore the context to remove the clipping path
        this.ctx.restore();
    }
    
    // Removed changeSkull() - skull is now fixed per page load
    
    drawFallback() {
        console.log('Drawing fallback crystal ball');
        if (!this.ctx) return;
        
        this.ctx.fillStyle = 'rgba(255, 215, 0, 0.3)';
        this.ctx.fillRect(0, 0, 120, 120);
        this.ctx.fillStyle = 'white';
        this.ctx.font = '24px Arial';
        this.ctx.fillText('🔮', 45, 70);
    }
    
    destroy() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('DOM loaded - initializing SimpleCrystalBall');
        const crystalBall = new SimpleCrystalBall();
        crystalBall.init();
    });
} else {
    console.log('DOM already loaded - initializing SimpleCrystalBall');
    const crystalBall = new SimpleCrystalBall();
    crystalBall.init();
}