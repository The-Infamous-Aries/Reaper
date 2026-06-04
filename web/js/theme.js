// Global Theme Loader
// Loads user's saved theme settings and applies CSS variables to all pages

async function loadUserTheme() {
    try {
        const response = await fetch('/api/settings');
        if (!response.ok) return;
        
        const settings = await response.json();
        if (settings && settings.theme_bg_color) {
            applyThemeToPage(settings);
        }
    } catch (error) {
        console.debug('Failed to load user theme:', error);
    }
}

function applyThemeToPage(settings) {
    const root = document.documentElement;
    if (settings.theme_bg_color) {
        root.style.setProperty('--bg-primary', settings.theme_bg_color);
    }
    if (settings.theme_bg_secondary) {
        root.style.setProperty('--bg-secondary', settings.theme_bg_secondary);
    }
    if (settings.theme_bg_tertiary) {
        root.style.setProperty('--bg-tertiary', settings.theme_bg_tertiary);
    }
    if (settings.theme_gold_primary) {
        root.style.setProperty('--gold-primary', settings.theme_gold_primary);
    }
    if (settings.theme_gold_secondary) {
        root.style.setProperty('--gold-secondary', settings.theme_gold_secondary);
    }
    if (settings.theme_text_primary) {
        root.style.setProperty('--text-primary', settings.theme_text_primary);
    }
    if (settings.theme_text_secondary) {
        root.style.setProperty('--text-secondary', settings.theme_text_secondary);
    }
}

// Initialize theme on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadUserTheme);
} else {
    loadUserTheme();
}

// Also load when dashboard navigates to a new page
document.addEventListener('dashboardPageLoaded', loadUserTheme);
