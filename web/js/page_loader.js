
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

        if (this.loadedScripts.has(scriptPath)) {
            if (callback) callback();
            return;
        }

        const script = document.createElement('script');
        script.src = scriptPath;
        script.type = scriptType;
        
        script.onload = () => {
            console.log(`Script loaded successfully: ${scriptPath}`);
            this.loadedScripts.add(scriptPath);
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

        if (this.loadedCSS.has(cssPath)) {
            if (callback) callback();
            return;
        }

        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = cssPath;

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
        this.loadedScripts.forEach(scriptPath => {
            const scriptElements = document.querySelectorAll(`script[src="${scriptPath}"]`);
            scriptElements.forEach(el => el.remove());
        });
        this.loadedScripts.clear();
        
        this.loadedCSS.forEach(cssPath => {
            const linkElements = document.querySelectorAll(`link[href="${cssPath}"]`);
            linkElements.forEach(el => el.remove());
        });
        this.loadedCSS.clear();
    }
}

const scriptManager = new PageScriptManager();
