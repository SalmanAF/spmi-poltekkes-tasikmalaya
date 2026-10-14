const dashboardData = {
  standar: 0,
  pedoman: 0,
  sop: 0,
  total: 0,
  integrasi: 0,
  lengkap: 0,
  revisi: 0,
  belumAda: 0,
};

const statCards = [
  {
    key: "standar",
    value: dashboardData.standar,
    label: "Dokumen",
    color: "blue",
    icon: "shield-check",
    title: "Standar PT",
  },
  {
    key: "pedoman",
    value: dashboardData.pedoman,
    label: "Dokumen",
    color: "green",
    icon: "book-open",
    title: "Pedoman",
  },
  {
    key: "sop",
    value: dashboardData.sop,
    label: "Dokumen",
    color: "orange",
    icon: "settings",
    title: "SOP",
  },
  {
    key: "total",
    value: dashboardData.total,
    label: "Dokumen",
    color: "purple",
    icon: "file-stack",
    title: "Total Dokumen Publik",
  },
];

function renderDashboardCards() {
  const grid = document.getElementById("dashboardStats");
  if (!grid) return;

  grid.innerHTML = statCards
    .map(
      (card) => `
    <article class="dashboard-stat ${card.color}">
      <div class="icon-wrap"><span data-lucide="${card.icon}"></span></div>
      <div class="value">${dashboardData[card.key]}</div>
      <div class="label">${card.title}</div>
      <div class="label">${card.label}</div>
      <a href="#" class="detail-link">Lihat Detail →</a>
    </article>
  `,
    )
    .join("");

  if (window.lucide) {
    lucide.createIcons();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  fetch("/api/documents/public")
    .then((response) =>
      response.ok
        ? response.json()
        : Promise.reject(new Error("Statistik tidak tersedia")),
    )
    .then(({ statistics }) => {
      dashboardData.standar = statistics.standar_pt || 0;
      dashboardData.pedoman = statistics.pedoman || 0;
      dashboardData.sop = statistics.sop || 0;
      dashboardData.total = statistics.total || 0;
      dashboardData.lengkap = dashboardData.total;
      renderDashboardCards();
    })
    .catch(() => renderDashboardCards());
});
