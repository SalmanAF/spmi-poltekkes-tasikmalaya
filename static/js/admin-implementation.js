document.addEventListener("DOMContentLoaded", () => {
  const documentSelect = document.getElementById("implementationDocumentSelect");
  const monitoringForm = document.getElementById("implementationMonitoringForm");
  const rows = [...document.querySelectorAll(".ppepp-stage-row")];
  const csrfToken =
    document.querySelector('meta[name="csrf-token"]')?.content || "";

  documentSelect?.addEventListener("change", () => {
    const selectedId = documentSelect.value;
    window.location.href = selectedId
      ? `/admin/implementasi?document_id=${encodeURIComponent(selectedId)}`
      : "/admin/implementasi";
  });

  const request = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        ...(options.headers || {}),
      },
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.detail || `Permintaan gagal (${response.status})`);
    }
    return result;
  };

  const notify = (element, message, isError = false) => {
    if (!element) return;
    element.textContent = message;
    element.dataset.state = isError ? "error" : "success";
  };

  const setInputsDisabled = (row, disabled) => {
    row.querySelectorAll("textarea").forEach((input) => {
      input.disabled = disabled;
    });
  };

  const saveSnapshot = (row) => {
    row.querySelectorAll("textarea").forEach((input) => {
      input.dataset.savedValue = input.value;
    });
  };

  const setSavedState = (row, exists) => {
    row.dataset.exists = String(exists);
    setInputsDisabled(row, exists);
    row.querySelector('[data-action="save"]').hidden = exists;
    row.querySelector('[data-action="edit"]').hidden = !exists;
    row.querySelector('[data-action="cancel"]').hidden = true;
    row.querySelector('[data-action="delete"]').hidden = !exists;
    saveSnapshot(row);
  };

  const updateCompleteness = () => {
    const complete = rows.length === 5 && rows.every((row) => {
      if (row.dataset.exists !== "true") return false;
      return [...row.querySelectorAll("textarea")].every((input) =>
        input.value.trim(),
      );
    });
    const label = document.querySelector("[data-ppepp-completeness]");
    if (label) {
      label.textContent = complete
        ? "Narasi lima tahap terisi lengkap"
        : "Pengisian PPEPP belum lengkap";
      label.dataset.complete = String(complete);
    }
  };

  rows.forEach((row) => {
    saveSnapshot(row);
    row.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.action;
        const documentId = documentSelect?.value;
        const stage = row.dataset.stage;
        const feedback = row.querySelector("[data-stage-feedback]");
        if (!documentId) return;

        if (action === "edit") {
          setInputsDisabled(row, false);
          row.querySelector('[data-action="save"]').hidden = false;
          row.querySelector('[data-action="edit"]').hidden = true;
          row.querySelector('[data-action="cancel"]').hidden = false;
          row.querySelector('[data-action="delete"]').hidden = true;
          notify(feedback, "Mode edit. Simpan perubahan atau batalkan.");
          return;
        }

        if (action === "cancel") {
          row.querySelectorAll("textarea").forEach((input) => {
            input.value = input.dataset.savedValue || "";
          });
          setSavedState(row, row.dataset.exists === "true");
          notify(feedback, "");
          updateCompleteness();
          return;
        }

        if (action === "save") {
          const payload = Object.fromEntries(
            [...row.querySelectorAll("textarea")].map((input) => [
              input.name,
              input.value.trim(),
            ]),
          );
          try {
            const result = await request(
              `/api/admin/implementations/${encodeURIComponent(documentId)}/ppepp/${stage}`,
              { method: "PUT", body: JSON.stringify(payload) },
            );
            setSavedState(row, true);
            notify(feedback, "Tahap PPEPP berhasil disimpan.");
            row.dataset.recordId = result.stage.id;
            updateCompleteness();
          } catch (error) {
            notify(feedback, error.message, true);
          }
          return;
        }

        if (action === "delete") {
          if (!window.confirm(`Hapus data tahap ${stage} untuk dokumen ini?`)) {
            return;
          }
          try {
            await request(
              `/api/admin/implementations/${encodeURIComponent(documentId)}/ppepp/${stage}`,
              { method: "DELETE" },
            );
            row.querySelectorAll("textarea").forEach((input) => {
              input.value = "";
              input.dataset.savedValue = "";
            });
            setSavedState(row, false);
            notify(feedback, "Data tahap PPEPP berhasil dihapus.");
            updateCompleteness();
          } catch (error) {
            notify(feedback, error.message, true);
          }
        }
      });
    });
  });

  document
    .getElementById("saveImplementationMonitoring")
    ?.addEventListener("click", async () => {
      if (!monitoringForm) return;
      const documentId = monitoringForm.dataset.documentId;
      const payload = Object.fromEntries(
        [...monitoringForm.querySelectorAll("[name]")].map((input) => [
          input.name,
          input.value.trim() || null,
        ]),
      );
      try {
        await request(
          `/api/admin/implementations/${encodeURIComponent(documentId)}/monitoring`,
          { method: "PUT", body: JSON.stringify(payload) },
        );
        notify(
          document.getElementById("implementationMonitoringFeedback"),
          "Informasi monitoring berhasil disimpan.",
        );
      } catch (error) {
        notify(
          document.getElementById("implementationMonitoringFeedback"),
          error.message,
          true,
        );
      }
    });

  updateCompleteness();
});
