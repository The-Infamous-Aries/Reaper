/**
 * Cache Utilities - Centralized cache busting functions
 * Provides consistent cache busting across the entire application
 */

class CacheUtils {
    constructor() {
        this.hourlyTimestamp = Math.floor(Date.now() / (60 * 60 * 1000));
        this.randomId = Math.random().toString(36).substr(2, 9);
        
        // Update cache parameters every hour
        this.startHourlyUpdate();
    }

    /**
     * Get hourly cache buster (updates every hour automatically)
     */
    getHourlyCacheBuster() {
        return `v=${this.hourlyTimestamp}&cb=${this.randomId}`;
    }

    /**
     * Get fresh cache buster (always new)
     */
    getFreshCacheBuster() {
        return `v=${Date.now()}&r=${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Add cache buster to URL
     */
    addCacheBuster(url, fresh = false) {
        const separator = url.includes('?') ? '&' : '?';
        const cacheBuster = fresh ? this.getFreshCacheBuster() : this.getHourlyCacheBuster();
        return `${url}${separator}${cacheBuster}`;
    }

    /**
     * Start automatic hourly cache parameter updates
     */
    startHourlyUpdate() {
        // Calculate milliseconds until next hour
        const now = Date.now();
        const nextHour = Math.ceil(now / (60 * 60 * 1000)) * (60 * 60 * 1000);
        const msUntilNextHour = nextHour - now;

        // Set initial timeout to next hour
        setTimeout(() => {
            this.updateCacheParameters();
            
            // Then update every hour
            setInterval(() => {
                this.updateCacheParameters();
            }, 60 * 60 * 1000); // 1 hour
        }, msUntilNextHour);

        console.log(`Cache parameters will auto-update in ${Math.round(msUntilNextHour / 1000 / 60)} minutes`);
    }

    /**
     * Update cache parameters (called automatically every hour)
     */
    updateCacheParameters() {
        this.hourlyTimestamp = Math.floor(Date.now() / (60 * 60 * 1000));
        this.randomId = Math.random().toString(36).substr(2, 9);
        
        console.log('🔄 Cache parameters updated automatically');
        
        // Trigger cache refresh for critical assets
        this.refreshCriticalAssets();
    }

    /**
     * Refresh critical assets when cache parameters update
     */
    refreshCriticalAssets() {
        // Only refresh if cache buster is available
        if (window.cacheBuster) {
            // Clear service worker caches
            window.cacheBuster.clearBrowserCache();
            
            // Note: We don't auto-reload CSS/JS here to avoid FOUC
            // Users can manually trigger with Ctrl+Alt+R if needed
        }
    }

    /**
     * Get fetch options with cache busting headers
     */
    getFetchOptions(fresh = false) {
        return {
            cache: 'no-cache',
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        };
    }
}

// Global cache utils instance
window.cacheUtils = new CacheUtils();

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CacheUtils;
}

console.log('💡 Cache Utils loaded! Automatic hourly cache parameter updates enabled.');