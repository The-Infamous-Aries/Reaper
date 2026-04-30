/**
 * Modal Utilities
 * Provides consistent modal management across the application
 */

class ModalUtils {
    static cleanupAllModals() {
        // Remove all modal backdrops
        document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
            backdrop.remove();
        });
        
        // Reset body classes and styles
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');
        
        // Close all Bootstrap modals
        document.querySelectorAll('.modal').forEach(modalEl => {
            const modalInstance = bootstrap.Modal.getInstance(modalEl);
            if (modalInstance) {
                modalInstance.hide();
            }
        });
    }
    
    static openModal(modalId, options = {}) {
        // Clean up any existing modals first
        this.cleanupAllModals();
        
        const modalElement = document.getElementById(modalId);
        if (!modalElement) {
            console.error(`Modal with id '${modalId}' not found`);
            return null;
        }
        
        // Wait a bit for cleanup to complete
        setTimeout(() => {
            const modal = new bootstrap.Modal(modalElement, {
                backdrop: true,
                keyboard: true,
                focus: true,
                ...options
            });
            
            // Set up proper event handlers
            modalElement.addEventListener('shown.bs.modal', function onShown() {
                modalElement.removeEventListener('shown.bs.modal', onShown);
                
                // Ensure proper z-index for backdrop and modal
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.style.zIndex = '1040';
                }
                modalElement.style.zIndex = '1050';
                
                // Ensure form elements are interactive
                const formElements = modalElement.querySelectorAll('input, select, button, textarea');
                formElements.forEach(element => {
                    element.style.pointerEvents = 'auto';
                });
            });
            
            // Clean up on hide
            modalElement.addEventListener('hidden.bs.modal', function onHidden() {
                modalElement.removeEventListener('hidden.bs.modal', onHidden);
                ModalUtils.cleanupAllModals();
            });
            
            modal.show();
            return modal;
        }, 100);
    }
    
    static closeModal(modalId) {
        const modalElement = document.getElementById(modalId);
        if (modalElement) {
            const modalInstance = bootstrap.Modal.getInstance(modalElement);
            if (modalInstance) {
                modalInstance.hide();
            }
        }
        
        // Always clean up after closing
        setTimeout(() => {
            this.cleanupAllModals();
        }, 300);
    }
}

// Make it globally available
window.ModalUtils = ModalUtils;

// Clean up modals when page changes
document.addEventListener('dashboardPageLoaded', function() {
    ModalUtils.cleanupAllModals();
});