/**
 * Cache Management Dashboard JavaScript
 * Handles Cloudflare cache operations and client-side cache busting
 */

let developmentModeEnabled = false;

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    loadCacheStatus();
});

// Also initialize when loaded via dashboard navigation
document.addEventListener('dashboardPageLoaded', function(event) {
    if (event.detail.page === 'cache-management.html') {
        loadCacheStatus();
    }
});

/**
 * Load cache status from API
 */
async function loadCacheStatus() {
    try {
        const response = await fetch('/api/cache/status');
        const data = await response.json();
        
        const statusDiv = document.getElementById('cache-status');
        if (data.success) {
            statusDiv.innerHTML = `
                <div class="text-success">
                    <i class="fas fa-check-circle"></i> Cache API Operational
                </div>
                <small class="text-muted">
                    Zone ID: ${data.zone_id || 'Not found'}<br>
                    API Configured: ${data.api_configured ? 'Yes' : 'No'}
                </small>
            `;
        } else {
            statusDiv.innerHTML = `
                <div class="text-warning">
                    <i class="fas fa-exclamation-triangle"></i> ${data.message}
                </div>
            `;
        }
    } catch (error) {
        const statusDiv = document.getElementById('cache-status');
        statusDiv.innerHTML = `
            <div class="text-danger">
                <i class="fas fa-times-circle"></i> Cache API Error
            </div>
            <small class="text-muted">Check server logs</small>
        `;
        logActivity('Error loading cache status: ' + error.message, 'error');
    }
}

/**
 * Purge all Cloudflare cache
 */
async function purgeAllCache() {
    if (!confirm('This will purge ALL cached content. Are you sure?')) {
        return;
    }
    
    logActivity('Purging all cache...', 'info');
    
    try {
        const response = await fetch('/api/cache/purge', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ purge_all: true })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logActivity('✅ All cache purged successfully', 'success');
            setTimeout(() => {
                logActivity('Reloading page to verify changes...', 'info');
                window.location.reload();
            }, 2000);
        } else {
            logActivity('❌ Failed to purge all cache', 'error');
        }
    } catch (error) {
        logActivity('❌ Error purging all cache: ' + error.message, 'error');
    }
}

/**
 * Purge dashboard-specific cache
 */
async function purgeDashboardCache() {
    logActivity('Purging dashboard cache...', 'info');
    
    try {
        const response = await fetch('/api/cache/purge-dashboard', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            logActivity('✅ Dashboard cache purged successfully', 'success');
            
            // Also bust client-side cache
            if (window.cacheBuster) {
                window.cacheBuster.bustAllCache();
            }
            
            setTimeout(() => {
                logActivity('Reloading dashboard...', 'info');
                window.location.reload();
            }, 2000);
        } else {
            logActivity('❌ Failed to purge dashboard cache', 'error');
        }
    } catch (error) {
        logActivity('❌ Error purging dashboard cache: ' + error.message, 'error');
    }
}

/**
 * Toggle Cloudflare development mode
 */
async function toggleDevelopmentMode() {
    const newState = !developmentModeEnabled;
    const action = newState ? 'Enabling' : 'Disabling';
    
    logActivity(`${action} development mode...`, 'info');
    
    try {
        const response = await fetch('/api/cache/development-mode', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ enabled: newState })
        });
        
        const data = await response.json();
        
        if (data.success) {
            developmentModeEnabled = newState;
            updateDevModeButton();
            logActivity(`✅ Development mode ${newState ? 'enabled' : 'disabled'}`, 'success');
            
            if (newState) {
                logActivity('ℹ️ Development mode will auto-disable in 3 hours', 'info');
            }
        } else {
            logActivity(`❌ Failed to ${action.toLowerCase()} development mode`, 'error');
        }
    } catch (error) {
        logActivity(`❌ Error ${action.toLowerCase()} development mode: ` + error.message, 'error');
    }
}

/**
 * Update development mode button state
 */
function updateDevModeButton() {
    const btn = document.getElementById('dev-mode-btn');
    if (developmentModeEnabled) {
        btn.className = 'btn btn-danger';
        btn.innerHTML = '<i class="fas fa-toggle-on"></i> Disable Dev Mode';
    } else {
        btn.className = 'btn btn-success';
        btn.innerHTML = '<i class="fas fa-toggle-off"></i> Enable Dev Mode';
    }
}

/**
 * Purge specific files
 */
async function purgeSpecificFiles() {
    const textarea = document.getElementById('files-to-purge');
    const files = textarea.value.split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);
    
    if (files.length === 0) {
        logActivity('❌ No files specified to purge', 'warning');
        return;
    }
    
    logActivity(`Purging ${files.length} specific files...`, 'info');
    
    try {
        const response = await fetch('/api/cache/purge', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ files: files })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logActivity(`✅ Successfully purged ${files.length} files`, 'success');
            textarea.value = ''; // Clear the textarea
        } else {
            logActivity('❌ Failed to purge specific files', 'error');
        }
    } catch (error) {
        logActivity('❌ Error purging specific files: ' + error.message, 'error');
    }
}

/**
 * Purge cache by tag
 */
async function purgeByTag(tag) {
    logActivity(`Purging cache for tag: ${tag}...`, 'info');
    
    try {
        const response = await fetch('/api/cache/purge', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ tags: [tag] })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logActivity(`✅ Successfully purged cache for tag: ${tag}`, 'success');
        } else {
            logActivity(`❌ Failed to purge cache for tag: ${tag}`, 'error');
        }
    } catch (error) {
        logActivity(`❌ Error purging cache for tag ${tag}: ` + error.message, 'error');
    }
}

/**
 * Bust client-side cache only
 */
function bustClientCache() {
    logActivity('Busting client-side cache...', 'info');
    
    if (window.cacheBuster) {
        window.cacheBuster.bustAllCache();
        logActivity('✅ Client-side cache busted', 'success');
    } else {
        logActivity('❌ Cache buster not available', 'error');
    }
}

/**
 * Reload current page with cache busting
 */
function reloadCurrentPage() {
    logActivity('Reloading current page...', 'info');
    
    if (typeof loadPage === 'function' && currentLoadedPage) {
        const page = currentLoadedPage.replace('.html', '');
        loadPage(page);
        logActivity('✅ Page reloaded with cache busting', 'success');
    } else {
        window.location.reload();
    }
}

/**
 * Log activity to the activity log
 */
function logActivity(message, type = 'info') {
    const logDiv = document.getElementById('activity-log');
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    entry.textContent = `[${timestamp}] ${message}`;
    
    logDiv.appendChild(entry);
    logDiv.scrollTop = logDiv.scrollHeight;
    
    // Keep only last 50 entries
    while (logDiv.children.length > 50) {
        logDiv.removeChild(logDiv.firstChild);
    }
}

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl+Shift+P = Purge dashboard cache
    if (e.ctrlKey && e.shiftKey && e.key === 'P') {
        e.preventDefault();
        purgeDashboardCache();
    }
    
    // Ctrl+Shift+D = Toggle development mode
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        toggleDevelopmentMode();
    }
});

console.log('🔧 Cache Management loaded! Keyboard shortcuts: Ctrl+Shift+P (purge), Ctrl+Shift+D (dev mode)');