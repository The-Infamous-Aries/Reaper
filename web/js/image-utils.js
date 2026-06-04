/**
 * Image utilities for handling external images through proxy
 */

/**
 * Convert an external image URL to use our image proxy to avoid CORS issues
 * @param {string} url - The original image URL
 * @returns {string} - The proxied URL or original URL if not external
 */
function proxyImageUrl(url) {
    if (!url) return url;
    
    // Proxy all external URLs to handle CORS issues universally
    // This ensures alliance flags work regardless of their source domain
    try {
        const urlObj = new URL(url);
        
        // Don't proxy if it's already our own domain
        if (urlObj.hostname === window.location.hostname) {
            return url;
        }
        
        // Proxy all external URLs
        const proxiedUrl = `/api/image-proxy?url=${encodeURIComponent(url)}`;
        return proxiedUrl;
    } catch (e) {
        // If URL parsing fails, return original
        console.warn('Failed to parse URL for proxying:', url);
        return url;
    }
}

/**
 * Set image source with automatic proxying for external URLs
 * @param {HTMLImageElement} imgElement - The image element
 * @param {string} url - The image URL
 */
function setImageSrc(imgElement, url) {
    if (imgElement && url) {
        imgElement.src = proxyImageUrl(url);
    }
}

// Export for use in other scripts
window.ImageUtils = {
    proxyImageUrl,
    setImageSrc
};