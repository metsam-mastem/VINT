const $ = (selector) => document.querySelector(selector);
const input = $("#fileInput");
const results = $("#results");
const records = [];
let engineOn = false;

const supported = {
  mp4: { ext: [".mp4"], media: "video", mime: ["video/mp4"] },
  mp3: { ext: [".mp3"], media: "audio", mime: ["audio/mpeg", "audio/mp3"] },
  wav: { ext: [".wav"], media: "audio", mime: ["audio/wav", "audio/x-wav"] },
  jpeg: { ext: [".jpg", ".jpeg"], media: "image", mime: ["image/jpeg"] },
  png: { ext: [".png"], media: "image", mime: ["image/png"] },
  pdf: { ext: [".pdf"], media: "document", mime: ["application/pdf"] }
};

function detectFormat(bytes) {
  const starts = (...values) => values.every((value, index) => bytes[index] === value);
  if (bytes.length >= 12 && String.fromCharCode(...bytes.slice(4, 8)) === "ftyp") return "mp4";
  if (starts(0x49, 0x44, 0x33) || (bytes.length > 1 && bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0)) return "mp3";
  if (bytes.length >= 12 && (String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" || String.fromCharCode(...bytes.slice(0, 4)) === "RF64") && String.fromCharCode(...bytes.slice(8, 12)) === "WAVE") return "wav";
  if (starts(0xff, 0xd8, 0xff)) return "jpeg";
  if (starts(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) return "png";
  if (String.fromCharCode(...bytes.slice(0, 5)) === "%PDF-") return "pdf";
  return null;
}

function humanSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return value.toFixed(2) + " " + units[unit];
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
}

async function mediaMetadata(file, format) {
  if (format === "jpeg" || format === "png") {
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      return { width: image.naturalWidth, height: image.naturalHeight };
    } finally { URL.revokeObjectURL(url); }
  }
  if (format === "mp4" || format === "mp3" || format === "wav") {
    const url = URL.createObjectURL(file);
    try {
      const element = document.createElement(format === "mp4" ? "video" : "audio");
      element.preload = "metadata";
      element.src = url;
      await new Promise((resolve, reject) => {
        element.onloadedmetadata = resolve;
        element.onerror = () => reject(new Error("مرورگر نتوانست فرادادهٔ رسانه را بخواند"));
      });
      const metadata = {};
      if (Number.isFinite(element.duration)) metadata.duration_ms = Math.round(element.duration * 1000);
      if (format === "mp4") {
        if (element.videoWidth) metadata.width = element.videoWidth;
        if (element.videoHeight) metadata.height = element.videoHeight;
      }
      element.removeAttribute("src");
      element.load();
      return metadata;
    } finally { URL.revokeObjectURL(url); }
  }
  return {};
}

function render() {
  $("#fileCount").textContent = new Intl.NumberFormat("fa-IR").format(records.length) + " فایل بررسی‌شده";
  $("#clearButton").disabled = records.length === 0;
  $("#exportButton").disabled = records.length === 0;
  if (!records.length) {
    results.innerHTML = '<div class="empty-state">هنوز فایلی وارد نشده است.</div>';
    return;
  }
  results.innerHTML = records.map((record) => {
    const details = record.error
      ? '<div class="file-error">' + escapeHtml(record.error) + '</div>'
      : '<div class="file-meta"><span>' + escapeHtml(humanSize(record.byte_size)) + '</span><span>' + escapeHtml(record.media_type) + '</span><span>' + escapeHtml(record.metadata.detected_format.toUpperCase()) + '</span>' +
        (record.duration_ms ? '<span>' + (record.duration_ms / 1000).toFixed(2) + ' sec</span>' : '') +
        (record.width ? '<span>' + record.width + ' × ' + record.height + '</span>' : '') + '</div><div class="hash">SHA-256 · ' + record.sha256 + '</div>';
    return '<article class="file-card"><div class="file-top"><span class="file-name">' + escapeHtml(record.filename) + '</span><span class="file-type">' + (record.error ? "REJECTED" : "INSPECTED") + '</span></div>' + details + '</article>';
  }).join("");
}

async function hashFileInChunks(file) {
  const hasher = new RISha256();
  const chunkSize = 4 * 1024 * 1024;
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    const chunk = await file.slice(offset, Math.min(offset + chunkSize, file.size)).arrayBuffer();
    hasher.update(new Uint8Array(chunk));
  }
  return hasher.digest();
}

async function inspect(file) {
  if (!engineOn) throw new Error("ابتدا موتور محلی را روشن کن.");
  if (!file || file.size === 0) throw new Error("فایل خالی است.");
  const extension = "." + (file.name.split(".").pop() || "").toLowerCase();
  const bytes = new Uint8Array(await file.slice(0, 32).arrayBuffer());
  const format = detectFormat(bytes);
  if (!format || !supported[format].ext.includes(extension)) throw new Error("قالب فایل پشتیبانی نمی‌شود یا پسوند با امضای فایل مطابقت ندارد.");
  const sha256 = await hashFileInChunks(file);
  const metadata = { detected_format: format, extension };
  const media = await mediaMetadata(file, format);
  Object.assign(metadata, media);
  return {
    schema_version: "1.0",
    record_type: "asset",
    asset_id: "asset-" + sha256.slice(0, 24),
    sha256,
    media_type: supported[format].media,
    filename: file.name,
    byte_size: file.size,
    source: { kind: "browser_local_file" },
    created_at: new Date().toISOString(),
    ...(media.duration_ms ? { duration_ms: media.duration_ms } : {}),
    ...(media.width ? { width: media.width, height: media.height } : {}),
    metadata
  };
}

async function addFiles(files) {
  if (!engineOn) {
    $("#engineLabel").textContent = "ENGINE OFF";
    return;
  }
  for (const file of files) {
    try {
      const record = await inspect(file);
      if (!records.some((item) => item.sha256 === record.sha256)) records.push(record);
    } catch (error) {
      records.push({ filename: file.name, byte_size: file.size, media_type: "unknown", metadata: {}, error: error.message });
    }
    render();
  }
}

$("#powerSwitch").addEventListener("click", () => {
  engineOn = !engineOn;
  $("#powerSwitch").setAttribute("aria-pressed", String(engineOn));
  $("#powerText").textContent = engineOn ? "خاموش کردن موتور" : "روشن کردن موتور";
  $("#engineLabel").textContent = engineOn ? "LOCAL ENGINE ON" : "STANDBY";
  $("#engineLabel").style.color = engineOn ? "var(--green)" : "var(--amber)";
  $("#connectionState").textContent = engineOn ? "موتور محلی فعال است" : "موتور در حالت آماده‌باش";
});
input.addEventListener("change", () => addFiles(Array.from(input.files || [])));
$("#clearButton").addEventListener("click", () => { records.length = 0; input.value = ""; render(); });
$("#exportButton").addEventListener("click", () => {
  const valid = records.filter((item) => !item.error);
  const report = { report_version: "1.0", generated_at: new Date().toISOString(), processing_mode: "browser_local", assets: valid, rejected_files: records.filter((item) => item.error).map(({filename, error}) => ({filename, error})) };
  const blob = new Blob([JSON.stringify(report, null, 2)], {type: "application/json;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "reel-intelligence-report.json";
  link.click();
  URL.revokeObjectURL(url);
});
const dropZone = $("#dropZone");
for (const eventName of ["dragenter", "dragover"]) dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.add("dragover"); });
for (const eventName of ["dragleave", "drop"]) dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.remove("dragover"); });
dropZone.addEventListener("drop", (event) => addFiles(Array.from(event.dataTransfer.files || [])));

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("./sw.js").then(() => {
    $("#connectionState").textContent = "محیط آماده · قابلیت آفلاین فعال";
  }).catch(() => { $("#connectionState").textContent = "محیط محلی آماده"; }));
}
