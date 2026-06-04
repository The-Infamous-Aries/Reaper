// ── Mega Menu Navigation ──────────────────────────────────────────────────────

class MegaMenu {
    constructor() {
        this.init();
    }

    init() {
        // Only initialize on desktop
        if (window.innerWidth <= 768) {
            return;
        }

        this.setupBrandLink();
        this.setupDropdowns();
        this.setupSearch();
        this.setupKeyboardNavigation();
        this.setupClickOutside();
    }

    setupBrandLink() {
        const brandLink = document.querySelector('.nav-brand');
        if (!brandLink) return;

        brandLink.addEventListener('click', (e) => {
            e.preventDefault();
            const page = brandLink.dataset.page;
            if (page && window.navigateTo) {
                window.navigateTo(page);
            }
        });
    }

    setupDropdowns() {
        const dropdowns = document.querySelectorAll('.dropdown');
        
        dropdowns.forEach(dropdown => {
            const toggle = dropdown.querySelector('.dropdown-toggle');
            const menu = dropdown.querySelector('.mega-menu');
            
            if (!toggle || !menu) return;

            // Hover handling
            dropdown.addEventListener('mouseenter', () => {
                this.openDropdown(menu);
            });

            dropdown.addEventListener('mouseleave', () => {
                this.closeDropdown(menu);
            });

            // Click handling for touch devices
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                const isOpen = menu.style.visibility === 'visible';
                
                // Close all other dropdowns
                document.querySelectorAll('.mega-menu').forEach(m => {
                    this.closeDropdown(m);
                });

                if (!isOpen) {
                    this.openDropdown(menu);
                }
            });

            // Handle menu item clicks
            const menuItems = menu.querySelectorAll('.mega-menu-item');
            menuItems.forEach(item => {
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = item.dataset.page;
                    const css = item.dataset.css || null;
                    const script = item.dataset.script || null;
                    
                    if (page && window.loadPageDirect) {
                        // Use loadPageDirect so the mega-menu's data-script/data-css are respected,
                        // then also update browser history via navigateTo's pushState logic.
                        const url = new URL(window.location);
                        url.searchParams.set('page', page);
                        history.pushState({ page }, '', url.toString());
                        window.loadPageDirect(page, script, 'script', css);
                    }
                    
                    this.closeDropdown(menu);
                });
            });
        });
    }

    openDropdown(menu) {
        menu.style.visibility = 'visible';
        menu.style.opacity = '1';
        menu.style.transform = 'translateY(0)';
    }

    closeDropdown(menu) {
        menu.style.visibility = 'hidden';
        menu.style.opacity = '0';
        menu.style.transform = 'translateY(-10px)';
    }

    setupSearch() {
        const searchInput = document.getElementById('nav-search');
        if (!searchInput) return;

        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            this.filterMenuItems(query);
        });

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const firstVisible = document.querySelector('.mega-menu-item:not([style*="display: none"])');
                if (firstVisible) {
                    firstVisible.click();
                }
            }
        });
    }

    filterMenuItems(query) {
        const menuItems = document.querySelectorAll('.mega-menu-item');
        
        menuItems.forEach(item => {
            const text = item.textContent.toLowerCase();
            const matches = text.includes(query);
            item.style.display = matches ? 'flex' : 'none';
        });
    }

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            // Escape to close all dropdowns
            if (e.key === 'Escape') {
                document.querySelectorAll('.mega-menu').forEach(menu => {
                    this.closeDropdown(menu);
                });
            }

            // Arrow keys for navigation
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                const activeDropdown = document.querySelector('.mega-menu[style*="visibility: visible"]');
                if (!activeDropdown) return;

                const visibleItems = Array.from(activeDropdown.querySelectorAll('.mega-menu-item:not([style*="display: none"])'));
                if (visibleItems.length === 0) return;

                const currentIndex = visibleItems.findIndex(item => item === document.activeElement);
                let nextIndex;

                if (e.key === 'ArrowDown') {
                    nextIndex = currentIndex < visibleItems.length - 1 ? currentIndex + 1 : 0;
                } else {
                    nextIndex = currentIndex > 0 ? currentIndex - 1 : visibleItems.length - 1;
                }

                visibleItems[nextIndex].focus();
                e.preventDefault();
            }
        });
    }

    setupClickOutside() {
        document.addEventListener('click', (e) => {
            const dropdowns = document.querySelectorAll('.dropdown');
            
            dropdowns.forEach(dropdown => {
                const menu = dropdown.querySelector('.mega-menu');
                if (!menu) return;

                if (!dropdown.contains(e.target)) {
                    this.closeDropdown(menu);
                }
            });
        });
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    new MegaMenu();
});
