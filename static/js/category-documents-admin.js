document.addEventListener("DOMContentLoaded", () => {
  const panel = document.querySelector(".category-document-admin");
  const tableBody = document.querySelector("#categoryDocumentsTable tbody");
  const dialog = document.getElementById("categoryDocumentDialog");
  const form = document.getElementById("categoryDocumentForm");
  const feedback = document.getElementById("categoryDocumentFeedback");
  const searchInput = document.getElementById("categoryDocumentSearch");
  if (!panel || !tableBody || !dialog || !form) return;

  const category = panel.dataset.category;
  let allDocuments = [];
  let categoryDocuments = [];
  const api = async (path, options = {}) => {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    if (options.method && !["GET", "HEAD"].includes(options.method.toUpperCase())) {
      headers.set(
        "X-CSRF-Token",
        document.querySelector('meta[name="csrf-token"]')?.content || "",
      );
    }
    const response = await fetch(path, { ...options, headers });
    const result = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(result.detail || `Permintaan gagal (${response.status})`);
    return result;
  };
  const announce = (message, isError = false) => {
    feedback.textContent = message;
    feedback.dataset.state = isError ? "error" : "success";
  };
  const cell = (row, value) => {
    const element = document.createElement("td");
    element.textContent = String(value ?? "");
    row.append(element);
    return element;
  };
  const actionButton = (label, icon, handler, className = "icon-btn") => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.title = label;
    button.setAttribute("aria-label", label);
    const glyph = document.createElement("i");
    glyph.dataset.lucide = icon;
    glyph.setAttribute("aria-hidden", "true");
    button.append(glyph);
    button.addEventListener("click", handler);
    return button;
  };

  const populateParentSelect = (fieldName, parentCategory, selectedId = "") => {
    const select = form.elements[fieldName];
    const label = select?.closest("[data-parent-link]");
    if (!select || !label) return;
    label.hidden =
      (fieldName === "standard_id" && category !== "Pedoman") ||
      (fieldName === "guideline_id" && category !== "SOP");
    const options = allDocuments.filter(
      (item) => item.kategori === parentCategory,
    );
    select.replaceChildren(new Option("Tidak dihubungkan", ""));
    options.forEach((item) => select.add(new Option(item.judul, item.id)));
    select.value = selectedId || "";
  };

  const openForm = (record = null) => {
    form.reset();
    form.elements.id.value = record?.id || "";
    form.elements.kategori.value = category;
    form.elements.kode.value = record?.kode || record?.no_dokumen || "";
    form.elements.judul.value = record?.judul || "";
    form.elements.tahun.value = record?.tahun || new Date().getFullYear();
    form.elements.link_download.value =
      record?.link_download || record?.file_url || "";
    form.elements.status.value = record?.status || "privat";
    populateParentSelect(
      "standard_id",
      "Standar PT",
      record?.standard_id || "",
    );
    populateParentSelect(
      "guideline_id",
      "Pedoman",
      record?.guideline_id || record?.parent_document_id || "",
    );
    document.getElementById("categoryDocumentDialogTitle").textContent = record
      ? `Edit ${category}`
      : `Tambah ${category}`;
    dialog.showModal();
  };

  const render = (records) => {
    tableBody.replaceChildren();
    document.getElementById("categoryDocumentCount").textContent =
      records.length;
    document.getElementById("categoryDocumentTotal").textContent =
      categoryDocuments.length;
    if (!records.length) {
      const row = document.createElement("tr");
      const hasQuery = Boolean(searchInput?.value.trim());
      const empty = cell(
        row,
        hasQuery
          ? `Tidak ada dokumen ${category} yang cocok dengan pencarian.`
          : `Belum ada dokumen ${category}.`,
      );
      empty.colSpan = 6;
      tableBody.append(row);
      return;
    }
    records.forEach((item) => {
      const row = document.createElement("tr");
      cell(row, item.kode || item.no_dokumen);
      cell(row, item.judul);
      cell(row, item.tahun || String(item.created_at || "").slice(0, 4));
      const isPublic = item.status === "publik";
      const status = cell(row, isPublic ? "Publik" : "Privat");
      status.className = `document-status ${isPublic ? "public" : "private"}`;
      const link = cell(row, "Buka link");
      const anchor = document.createElement("a");
      anchor.href = item.link_download || item.file_url;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = "Buka link";
      link.replaceChildren(anchor);
      const actions = document.createElement("td");
      actions.className = "document-row-actions";
      actions.append(
        actionButton(`Edit ${item.judul}`, "pencil", () => openForm(item)),
        actionButton(
          isPublic ? "Jadikan privat" : "Jadikan publik",
          isPublic ? "eye-off" : "eye",
          async () => {
            try {
              await api(
                `/admin/documents/toggle-status/${encodeURIComponent(item.id)}`,
                { method: "POST" },
              );
              announce(
                isPublic
                  ? "Dokumen sekarang privat."
                  : "Dokumen sekarang publik.",
              );
              await loadDocuments();
            } catch (error) {
              announce(error.message, true);
            }
          },
        ),
        actionButton(
          `Hapus ${item.judul}`,
          "trash-2",
          async () => {
            if (!window.confirm(`Hapus dokumen “${item.judul}”?`)) return;
            try {
              await api(
                `/admin/documents/delete/${encodeURIComponent(item.id)}`,
                { method: "POST" },
              );
              announce("Dokumen berhasil dihapus.");
              await loadDocuments();
            } catch (error) {
              announce(error.message, true);
            }
          },
          "btn btn-small btn-danger",
        ),
      );
      row.append(actions);
      tableBody.append(row);
    });
    window.lucide?.createIcons();
  };

  const loadDocuments = async () => {
    announce("Memuat dokumen...");
    try {
      const result = await api("/api/admin/documents");
      allDocuments = result.documents || [];
      populateParentSelect("standard_id", "Standar PT");
      populateParentSelect("guideline_id", "Pedoman");
      categoryDocuments = allDocuments.filter(
        (item) => item.kategori === category,
      );
      filterDocuments();
      announce(`${categoryDocuments.length} ${category} dimuat.`);
    } catch (error) {
      announce(error.message, true);
    }
  };

  const filterDocuments = () => {
    const query = searchInput?.value.trim().toLocaleLowerCase("id") || "";
    const matchingDocuments = categoryDocuments.filter((item) => {
      const searchableText = [
        item.kode,
        item.no_dokumen,
        item.judul,
        item.tahun || String(item.created_at || "").slice(0, 4),
        item.status,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase("id");
      return searchableText.includes(query);
    });
    render(matchingDocuments);
  };

  searchInput?.addEventListener("input", filterDocuments);
  document
    .getElementById("reloadCategoryDocuments")
    .addEventListener("click", loadDocuments);
  document
    .getElementById("addCategoryDocument")
    .addEventListener("click", () => openForm());
  document
    .getElementById("cancelCategoryDocument")
    .addEventListener("click", () => dialog.close());
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      kode: form.elements.kode.value.trim(),
      judul: form.elements.judul.value.trim(),
      kategori: category,
      tahun: form.elements.tahun.value,
      link_download: form.elements.link_download.value.trim(),
      status: form.elements.status.value,
      ...(category === "Pedoman"
        ? { standard_id: form.elements.standard_id.value }
        : {}),
      ...(category === "SOP"
        ? { guideline_id: form.elements.guideline_id.value }
        : {}),
    };
    const id = form.elements.id.value;
    try {
      await api(
        id
          ? `/admin/documents/edit/${encodeURIComponent(id)}`
          : "/admin/documents/add",
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      );
      dialog.close();
      announce(
        id ? "Perubahan dokumen disimpan." : "Dokumen berhasil ditambahkan.",
      );
      await loadDocuments();
    } catch (error) {
      announce(error.message, true);
    }
  });
  loadDocuments();
});
