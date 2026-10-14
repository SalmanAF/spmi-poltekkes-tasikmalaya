document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("catalogFilters");
  if (!form) return;
  const params = new URLSearchParams(window.location.search);
  form.querySelectorAll("[name]").forEach((control) => {
    if (params.has(control.name)) control.value = params.get(control.name);
  });
  form.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches("input"))
      form.requestSubmit();
  });
});
