document.addEventListener("DOMContentLoaded", () => {
  const explorer = document.getElementById("integrationExplorer");
  if (!explorer) return;

  let documents = [];
  try {
    documents = JSON.parse(explorer.dataset.documents || "[]");
  } catch {
    documents = [];
  }

  const byId = new Map(
    documents.map((document) => [String(document.id), document]),
  );
  const policySelect = document.getElementById("policySelect");
  const standardSelect = document.getElementById("standardSelect");
  const guidelineSelect = document.getElementById("guidelineSelect");
  const policySelection = document.getElementById("policySelection");
  const standardSelection = document.getElementById("standardSelection");
  const guidelineSelection = document.getElementById("guidelineSelection");
  const procedureSelection = document.getElementById("procedureSelection");
  const formSelection = document.getElementById("formSelection");
  const kindLabel = {
    kebijakan: "Kebijakan",
    "standar-pt": "Standar PT",
    pedoman: "Pedoman",
    sop: "SOP",
    formulir: "Formulir",
    lainnya: "Subjudul",
  };

  const renderDocument = (record) => {
    const card = document.createElement("article");
    card.className = "map-document";
    const type = document.createElement("span");
    type.textContent = kindLabel[record.type] || record.type;
    const title = document.createElement("a");
    title.textContent = record.name;
    title.href = `/dokumen/${encodeURIComponent(record.id)}`;
    card.append(type, title);
    if (record.download_allowed) {
      const download = document.createElement("a");
      download.className = "map-download";
      download.href = `/dokumen/${encodeURIComponent(record.id)}/unduh`;
      download.textContent = "Unduh dokumen";
      card.append(download);
    }
    return card;
  };

  const matchesRelation = (document, parentId, parentType) => {
    if (!parentId) return false;
    const links = Array.isArray(document.related_ids)
      ? document.related_ids.map(String)
      : [];
    if (links.includes(String(parentId))) return true;

    const parentDocument = byId.get(String(parentId));
    if (parentDocument) {
      const parentLinks = Array.isArray(parentDocument.related_ids)
        ? parentDocument.related_ids.map(String)
        : [];
      if (parentLinks.includes(String(document.id))) return true;
    }

    if (parentType === "standar-pt") {
      return String(document.standard_id || "") === String(parentId);
    }
    if (parentType === "pedoman") {
      return String(document.guideline_id || "") === String(parentId);
    }
    return false;
  };

  const relatedStandardForPolicy = (policyId) => {
    const policy = byId.get(String(policyId || ""));
    if (!policy) return [];
    const targetStandardId = String(policy.standard_id || "");
    if (targetStandardId) {
      return documents.filter(
        (item) => item.type === "standar-pt" && String(item.id) === targetStandardId,
      );
    }
    return documents.filter(
      (item) =>
        item.type === "standar-pt" &&
        documents.some(
          (document) =>
            document.type === "kebijakan" &&
            String(document.id) === String(policyId) &&
            matchesRelation(item, document.id, "kebijakan"),
        ),
    );
  };

  const firstStandardWithGuidelines = () =>
    documents.find(
      (item) =>
        item.type === "standar-pt" &&
        documents.some(
          (document) =>
            document.type === "pedoman" &&
            matchesRelation(document, item.id, "standar-pt"),
        ),
    ) || null;

  const populateSelect = (select, label, items, grouped = false) => {
    if (!select) return;
    const firstOption = new Option(label, "");
    select.replaceChildren(firstOption);
    const groups = new Map();
    items.forEach((item) => {
      const groupName = grouped ? String(item.subjudul || "").trim() : "";
      if (!groupName) {
        select.add(new Option(item.name, item.id));
        return;
      }
      const year = String(item.tahun_integrasi || "").trim();
      const label = year ? `${year} · ${groupName}` : groupName;
      if (!groups.has(label)) {
        const group = document.createElement("optgroup");
        group.label = label;
        groups.set(label, group);
        select.add(group);
      }
      groups.get(label).append(new Option(item.name, item.id));
    });
    select.disabled = items.length === 0;
  };

  const paintSelection = (container, items, emptyText) => {
    container.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "muted-note";
      empty.textContent = emptyText;
      container.append(empty);
      return;
    }
    items.forEach((item) => container.append(renderDocument(item)));
  };

  const refreshPolicySelection = () => {
    const policyOptions = documents.filter((item) => item.type === "kebijakan");
    populateSelect(policySelect, "Pilih Kebijakan", policyOptions);

    const selectedId = policySelect?.value || "";
    const selection = selectedId ? [byId.get(selectedId)].filter(Boolean) : policyOptions;
    paintSelection(
      policySelection,
      selection,
      "Belum ada Kebijakan publik.",
    );

    if (standardSelect) {
      const options = documents.filter(
        (item) =>
          item.type === "standar-pt" &&
          String(item.standard_id || "") === String(item.id),
      );
      populateSelect(standardSelect, "Pilih Standar PT", options, true);
    }

    if (!selectedId) {
      paintSelection(
        standardSelection,
        [],
        "Pilih kebijakan untuk melihat standar terkait.",
      );
      return;
    }

    const related = relatedStandardForPolicy(selectedId);
    if (related.length) {
      const nextStandard = related[0];
      if (standardSelect) {
        standardSelect.value = nextStandard.id;
      }
      paintSelection(
        standardSelection,
        related,
        "Standar terkait.",
      );
      standardSelect?.dispatchEvent(new Event("change"));
      return;
    }

    paintSelection(
      standardSelection,
      [],
      "Tidak ada standar terkait yang tercatat untuk kebijakan ini.",
    );
  };

  policySelect?.addEventListener("change", () => {
    refreshPolicySelection();
  });

  standardSelect?.addEventListener("change", () => {
    const selectedId = standardSelect.value;
    const selectedStandard = byId.get(selectedId);
    const subheadings = documents.filter(
      (item) =>
        item.type === "lainnya" &&
        String(item.standard_id || "") === String(selectedId),
    );
    const related = documents.filter(
      (item) =>
        item.type === "pedoman" &&
        matchesRelation(item, selectedId, "standar-pt"),
    );
    paintSelection(
      standardSelection,
      selectedId
        ? [selectedStandard, ...subheadings].filter(Boolean)
        : [],
      "Pilih standar untuk melihat pedoman terkait.",
    );
    guidelineSelect.replaceChildren(new Option("Pilih Pedoman terkait", ""));
    related.forEach((item) =>
      guidelineSelect.add(new Option(item.name, item.id)),
    );
    guidelineSelect.disabled = related.length === 0;
    paintSelection(
      guidelineSelection,
      related,
      selectedId
        ? "Tidak ada pedoman terkait yang tercatat."
        : "Pilih standar terlebih dahulu.",
    );
    procedureSelection.innerHTML =
      '<p class="muted-note">Pilih pedoman untuk melihat SOP terkait.</p>';
    const forms = documents.filter(
      (item) => item.type === "formulir" && matchesRelation(item, selectedId, "standar-pt"),
    );
    paintSelection(
      formSelection,
      forms,
      selectedId ? "Tidak ada formulir terkait yang tercatat." : "Pilih standar untuk melihat formulir terkait.",
    );
  });

  guidelineSelect?.addEventListener("change", () => {
    const selectedId = guidelineSelect.value;
    const guideline = byId.get(selectedId);
    const related = documents.filter(
      (item) =>
        item.type === "sop" && matchesRelation(item, selectedId, "pedoman"),
    );
    paintSelection(
      guidelineSelection,
      guideline ? [guideline] : [],
      "Pilih pedoman terkait.",
    );
    paintSelection(
      procedureSelection,
      related,
      selectedId
        ? "Tidak ada SOP terkait yang tercatat."
        : "Pilih pedoman untuk melihat SOP terkait.",
    );
  });

  if (policySelect) {
    const policyOptions = documents.filter((item) => item.type === "kebijakan");
    if (policyOptions.length) {
      const firstPolicy = policyOptions[0];
      policySelect.value = firstPolicy.id;
      refreshPolicySelection();
    } else {
      populateSelect(policySelect, "Pilih Kebijakan", []);
      paintSelection(policySelection, [], "Belum ada Kebijakan publik.");
    }
  }

  if (standardSelect) {
    const defaultStandard = firstStandardWithGuidelines();
    if (defaultStandard) {
      standardSelect.value = defaultStandard.id;
      standardSelect.dispatchEvent(new Event("change"));
    }
  }
});
