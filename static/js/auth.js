document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.textContent = reveal ? "Sembunyi" : "Lihat";
      button.setAttribute("aria-label", `${reveal ? "Sembunyikan" : "Tampilkan"} password`);
      button.setAttribute("aria-pressed", String(reveal));
    });
  });

  const password = document.getElementById("password");
  const confirmation = document.getElementById("password_confirmation");
  if (!password || !confirmation) return;
  const validateConfirmation = () => {
    confirmation.setCustomValidity(
      confirmation.value && confirmation.value !== password.value
        ? "Konfirmasi password tidak sama."
        : "",
    );
  };
  password.addEventListener("input", validateConfirmation);
  confirmation.addEventListener("input", validateConfirmation);
});
