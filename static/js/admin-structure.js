document.addEventListener("DOMContentLoaded", () => {
  const yearSelect = document.getElementById("structureYear");
  const typeSelect = document.getElementById("structureType");
  const statusSelect = document.getElementById("structureStatus");
  const searchInput = document.getElementById("structureSearch");
  const treeContainer = document.getElementById("structureTree");
  const searchResults = document.getElementById("structureSearchResults");
  const message = document.getElementById("structureMessage");
  if (
    !yearSelect ||
    !typeSelect ||
    !statusSelect ||
    !searchInput ||
    !treeContainer ||
    !searchResults ||
    !message
  ) {
    return;
  }

  const apiBase = "/api/v1/struktur-dokumen";
  let searchTimer;

  const showError = (error) => {
    message.textContent = `Struktur dokumen tidak dapat dimuat: ${error.message}`;
    message.dataset.state = "error";
  };

  const fetchJson = async (url) => {
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error(
        response.status === 401
          ? "Sesi admin berakhir. Silakan login kembali."
          : `Permintaan gagal (${response.status}).`,
      );
    }
    return response.json();
  };

  const selectedParams = () => {
    const params = new URLSearchParams();
    if (yearSelect.value) params.set("tahun", yearSelect.value);
    return params;
  };

  const renderNode = (node, depth = 0) => {
    const branch = document.createElement(depth < 2 ? "details" : "div");
    branch.className = `structure-branch ${
      depth === 1 ? "structure-branch-pedoman" : ""
    } ${depth >= 2 ? "structure-branch-sop" : ""}`;
    if (depth < 2) branch.open = depth === 0;

    const heading = document.createElement(depth < 2 ? "summary" : "div");
    if (depth === 2) heading.className = "structure-node-main";
    const main = depth === 2 ? heading : document.createElement("span");
    if (depth < 2) main.className = "structure-node-main";

    const title = document.createElement("strong");
    title.textContent = node.judul;
    const metadata = document.createElement("small");
    metadata.textContent = `${node.kategori} · ${node.kode || "Tanpa kode"}`;
    main.append(title, metadata);

    const badges = document.createElement("span");
    badges.className = "structure-node-meta";
    const year = node.tahun_integrasi || node.tahun;
    if (year) {
      const yearBadge = document.createElement("span");
      yearBadge.textContent = `Tahun ${year}`;
      badges.append(yearBadge);
    }
    const statusBadge = document.createElement("span");
    statusBadge.textContent =
      node.status.charAt(0).toUpperCase() + node.status.slice(1);
    badges.append(statusBadge);
    main.append(badges);

    if (depth < 2) heading.append(main);
    branch.append(heading);

    if (node.children?.length) {
      const children = document.createElement("div");
      children.className = "structure-children";
      node.children.forEach((child) =>
        children.append(renderNode(child, depth + 1)),
      );
      branch.append(children);
    }
    return branch;
  };

  const setStatistics = (summary) => {
    document.getElementById("structureStandardCount").textContent =
      summary.per_tipe["Standar PT"];
    document.getElementById("structureGuidelineCount").textContent =
      summary.per_tipe.Pedoman;
    document.getElementById("structureProcedureCount").textContent =
      summary.per_tipe.SOP;
    document.getElementById("structureTotalCount").textContent =
      summary.total_dokumen;

    const selectedYear = yearSelect.value;
    if (!selectedYear) {
      const years = summary.tahun_tersedia;
      const existingValues = new Set(
        [...yearSelect.options].map((option) => option.value),
      );
      years.forEach((year) => {
        if (existingValues.has(year)) return;
        const option = document.createElement("option");
        option.value = year;
        option.textContent = year;
        yearSelect.append(option);
      });
    }
  };

  const renderTree = (tree) => {
    treeContainer.replaceChildren();
    const nodes = [...tree.standards, ...tree.unlinked];
    if (!nodes.length) {
      const empty = document.createElement("div");
      empty.className = "structure-empty";
      empty.textContent = "Tidak ada dokumen untuk tahun yang dipilih.";
      treeContainer.append(empty);
      return;
    }
    nodes.forEach((node) => treeContainer.append(renderNode(node)));
  };

  const renderSearchResults = (result) => {
    searchResults.replaceChildren();
    if (!result.documents.length) {
      const empty = document.createElement("div");
      empty.className = "structure-empty";
      empty.textContent = "Dokumen tidak ditemukan pada filter yang dipilih.";
      searchResults.append(empty);
      return;
    }
    result.documents.forEach((item) => {
      const row = document.createElement("article");
      row.className = "structure-search-item";
      const content = document.createElement("span");
      content.className = "structure-node-main";
      const title = document.createElement("strong");
      title.textContent = item.judul;
      const detail = document.createElement("small");
      detail.textContent = `${item.kategori} · ${item.kode} · ${
        item.tahun_integrasi || item.tahun || "Tahun tidak dicatat"
      } · ${item.status}`;
      content.append(title, detail);
      row.append(content);
      searchResults.append(row);
    });
  };

  const loadPageData = async () => {
    message.textContent = "Memuat struktur dokumen...";
    message.dataset.state = "loading";
    treeContainer.hidden = false;
    searchResults.hidden = true;

    try {
      const params = selectedParams();
      const query = params.toString() ? `?${params.toString()}` : "";
      const [summary, tree] = await Promise.all([
        fetchJson(`${apiBase}/summary${query}`),
        fetchJson(`${apiBase}/tree${query}`),
      ]);
      setStatistics(summary);
      renderTree(tree);
      message.textContent = yearSelect.value
        ? `Menampilkan struktur dokumen tahun ${yearSelect.value}. Dokumen induk lintas tahun ditampilkan sebagai konteks relasi.`
        : `Menampilkan semua tahun (${summary.total_dokumen} dokumen).`;
      message.dataset.state = "ready";
    } catch (error) {
      showError(error);
    }
  };

  const searchDocuments = async () => {
    const params = selectedParams();
    if (searchInput.value.trim()) params.set("keyword", searchInput.value.trim());
    if (typeSelect.value) params.set("tipe", typeSelect.value);
    if (statusSelect.value) params.set("status", statusSelect.value);
    message.textContent = "Mencari dokumen...";
    message.dataset.state = "loading";
    treeContainer.hidden = true;
    searchResults.hidden = false;
    try {
      const result = await fetchJson(
        `${apiBase}/search?${params.toString()}`,
      );
      renderSearchResults(result);
      message.textContent = `${result.total} dokumen ditemukan.`;
      message.dataset.state = "ready";
    } catch (error) {
      showError(error);
    }
  };

  const updateView = () => {
    if (searchInput.value.trim() || typeSelect.value || statusSelect.value) {
      searchDocuments();
    } else {
      loadPageData();
    }
  };

  yearSelect.addEventListener("change", updateView);
  typeSelect.addEventListener("change", updateView);
  statusSelect.addEventListener("change", updateView);
  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(updateView, 250);
  });

  loadPageData();
});
