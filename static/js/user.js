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

  const publicCatalog = document.querySelector("[data-public-catalog]");
  const latestDocuments = document.getElementById("publicLatestDocuments");
  if (publicCatalog || latestDocuments) {
    fetch("/api/documents/public")
      .then((response) => {
        if (!response.ok) throw new Error("Data dokumen gagal dimuat.");
        return response.json();
      })
      .then((payload) => {
        renderPublicStats(payload.statistics || {});
        if (publicCatalog)
          renderPublicCatalog(publicCatalog, payload.documents || []);
        if (latestDocuments)
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

function renderPublicCatalog(container, documents) {
  const query = new URLSearchParams(window.location.search);
  const typeAliases = {
    "standar-pt": "Standar PT",
    pedoman: "Pedoman",
    sop: "SOP",
  };
  const selectedCategory =
    typeAliases[query.get("jenis")] ||
    query.get("jenis") ||
    container.dataset.category ||
    "";
  const categoryFilter = query.get("kategori") || "";
  const search = (query.get("q") || "").toLocaleLowerCase("id");
  const year = query.get("tahun") || "";
  const format = (query.get("format") || "").toUpperCase();
  const downloadsOnly = container.dataset.downloadsOnly === "true";
  const sort = query.get("urut") || "terbaru";
  const filtered = documents.filter((item) => {
    const matchesCategory =
      !selectedCategory || item.kategori === selectedCategory;
    const matchesCategoryFilter =
      !categoryFilter || item.kategori === categoryFilter;
    const matchesYear = !year || item.created_at.startsWith(year);
    const matchesFormat = !format || item.file_format === format;
    const matchesDownload = !downloadsOnly || item.is_downloadable;
    const matchesSearch =
      !search ||
      `${item.judul} ${item.kategori} ${item.id}`
        .toLocaleLowerCase("id")
        .includes(search);
    return (
      matchesCategory &&
      matchesCategoryFilter &&
      matchesYear &&
      matchesFormat &&
      matchesDownload &&
      matchesSearch
    );
  });
  filtered.sort((left, right) =>
    sort === "nama"
      ? left.judul.localeCompare(right.judul, "id")
      : right.created_at.localeCompare(left.created_at),
  );
  const pageSize = 12;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const page = Math.min(
    Math.max(1, Number.parseInt(query.get("halaman") || "1", 10) || 1),
    pageCount,
  );
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const resultCount = document.querySelector(".result-total strong");
  if (resultCount) resultCount.textContent = String(filtered.length);
  const summary = document.querySelector(".results-toolbar span");
  if (summary)
    summary.textContent = `Menampilkan ${pageItems.length} dari ${filtered.length}`;
  container.replaceChildren();
  if (!pageItems.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const heading = document.createElement("h2");
    heading.textContent = "Dokumen tidak ditemukan.";
    const reset = document.createElement("a");
    reset.className = "button button-dark";
    reset.href = window.location.pathname;
    reset.textContent = "Reset Pencarian";
    empty.append(heading, reset);
    container.append(empty);
  }
  pageItems.forEach((item) => {
    const card = document.createElement("article");
    card.className = "document-card";
    const code = document.createElement("p");
    code.className = "document-code";
    code.textContent = item.id;
    const title = document.createElement("h2");
    title.append(makeDocumentLink(item, item.judul));
    const summaryText = document.createElement("p");
    summaryText.className = "document-description";
    summaryText.textContent =
      item.tipe_sumber === "drive_link"
        ? "Tersedia melalui Google Drive."
        : `Berkas ${item.file_format || "tersedia"}.`;
    const meta = document.createElement("div");
    meta.className = "document-meta";
    [item.kategori, item.tipe_sumber, item.created_at].forEach((value) => {
      const badge = document.createElement("span");
      badge.textContent = value;
      meta.append(badge);
    });
    const actions = document.createElement("div");
    actions.className = "document-card-bottom";
    const previewActions = document.createElement("div");
    const preview = document.createElement("a");
    preview.className = "button button-small button-muted";
    preview.textContent = "Lihat / Preview";
    preview.href =
      item.tipe_sumber === "drive_link"
        ? item.preview_url
        : `/dokumen/${encodeURIComponent(item.id)}`;
    if (item.tipe_sumber === "drive_link") {
      preview.target = "_blank";
      preview.rel = "noopener noreferrer";
    }
    previewActions.append(preview);
    if (item.is_downloadable) {
      const download = document.createElement("a");
      download.className = "button button-small button-dark";
      download.textContent = "Unduh";
      download.href = `/dokumen/${encodeURIComponent(item.id)}/unduh`;
      if (item.tipe_sumber === "drive_link") {
        download.target = "_blank";
        download.rel = "noopener noreferrer";
      }
      previewActions.append(download);
    }
    const date = document.createElement("time");
    date.textContent = item.created_at;
    actions.append(date, previewActions);
    card.append(code, title, summaryText, meta, actions);
    container.append(card);
  });
  let pagination = document.querySelector(".catalog-results .pagination");
  if (!pagination) {
    pagination = document.createElement("nav");
    pagination.className = "pagination";
    pagination.setAttribute("aria-label", "Paginasi katalog");
    container.after(pagination);
  }
  pagination.replaceChildren();
  if (pageCount > 1) {
    if (page > 1)
      pagination.append(
        makePageLink(query, page - 1, "Halaman sebelumnya", "‹"),
      );
    const pageLabel = document.createElement("span");
    pageLabel.textContent = `Halaman ${page} dari ${pageCount}`;
    pagination.append(pageLabel);
    if (page < pageCount)
      pagination.append(
        makePageLink(query, page + 1, "Halaman berikutnya", "›"),
      );
  }
}

function makePageLink(query, page, label, symbol) {
  const link = document.createElement("a");
  const params = new URLSearchParams(query);
  params.set("halaman", String(page));
  link.href = `${window.location.pathname}?${params.toString()}`;
  link.setAttribute("aria-label", label);
  link.textContent = symbol;
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
    category.textContent = `${item.kategori} · ${item.created_at}`;
    name.append(category);
    const preview = makeDocumentLink(
      item,
      "Detail",
      "button button-small button-muted",
    );
    const actions = document.createElement("div");
    actions.className = "latest-actions";
    actions.append(preview);
    if (item.is_downloadable) {
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
    row.append(name, actions);
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
