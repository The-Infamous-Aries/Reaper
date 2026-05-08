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
    
    // List of external domains that need proxying
    const externalDomains = [
        'upload.wikimedia.org',
        // Add other external domains as needed
    ];
    
    try {
        const urlObj = new URL(url);
        const isExternal = externalDomains.some(domain => urlObj.hostname === domain);
        
        if (isExternal) {
            const proxiedUrl = `/api/image-proxy?url=${encodeURIComponent(url)}`;
            console.log(`Proxying image URL: ${url} -> ${proxiedUrl}`);
            return proxiedUrl;
        }
    } catch (e) {
        // If URL parsing fails, return original
        console.warn('Failed to parse URL for proxying:', url);
    }
    
    return url;
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