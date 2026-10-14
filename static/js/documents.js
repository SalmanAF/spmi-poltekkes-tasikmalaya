document.addEventListener('DOMContentLoaded', () => {
  const searchInputs = document.querySelectorAll('.search-box input');
  searchInputs.forEach((input) => {
    input.addEventListener('input', () => {
      const { value } = input;
      const table = input.closest('.panel-card')?.querySelector('.data-table') || document.querySelector('.data-table');
      if (!table) return;
      const rows = [...table.querySelectorAll('tbody tr')];
      rows.forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(value.toLowerCase()) ? '' : 'none';
      });
    });
  });
});
