/**
 * Reward Manager — main.js
 * Minimal vanilla JS: sidebar toggle, user dropdown, alert dismissal,
 * confirm-delete modal, code reveal, tab switching, form enhancements.
 */

document.addEventListener('DOMContentLoaded', () => {

  // ── Sidebar toggle (mobile) ────────────────────────────────
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const hamburger = document.getElementById('sidebarToggle');

  function openSidebar() {
    sidebar?.classList.add('open');
    overlay?.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    sidebar?.classList.remove('open');
    overlay?.classList.remove('open');
    document.body.style.overflow = '';
  }

  hamburger?.addEventListener('click', openSidebar);
  overlay?.addEventListener('click', closeSidebar);

  // ── User dropdown ──────────────────────────────────────────
  const userBtn = document.getElementById('userMenuBtn');
  userBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    userBtn.classList.toggle('open');
  });

  document.addEventListener('click', () => {
    userBtn?.classList.remove('open');
  });

  // ── Alert / message dismiss ────────────────────────────────
  document.querySelectorAll('.alert-close').forEach(btn => {
    btn.addEventListener('click', () => {
      const alert = btn.closest('.alert');
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-8px)';
      setTimeout(() => alert.remove(), 300);
    });
  });

  // Auto-dismiss alerts after 5 seconds
  document.querySelectorAll('.alert').forEach(alert => {
    setTimeout(() => {
      if (alert.isConnected) {
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-8px)';
        setTimeout(() => alert.remove(), 300);
      }
    }, 5000);
  });

  // ── Confirm-Delete Modal ───────────────────────────────────
  const deleteModal = document.getElementById('deleteModal');
  let pendingDeleteForm = null;

  document.querySelectorAll('[data-confirm-delete]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      pendingDeleteForm = document.getElementById(btn.dataset.confirmDelete)
        || btn.closest('form');
      openModal();
    });
  });

  document.getElementById('confirmDeleteBtn')?.addEventListener('click', () => {
    pendingDeleteForm?.submit();
  });

  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', closeModal);
  });

  deleteModal?.addEventListener('click', (e) => {
    if (e.target === deleteModal) closeModal();
  });

  function openModal() { deleteModal?.classList.add('open'); }
  function closeModal() {
    deleteModal?.classList.remove('open');
    pendingDeleteForm = null;
  }

  // ── Code / PIN reveal ─────────────────────────────────────
  document.querySelectorAll('.reveal-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.target);
      const hidden = document.getElementById(btn.dataset.hidden);
      if (target && hidden) {
        const isHidden = target.style.display === 'none' || !target.style.display;
        // If currently shown, hide; else show
        if (target.classList.contains('d-none')) {
          target.classList.remove('d-none');
          hidden.classList.add('d-none');
          btn.textContent = 'Hide';
        } else {
          target.classList.add('d-none');
          hidden.classList.remove('d-none');
          btn.textContent = 'Reveal';
        }
      }
    });
  });

  // ── Copy to clipboard ─────────────────────────────────────
  document.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = document.getElementById(btn.dataset.copy)?.textContent
        || btn.dataset.copyValue;
      if (text) {
        navigator.clipboard.writeText(text.trim()).then(() => {
          const original = btn.textContent;
          btn.textContent = 'Copied!';
          btn.classList.add('btn-success');
          btn.classList.remove('btn-secondary');
          setTimeout(() => {
            btn.textContent = original;
            btn.classList.remove('btn-success');
            btn.classList.add('btn-secondary');
          }, 2000);
        });
      }
    });
  });

  // ── Profile Tabs ───────────────────────────────────────────
  const tabs = document.querySelectorAll('.profile-tab');
  const panels = document.querySelectorAll('.tab-panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const target = document.getElementById(tab.dataset.tab);
      target?.classList.add('active');
    });
  });

  // ── Filter form auto-submit on select change ───────────────
  document.querySelectorAll('.auto-submit select').forEach(sel => {
    sel.addEventListener('change', () => sel.closest('form').submit());
  });

  // ── Highlight active nav item ──────────────────────────────
  const currentPath = window.location.pathname;
  document.querySelectorAll('.nav-item[href]').forEach(item => {
    const href = item.getAttribute('href');
    if (href && currentPath.startsWith(href) && href !== '/') {
      item.classList.add('active');
    }
  });

  // ── Expiry countdown bars ──────────────────────────────────
  document.querySelectorAll('[data-expiry]').forEach(el => {
    const expiry = new Date(el.dataset.expiry);
    const issued = new Date(el.dataset.issued || el.dataset.expiry);
    const now = new Date();
    const total = expiry - issued;
    const remaining = expiry - now;
    const pct = total > 0 ? Math.max(0, Math.min(100, (remaining / total) * 100)) : 0;
    const fill = el.querySelector('.expiry-bar-fill');
    if (fill) {
      fill.style.width = pct + '%';
      if (pct < 20) fill.classList.add('critical');
    }
  });

  // ── Form: datetime-local value init for edit forms ────────
  document.querySelectorAll('input[type="datetime-local"]').forEach(input => {
    if (input.dataset.value) {
      // Convert ISO string to datetime-local compatible format
      const dt = new Date(input.dataset.value);
      if (!isNaN(dt)) {
        const local = new Date(dt.getTime() - dt.getTimezoneOffset() * 60000)
          .toISOString().slice(0, 16);
        input.value = local;
      }
    }
  });

  // ── Star toggle (visual feedback; actual persistence via form) ──
  document.querySelectorAll('.star-toggle-form').forEach(form => {
    form.addEventListener('submit', (e) => {
      const btn = form.querySelector('.star-btn');
      btn?.classList.toggle('starred');
    });
  });

});
