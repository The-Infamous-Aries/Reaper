/**
 * Cache Buster Utility
 * Forces refresh of all cached assets when Cloudflare caching issues occur
 */

class CacheBuster {
    constructor() {
        this.timestamp = Date.now();
        this.randomId = Math.random().toString(36).substr(2, 9);
        this.hourlyTimestamp = Math.floor(Date.now() / (60 * 60 * 1000)); // Updates every hour
    }

    /**
     * Generate cache-busting parameter that updates every hour
     */
    getCacheBuster() {
        return `cb=${this.hourlyTimestamp}&r=${this.randomId}`;
    }

    /**
     * Generate fresh cache-busting parameter (for manual refresh)
     */
    getFreshCacheBuster() {
        return `cb=${Date.now()}&r=${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Force reload all CSS files with cache-busting
     */
    reloadAllCSS() {
        const cssLinks = document.querySelectorAll('link[rel="stylesheet"]');
        cssLinks.forEach(link => {
            const href = link.href.split('?')[0]; // Remove existing parameters
            const newHref = `${href}?${this.getFreshCacheBuster()}`;
            
            const newLink = document.createElement('link');
            newLink.rel = 'stylesheet';
            newLink.href = newHref;
            
            newLink.onload = () => {
                link.remove();
                console.log(`CSS reloaded: ${href}`);
            };
            
            document.head.appendChild(newLink);
        });
    }

    /**
     * Force reload all JavaScript files with cache-busting
     */
    reloadAllJS() {
        const scripts = document.querySelectorAll('script[src]');
        scripts.forEach(script => {
            if (script.src.includes('cdn.') || script.src.includes('unpkg.') || script.src.includes('googleapis.')) {
                return; // Skip external CDN scripts
            }
            
            const src = script.src.split('?')[0]; // Remove existing parameters
            const newSrc = `${src}?${this.getFreshCacheBuster()}`;
            
            const newScript = document.createElement('script');
            newScript.src = newSrc;
            newScript.type = script.type || 'text/javascript';
            
            newScript.onload = () => {
                console.log(`JS reloaded: ${src}`);
            };
            
            document.head.appendChild(newScript);
        });
    }

    /**
     * Force reload current page content
     */
    reloadPageContent() {
        if (typeof loadPage === 'function' && currentLoadedPage) {
            console.log('Reloading current page with cache-busting...');
            const page = currentLoadedPage.replace('.html', '');
            loadPage(page);
        }
    }

    /**
     * Clear browser cache for the current domain
     */
    clearBrowserCache() {
        if ('caches' in window) {
            caches.keys().then(names => {
                names.forEach(name => {
                    caches.delete(name);
                });
            });
        }
    }

    /**
     * Full cache bust - reload everything
     */
    bustAllCache() {
        console.log('🔄 Starting full cache bust...');
        
        // Clear service worker caches
        this.clearBrowserCache();
        
        // Reload CSS
        this.reloadAllCSS();
        
        // Reload current page content
        setTimeout(() => {
            this.reloadPageContent();
        }, 500);
        
        console.log('✅ Cache bust complete!');
    }

    /**
     * Add cache-busting to a URL
     */
    addCacheBuster(url) {
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}${this.getFreshCacheBuster()}`;
    }
}

// Global cache buster instance
window.cacheBuster = new CacheBuster();

// Auto-run on every page load — only clear service worker caches.
// CSS reload is intentionally NOT run automatically: it causes FOUC and
// breaks layout calculations in ss_map, wheel, races, mypet etc. that
// read getBoundingClientRect() / clientWidth during init.
// The server already sends no-cache headers and the <link> tags in
// dashboard.html carry ?v= params, so CSS is always fresh without this.
(function autoInit() {
    function runBust() {
        window.cacheBuster.clearBrowserCache();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runBust);
    } else {
        runBust();
    }
})();

// Ctrl+Shift+R OR Ctrl+Alt+R — manual emergency bust (CSS reload is safe here because
// the user is explicitly asking for it after the page is fully loaded).
document.addEventListener('keydown', (e) => {
    // Check for both uppercase and lowercase 'r' to handle different browser behaviors
    const isRKey = e.key === 'R' || e.key === 'r';
    if ((e.ctrlKey && e.shiftKey && isRKey) || (e.ctrlKey && e.altKey && isRKey)) {
        e.preventDefault();
        console.log('🚨 Emergency cache bust triggered!');
        window.cacheBuster.bustAllCache();
    }
});

// Add console command for manual cache busting
console.log('💡 Cache Buster loaded! Use cacheBuster.bustAllCache() or Ctrl+Shift+R / Ctrl+Alt+R to force refresh all assets.');