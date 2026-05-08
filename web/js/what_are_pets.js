/**
 * what_are_pets.js
 * Accordion toggle logic for the Pet System Guide page.
 * Vanilla JS, no dependencies.
 */

(function () {
  'use strict';

  // ── Core init ──────────────────────────────────────────────────────────────

  /**
   * Attach click handlers to every .wap2-card-header found in the document.
   * Safe to call multiple times — uses a data attribute to avoid double-binding.
   */
  function initAccordion() {
    const headers = document.querySelectorAll('.wap2-card-header:not([data-wap2-bound])');

    headers.forEach(function (header) {
      header.setAttribute('data-wap2-bound', '1');

      header.addEventListener('click', function () {
        const card = header.closest('.wap2-card');
        if (!card) return;
        toggleCard(card);
      });
    });

    // Expand / Collapse All buttons
    const expandBtn   = document.getElementById('wap2ExpandAll');
    const collapseBtn = document.getElementById('wap2CollapseAll');

    if (expandBtn && !expandBtn.dataset.wap2Bound) {
      expandBtn.dataset.wap2Bound = '1';
      expandBtn.addEventListener('click', function () {
        document.querySelectorAll('.wap2-card').forEach(function (card) {
          openCard(card);
        });
      });
    }

    if (collapseBtn && !collapseBtn.dataset.wap2Bound) {
      collapseBtn.dataset.wap2Bound = '1';
      collapseBtn.addEventListener('click', function () {
        document.querySelectorAll('.wap2-card').forEach(function (card) {
          closeCard(card);
        });
      });
    }
  }

  // ── Card state helpers ─────────────────────────────────────────────────────

  /**
   * Toggle a card open/closed.
   * @param {HTMLElement} card
   */
  function toggleCard(card) {
    if (card.classList.contains('wap2-card-open')) {
      closeCard(card);
    } else {
      openCard(card);
    }
  }

  /**
   * Open a card.
   * @param {HTMLElement} card
   */
  function openCard(card) {
    card.classList.add('wap2-card-open');

    const header  = card.querySelector('.wap2-card-header');
    const chevron = card.querySelector('.wap2-chevron');

    if (header)  header.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.classList.add('wap2-chevron-open');
  }

  /**
   * Close a card.
   * @param {HTMLElement} card
   */
  function closeCard(card) {
    card.classList.remove('wap2-card-open');

    const header  = card.querySelector('.wap2-card-header');
    const chevron = card.querySelector('.wap2-chevron');

    if (header)  header.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.classList.remove('wap2-chevron-open');
  }

  // ── SPA integration ────────────────────────────────────────────────────────

  /**
   * The dashboard SPA fires 'dashboardPageLoaded' with { detail: { page } }
   * whenever a new page fragment is injected. Re-initialise if it's our page.
   */
  document.addEventListener('dashboardPageLoaded', function (e) {
    const page = e && e.detail && e.detail.page;
    if (page === 'what_are_pets') {
      // Strip old bindings so initAccordion can re-attach cleanly
      document.querySelectorAll('[data-wap2-bound]').forEach(function (el) {
        el.removeAttribute('data-wap2-bound');
      });
      initAccordion();
    }
  });

  // ── Boot ───────────────────────────────────────────────────────────────────

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAccordion);
  } else {
    // Fragment was injected after DOMContentLoaded already fired
    initAccordion();
  }

}());
