// Global theme runtime.
// Applies saved theme settings to every dashboard page and dynamically loaded page.

(function () {
    const DEFAULT_THEME = {
        theme_bg_color: '#0a0a0a',
        theme_bg_secondary: '#0f0f0f',
        theme_bg_tertiary: '#141414',
        theme_gold_primary: '#ffd700',
        theme_gold_secondary: '#ffed4e',
        theme_text_primary: '#f0f0f0',
        theme_text_secondary: '#b9bbbe',
        theme_hide_bg_image: 0,
        theme_custom_bg_url: null,
    };

    const THEME_FIELDS = [
        ['theme_bg_color', '--bg-primary'],
        ['theme_bg_secondary', '--bg-secondary'],
        ['theme_bg_tertiary', '--bg-tertiary'],
        ['theme_gold_primary', '--gold-primary'],
        ['theme_gold_secondary', '--gold-secondary'],
        ['theme_text_primary', '--text-primary'],
        ['theme_text_secondary', '--text-secondary'],
    ];

    function normalizeTheme(settings) {
        return { ...DEFAULT_THEME, ...(settings || {}) };
    }

    function isHex(value) {
        return /^#[0-9a-fA-F]{6}$/.test(String(value || ''));
    }

    function hexToRgb(hex) {
        if (!isHex(hex)) return null;
        const value = hex.slice(1);
        return [
            parseInt(value.slice(0, 2), 16),
            parseInt(value.slice(2, 4), 16),
            parseInt(value.slice(4, 6), 16),
        ];
    }

    function hexToRgba(hex, alpha) {
        const rgb = hexToRgb(hex);
        return rgb ? `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})` : '';
    }

    function relativeLuminance(hex) {
        const rgb = hexToRgb(hex);
        if (!rgb) return 0;
        const parts = rgb.map(v => {
            const n = v / 255;
            return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2];
    }

    function safeUrl(value) {
        const raw = String(value || '').trim();
        if (!raw) return '';
        return raw.replace(/["\\]/g, '');
    }

    function applyThemeToPage(settings) {
        const theme = normalizeTheme(settings);
        const root = document.documentElement;
        const accentRgb = hexToRgb(theme.theme_gold_primary) || [255, 215, 0];
        const accentText = relativeLuminance(theme.theme_gold_primary) > 0.45 ? '#0a0a0a' : '#ffffff';

        THEME_FIELDS.forEach(([field, cssVar]) => {
            if (isHex(theme[field])) root.style.setProperty(cssVar, theme[field]);
        });

        root.style.setProperty('--gold-rgb', accentRgb.join(','));
        root.style.setProperty('--gold-glow', hexToRgba(theme.theme_gold_primary, 0.3) || 'rgba(255, 215, 0, 0.3)');
        root.style.setProperty('--accent-contrast', accentText);
        root.style.setProperty('--border-primary', hexToRgba(theme.theme_gold_primary, 0.3));
        root.style.setProperty('--surface-overlay', hexToRgba(theme.theme_bg_secondary, 0.86));

        root.style.setProperty('--bs-body-bg', theme.theme_bg_color);
        root.style.setProperty('--bs-body-color', theme.theme_text_primary);
        root.style.setProperty('--bs-primary', theme.theme_gold_primary);
        root.style.setProperty('--bs-secondary', theme.theme_bg_tertiary);
        root.style.setProperty('--bs-link-color', theme.theme_gold_primary);
        root.style.setProperty('--bs-link-hover-color', theme.theme_gold_secondary);
        root.style.setProperty('--bs-border-color', hexToRgba(theme.theme_gold_primary, 0.25));

        document.body.style.backgroundColor = theme.theme_bg_color;
        document.body.style.color = theme.theme_text_primary;

        const hide = theme.theme_hide_bg_image === true || theme.theme_hide_bg_image === 1 || theme.theme_hide_bg_image === '1';
        const customBg = safeUrl(theme.theme_custom_bg_url);
        if (customBg) {
            document.body.style.backgroundImage = `url("${customBg}")`;
            document.body.style.backgroundSize = 'cover';
            document.body.style.backgroundPosition = 'center';
            document.body.style.backgroundAttachment = 'fixed';
            document.body.style.backgroundRepeat = 'no-repeat';
        } else if (hide) {
            document.body.style.backgroundImage = 'none';
        } else {
            document.body.style.backgroundImage = '';
            document.body.style.backgroundSize = '';
            document.body.style.backgroundPosition = '';
            document.body.style.backgroundAttachment = '';
            document.body.style.backgroundRepeat = '';
        }

        document.documentElement.dataset.themeReady = 'true';
        window.dispatchEvent(new CustomEvent('reaperThemeApplied', { detail: { theme } }));
    }

    function readLocalTheme() {
        try {
            const raw = localStorage.getItem('reaper_theme');
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }

    function readPreviewTheme() {
        try {
            const active = sessionStorage.getItem('reaper_theme_preview_active') === '1';
            if (!active) return null;
            const raw = sessionStorage.getItem('reaper_theme_preview');
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }

    async function loadUserTheme() {
        const localTheme = readLocalTheme();
        const previewTheme = readPreviewTheme();
        applyThemeToPage(previewTheme || localTheme || DEFAULT_THEME);

        try {
            const response = await fetch('/api/settings', { credentials: 'same-origin' });
            if (!response.ok) return;
            const settings = await response.json();
            const theme = normalizeTheme({ ...localTheme, ...(settings || {}) });
            const preview = readPreviewTheme();
            applyThemeToPage(preview || theme);
            try {
                localStorage.setItem('reaper_theme', JSON.stringify(theme));
                localStorage.setItem('reaper_theme_saved_at', Date.now().toString());
            } catch {
                // Local storage can be disabled; server settings still apply.
            }
        } catch (error) {
            console.debug('Failed to load user theme:', error);
        }
    }

    window.ReaperTheme = {
        DEFAULT_THEME,
        applyThemeToPage,
        loadUserTheme,
        normalizeTheme,
        hexToRgb,
        hexToRgba,
        relativeLuminance,
        readPreviewTheme,
    };
    window.applyThemeToPage = applyThemeToPage;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadUserTheme);
    } else {
        loadUserTheme();
    }

    document.addEventListener('dashboardPageLoaded', loadUserTheme);
})();
