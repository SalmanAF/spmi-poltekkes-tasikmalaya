document.addEventListener("DOMContentLoaded", async () => {
  let statistics = { standar_pt: 0, pedoman: 0, sop: 0, total: 0 };
  try {
    const response = await fetch("/api/documents/public");
    if (!response.ok) throw new Error("Statistics request failed");
    statistics = (await response.json()).statistics;
  } catch {
    document.querySelectorAll("[data-admin-stat]").forEach((item) => {
      item.textContent = "0";
    });
  }

  document.querySelectorAll("[data-admin-stat]").forEach((item) => {
    item.textContent = String(statistics[item.dataset.adminStat] ?? 0);
  });

  const statusCanvas = document.getElementById("docStatusChart");
  if (statusCanvas && window.Chart) {
    new Chart(statusCanvas, {
      type: "doughnut",
      data: {
        labels: ["Standar PT", "Pedoman", "SOP"],
        datasets: [
          {
            data: [statistics.standar_pt, statistics.pedoman, statistics.sop],
            backgroundColor: ["#1683d8", "#20a65a", "#ff8a24"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: {
            display: true,
            position: "right",
            labels: {
              color: "#526477",
              boxWidth: 12,
              boxHeight: 12,
              padding: 16,
              usePointStyle: true,
              pointStyle: "circle",
              font: { size: 12, weight: 600 },
            },
          },
        },
      },
    });
  }

  const trendCanvas = document.getElementById("documentTrendChart");
  if (trendCanvas) {
    const message = document.createElement("p");
    message.className = "muted-note";
    message.textContent =
      "Riwayat perubahan belum tersedia pada skema dokumen saat ini.";
    trendCanvas.replaceWith(message);
  }
});
