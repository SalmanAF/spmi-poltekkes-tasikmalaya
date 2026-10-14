(() => {
  const modal = document.getElementById("visiMisiModal");
  if (!modal) return;

  const dialog = modal.querySelector(".visi-misi-dialog");
  const closeButtons = modal.querySelectorAll("[data-visi-misi-close]");
  const storageKey = "spmi-visi-misi-dismissed";
  let previousFocus = null;

  const closeModal = () => {
    if (modal.hidden) return;

    try {
      window.sessionStorage.setItem(storageKey, "true");
    } catch (error) {
      console.error("Status pop-up Visi dan Misi tidak dapat disimpan.", error);
    }

    modal.hidden = true;
    document.body.style.removeProperty("overflow");
    document.removeEventListener("keydown", handleKeydown);
    const focusTarget =
      previousFocus instanceof HTMLElement &&
      previousFocus !== document.body &&
      previousFocus.isConnected
        ? previousFocus
        : document.querySelector("#main-content a[href]");
    focusTarget?.focus({ preventScroll: true });
  };

  const handleKeydown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
      return;
    }

    if (event.key !== "Tab") return;

    const focusableElements = modal.querySelectorAll(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (!firstElement || !lastElement) {
      event.preventDefault();
      dialog?.focus();
    } else if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement.focus();
    } else if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement.focus();
    }
  };

  let alreadyDismissed = false;
  try {
    alreadyDismissed =
      window.sessionStorage.getItem(storageKey) === "true";
  } catch (error) {
    console.error("Status pop-up Visi dan Misi tidak dapat dibaca.", error);
  }

  if (alreadyDismissed) return;

  previousFocus = document.activeElement;
  modal.hidden = false;
  document.body.style.overflow = "hidden";
  closeButtons[0]?.focus();

  closeButtons.forEach((button) => {
    button.addEventListener("click", closeModal);
  });
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  document.addEventListener("keydown", handleKeydown);
})();
