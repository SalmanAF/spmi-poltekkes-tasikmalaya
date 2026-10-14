document.addEventListener("DOMContentLoaded", () => {
  const endpoints = {
    kelengkapan: "/api/v1/laporan/kelengkapan",
    integrasi: "/api/v1/laporan/integrasi",
    implementasi: "/api/v1/laporan/implementasi",
    revisi: "/api/v1/laporan/revisi",
    perkembangan: "/api/v1/laporan/perkembangan",
  };

  const setReport = (name, summary, detail) => {
    const card = document.querySelector(`[data-report="${name}"]`);
    if (!card) return;
    card.querySelector("[data-report-summary]").textContent = summary;
    card.querySelector("[data-report-detail]").textContent = detail;
  };

  const loadReport = async (name, render) => {
    try {
      const response = await fetch(endpoints[name], {
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(
          response.status === 401
            ? "Sesi admin berakhir. Login kembali untuk melihat laporan."
            : `Laporan gagal dimuat (${response.status}).`,
        );
      }
      render(await response.json());
    } catch (error) {
      setReport(name, "Laporan tidak dapat dimuat.", error.message);
    }
  };

  loadReport("kelengkapan", (report) => {
    setReport(
      "kelengkapan",
      `${report.siap_audit} dari ${report.total_dokumen} dokumen siap audit (${report.persentase_siap_audit}%).`,
      `${report.belum_lengkap} dokumen belum lengkap.`,
    );
  });

  loadReport("integrasi", (report) => {
    setReport(
      "integrasi",
      `${report.integrasi_lengkap} dari ${report.total_dokumen} dokumen terintegrasi lengkap (${report.persentase_integrasi_lengkap}%).`,
      `${report.dokumen_yatim.length} relasi yatim; ${report.standar_tanpa_pedoman.length} Standar tanpa Pedoman; ${report.pedoman_tanpa_sop.length} Pedoman tanpa SOP.`,
    );
  });

  loadReport("implementasi", (report) => {
    setReport(
      "implementasi",
      `${report.terpantau} dokumen memiliki monitoring lengkap; ${report.ppepp_lengkap} dokumen menyelesaikan seluruh siklus PPEPP.`,
      `PPEPP lengkap ${report.persentase_ppepp_lengkap}%. Belum lengkap: ${report.ppepp_belum_lengkap.length} dokumen.`,
    );
  });

  loadReport("revisi", (report) => {
    setReport(
      "revisi",
      `${report.total} dokumen perlu perhatian.`,
      report.data_tersedia
        ? `${report.kedaluwarsa} kedaluwarsa · ${report.dalam_peninjauan} ditinjau · ${report.perlu_revisi} perlu revisi.`
        : report.message,
    );
  });

  loadReport("perkembangan", (report) => {
    const latest = report.perkembangan[report.perkembangan.length - 1];
    setReport(
      "perkembangan",
      latest
        ? `${latest.dokumen_baru} dokumen dicatat pada ${latest.tahun}; kumulatif ${latest.kumulatif}.`
        : "Belum ada data tahun pencatatan dokumen.",
      report.catatan,
    );
  });
});
