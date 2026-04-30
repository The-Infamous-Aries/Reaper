
class PageScriptManager {
    constructor() {
        this.loadedScripts = new Set();
        this.loadedCSS = new Set();
    }

    loadScript(scriptPath, scriptType = 'script', callback) {
        if (!scriptPath) {
            if (callback) callback();
            return;
        }

        const script = document.createElement('script');
        // Use centralized cache utils if available, otherwise fallback to timestamp
        const cacheBuster = window.cacheUtils ? 
            window.cacheUtils.getFreshCacheBuster() : 
            `v=${Date.now()}&r=${Math.random().toString(36).substr(2, 9)}`;
        const src = scriptPath + (scriptPath.includes('?') ? '&' : '?') + cacheBuster;
        script.src = src;
        script.type = scriptType;
        
        // Add cache control attributes
        script.setAttribute('cache', 'no-cache');
        
        script.onload = () => {
            console.log(`Script loaded successfully: ${scriptPath}`);
            this.loadedScripts.add(src);
            if (callback) callback();
        };

        script.onerror = () => {
            console.error(`Failed to load script: ${scriptPath}`);
            if (callback) callback(); // Still call callback to not halt execution
        };

        document.head.appendChild(script);
    }

    loadCSS(cssPath, callback) {
        if (!cssPath) {
            if (callback) callback();
            return;
        }

        // Use centralized cache utils if available, otherwise fallback to timestamp
        const cacheBuster = window.cacheUtils ? 
            window.cacheUtils.getFreshCacheBuster() : 
            `v=${Date.now()}&r=${Math.random().toString(36).substr(2, 9)}`;
        const href = cssPath + (cssPath.includes('?') ? '&' : '?') + cacheBuster;

        if (this.loadedCSS.has(cssPath)) {
            if (callback) callback();
            return;
        }

        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;

        link.onload = () => {
            console.log(`CSS loaded successfully: ${cssPath}`);
            this.loadedCSS.add(cssPath);
            if (callback) callback();
        };

        link.onerror = () => {
            console.error(`Failed to load CSS: ${cssPath}`);
            if (callback) callback();
        };

        document.head.appendChild(link);
    }

    unloadAll() {
        // Remove by full src (including cache-buster)
        this.loadedScripts.forEach(src => {
            document.querySelectorAll(`script[src*="${src.split('?')[0]}"]`).forEach(el => el.remove());
        });
        this.loadedScripts.clear();
        
        this.loadedCSS.forEach(cssPath => {
            const linkElements = document.querySelectorAll(`link[href*="${cssPath}"]`);
            linkElements.forEach(el => el.remove());
        });
        this.loadedCSS.clear();
    }
}

const scriptManager = new PageScriptManager();
