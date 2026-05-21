/**
 * what_are_pets.js — Pet System Guide toggle-card modal logic.
 * Matches the exact IIFE + readyState boot pattern used by bazaar.js.
 */

(function () {
    'use strict';

    var _activeModal = null;

    // ── Helpers ───────────────────────────────────────────────────────────────

    function el(id) { return document.getElementById(id); }

    // ── Hoist modals to <body> ────────────────────────────────────────────────
    // Moves modals and backdrop out of #content so position:fixed works
    // correctly regardless of any CSS transforms on ancestor elements.

    function hoistToBody() {
        var backdrop = el('wap2ModalBackdrop');
        if (backdrop && backdrop.parentNode !== document.body) {
            document.body.appendChild(backdrop);
        }
        document.querySelectorAll('.wap2-modal').forEach(function (m) {
            if (m.parentNode !== document.body) {
                document.body.appendChild(m);
            }
        });
    }

    // ── Toggle cards ──────────────────────────────────────────────────────────

    function bindCards() {
        document.querySelectorAll('.wap2-toggle-card').forEach(function (card) {
            card.style.cursor = 'pointer';
            card.addEventListener('click', function () {
                openModal(card.getAttribute('data-modal'));
            });
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openModal(card.getAttribute('data-modal'));
                }
            });
        });
    }

    // ── Modal open / close ────────────────────────────────────────────────────

    function openModal(modalId) {
        if (!modalId) return;
        var modal    = el(modalId);
        var backdrop = el('wap2ModalBackdrop');
        if (!modal || !backdrop) return;

        if (_activeModal && _activeModal !== modal) closeModal();
        _activeModal = modal;
        modal.classList.add('wap2-active');
        backdrop.classList.add('wap2-active');
        document.body.style.overflow = 'hidden';

        var btn = modal.querySelector('.wap2-modal-close');
        if (btn) setTimeout(function () { btn.focus(); }, 40);
    }

    function closeModal() {
        if (_activeModal) {
            _activeModal.classList.remove('wap2-active');
            _activeModal = null;
        }
        var backdrop = el('wap2ModalBackdrop');
        if (backdrop) backdrop.classList.remove('wap2-active');
        document.body.style.overflow = '';
    }

    function bindClose() {
        document.querySelectorAll('.wap2-modal-close').forEach(function (btn) {
            btn.addEventListener('click', closeModal);
        });
        var backdrop = el('wap2ModalBackdrop');
        if (backdrop) backdrop.addEventListener('click', closeModal);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeModal();
        });
    }

    // ── Tabs ──────────────────────────────────────────────────────────────────

    function bindTabs() {
        document.querySelectorAll('.wap2-modal-tabs').forEach(function (bar) {
            bar.querySelectorAll('.wap2-tab').forEach(function (tab) {
                tab.addEventListener('click', function () {
                    var targetId = tab.getAttribute('data-tab');
                    if (!targetId) return;

                    bar.querySelectorAll('.wap2-tab').forEach(function (t) {
                        t.classList.remove('active');
                    });
                    tab.classList.add('active');

                    var modal = bar.closest('.wap2-modal');
                    if (!modal) return;
                    var body = modal.querySelector('.wap2-modal-body');
                    if (!body) return;

                    body.querySelectorAll('.wap2-tab-panel').forEach(function (p) {
                        p.classList.remove('active');
                    });
                    var panel = body.querySelector('#' + targetId);
                    if (panel) {
                        panel.classList.add('active');
                        body.scrollTop = 0;
                    }
                });
            });
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    function init() {
        hoistToBody();
        bindCards();
        bindClose();
        bindTabs();
    }

    // ── Boot — exact same pattern as bazaar.js ────────────────────────────────

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

}());
