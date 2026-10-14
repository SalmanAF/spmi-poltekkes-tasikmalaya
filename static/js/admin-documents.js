document.addEventListener("DOMContentLoaded", () => {
  const reloadButton = document.getElementById("reloadDocuments");
  const createForm = document.getElementById("documentCreateForm");
  const editDialog = document.getElementById("documentEditDialog");
  const editForm = document.getElementById("documentEditForm");
  const tableBody = document.querySelector("#adminDocumentsTable tbody");
  const feedback = document.getElementById("adminFeedback");
  const sourceType = document.getElementById("sourceType");
  const driveField = document.getElementById("driveUrlField");
  const fileField = document.getElementById("localFileField");
  if (!createForm || !tableBody) return;

  const api = async (path, options = {}) => {
    const headers = new Headers(options.headers || {});
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    if (options.method && !["GET", "HEAD"].includes(options.method.toUpperCase())) {
      headers.set("X-CSRF-Token", csrfToken || "");
    }
    const response = await fetch(path, { ...options, headers });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(
        payload.detail || `Permintaan gagal (${response.status})`,
      );
    return payload;
  };
  const announce = (message, isError = false) => {
    feedback.textContent = message;
    feedback.dataset.state = isError ? "error" : "success";
  };
  const safeText = (value) => String(value ?? "");
  const addCell = (row, value) => {
    const cell = document.createElement("td");
    cell.textContent = safeText(value);
    row.append(cell);
    return cell;
  };

  const renderRows = (documents) => {
    tableBody.replaceChildren();
    if (!documents.length) {
      const row = document.createElement("tr");
      const cell = addCell(row, "Belum ada dokumen.");
      cell.colSpan = 7;
      tableBody.append(row);
      return;
    }
    documents.forEach((document) => {
      const row = document.createElement("tr");
      addCell(row, document.judul);
      addCell(row, document.kategori);
      addCell(
        row,
        document.tipe_sumber === "drive_link" ? "Google Drive" : "Berkas lokal",
      );
      const statusCell = addCell(row, document.status);
      statusCell.className =
        document.status === "publik"
          ? "document-status public"
          : "document-status draft";
      addCell(row, document.is_downloadable ? "Diizinkan" : "Tidak diizinkan");
      addCell(row, document.created_at);
      const actions = document.createElement("td");
      actions.className = "document-row-actions";
      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.className = "icon-btn";
      editButton.title = "Edit dokumen";
      editButton.setAttribute("aria-label", `Edit ${document.judul}`);
      editButton.textContent = "Edit";
      editButton.addEventListener("click", () => openEdit(document));
      const toggleButton = document.createElement("button");
      toggleButton.type = "button";
      toggleButton.className = "btn btn-small btn-secondary";
      toggleButton.textContent =
        document.status === "publik" ? "Jadikan draft" : "Publikasikan";
      toggleButton.addEventListener("click", async () => {
        try {
          await api(`/api/admin/documents/${encodeURIComponent(document.id)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              status: document.status === "publik" ? "draft" : "publik",
            }),
          });
          announce("Status publikasi diperbarui.");
          await loadDocuments();
        } catch (error) {
          announce(error.message, true);
        }
      });
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "btn btn-small btn-danger";
      deleteButton.textContent = "Hapus";
      deleteButton.addEventListener("click", async () => {
        if (
          !window.confirm(
            `Hapus dokumen “${document.judul}” beserta berkas lokalnya?`,
          )
        )
          return;
        try {
          await api(`/api/admin/documents/${encodeURIComponent(document.id)}`, {
            method: "DELETE",
          });
          announce("Dokumen dihapus.");
          await loadDocuments();
        } catch (error) {
          announce(error.message, true);
        }
      });
      actions.append(editButton, toggleButton, deleteButton);
      row.append(actions);
      tableBody.append(row);
    });
  };

  const loadDocuments = async () => {
    announce("Memuat dokumen...");
    try {
      const payload = await api("/api/admin/documents");
      renderRows(payload.documents || []);
      announce(`${payload.documents.length} dokumen dimuat.`);
    } catch (error) {
      announce(error.message, true);
    }
  };

  const openEdit = (document) => {
    editForm.elements.id.value = document.id;
    editForm.elements.judul.value = document.judul;
    editForm.elements.kategori.value = document.kategori;
    editForm.elements.status.value = document.status;
    editForm.elements.is_downloadable.checked = document.is_downloadable;
    editDialog.showModal();
  };

  reloadButton?.addEventListener("click", loadDocuments);
  sourceType?.addEventListener("change", () => {
    const isLocal = sourceType.value === "local_file";
    driveField.hidden = isLocal;
    fileField.hidden = !isLocal;
    createForm.elements.file_url.required = !isLocal;
    createForm.elements.file.required = isLocal;
  });
  createForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(createForm);
    formData.set(
      "is_downloadable",
      String(createForm.elements.is_downloadable.checked),
    );
    try {
      await api("/api/admin/documents", { method: "POST", body: formData });
      createForm.reset();
      sourceType.dispatchEvent(new Event("change"));
      announce("Dokumen berhasil ditambahkan.");
      await loadDocuments();
    } catch (error) {
      announce(error.message, true);
    }
  });
  editForm?.addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault();
    const id = editForm.elements.id.value;
    const body = {
      judul: editForm.elements.judul.value,
      kategori: editForm.elements.kategori.value,
      status: editForm.elements.status.value,
      is_downloadable: editForm.elements.is_downloadable.checked,
    };
    try {
      await api(`/api/admin/documents/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      editDialog.close();
      announce("Perubahan dokumen disimpan.");
      await loadDocuments();
    } catch (error) {
      announce(error.message, true);
    }
  });
  loadDocuments();
});
