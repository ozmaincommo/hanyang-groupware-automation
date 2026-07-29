(function () {
  const index = window.__CATALOG_INDEX__ || [];
  const catalog = window.__CATALOG__ || {};

  const listEl = document.getElementById("menu-list");
  const imgEl = document.getElementById("screenshot");
  const boxesEl = document.getElementById("boxes");
  const detailEl = document.getElementById("detail");

  let currentItemId = null;
  let currentEntry = null;
  let activeBoxEl = null;

  function renderList() {
    listEl.innerHTML = "";
    index.forEach((item) => {
      const li = document.createElement("li");
      li.dataset.itemId = item.itemId;

      const dot = document.createElement("span");
      dot.className = "status-dot " + item.status;

      const label = document.createElement("span");
      label.textContent = `${item.label} (${item.componentCount})`;
      label.title = item.label;

      li.appendChild(label);
      li.appendChild(dot);
      li.addEventListener("click", () => selectItem(item.itemId));
      listEl.appendChild(li);
    });
  }

  function selectItem(itemId) {
    const entry = catalog[itemId];
    if (!entry || !entry.screenshotFile) {
      detailEl.innerHTML = `<p id="detail-placeholder">이 항목은 아직 리컨 결과(스크린샷)가 없습니다.</p>`;
      boxesEl.innerHTML = "";
      imgEl.removeAttribute("src");
      currentItemId = itemId;
      currentEntry = null;
      highlightActiveListItem(itemId);
      return;
    }
    currentItemId = itemId;
    currentEntry = entry;
    highlightActiveListItem(itemId);

    imgEl.src = `../output/catalog/${entry.screenshotFile}`;
    imgEl.onload = () => renderBoxes(entry);
    detailEl.innerHTML = `<p id="detail-placeholder">버튼 박스를 클릭하면 상세 정보가 여기 표시됩니다.</p>`;
  }

  function highlightActiveListItem(itemId) {
    Array.from(listEl.children).forEach((li) => {
      li.classList.toggle("active", li.dataset.itemId === itemId);
    });
  }

  function renderBoxes(entry) {
    boxesEl.innerHTML = "";
    boxesEl.style.width = imgEl.clientWidth + "px";
    boxesEl.style.height = imgEl.clientHeight + "px";

    const scaleX = imgEl.clientWidth / imgEl.naturalWidth;
    const scaleY = imgEl.clientHeight / imgEl.naturalHeight;

    (entry.components || []).forEach((comp, i) => {
      if (!comp.bbox) return;
      const box = document.createElement("div");
      box.className = "comp-box";
      box.style.left = comp.bbox.x * scaleX + "px";
      box.style.top = comp.bbox.y * scaleY + "px";
      box.style.width = comp.bbox.width * scaleX + "px";
      box.style.height = comp.bbox.height * scaleY + "px";

      const label = document.createElement("span");
      label.className = "label";
      label.textContent = comp.id || comp.text || `#${i}`;
      box.appendChild(label);

      box.addEventListener("click", (e) => {
        e.stopPropagation();
        if (activeBoxEl) activeBoxEl.classList.remove("active");
        box.classList.add("active");
        activeBoxEl = box;
        renderDetail(comp);
      });

      boxesEl.appendChild(box);
    });
  }

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  function renderDetail(comp) {
    detailEl.innerHTML = `
      <h2>${esc(comp.id || comp.text || "(이름 없음)")}</h2>
      <dl>
        <dt>tag / type</dt><dd>${esc(comp.tag)}${comp.type ? " / " + esc(comp.type) : ""}</dd>
        <dt>text / value</dt><dd>${esc(comp.text)}</dd>
        <dt>class</dt><dd>${esc(comp.class)}</dd>
        <dt>onclick</dt><dd>${esc(comp.onclick)}</dd>
        <dt>visible</dt><dd>${esc(comp.visible)}</dd>
        <dt>functionSummary</dt><dd>${esc(comp.functionSummary) || "(미작성)"}</dd>
        <dt>reviewNotes</dt><dd>${esc(comp.reviewNotes) || "(미작성)"}</dd>
      </dl>
    `;
  }

  window.addEventListener("resize", () => {
    if (currentEntry) renderBoxes(currentEntry);
  });

  renderList();
  if (index.length > 0) selectItem(index[0].itemId);
})();
