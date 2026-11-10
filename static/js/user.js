document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".mobile-nav-toggle");
  const navigation = document.getElementById("user-navigation");
  if (toggle && navigation) {
    toggle.addEventListener("click", () => {
      const isOpen = navigation.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
      toggle.setAttribute(
        "aria-label",
        isOpen ? "Tutup navigasi" : "Buka navigasi",
      );
      toggle.innerHTML = `<i data-lucide="${isOpen ? "x" : "menu"}" aria-hidden="true"></i>`;
      if (window.lucide) window.lucide.createIcons();
    });
    navigation.addEventListener("click", (event) => {
      if (event.target.closest("a")) {
        navigation.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && navigation.classList.contains("is-open")) {
        navigation.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  }

  const qrTarget = document.getElementById("documentQr");
  if (qrTarget && window.QRCode) {
    new window.QRCode(qrTarget, {
      text: qrTarget.dataset.qrUrl || window.location.href,
      width: 92,
      height: 92,
      colorDark: "#102c3e",
      colorLight: "#ffffff",
      correctLevel: window.QRCode.CorrectLevel.M,
    });
  }

  document.querySelectorAll("[data-share-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      const shareUrl = button.dataset.shareUrl || window.location.href;
      try {
        if (navigator.share) {
          await navigator.share({ title: document.title, url: shareUrl });
        } else {
          await navigator.clipboard.writeText(shareUrl);
          showUserToast("Tautan dokumen disalin.");
        }
      } catch (error) {
        if (error.name !== "AbortError")
          showUserToast("Tautan tidak dapat dibagikan.");
      }
    });
  });

  const latestDocuments = document.getElementById("publicLatestDocuments");
  if (latestDocuments) {
    fetch("/api/documents/public")
      .then((response) => {
        if (!response.ok) throw new Error("Data dokumen gagal dimuat.");
        return response.json();
      })
      .then((payload) => {
        renderPublicStats(payload.statistics || {});
        renderLatestPublicDocuments(latestDocuments, payload.documents || []);
      })
      .catch(() => showUserToast("Dokumen publik belum dapat dimuat."));
  }
});

function renderPublicStats(statistics) {
  document.querySelectorAll("[data-public-stat]").forEach((element) => {
    const key = element.dataset.publicStat;
    element.textContent = String(statistics[key] ?? 0);
  });
}

function makeDocumentLink(documentRecord, text, className = "") {
  const link = document.createElement("a");
  link.className = className;
  link.href = `/dokumen/${encodeURIComponent(documentRecord.id)}`;
  link.textContent = text;
  return link;
}

function renderLatestPublicDocuments(container, documents) {
  const latest = [...documents]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 6);
  container.replaceChildren();
  if (!latest.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const heading = document.createElement("h3");
    heading.textContent = "Belum ada dokumen publik";
    const message = document.createElement("p");
    message.textContent =
      "Dokumen akan tampil setelah dipublikasikan oleh pengelola.";
    empty.append(heading, message);
    container.append(empty);
    return;
  }
  const list = document.createElement("div");
  list.className = "latest-list";
  latest.forEach((item) => {
    const row = document.createElement("article");
    row.className = "latest-row";
    const name = makeDocumentLink(item, item.judul);
    name.className = "latest-info";
    const category = document.createElement("span");
    category.textContent = `${item.kategori} · ${
      item.document_date ||
      item.document_year ||
      item.tahun ||
      "Tanggal dokumen tidak tersedia"
    }`;
    name.append(category);
    const uploadDate = document.createElement("time");
    uploadDate.textContent = `Diunggah ${item.created_at || "tidak tersedia"}`;
    const preview = makeDocumentLink(
      item,
      "Detail",
      "button button-small button-muted",
    );
    const actions = document.createElement("div");
    actions.className = "latest-actions";
    actions.append(preview);
    if (item.download_allowed) {
      const download = document.createElement("a");
      download.className = "icon-action";
      download.href =
        item.tipe_sumber === "drive_link"
          ? item.file_url
          : `/dokumen/${encodeURIComponent(item.id)}/unduh`;
      download.setAttribute("aria-label", `Unduh ${item.judul}`);
      download.textContent = "↓";
      actions.append(download);
    }
    row.append(name, uploadDate, actions);
    list.append(row);
  });
  container.append(list);
}

function showUserToast(message) {
  const toast = document.querySelector(".user-toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showUserToast.timeout);
  showUserToast.timeout = window.setTimeout(
    () => toast.classList.remove("show"),
    2400,
  );
}
