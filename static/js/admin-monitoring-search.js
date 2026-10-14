document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("implementationMonitoringSearch");
  const tableBody = document.querySelector(
    ".implementation-monitoring-table tbody",
  );
  const count = document.getElementById("implementationMonitoringCount");
  const emptyRow = tableBody?.querySelector("[data-monitoring-empty]");
  const noResultsRow = tableBody?.querySelector("[data-monitoring-no-results]");
  if (!searchInput || !tableBody || !count || !noResultsRow) return;

  const rows = [...tableBody.querySelectorAll("[data-monitoring-record]")];
  const filterRows = () => {
    const query = searchInput.value.trim().toLocaleLowerCase("id");
    let visibleCount = 0;

    rows.forEach((row) => {
      const matches = row.textContent
        .trim()
        .toLocaleLowerCase("id")
        .includes(query);
      row.hidden = !matches;
      if (matches) visibleCount += 1;
    });

    count.textContent = String(visibleCount);
    noResultsRow.hidden = !query || visibleCount > 0 || rows.length === 0;
    if (emptyRow) emptyRow.hidden = rows.length > 0;
  };

  searchInput.addEventListener("input", filterRows);
});
