document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');

  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }

  document.body.addEventListener('click', (event) => {
    const target = event.target;

    if (sidebar && sidebar.classList.contains('open')) {
      const clickedInsideSidebar = sidebar.contains(target);
      if (!clickedInsideSidebar && !sidebarToggle.contains(target)) {
        sidebar.classList.remove('open');
      }
    }

    const modalDismiss = target.closest('[data-dismiss="modal"]');
    if (modalDismiss) {
      const modal = modalDismiss.closest('.modal');
      if (modal) {
        modal.classList.remove('active');
      }
    }

    const toastTrigger = target.closest('[data-action="show-toast"]');
    if (toastTrigger) {
      const message = toastTrigger.dataset.message || 'Fitur ini belum tersedia.';
      showToast(message);
    }

    const modalTrigger = target.closest('[data-action="open-modal"]');
    if (modalTrigger) {
      const modalId = modalTrigger.dataset.modal;
      const modal = document.getElementById(modalId);
      if (modal) {
        modal.classList.add('active');
      }
    }
  });

  const navLinks = document.querySelectorAll('.nav-item');
  navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 1100 && sidebar) {
        sidebar.classList.remove('open');
      }
    });
  });

  document.querySelectorAll('.integration-node').forEach((node) => {
    node.addEventListener('click', () => {
      const target = node.dataset.target;
      document.querySelectorAll('.detail-box').forEach((box) => {
        box.classList.toggle('active', box.id === target);
      });
    });
  });
});

function showToast(message) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toast.classList.remove('show');
  }, 2000);
}
