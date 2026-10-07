"use strict";

// ---------- Tiện ích ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (t) => (t == null ? "–" : `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`);

const S = { settings: {}, voices: {}, providers: {}, scripts: [], sources: [], projects: [],
  fonts: [], colors: [], music: [], videoExt: [".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm", ".3gp"],
  scriptId: null, script: null, project: null, jobs: new Map() };

const ORIGIN = { competitor: "Đối thủ", template: "Mẫu", rewrite: "Đã viết lại", manual: "Tự viết", weekly: "Kế hoạch tuần", imported: "Nhập tài liệu", auto: "Từ video của bạn" };
const PLACEHOLDER = /\[[^\]]+\]/g;
const plain = (t) => String(t || "").normalize("NFD").replace(/\p{M}/gu, "").replace(/đ/g, "d").toLowerCase();
const POS = { top: "Trên", center: "Giữa", bottom: "Dưới" };
const PROJECT_DEFAULTS = { ratio: "9:16", fit: "blur", voice_on: true, subtitles: true, music: "auto",
  music_volume: 0.35, source_volume: 0.3, logo_on: true, fade: 0.25 };

async function api(method, path, body, form) {
  const opt = { method, headers: {} };
  if (form) opt.body = form;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, opt);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Lỗi ${res.status}`);
  return data;
}

let toastTimer;
function toast(msg) {
  let el = $(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.append(el); }
  el.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.remove(), 3500);
}

// ---------- Tác vụ nền ----------
function watchJob(job, label, onDone, onError) {
  let fails = 0;
  S.jobs.set(job.id, { label, message: job.message });
  renderJobs();
  const tick = async () => {
    let j;
    try { j = await api("GET", `/api/jobs/${job.id}`); fails = 0; } catch (e) {
      // mạng chập chờn thì thử lại; tác vụ không còn (app đã khởi động lại) thì thôi, không hỏi mãi
      if (++fails >= 5) { S.jobs.delete(job.id); renderJobs(); return; }
      setTimeout(tick, 3000); return;
    }
    S.jobs.get(job.id).message = j.message;
    renderJobs();
    if (j.status === "running") { setTimeout(tick, 1500); return; }
    S.jobs.delete(job.id);
    renderJobs();
    if (j.status === "done") onDone && onDone(j.result);
    else { toast(`${label}: ${j.error}`); onError && onError(j.error); }
  };
  setTimeout(tick, 1000);
}

function renderJobs() {
  const items = [...S.jobs.values()];
  $("#jobs").innerHTML = items.length
    ? `<span class="spin"></span> ${items.map((j) => `${esc(j.label)} · ${esc(j.message)}`).join(" | ")}`
    : "";
}

// ---------- Điều hướng ----------
function showPage(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.page === name));
  $$(".page").forEach((p) => p.classList.toggle("on", p.id === `page-${name}`));
  history.replaceState(null, "", `#${name}`);
}
$("#tabs").addEventListener("click", (e) => { if (e.target.dataset.page) showPage(e.target.dataset.page); });

// ================= KỊCH BẢN =================
async function loadScripts(selectId) {
  S.scripts = await api("GET", "/api/scripts");
  renderScriptList();
  if (typeof renderBatchScripts === "function") renderBatchScripts();
  if (selectId) selectScript(selectId);
  if (S.scripts.some((s) => s.status === "processing")) setTimeout(() => loadScripts(), 4000);
}

function batchLabel(b) {
  const m = /^tuan-(\d{4})-(\d\d)-(\d\d)$/.exec(b || "");
  return m ? `Tuần ${m[3]}/${m[2]}/${m[1]}` : b || "";
}

function scriptMatches(s, q) {
  if (!q) return true;
  const hay = plain([s.title, s.summary, s.product, s.code, s.channel, s.channel_name, s.group, s.hook_type].join(" "));
  const words = hay.split(/[^a-z0-9]+/);
  return plain(q).split(/\s+/).filter(Boolean).every((w) => (w.length <= 3 ? words.includes(w) : hay.includes(w)));
}

function renderScriptList() {
  const q = ($("#script-search") || {}).value || "";
  const list = S.scripts.filter((s) => scriptMatches(s, q));
  $("#script-count").textContent = q ? `${list.length}/${S.scripts.length}` : S.scripts.length;
  $("#script-list").innerHTML = list.length ? list.map((s) => `
    <div class="item ${s.id === S.scriptId ? "on" : ""}" data-id="${s.id}">
      ${s.poster ? `<img src="${esc(s.poster)}" alt="">` : `<div class="thumb-ph"></div>`}
      <div class="grow"><div class="t">${esc(s.title || "Chưa đặt tên")}</div>
        <div class="row small" style="gap:6px"><span class="chip ${s.origin}">${s.channel ? esc(s.channel) + " · " : ""}${ORIGIN[s.origin] || s.origin}</span>
          ${s.status === "processing" ? `<span class="chip processing">Đang phân tích</span>` : ""}
          ${s.status === "error" ? `<span class="chip error">Lỗi</span>` : ""}
          <span class="muted">${(s.beats || []).length} cảnh${s.batch ? ` · ${esc(batchLabel(s.batch))}` : ""}</span></div></div>
    </div>`).join("") : `<div class="empty small">${S.scripts.length ? "Không có kịch bản khớp" : "Chưa có kịch bản"}</div>`;
}
$("#script-search").addEventListener("input", renderScriptList);
$("#script-list").addEventListener("click", (e) => { const it = e.target.closest(".item"); if (it) selectScript(it.dataset.id); });

function selectScript(id) {
  S.scriptId = id;
  const found = S.scripts.find((s) => s.id === id);
  S.script = found ? structuredClone(found) : null;
  renderScriptList();
  renderScriptDetail();
}

function beatRow(b, i) {
  return `<tr data-i="${i}">
    <td class="muted">${i + 1}</td>
    <td><textarea data-k="shot" rows="3">${esc(b.shot)}</textarea></td>
    <td><textarea data-k="voice" rows="3">${esc(b.voice)}</textarea></td>
    <td><textarea data-k="text" rows="2">${esc(b.text)}</textarea>
      <select data-k="text_pos">${Object.entries(POS).map(([k, v]) => `<option value="${k}" ${b.text_pos === k ? "selected" : ""}>${v}</option>`).join("")}</select></td>
    <td style="width:70px"><input type="number" data-k="duration" step="0.5" min="0.5" value="${esc(b.duration ?? 3)}"></td>
    <td><button class="btn ghost sm" data-act="del-beat" title="Xoá cảnh">✕</button></td></tr>`;
}

function renderScriptDetail() {
  const s = S.script;
  const box = $("#script-detail");
  if (!s) { box.innerHTML = `<div class="card empty">Chọn một kịch bản bên trái.</div>`; return; }
  if (s.status === "processing") { box.innerHTML = `<div class="card empty"><span class="spin"></span> AI đang phân tích video đối thủ…</div>`; return; }
  box.innerHTML = `<div class="stack">
    <div class="card stack">
      <div class="row"><input type="text" id="sd-title" class="grow" value="${esc(s.title)}" style="font-weight:600;font-size:16px">
        <span class="chip ${s.origin}">${ORIGIN[s.origin] || ""}</span></div>
      ${s.status === "error" ? `<div class="err">Phân tích lỗi: ${esc(s.error)}</div>` : ""}
      ${s.video ? `<video src="${esc(s.video)}" controls playsinline style="max-height:320px;border-radius:10px;background:#000"></video>` : ""}
      <div class="fields">
        <div><div class="muted small">Kiểu hook</div>${esc(s.hook_type) || "–"}</div>
        <div><div class="muted small">Tóm tắt</div>${esc(s.summary) || "–"}</div>
        <div><div class="muted small">Vì sao hiệu quả</div>${esc(s.why_it_works) || "–"}</div>
      </div>
      ${s.transcript ? `<details><summary class="muted small">Lời thoại gốc (tự động)</summary><pre class="small" style="white-space:pre-wrap">${esc(s.transcript)}</pre></details>` : ""}
      ${(s.needs_info || []).length ? `<div class="warn"><b>Cần bổ sung:</b> ${s.needs_info.map(esc).join(" · ")}</div>` : ""}
    </div>
    <div class="card">
      <div class="row" style="margin-bottom:8px"><h3 class="grow">Các cảnh</h3>
        <button class="btn sm" data-act="add-beat">+ Thêm cảnh</button></div>
      <div style="overflow-x:auto"><table class="beats"><thead><tr><th>#</th><th>Cảnh quay</th><th>Lời đọc</th><th>Chữ trên màn hình</th><th>Giây</th><th></th></tr></thead>
        <tbody id="sd-beats">${(s.beats || []).map(beatRow).join("")}</tbody></table></div>
      ${(s.alt_hooks || []).length ? `<div style="margin-top:10px"><div class="muted small">Hook khác gợi ý</div>
        <ul class="small">${s.alt_hooks.map((h) => `<li><b>${esc(h.text)}</b> — ${esc(h.voice)}</li>`).join("")}</ul></div>` : ""}
    </div>
    <div class="card stack">
      <label class="f">Caption khi đăng<textarea id="sd-caption" rows="2">${esc(s.caption)}</textarea></label>
      <label class="f">Hashtag (cách nhau bằng dấu cách)<input type="text" id="sd-tags" value="${esc((s.hashtags || []).join(" "))}"></label>
      <div class="row"><button class="btn" data-act="save-script">Lưu thay đổi</button>
        <button class="btn primary" data-act="to-project">Dựng video từ kịch bản này →</button>
        <span class="grow"></span><button class="btn ghost" data-act="del-script">Xoá</button></div>
    </div>
    <div class="card stack">
      <div><h3>Viết lại cho sản phẩm của tôi</h3>
        <p class="muted small">AI giữ cấu trúc và nhịp của kịch bản này, viết lời mới theo sản phẩm của bạn. Thông tin nào để trống sẽ không bị bịa ra.</p></div>
      <div class="fields">
        <label class="f">Tên sản phẩm<input type="text" id="rw-name"></label>
        <label class="f">Giá bán<input type="text" id="rw-price" placeholder="VD: 48k"></label>
        <label class="f">Quy cách / khổ<input type="text" id="rw-spec" placeholder="VD: 30x40, canvas"></label>
        <label class="f">Khách hàng<input type="text" id="rw-audience" placeholder="VD: bố mẹ có con tiểu học"></label>
      </div>
      <label class="f">Điểm nổi bật<textarea id="rw-features" rows="2" placeholder="VD: in được tên con, có bản bé trai/bé gái"></textarea></label>
      <label class="f">Khuyến mãi đang chạy<input type="text" id="rw-promo" placeholder="Để trống nếu không có"></label>
      <div><button class="btn primary" data-act="rewrite" ${S.settings.ai_ready ? "" : "disabled"}>Viết lại bằng AI</button>
        ${S.settings.ai_ready ? "" : `<span class="muted small"> Cần nhập Anthropic API key trong Cài đặt</span>`}</div>
    </div></div>`;
}

function readScriptForm() {
  const s = S.script;
  s.title = $("#sd-title").value.trim();
  s.caption = $("#sd-caption").value.trim();
  s.hashtags = $("#sd-tags").value.split(/\s+/).filter(Boolean);
  s.beats = $$("#sd-beats tr").map((tr) => {
    const get = (k) => $(`[data-k="${k}"]`, tr).value;
    return { shot: get("shot"), voice: get("voice"), text: get("text"), text_pos: get("text_pos"), duration: parseFloat(get("duration")) || 3 };
  });
  return s;
}

$("#script-detail").addEventListener("click", async (e) => {
  const act = e.target.dataset.act;
  if (!act || !S.script) return;
  const s = S.script;
  try {
    if (act === "add-beat") {
      readScriptForm(); s.beats.push({ shot: "", voice: "", text: "", text_pos: "top", duration: 3 }); renderScriptDetail();
    } else if (act === "del-beat") {
      readScriptForm(); s.beats.splice(+e.target.closest("tr").dataset.i, 1); renderScriptDetail();
    } else if (act === "save-script") {
      await api("PUT", `/api/scripts/${s.id}`, readScriptForm()); toast("Đã lưu kịch bản"); loadScripts(s.id);
    } else if (act === "del-script") {
      if (!confirm("Xoá kịch bản này?")) return;
      await api("DELETE", `/api/scripts/${s.id}`); S.scriptId = null; S.script = null; renderScriptDetail(); loadScripts();
    } else if (act === "to-project") {
      await api("PUT", `/api/scripts/${s.id}`, readScriptForm());
      const p = await api("POST", "/api/projects", { script_id: s.id });
      await loadProjects(); await selectProject(p.id); showPage("studio");
    } else if (act === "rewrite") {
      await api("PUT", `/api/scripts/${s.id}`, readScriptForm());
      const product = { "Tên sản phẩm": $("#rw-name").value, "Giá bán": $("#rw-price").value,
        "Quy cách": $("#rw-spec").value, "Khách hàng": $("#rw-audience").value,
        "Điểm nổi bật": $("#rw-features").value, "Khuyến mãi": $("#rw-promo").value };
      const job = await api("POST", `/api/scripts/${s.id}/rewrite`, product);
      e.target.disabled = true;
      watchJob(job, "Viết lại kịch bản", (res) => { loadScripts(res.id); toast("Đã có kịch bản mới"); },
        () => { e.target.disabled = false; });
    }
  } catch (err) { toast(err.message); }
});

$("#imp-go").addEventListener("click", async () => {
  const file = $("#imp-file").files[0];
  const url = $("#imp-url").value.trim();
  $("#imp-err").textContent = "";
  if (!file && !url) { $("#imp-err").textContent = "Chọn video hoặc dán link."; return; }
  if (!S.settings.ai_ready) { $("#imp-err").textContent = "Cần nhập Anthropic API key trong Cài đặt trước."; return; }
  const form = new FormData();
  if (file) form.append("file", file);
  form.append("url", url);
  form.append("notes", $("#imp-notes").value);
  $("#imp-go").disabled = true;
  try {
    const r = await api("POST", "/api/scripts/import", undefined, form);
    $("#imp-file").value = ""; $("#imp-url").value = ""; $("#imp-notes").value = "";
    await loadScripts(r.script.id);
    watchJob(r.job, "Bóc kịch bản", () => loadScripts(r.script.id), () => loadScripts(r.script.id));
  } catch (err) { $("#imp-err").textContent = err.message; }
  $("#imp-go").disabled = false;
});

$("#doc-go").addEventListener("click", async () => {
  const file = $("#doc-file").files[0], url = $("#doc-url").value.trim(), text = $("#doc-text").value.trim();
  $("#doc-err").textContent = "";
  if (!file && !url && !text) { $("#doc-err").textContent = "Chọn file, dán link hoặc dán nội dung."; return; }
  const form = new FormData();
  if (file) form.append("file", file);
  form.append("url", url);
  form.append("text", text);
  $("#doc-go").disabled = true;
  try {
    const job = await api("POST", "/api/scripts/import-doc", undefined, form);
    watchJob(job, "Nhập kịch bản", (res) => {
      $("#doc-go").disabled = false;
      $("#doc-file").value = ""; $("#doc-url").value = ""; $("#doc-text").value = "";
      toast(`Đã nhập ${res.added} kịch bản mới${res.updated ? `, cập nhật ${res.updated} kịch bản trùng mã` : ""}`);
      loadScripts();
    }, (err) => { $("#doc-go").disabled = false; $("#doc-err").textContent = err; });
  } catch (err) { $("#doc-go").disabled = false; $("#doc-err").textContent = err.message; }
});
$("#bt-import").addEventListener("click", () => { showPage("scripts"); $("#doc-card").scrollIntoView({ behavior: "smooth" }); });

$("#script-new").addEventListener("click", async () => {
  const s = await api("POST", "/api/scripts", { title: "Kịch bản mới", beats: [{ shot: "", voice: "", text: "", text_pos: "top", duration: 3 }] });
  loadScripts(s.id);
});

// ================= VIDEO NGUỒN =================
async function loadSources() {
  S.sources = await api("GET", "/api/sources");
  renderSources();
  if (S.sources.some((s) => s.status === "processing")) setTimeout(loadSources, 3000);
}

function renderSources() {
  renderBatchSources();
  $("#source-grid").innerHTML = S.sources.length ? S.sources.map((s) => `
    <div class="src">
      ${s.poster ? `<img src="${esc(s.poster)}" alt="">` : `<div class="thumb-ph" style="width:100%;height:auto;aspect-ratio:9/12;display:grid;place-items:center">${s.status === "processing" ? `<span class="spin"></span>` : ""}</div>`}
      <div class="b"><div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.name)}</div>
        <div class="row small" style="gap:6px">
          ${s.status === "processing" ? `<span class="chip processing">Đang xử lý</span>` : ""}
          ${s.status === "error" ? `<span class="chip error" title="${esc(s.error)}">Lỗi</span>` : ""}
          ${s.info ? `<span class="muted">${fmt(s.info.duration)} · ${(s.shots || []).length} đoạn</span>` : ""}
          <span class="grow"></span><button class="btn ghost sm" data-del="${s.id}" title="Xoá">✕</button></div></div>
    </div>`).join("") : `<div class="empty">Chưa có video nguồn</div>`;
}

$("#source-grid").addEventListener("click", async (e) => {
  const id = e.target.dataset.del;
  if (!id || !confirm("Xoá video nguồn này?")) return;
  await api("DELETE", `/api/sources/${id}`);
  loadSources();
});

// Tải một file lên và báo phần trăm (fetch không cho biết tiến độ tải lên, mà video iPhone nặng cả trăm MB)
function xhrUpload(path, form, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* phản hồi không phải JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(data.detail || `Lỗi ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("Mất kết nối khi tải lên. Kiểm tra cửa sổ đen của app còn mở không rồi thử lại."));
    xhr.send(form);
  });
}

const extOf = (name) => (/\.[^.]+$/.exec(name || "") || [""])[0].toLowerCase();
const isVideoFile = (f) => (f.type || "").startsWith("video/") || S.videoExt.includes(extOf(f.name));
const mb = (bytes) => bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;

let uploadChain = Promise.resolve();   // thả thêm file khi đang tải thì xếp hàng, không tải chồng lên nhau
function uploadSources(files) {
  const all = [...files];
  const videos = all.filter(isVideoFile), skipped = all.filter((f) => !isVideoFile(f));
  if (skipped.length) toast(`Bỏ qua ${skipped.length} file không phải video: ${skipped.slice(0, 3).map((f) => f.name).join(", ")}${skipped.length > 3 ? "…" : ""}`);
  if (!videos.length) return uploadChain;
  uploadChain = uploadChain.then(() => uploadOneByOne(videos));
  return uploadChain;
}

async function uploadOneByOne(videos) {
  const failed = [];
  for (const [i, file] of videos.entries()) {
    const label = `${i + 1}/${videos.length} · ${file.name} (${mb(file.size)})`;
    S.jobs.set("upload", { label: "Tải lên", message: `${label} · 0%` });
    renderJobs();
    const form = new FormData();
    form.append("files", file);
    try {
      const items = await xhrUpload("/api/sources", form, (p) => {
        S.jobs.set("upload", { label: "Tải lên", message: `${label} · ${Math.round(p * 100)}%` });
        renderJobs();
      });
      items.forEach((it) => watchJob({ id: it.job, message: "Đang xử lý" }, `Xử lý ${it.name}`, loadSources, loadSources));
      loadSources();
    } catch (err) { failed.push(`${file.name}: ${err.message}`); }
  }
  S.jobs.delete("upload");
  renderJobs();
  if (failed.length) toast(`Không tải lên được ${failed.length} file. ${failed[0]}`);
}
function wireDrop(zone, input) {
  // ô chọn file nằm trong vùng thả: cú bấm giả do input.click() nổi bọt ngược lên vùng thả, nên bỏ qua để không mở hộp chọn hai lần
  zone.addEventListener("click", (e) => { if (e.target !== input) input.click(); });
  input.addEventListener("change", (e) => { uploadSources(e.target.files); e.target.value = ""; });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("over"); uploadSources(e.dataTransfer.files); });
}
wireDrop($("#bt-drop"), $("#bt-file"));
const drop = $("#drop");
$("#src-file").addEventListener("change", (e) => { uploadSources(e.target.files); e.target.value = ""; });
drop.addEventListener("click", (e) => { if (e.target !== $("#src-file")) $("#src-file").click(); });
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); uploadSources(e.dataTransfer.files); });

// ================= DỰNG VIDEO =================
async function loadProjects() {
  S.projects = await api("GET", "/api/projects");
  renderProjectList();
}

function renderProjectList() {
  $("#project-list").innerHTML = S.projects.length ? S.projects.map((p) => `
    <div class="item ${S.project && p.id === S.project.id ? "on" : ""}" data-id="${p.id}">
      <div class="grow"><div class="t">${esc(p.name)}</div>
        <div class="muted small">${(p.beats || []).length} cảnh · ${(p.renders || []).length} video đã xuất</div></div>
    </div>`).join("") : `<div class="empty small">Chưa có dự án</div>`;
}
$("#project-list").addEventListener("click", (e) => { const it = e.target.closest(".item"); if (it) selectProject(it.dataset.id); });

async function selectProject(id) {
  S.project = await api("GET", `/api/projects/${id}`);
  if (!S.sources.length) await loadSources();
  renderProjectList();
  renderStudio();
}

$("#project-new").addEventListener("click", async () => {
  const p = await api("POST", "/api/projects", { name: "Video mới" });
  await loadProjects(); selectProject(p.id);
});

let saveTimer;
function queueSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveProject, 600);
}
async function saveProject() {
  clearTimeout(saveTimer);
  const p = S.project;
  if (!p) return;
  await api("PUT", `/api/projects/${p.id}`, { name: p.name, beats: p.beats, settings: p.settings,
    caption: p.caption, hashtags: p.hashtags, alt_hooks: p.alt_hooks });
}

function ps() { return { ...PROJECT_DEFAULTS, tts_provider: S.settings.tts_provider, tts_voice: S.settings.tts_voice,
  tts_rate: S.settings.tts_rate, text_font: S.settings.text_font, text_color: S.settings.text_color,
  sub_color: S.settings.sub_color, text_style: S.settings.text_style, ...(S.project.settings || {}) }; }

function clipThumb(clip) {
  if (!clip) return null;
  const src = S.sources.find((s) => s.id === clip.source_id);
  if (!src) return null;
  const shot = (src.shots || []).find((sh) => clip.start >= sh.start - 0.01 && clip.start < sh.end);
  return shot ? shot.thumb : src.poster;
}

function voiceOptions(provider, current) {
  return (S.voices[provider] || []).map((v) => `<option value="${v.id}" ${v.id === current ? "selected" : ""}>${esc(v.name)}</option>`).join("");
}

function estSeconds(text) {
  const words = (text || "").trim().split(/\s+/).filter(Boolean).length;
  return words ? (words / 3.6).toFixed(1) : 0;
}

function renderStudio() {
  const p = S.project;
  const box = $("#studio");
  if (!p) { box.innerHTML = ""; return; }
  const cfg = ps();
  const musicUploaded = cfg.music && !["auto", "none"].includes(cfg.music);
  box.innerHTML = `<div class="stack">
    <div class="card stack">
      <div class="row"><input type="text" id="pj-name" class="grow" value="${esc(p.name)}" style="font-weight:600;font-size:16px">
        <button class="btn" data-act="match" ${S.settings.ai_ready ? "" : "disabled title='Cần Anthropic API key'"}>AI ghép cảnh tự động</button>
        <button class="btn primary" data-act="render">Xuất video</button>
        <button class="btn ghost" data-act="del-project" title="Xoá dự án">✕</button></div>
      <div class="fields">
        <label class="f">Giọng đọc<select data-set="tts_provider">${Object.entries(S.providers).map(([k, v]) => `<option value="${k}" ${k === cfg.tts_provider ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
        <label class="f">Giọng<select data-set="tts_voice">${voiceOptions(cfg.tts_provider, cfg.tts_voice)}</select></label>
        <label class="f">Tốc độ đọc (%)<input type="number" data-set="tts_rate" step="5" min="-50" max="50" value="${esc(cfg.tts_rate)}"></label>
        <label class="f">Nhạc nền<select data-set="music">
          <option value="auto" ${cfg.music === "auto" ? "selected" : ""}>Tự tạo nhạc Tết (không bản quyền)</option>
          <option value="none" ${cfg.music === "none" ? "selected" : ""}>Không nhạc</option>
          ${S.music.map((m) => `<option value="${esc(m.path)}" ${m.path === cfg.music ? "selected" : ""}>${esc(m.name)}</option>`).join("")}
          ${musicUploaded && !S.music.some((m) => m.path === cfg.music) ? `<option value="${esc(cfg.music)}" selected>File đã upload</option>` : ""}</select></label>
        <label class="f">Phông chữ<select data-set="text_font">${S.fonts.map((f) => `<option value="${esc(f.family)}" ${f.family === cfg.text_font ? "selected" : ""}>${f.recommended ? "★ " : ""}${esc(f.family)}</option>`).join("")}</select></label>
        <label class="f">Màu chữ<select data-set="text_color">${S.colors.map((c) => `<option value="${c.hex}" ${c.hex === cfg.text_color ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
        <label class="f">Màu phụ đề<select data-set="sub_color">${S.colors.map((c) => `<option value="${c.hex}" ${c.hex === cfg.sub_color ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
        <label class="f">Kiểu chữ<select data-set="text_style">
          <option value="box" ${cfg.text_style === "box" ? "selected" : ""}>Nền hộp mờ</option>
          <option value="outline" ${cfg.text_style === "outline" ? "selected" : ""}>Chữ viền</option></select></label>
        <label class="f">Âm lượng nhạc<input type="range" data-set="music_volume" min="0" max="1" step="0.05" value="${cfg.music_volume}"></label>
        <label class="f">Âm lượng tiếng gốc<input type="range" data-set="source_volume" min="0" max="1" step="0.05" value="${cfg.source_volume}"></label>
        <label class="f">Khung hình<select data-set="ratio">${["9:16", "1:1", "4:5", "16:9"].map((r) => `<option ${r === cfg.ratio ? "selected" : ""}>${r}</option>`).join("")}</select></label>
        <label class="f">Lấp khung<select data-set="fit">${[["blur", "Nền mờ"], ["crop", "Cắt tràn khung"], ["pad", "Viền đen"]].map(([k, v]) => `<option value="${k}" ${k === cfg.fit ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      </div>
      <div class="row small">
        <label><input type="checkbox" data-set="voice_on" ${cfg.voice_on ? "checked" : ""}> Lồng giọng đọc</label>
        <label><input type="checkbox" data-set="subtitles" ${cfg.subtitles ? "checked" : ""}> Phụ đề theo lời đọc</label>
        <label><input type="checkbox" data-set="logo_on" ${cfg.logo_on ? "checked" : ""}> Chèn logo ${S.settings.logo ? "" : "(chưa có logo)"}</label>
        <label class="btn sm">Upload nhạc riêng<input type="file" id="pj-music" accept="audio/*" hidden></label>
      </div>
    </div>
    ${(p.needs_info || []).length ? `<div class="warn"><b>Cần kiểm tra trước khi đăng:</b><ul style="margin:6px 0 0">${p.needs_info.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>` : ""}
    ${(p.missing || []).length ? `<div class="warn"><b>Cần quay thêm:</b><ul style="margin:6px 0 0">${p.missing.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>` : ""}
    ${(p.alt_hooks || []).length ? `<div class="card"><div class="muted small" style="margin-bottom:6px">Hook khác cho cảnh 1 (bấm để dùng)</div>
      <div class="row">${p.alt_hooks.map((h, i) => `<button class="btn sm" data-act="use-hook" data-i="${i}">${esc(h.text)}</button>`).join("")}</div></div>` : ""}
    <div class="stack" id="pj-beats">${p.beats.map((b, i) => beatCard(b, i, cfg)).join("")}</div>
    <div><button class="btn" data-act="add-beat">+ Thêm cảnh</button></div>
    <div class="card stack">
      <h3>Caption khi đăng</h3>
      <textarea id="pj-caption" rows="3">${esc([p.caption, (p.hashtags || []).join(" ")].filter(Boolean).join("\n"))}</textarea>
      <div><button class="btn sm" data-act="copy-caption">Sao chép caption</button></div>
    </div>
    <div class="card"><h3 style="margin-bottom:10px">Video đã xuất</h3>
      ${(p.renders || []).length ? `<div class="renders">${p.renders.map((r) => `<div class="stack" style="gap:6px">
        <video src="${esc(r.path)}" controls playsinline preload="metadata"></video>
        <div class="row small"><span class="muted grow">${fmt(r.duration)} · ${new Date(r.created * 1000).toLocaleString("vi-VN")}</span>
          <a class="btn sm" href="${esc(r.path)}" download>Tải về</a></div></div>`).join("")}</div>`
        : `<div class="muted small">Chưa có. Bấm "Xuất video" khi các cảnh đã có đoạn video.</div>`}</div>
  </div>`;
}

function blanksOf(b) {
  return [...new Set(`${b.voice || ""} ${b.text || ""}`.match(PLACEHOLDER) || [])];
}

function blankWarning(blanks) {
  return `Còn ô chưa điền: <b>${blanks.map(esc).join(" ")}</b>. Sửa lại câu này bằng thông tin thật, nếu không sẽ không xuất được video.`;
}

function refreshBlanks(card, beat) {
  const blanks = blanksOf(beat);
  card.classList.toggle("has-blank", blanks.length > 0);
  let note = $(".blank-note", card);
  if (blanks.length && !note) {
    note = document.createElement("div");
    note.className = "full err blank-note";
    $(".body", card).append(note);
  }
  if (note) { if (blanks.length) note.innerHTML = blankWarning(blanks); else note.remove(); }
}

function beatCard(b, i, cfg) {
  const thumb = clipThumb(b.clip);
  const est = estSeconds(b.voice);
  const blanks = blanksOf(b);
  return `<div class="beat ${blanks.length ? "has-blank" : ""}" data-i="${i}">
    <div class="clip">
      ${thumb ? `<img src="${esc(thumb)}" alt="">` : `<div class="thumb-ph">Chưa chọn đoạn video</div>`}
      ${b.clip ? `<div class="small muted">${fmt(b.clip.start)} → ${fmt(b.clip.end)}</div>` : ""}
      <button class="btn sm" data-act="pick">${b.clip ? "Đổi đoạn" : "Chọn đoạn"}</button>
    </div>
    <div class="stack" style="gap:10px">
      <div class="row"><span class="n">Cảnh ${i + 1}</span><span class="grow"></span>
        <button class="btn ghost sm" data-act="up" title="Lên">↑</button>
        <button class="btn ghost sm" data-act="down" title="Xuống">↓</button>
        <button class="btn ghost sm" data-act="del" title="Xoá cảnh">✕</button></div>
      <div class="body">
        <label class="f full">Cảnh quay<input type="text" data-k="shot" value="${esc(b.shot)}"></label>
        <label class="f full">Lời đọc ${est ? `<span class="small">(~${est}s)</span>` : ""}<textarea data-k="voice" rows="2">${esc(b.voice)}</textarea></label>
        ${b.adapted && b.orig_voice ? `<div class="full small muted">Đã viết lại cho khớp video quay. Lời gốc: ${esc(b.orig_voice)}</div>` : ""}
        ${blanks.length ? `<div class="full err blank-note">${blankWarning(blanks)}</div>` : ""}
        <label class="f">Chữ trên màn hình<textarea data-k="text" rows="2">${esc(b.text)}</textarea></label>
        <div class="stack" style="gap:8px">
          <label class="f">Vị trí chữ<select data-k="text_pos">${Object.entries(POS).map(([k, v]) => `<option value="${k}" ${b.text_pos === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
          <label class="f">Giây (khi không có lời)<input type="number" data-k="duration" step="0.5" min="0.5" value="${esc(b.duration ?? 3)}"></label>
        </div>
      </div>
      ${b.clip && b.clip.note ? `<div class="muted small">AI: ${esc(b.clip.note)}</div>` : ""}
      ${b.clip && (b.clip.avoid || []).length ? `<div class="muted small">Đoạn này đã có chữ sẵn ở ${(b.clip.avoid || []).map((p) => POS[p] || p).join(", ")}: chữ và phụ đề mới sẽ được đặt tránh chỗ đó.</div>` : ""}
      ${b.clip && b.clip.talking ? `<div class="muted small">Trong đoạn này đã có người nói với máy quay nên app không chèn chữ lên hình.</div>` : ""}
      ${b.clip && b.clip.crop ? `<div class="muted small">Đã cắt bỏ dải ${Object.keys(b.clip.crop).map((k) => (k === "top" ? "trên" : "dưới")).join(", ")} khung hình để bỏ chữ của bản dựng cũ.</div>` : ""}
      <div class="row"><button class="btn sm" data-act="listen" ${b.voice && cfg.voice_on ? "" : "disabled"}>Nghe thử lời đọc</button><audio hidden></audio></div>
    </div></div>`;
}

$("#studio").addEventListener("input", (e) => {
  const p = S.project;
  if (!p) return;
  const t = e.target;
  if (t.id === "pj-name") p.name = t.value;
  else if (t.id === "pj-caption") {
    const lines = t.value.split("\n");
    const tags = lines.join(" ").match(/#\S+/g) || [];
    p.hashtags = tags;
    p.caption = t.value.replace(/#\S+/g, "").trim();
  } else if (t.dataset.k) {
    const beat = p.beats[+t.closest(".beat").dataset.i];
    beat[t.dataset.k] = t.dataset.k === "duration" ? parseFloat(t.value) || 3 : t.value;
    if (t.dataset.k === "voice" || t.dataset.k === "text") refreshBlanks(t.closest(".beat"), beat);
  } else if (t.dataset.set) {
    p.settings = p.settings || {};
    const k = t.dataset.set;
    p.settings[k] = t.type === "checkbox" ? t.checked : t.type === "range" || t.type === "number" ? parseFloat(t.value) : t.value;
    if (k === "tts_provider") { p.settings.tts_voice = (S.voices[t.value] || [{}])[0].id; renderStudio(); }
  } else return;
  queueSave();
});
$("#studio").addEventListener("change", (e) => {
  if (e.target.id === "pj-music" && e.target.files[0]) {
    const form = new FormData(); form.append("file", e.target.files[0]);
    api("POST", `/api/projects/${S.project.id}/music`, undefined, form)
      .then((p) => { S.project.settings = p.settings; renderStudio(); toast("Đã thêm nhạc"); })
      .catch((err) => toast(err.message));
  }
});

$("#studio").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn || !S.project) return;
  const p = S.project;
  const card = btn.closest(".beat");
  const i = card ? +card.dataset.i : -1;
  const act = btn.dataset.act;
  try {
    if (act === "pick") openPicker(i);
    else if (act === "up" && i > 0) { [p.beats[i - 1], p.beats[i]] = [p.beats[i], p.beats[i - 1]]; renderStudio(); queueSave(); }
    else if (act === "down" && i < p.beats.length - 1) { [p.beats[i + 1], p.beats[i]] = [p.beats[i], p.beats[i + 1]]; renderStudio(); queueSave(); }
    else if (act === "del") { if (p.beats.length > 1 || confirm("Xoá cảnh cuối cùng?")) { p.beats.splice(i, 1); renderStudio(); queueSave(); } }
    else if (act === "add-beat") { p.beats.push({ shot: "", voice: "", text: "", text_pos: "top", duration: 3, clip: null }); renderStudio(); queueSave(); }
    else if (act === "use-hook") {
      const h = p.alt_hooks[+btn.dataset.i];
      const old = { text: p.beats[0].text, voice: p.beats[0].voice };
      Object.assign(p.beats[0], { text: h.text, voice: h.voice });
      p.alt_hooks[+btn.dataset.i] = old;
      renderStudio(); queueSave(); toast("Đã đổi hook cảnh 1");
    } else if (act === "listen") {
      const cfg = ps();
      btn.disabled = true; btn.textContent = "Đang tạo giọng…";
      const r = await api("POST", "/api/tts/preview", { text: p.beats[i].voice, provider: cfg.tts_provider, voice: cfg.tts_voice, rate: cfg.tts_rate });
      const audio = $("audio", card); audio.src = r.url; audio.hidden = false; audio.controls = true; audio.play();
      btn.disabled = false; btn.textContent = `Nghe thử lời đọc (${r.duration.toFixed(1)}s)`;
    } else if (act === "copy-caption") {
      await navigator.clipboard.writeText($("#pj-caption").value); toast("Đã sao chép caption");
    } else if (act === "del-project") {
      if (!confirm("Xoá dự án và các video đã xuất?")) return;
      await api("DELETE", `/api/projects/${p.id}`); S.project = null; renderStudio(); loadProjects();
    } else if (act === "match") {
      await saveProject();
      btn.disabled = true;
      const job = await api("POST", `/api/projects/${p.id}/match`, {});
      watchJob(job, "AI ghép cảnh", () => selectProject(p.id), () => { btn.disabled = false; });
    } else if (act === "render") {
      const missing = p.beats.findIndex((b) => !b.clip);
      if (missing >= 0) { toast(`Cảnh ${missing + 1} chưa chọn đoạn video`); return; }
      await saveProject();
      btn.disabled = true; btn.textContent = "Đang xuất…";
      const job = await api("POST", `/api/projects/${p.id}/render`);
      const done = () => { selectProject(p.id); loadProjects(); };
      watchJob(job, "Xuất video", () => { done(); toast("Đã xuất xong video"); }, done);
    }
  } catch (err) {
    toast(err.message);
    if (act === "listen") { btn.disabled = false; btn.textContent = "Nghe thử lời đọc"; }
  }
});

// ---------- Hộp chọn đoạn video ----------
let pk = { i: -1 };
function openPicker(i) {
  const ready = S.sources.filter((s) => s.status === "ready");
  if (!ready.length) { toast("Chưa có video nguồn. Vào tab Video nguồn để upload."); return; }
  const clip = S.project.beats[i].clip;
  pk = { i, sourceId: clip && ready.some((s) => s.id === clip.source_id) ? clip.source_id : ready[0].id };
  $("#pk-n").textContent = i + 1;
  $("#pk-source").innerHTML = ready.map((s) => `<option value="${s.id}" ${s.id === pk.sourceId ? "selected" : ""}>${esc(s.name)} (${fmt(s.info.duration)})</option>`).join("");
  loadPickerSource(clip && clip.source_id === pk.sourceId ? clip : null);
  $("#picker").showModal();
}

function loadPickerSource(clip) {
  const src = S.sources.find((s) => s.id === pk.sourceId);
  const v = $("#pk-video");
  v.src = src.proxy;
  const start = clip ? clip.start : (src.shots[0] || { start: 0 }).start;
  const end = clip ? clip.end : (src.shots[0] || { end: src.info.duration }).end;
  $("#pk-start").value = (+start).toFixed(1);
  $("#pk-end").value = (+end).toFixed(1);
  v.addEventListener("loadedmetadata", () => { v.currentTime = start; }, { once: true });
  renderShots();
}

function renderShots() {
  const src = S.sources.find((s) => s.id === pk.sourceId);
  const st = parseFloat($("#pk-start").value);
  $("#pk-shots").innerHTML = (src.shots || []).map((sh, k) => `<button data-k="${k}" class="${Math.abs(sh.start - st) < 0.05 ? "on" : ""}">
    <img src="${esc(sh.thumb)}" alt=""><span>${sh.start.toFixed(1)}–${sh.end.toFixed(1)}s</span>
    ${sh.sub || sh.marks ? `<span class="sub-badge bad" title="${esc(sh.sub || sh.marks)}">⚠ ${sh.sub ? "chữ sẵn" : "nét vẽ sẵn"}</span>` : ""}</button>`).join("");
}

$("#pk-source").addEventListener("change", (e) => { pk.sourceId = e.target.value; loadPickerSource(null); });
$("#pk-shots").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const sh = S.sources.find((s) => s.id === pk.sourceId).shots[+b.dataset.k];
  $("#pk-start").value = sh.start.toFixed(1);
  $("#pk-end").value = sh.end.toFixed(1);
  $("#pk-video").currentTime = sh.start;
  $("#pk-video").play().catch(() => {});
  renderShots();
});
$("#pk-set-start").addEventListener("click", () => { $("#pk-start").value = $("#pk-video").currentTime.toFixed(1); renderShots(); });
$("#pk-set-end").addEventListener("click", () => { $("#pk-end").value = $("#pk-video").currentTime.toFixed(1); });
$("#pk-close").addEventListener("click", () => { $("#pk-video").pause(); $("#picker").close(); });
$("#pk-ok").addEventListener("click", () => {
  const start = parseFloat($("#pk-start").value), end = parseFloat($("#pk-end").value);
  if (!(end > start)) { toast("Điểm kết thúc phải sau điểm bắt đầu"); return; }
  S.project.beats[pk.i].clip = { source_id: pk.sourceId, start, end };
  $("#pk-video").pause();
  $("#picker").close();
  renderStudio(); queueSave();
});

// ---------- Nhạc nền dùng chung ----------
function renderMusic() {
  const sel = $("#bt-music");
  if (sel) {
    const keep = sel.value;
    sel.innerHTML = `<option value="auto">Tự tạo nhạc Tết, mỗi video một nhịp khác</option>
      <option value="none">Không nhạc</option>` +
      S.music.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("");
    sel.value = S.music.some((m) => m.id === keep) || ["auto", "none"].includes(keep) ? keep : "auto";
    $("#bt-music-del").hidden = ["auto", "none"].includes(sel.value);
  }
  const box = $("#set-music");
  if (box) box.innerHTML = S.music.length ? S.music.map((m) => `<div class="row small" data-m="${esc(m.id)}">
      <span class="grow">${esc(m.name)}</span><audio src="${esc(m.path)}" controls preload="none" style="height:30px"></audio>
      <button class="btn ghost sm" data-del-music="${esc(m.id)}">✕</button></div>`).join("")
    : `<div class="muted small">Chưa có nhạc nào. Upload file mp3 hoặc m4a để dùng cho video.</div>`;
}

async function uploadMusic(file, after) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    S.music = await api("POST", "/api/music", undefined, form);
    renderMusic();
    if (after) after();
    toast("Đã thêm nhạc nền");
  } catch (err) { toast(err.message); }
}
$("#set-music-file").addEventListener("change", (e) => { uploadMusic(e.target.files[0]); e.target.value = ""; });
$("#bt-music-file").addEventListener("change", (e) => {
  uploadMusic(e.target.files[0], () => { $("#bt-music").value = S.music[S.music.length - 1].id; renderMusic(); });
  e.target.value = "";
});
$("#bt-music").addEventListener("change", renderMusic);
$("#bt-music-del").addEventListener("click", async () => {
  const id = $("#bt-music").value;
  if (["auto", "none"].includes(id) || !confirm("Xoá file nhạc này?")) return;
  S.music = await api("DELETE", `/api/music/${encodeURIComponent(id)}`);
  $("#bt-music").value = "auto"; renderMusic();
});
$("#set-music").addEventListener("click", async (e) => {
  const id = e.target.dataset.delMusic;
  if (!id || !confirm("Xoá file nhạc này?")) return;
  S.music = await api("DELETE", `/api/music/${encodeURIComponent(id)}`);
  renderMusic();
});

// ================= CÀI ĐẶT =================
function swatches(box, value, onPick) {
  box.innerHTML = S.colors.map((c) => `<button class="sw ${c.hex === value ? "on" : ""}" data-hex="${c.hex}"
    title="${esc(c.name)}" style="background:${c.hex}"></button>`).join("");
  box.onclick = (e) => {
    const hex = e.target.dataset.hex;
    if (!hex) return;
    onPick(hex);
    swatches(box, hex, onPick);
  };
}

function renderTextPreview() {
  const box = $("#set-preview");
  if (!box) return;
  const s = S.settings;
  const span = $("span", box);
  span.style.fontFamily = `"${s.text_font || "DejaVu Sans"}", sans-serif`;
  span.style.color = s.text_color || "#FFFFFF";
  if ((s.text_style || "box") === "box") {
    span.style.background = "rgba(0,0,0,.55)";
    span.style.textShadow = "none";
  } else {
    span.style.background = "transparent";
    const dark = parseInt((s.text_color || "#fff").slice(1, 3), 16) < 90;
    span.style.textShadow = `0 0 6px ${dark ? "#fff" : "#000"}, 0 2px 4px ${dark ? "#fff" : "#000"}`;
  }
}

function renderSettings() {
  const s = S.settings;
  $("#set-provider").innerHTML = Object.entries(S.providers).map(([k, v]) => `<option value="${k}" ${k === s.tts_provider ? "selected" : ""}>${esc(v)}</option>`).join("");
  $("#set-voice").innerHTML = voiceOptions(s.tts_provider, s.tts_voice);
  $("#set-rate").value = s.tts_rate;
  $("#set-azure-region").value = s.azure_region || "";
  $("#set-shop").value = s.shop_name || "";
  for (const [id, key] of [["#set-anthropic", "anthropic_api_key_set"], ["#set-azure", "azure_key_set"], ["#set-fpt", "fpt_key_set"]]) {
    $(id).value = ""; $(id).placeholder = s[key] ? "Đã lưu (nhập để thay)" : "Chưa có";
  }
  $("#set-logo-img").hidden = !s.logo; if (s.logo) $("#set-logo-img").src = s.logo + "?t=" + Date.now();
  $("#set-logo-del").hidden = !s.logo;
  $("#set-font").innerHTML = S.fonts.map((f) => `<option value="${esc(f.family)}" ${f.family === s.text_font ? "selected" : ""}>${f.recommended ? "★ " : ""}${esc(f.family)}</option>`).join("")
    || `<option value="DejaVu Sans">DejaVu Sans</option>`;
  $("#set-text-style").value = s.text_style || "box";
  swatches($("#set-color"), s.text_color || "#FFFFFF", (hex) => { S.settings.text_color = hex; renderTextPreview(); });
  swatches($("#set-subcolor"), s.sub_color || "#FFFFFF", (hex) => { S.settings.sub_color = hex; renderTextPreview(); });
  renderTextPreview();
  renderMusic();
}
$("#set-font").addEventListener("change", (e) => { S.settings.text_font = e.target.value; renderTextPreview(); });
$("#set-text-style").addEventListener("change", (e) => { S.settings.text_style = e.target.value; renderTextPreview(); });
$("#set-provider").addEventListener("change", (e) => { $("#set-voice").innerHTML = voiceOptions(e.target.value); });
$("#set-save").addEventListener("click", async () => {
  try {
    S.settings = await api("PUT", "/api/settings", {
      anthropic_api_key: $("#set-anthropic").value.trim(), tts_provider: $("#set-provider").value,
      tts_voice: $("#set-voice").value, tts_rate: parseInt($("#set-rate").value) || 0,
      azure_key: $("#set-azure").value.trim(), azure_region: $("#set-azure-region").value.trim(),
      fpt_key: $("#set-fpt").value.trim(), shop_name: $("#set-shop").value.trim(),
      text_font: $("#set-font").value, text_style: $("#set-text-style").value,
      text_color: S.settings.text_color, sub_color: S.settings.sub_color });
    renderSettings(); $("#set-msg").textContent = "Đã lưu"; setTimeout(() => ($("#set-msg").textContent = ""), 2500);
    if (S.script) renderScriptDetail();
    if (S.project) renderStudio();
  } catch (err) { toast(err.message); }
});
$("#set-test").addEventListener("click", async () => {
  $("#set-tts-err").textContent = "";
  $("#set-test").disabled = true;
  try {
    const r = await api("POST", "/api/tts/preview", { text: $("#set-test-text").value, provider: $("#set-provider").value,
      voice: $("#set-voice").value, rate: parseInt($("#set-rate").value) || 0 });
    const a = $("#set-audio"); a.src = r.url; a.hidden = false; a.play();
  } catch (err) { $("#set-tts-err").textContent = err.message; }
  $("#set-test").disabled = false;
});
$("#set-logo").addEventListener("change", async (e) => {
  const form = new FormData(); form.append("file", e.target.files[0]);
  S.settings = await api("POST", "/api/settings/logo", undefined, form); renderSettings(); toast("Đã lưu logo");
});
$("#set-logo-del").addEventListener("click", async () => { S.settings = await api("DELETE", "/api/settings/logo"); renderSettings(); });


// ================= TẠO HÀNG LOẠT =================
const BT_STATUS = { pending: ["Đang chờ", ""], matching: ["Ghép cảnh", "running"], rendering: ["Đang dựng", "running"],
  done: ["Xong", "ok"], blocked: ["Cần điền", "warn"], error: ["Lỗi", "error"] };
const BT_RUN = { running: "Đang chạy", done: "Hoàn tất", cancelled: "Đã dừng", interrupted: "Bị ngắt", error: "Lỗi" };
S.btSel = new Set();
S.btChannel = "";
S.batches = [];
S.batchId = null;
let btPoll;

function blanksOfScript(s) {
  return [...new Set((s.beats || []).flatMap((b) => `${b.voice || ""} ${b.text || ""}`.match(PLACEHOLDER) || []))];
}

function burnedLabel(n) {
  const mode = ($("#bt-strict") || {}).value || "strict";
  if (mode === "salvage") return `${n} đoạn có chữ cũ · sẽ cắt bỏ dải chữ`;
  if (mode === "lenient") return `${n} đoạn có chữ cũ · chữ mới sẽ tránh chỗ đó`;
  return `Bỏ ${n} đoạn còn chữ hoặc nét chèn sẵn`;
}

function renderBatchSources() {
  const box = $("#bt-sources");
  if (!box) return;
  box.innerHTML = S.sources.length ? S.sources.map((s) => {
    const shots = s.shots || [], labelled = shots.filter((x) => x.desc).length;
    const burned = shots.filter((x) => x.sub || x.marks);
    return `<div class="src-row" data-id="${s.id}">
      ${s.poster ? `<img src="${esc(s.poster)}" alt="">` : `<div class="thumb-ph" style="width:36px;height:62px"></div>`}
      <div class="grow"><div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.name)}</div>
        <div class="row small muted" style="gap:6px">
          ${s.status === "processing" ? `<span class="chip processing">Đang xử lý</span>` : ""}
          ${s.status === "error" ? `<span class="chip error">Lỗi</span><span class="err">${esc(s.error)}</span>` : ""}
          ${s.info ? `<span>${fmt(s.info.duration)} · ${shots.length} đoạn${labelled ? ` · AI đã mô tả ${labelled}` : ""}</span>` : ""}
          ${burned.length ? `<span class="chip warn" title="${esc(burned.map((x) => x.sub || x.marks).join(" · "))}">${burnedLabel(burned.length)}</span>` : ""}</div></div>
      <input type="text" data-note="${s.id}" value="${esc(s.note || "")}" placeholder="Ghi chú sản phẩm: VD lịch bloc 14,5×20,5">
      <button class="btn ghost sm" data-del="${s.id}" title="Xoá">✕</button></div>`;
  }).join("") : `<div class="empty small">Chưa có video nguồn. Thả video vào khung trên.</div>`;
  renderBatchEstimate();
}
$("#bt-sources").addEventListener("input", (e) => {
  const id = e.target.dataset.note;
  if (!id) return;
  clearTimeout(e.target._t);
  e.target._t = setTimeout(() => {
    api("PUT", `/api/sources/${id}`, { note: e.target.value }).then((src) => {
      const i = S.sources.findIndex((x) => x.id === id); if (i >= 0) S.sources[i] = src;
    }).catch((err) => toast(err.message));
  }, 600);
});
$("#bt-sources").addEventListener("click", async (e) => {
  const id = e.target.dataset.del;
  if (!id || !confirm("Xoá video nguồn này?")) return;
  await api("DELETE", `/api/sources/${id}`); loadSources();
});

function btVisibleScripts() {
  const q = $("#bt-search").value;
  return S.scripts.filter((s) => s.status === "ready" && (s.beats || []).length && scriptMatches(s, q)
    && (!S.btChannel || s.channel === S.btChannel));
}

function renderBatchScripts() {
  const channels = [...new Set(S.scripts.map((s) => s.channel).filter(Boolean))];
  $("#bt-channels").innerHTML = ["", ...channels].map((c) =>
    `<button class="chip ${S.btChannel === c ? "on" : ""}" data-ch="${esc(c)}">${c ? esc(c) : "Tất cả kênh"}</button>`).join("");
  const sel = $("#gen-channel");
  if (sel && sel.dataset.list !== channels.join("|")) {
    sel.dataset.list = channels.join("|");
    sel.innerHTML = [`<option value="">Chưa chọn</option>`, ...channels.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`)].join("");
  }
  const list = btVisibleScripts();
  $("#bt-scripts").innerHTML = list.length ? list.map((s) => {
    const blanks = blanksOfScript(s);
    const fresh = S.btFresh && S.btFresh.has(s.id);
    const open = S.btOpen && S.btOpen.has(s.id);
    return `<label class="item ${fresh ? "fresh" : ""} ${open ? "open" : ""}" data-id="${s.id}"><input type="checkbox" ${S.btSel.has(s.id) ? "checked" : ""}>
      <div class="grow"><div class="t">${esc(s.title)}</div>
        <div class="small muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.product || s.summary || "")}${s.batch ? ` · ${esc(batchLabel(s.batch))}` : ""}</div>
        <div class="small muted">${(s.beats || []).length} cảnh · khoảng ${scriptSeconds(s)} giây${s.origin === "auto" ? " · đã gắn sẵn đoạn quay" : ""}${s.why_it_works ? ` · ${esc(s.why_it_works)}` : ""}</div>
        ${open ? scriptPreview(s) : ""}</div>
      ${blanks.length ? `<span class="chip warn" title="${esc(blanks.join(" "))}">Còn ${blanks.length} ô trống</span>` : ""}
      <button class="btn sm" data-peek="${s.id}">${open ? "Ẩn kịch bản" : "Xem kịch bản"}</button>
      <span class="chip ${s.origin}">${s.channel ? esc(s.channel) + " · " : ""}${ORIGIN[s.origin] || ""}</span></label>`;
  }).join("") : `<div class="empty small">Không có kịch bản khớp</div>`;
  renderBatchEstimate();
}

// Độ dài ước tính: lời đọc khoảng 4 từ mỗi giây, cộng khoảng nghỉ đầu và cuối mỗi cảnh
function scriptSeconds(s) {
  return Math.round((s.beats || []).reduce((sum, b) => sum + beatSeconds(b), 0));
}

function beatSeconds(b) {
  const words = String(b.voice || "").trim().split(/\s+/).filter(Boolean).length;
  return words ? 0.5 + words / 4 : Math.max(1, parseFloat(b.duration) || 3);
}

function shotOf(clip) {
  if (!clip) return null;
  const src = S.sources.find((s) => s.id === clip.source_id);
  if (!src) return null;
  return (src.shots || []).find((sh) => clip.start >= sh.start - 0.01 && clip.start < sh.end) || null;
}

function scriptPreview(s) {
  const rows = (s.beats || []).map((b, i) => {
    const thumb = clipThumb(b.clip), shot = shotOf(b.clip);
    return `<tr><td class="muted">${i + 1}</td>
      <td>${thumb ? `<img src="${esc(thumb)}" alt="" class="peek-thumb">` : `<span class="muted small">${esc((b.shot || "").slice(0, 40)) || "–"}</span>`}</td>
      <td><div>${esc(b.voice) || `<span class="muted">(không có lời)</span>`}</div>
        <div class="small" style="margin-top:3px">${b.text
          ? `<span class="tag-text">Chữ trên hình: ${esc(b.text)}</span>`
          : `<span class="muted">${shot && shot.talking ? "Không chèn chữ · trong hình đã có người nói" : "Không chèn chữ"}</span>`}
          <span class="muted"> · ${Math.round(beatSeconds(b))}s${b.part ? ` · ${esc(b.part)}` : ""}</span></div></td></tr>`;
  }).join("");
  return `<div class="peek"><table class="peek-table"><tbody>${rows}</tbody></table>
    <div class="small muted">Tổng khoảng ${scriptSeconds(s)} giây. Lúc tạo, AI còn soát lại từng cảnh cho khớp video của bạn.</div></div>`;
}

$("#bt-scripts").addEventListener("click", (e) => {
  const id = e.target.dataset.peek;
  if (!id) return;
  e.preventDefault();   // bấm nút trong label thì không tick chọn kịch bản
  S.btOpen = S.btOpen || new Set();
  S.btOpen.has(id) ? S.btOpen.delete(id) : S.btOpen.add(id);
  renderBatchScripts();
});

// ---------- AI tự viết kịch bản từ video đã quay ----------
$("#gen-go").addEventListener("click", async () => {
  $("#gen-err").textContent = "";
  if (!S.settings.ai_ready) { $("#gen-err").textContent = "Cần nhập Anthropic API key trong Cài đặt trước."; return; }
  if (!S.sources.some((s) => s.status === "ready")) { $("#gen-err").textContent = "Chưa có video nguồn nào xử lý xong. Thả video vào Bước 1 trước."; return; }
  const btn = $("#gen-go");
  btn.disabled = true;
  $("#gen-hint").textContent = "AI đang xem từng phân đoạn, việc này mất vài phút…";
  try {
    const job = await api("POST", "/api/scripts/suggest", { count: parseInt($("#gen-count").value) || 3,
      note: $("#gen-note").value, channel: $("#gen-channel").value, mode: $("#bt-strict").value });
    watchJob(job, "Viết kịch bản từ video", async (res) => {
      btn.disabled = false; $("#gen-hint").textContent = "";
      S.btFresh = new Set(res.ids || []);
      $("#bt-search").value = ""; S.btChannel = "";
      await Promise.all([loadScripts(), loadSources()]);  // tải lại nguồn để hiện đoạn AI vừa xem và vừa bỏ
      $("#bt-scripts").scrollIntoView({ behavior: "smooth", block: "center" });
      toast(`Đã viết ${res.added} kịch bản từ ${res.shots} đoạn quay của bạn` +
        (res.dropped ? ` (bỏ ${res.dropped} đoạn còn chữ hoặc nét chèn sẵn)` : "") +
        " — chọn kịch bản bạn thích." + (res.note ? " " + res.note : ""));
    }, (err) => { btn.disabled = false; $("#gen-hint").textContent = ""; $("#gen-err").textContent = err; });
  } catch (err) { btn.disabled = false; $("#gen-hint").textContent = ""; $("#gen-err").textContent = err.message; }
});

function renderBatchEstimate() {
  const n = S.btSel.size;
  const blocked = [...S.btSel].map((id) => S.scripts.find((s) => s.id === id)).filter((s) => s && blanksOfScript(s).length).length;
  const ready = S.sources.filter((s) => s.status === "ready").length;
  $("#bt-selcount").textContent = n ? `· đã chọn ${n}` : "";
  const parts = [];
  if (n) parts.push(`<b>${n}</b> video, dựng khoảng <b>${Math.max(1, Math.round(n * 0.8))}–${Math.max(2, n * 2)} phút</b> tuỳ máy. Có thể để máy chạy và làm việc khác.`);
  else parts.push("Chọn ít nhất một kịch bản ở Bước 2.");
  if (blocked) parts.push(`${blocked} kịch bản còn ô <code>[kiểm tra]</code> trong lời đọc sẽ được giữ lại, sửa xong bấm Tiếp tục.`);
  if (!ready) parts.push("Chưa có video nguồn nào xử lý xong.");
  if (!S.settings.ai_ready) parts.push("Chưa có Anthropic API key: app vẫn tạo được video nhưng ghép cảnh đơn giản, không hiểu nội dung video.");
  $("#bt-estimate").innerHTML = parts.join("<br>");
  const running = S.batches.some((b) => b.status === "running");
  $("#bt-start").disabled = !n || !ready || running;
  $("#bt-start").textContent = running ? "Đang có một đợt chạy…" : n ? `Bắt đầu tạo ${n} video` : "Bắt đầu tạo video";
}

$("#bt-strict").addEventListener("change", renderBatchSources);
$("#bt-search").addEventListener("input", renderBatchScripts);
$("#bt-channels").addEventListener("click", (e) => { if (e.target.dataset.ch !== undefined) { S.btChannel = e.target.dataset.ch; renderBatchScripts(); } });
$("#bt-scripts").addEventListener("change", (e) => {
  const id = e.target.closest(".item").dataset.id;
  e.target.checked ? S.btSel.add(id) : S.btSel.delete(id);
  renderBatchEstimate();
});
$("#bt-all").addEventListener("click", () => { btVisibleScripts().forEach((s) => S.btSel.add(s.id)); renderBatchScripts(); });
$("#bt-none").addEventListener("click", () => { S.btSel.clear(); renderBatchScripts(); });

$("#bt-start").addEventListener("click", async () => {
  $("#bt-err").textContent = "";
  const order = S.scripts.filter((s) => S.btSel.has(s.id)).map((s) => s.id);
  try {
    const b = await api("POST", "/api/batches", { script_ids: order, options: {
      voice_mode: $("#bt-voice").value, music: $("#bt-music").value,
      source_volume: parseFloat($("#bt-audio").value), adapt: $("#bt-adapt").value === "1",
      review: $("#bt-review").value === "1", mode: $("#bt-strict").value } });
    S.btSel.clear(); renderBatchScripts();
    await loadBatches(b.id);
    $("#bt-run").scrollIntoView({ behavior: "smooth" });
  } catch (err) { $("#bt-err").textContent = err.message; }
});

async function loadBatches(selectId) {
  S.batches = await api("GET", "/api/batches");
  if (selectId) S.batchId = selectId;
  else if (!S.batchId || !S.batches.some((b) => b.id === S.batchId)) {
    const running = S.batches.find((b) => b.status === "running");
    S.batchId = (running || S.batches[0] || {}).id || null;
  }
  renderBatchRun();
  renderBatchEstimate();
  clearTimeout(btPoll);
  if (S.batches.some((b) => b.status === "running")) btPoll = setTimeout(pollBatch, 2500);
}

async function pollBatch() {
  try {
    const running = S.batches.find((b) => b.status === "running");
    if (running) {
      const fresh = await api("GET", `/api/batches/${running.id}`);
      S.batches[S.batches.findIndex((b) => b.id === fresh.id)] = fresh;
      if (fresh.status !== "running") { await loadBatches(); loadProjects(); return; }
      renderBatchRun();
    }
  } catch (e) { /* mạng chập chờn: thử lại lần sau */ }
  btPoll = setTimeout(pollBatch, 2500);
}

function itemHtml(it, i, b) {
  const [label0, cls] = BT_STATUS[it.status] || [it.status, ""];
  const label = it.status === "blocked" && it.block_kind === "footage" ? "Thiếu video quay" : label0;
  const rewritten = (it.changes || []).filter((c) => c.kind === "rewrite").length, dropped = (it.changes || []).filter((c) => c.kind === "drop").length;
  const reviewed = (it.changes || []).filter((c) => c.kind === "review").length;
  const adaptChip = rewritten || dropped || reviewed ? `<span class="chip running" title="Kịch bản gốc chỉ để tham khảo: các cảnh chưa khớp đã được viết lại theo video bạn quay và soát lại trước khi dựng">Đã chỉnh kịch bản</span>` : "";
  const lenChip = it.seconds ? `<span class="chip ${it.seconds >= 28 && it.seconds <= 45 ? "ok" : "warn"}" title="Độ dài ước tính của video">${Math.round(it.seconds)}s</span>` : "";
  const q = it.status === "done" ? (it.quality === "ok" ? `<span class="chip ok">Ghép cảnh tốt</span>` : `<span class="chip warn" title="Có cảnh chưa thật khớp hoặc dùng tạm, nên xem video và đổi cảnh nếu cần">Nên xem lại</span>`) : "";
  const open = S.openVideos && S.openVideos.has(`${b.id}:${i}`);
  return `<div class="run-item" data-i="${i}">
    <div class="row" style="gap:8px">
      <span class="chip ${cls}">${label}</span>${q}${adaptChip}${lenChip}
      <div class="grow"><b>${esc(it.title)}</b>
        <div class="small ${it.status === "error" || it.status === "blocked" ? "err" : "muted"}">${esc(it.status === "done" ? "" : it.message)}</div></div>
      ${it.status === "done" ? `<button class="btn sm" data-act="view">${open ? "Ẩn video" : "Xem"}</button>
        <a class="btn sm" href="${esc(it.render.path)}" download>Tải về</a>` : ""}
      ${it.project_id ? `<button class="btn sm" data-act="project">Mở để chỉnh</button>` : ""}
      ${it.status === "blocked" && it.block_kind !== "footage" ? `<button class="btn sm" data-act="script">Sửa kịch bản</button>` : ""}
    </div>
    ${(it.changes || []).length ? `<details class="small" style="margin-top:4px"><summary style="cursor:pointer">Xem ${[rewritten ? `${rewritten} cảnh đã viết lại` : "", dropped ? `${dropped} cảnh đã bỏ` : "", reviewed ? `${reviewed} cảnh đã soát lại` : ""].filter(Boolean).join(", ")}</summary>
      ${it.changes.map((c) => `<div style="margin:6px 0;padding-left:8px;border-left:3px solid var(--bd)"><b>Cảnh ${c.beat + 1}${c.kind === "drop" ? " (bỏ)" : c.kind === "review" ? " (soát lại)" : ""}</b>
        <div class="muted">Gốc: ${esc(c.old)}</div>${c.kind === "drop" ? "" : `<div>Mới: ${esc(c.new)}</div>`}<div class="muted">${esc(c.reason)}</div></div>`).join("")}</details>` : ""}
    ${(it.warnings || []).length ? `<div class="small" style="color:var(--wn);margin-top:4px">${it.warnings.map(esc).join("<br>")}</div>` : ""}
    ${open ? `<video src="${esc(it.render.path)}" controls playsinline preload="metadata"></video>` : ""}</div>`;
}

function renderBatchRun() {
  const box = $("#bt-run");
  const b = S.batches.find((x) => x.id === S.batchId);
  if (!b) { box.innerHTML = ""; return; }
  S.openVideos = S.openVideos || new Set();
  const total = b.items.length;
  const finished = b.items.filter((i) => ["done", "blocked", "error"].includes(i.status)).length;
  const done = b.items.filter((i) => i.status === "done").length;
  const stuck = b.items.filter((i) => ["blocked", "error"].includes(i.status)).length;
  const head = `
    <div class="row"><h3 class="grow">${esc(b.name)} <span class="chip ${b.status === "running" ? "running" : b.status === "done" ? "ok" : "warn"}">${BT_RUN[b.status] || b.status}</span></h3>
      ${S.batches.length > 1 ? `<select id="bt-pick" style="width:auto">${S.batches.map((x) => `<option value="${x.id}" ${x.id === b.id ? "selected" : ""}>${esc(x.name)} (${x.items.filter((i) => i.status === "done").length}/${x.items.length})</option>`).join("")}</select>` : ""}
      ${b.status === "running" ? `<button class="btn" data-act="cancel">Dừng</button>` : ""}
      ${b.status !== "running" && (b.items.some((i) => ["pending", "blocked", "error"].includes(i.status))) ? `<button class="btn primary" data-act="resume">Tiếp tục${stuck ? " (kiểm tra lại các video bị giữ)" : ""}</button>` : ""}
      ${done ? `<a class="btn primary" href="/api/batches/${b.id}/zip" download>Tải tất cả (${done} video, ZIP)</a>` : ""}
      ${b.status !== "running" ? `<button class="btn ghost" data-act="delete" title="Xoá đợt này">✕</button>` : ""}</div>
    <div class="bar"><i style="width:${total ? (finished / total) * 100 : 0}%"></i></div>
    <div class="small muted">${finished}/${total} · ${done} video xong${stuck ? ` · ${stuck} cần xử lý` : ""} · ${esc(b.message || "")}</div>
    ${(b.notes || []).map((n) => `<div class="warn">${esc(n)}</div>`).join("")}
    ${(b.missing || []).length ? `<div class="warn"><b>Gợi ý quay thêm để video lần sau tốt hơn:</b><ul style="margin:6px 0 0">${b.missing.map((m) => `<li>${esc(m.text)} <span class="muted">(cho ${m.codes.map(esc).join(", ")})</span></li>`).join("")}</ul></div>` : ""}`;
  let host = $("#bt-run-card");
  if (!host || host.dataset.id !== b.id) {
    box.innerHTML = `<div class="card stack" id="bt-run-card" data-id="${b.id}"><div id="bt-run-head" class="stack"></div><div class="stack" id="bt-items"></div></div>`;
    host = $("#bt-run-card");
  }
  $("#bt-run-head").innerHTML = head;
  // chỉ thay hàng nào thay đổi để video đang xem không bị tải lại
  const list = $("#bt-items");
  b.items.forEach((it, i) => {
    const html = itemHtml(it, i, b);
    let row = list.children[i];
    if (!row) { list.insertAdjacentHTML("beforeend", html); return; }
    if (row.dataset.html !== html) { row.outerHTML = html; row = list.children[i]; }
    row.dataset.html = html;
  });
  [...list.children].forEach((row, i) => { row.dataset.html = itemHtml(b.items[i], i, b); });
}

$("#bt-run").addEventListener("change", (e) => { if (e.target.id === "bt-pick") { S.batchId = e.target.value; $("#bt-run").innerHTML = ""; renderBatchRun(); } });
$("#bt-run").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const b = S.batches.find((x) => x.id === S.batchId);
  const row = btn.closest(".run-item");
  const it = row ? b.items[+row.dataset.i] : null;
  try {
    if (btn.dataset.act === "cancel") { await api("POST", `/api/batches/${b.id}/cancel`); toast("Sẽ dừng sau khi dựng xong video đang chạy"); }
    else if (btn.dataset.act === "resume") { await api("POST", `/api/batches/${b.id}/resume`); await loadScripts(); await loadBatches(b.id); }
    else if (btn.dataset.act === "delete") { if (!confirm("Xoá đợt này? Các video đã xuất vẫn còn trong từng dự án.")) return; await api("DELETE", `/api/batches/${b.id}`); S.batchId = null; await loadBatches(); }
    else if (btn.dataset.act === "view") { const k = `${b.id}:${row.dataset.i}`; S.openVideos.has(k) ? S.openVideos.delete(k) : S.openVideos.add(k); renderBatchRun(); }
    else if (btn.dataset.act === "project") { await loadProjects(); await selectProject(it.project_id); showPage("studio"); }
    else if (btn.dataset.act === "script") { await loadScripts(it.script_id); showPage("scripts"); }
  } catch (err) { toast(err.message); }
});

// ================= KHỞI ĐỘNG =================
(async function init() {
  const st = await api("GET", "/api/state");
  Object.assign(S, { settings: st.settings, voices: st.voices, providers: st.providers,
    fonts: st.fonts || [], colors: st.colors || [], music: st.music || [],
    videoExt: st.video_ext || S.videoExt });
  $("#ver").textContent = st.version ? `v${st.version}` : "";
  if (st.ffmpeg && st.ffmpeg.problems.length) {
    const box = $("#env-warn");
    box.hidden = false;
    box.innerHTML = `<b>ffmpeg trên máy thiếu chức năng, video có thể dựng lỗi:</b><ul style="margin:6px 0 0">${st.ffmpeg.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>Cài lại bản ffmpeg đầy đủ theo hướng dẫn (bước 2 phần A).`;
  }
  renderSettings();
  await Promise.all([loadScripts(), loadSources(), loadProjects()]);
  renderBatchScripts();
  await loadBatches();
  const page = location.hash.slice(1);
  if (["batch", "scripts", "sources", "studio", "settings"].includes(page)) showPage(page);
  if (!S.settings.ai_ready) toast("Chưa có Anthropic API key: nhập trong Cài đặt để dùng các tính năng AI");
})();
