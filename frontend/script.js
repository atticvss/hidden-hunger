const API_URL = "/api/scans/upload";
const HISTORY_API_URL = "/api/history/";

// ── Element refs ──────────────────────────────────────────────
const fileInput      = document.getElementById("file-input");
const browseBtn      = document.getElementById("browse-btn");
const dropZone       = document.getElementById("drop-zone");
const clearBtn       = document.getElementById("clear-btn");
const fileInfo       = document.getElementById("file-info");
const fileName       = document.getElementById("file-name");
const fileSize       = document.getElementById("file-size");
const processBtn     = document.getElementById("process-btn");
const nirBand        = document.getElementById("nir-band");
const reBand         = document.getElementById("re-band");
const stressThreshold = document.getElementById("stress-threshold");
const sampleIdInput = document.getElementById("sample-id");
const plantIdInput = document.getElementById("plant-id");
const autoBandSelect = document.getElementById("auto-band-select");
const autoThreshold = document.getElementById("auto-threshold");
const progressWrap   = document.getElementById("progress-wrap");
const progressBar    = document.getElementById("progress-bar");
const progressPct    = document.getElementById("progress-pct");
const progressLabel  = document.getElementById("progress-label");
const originalImg    = document.getElementById("original-img");
const originalMeta   = document.getElementById("original-meta");
const originalPlaceholder = document.getElementById("original-placeholder");
const heatmapImg     = document.getElementById("heatmap-img");
const heatmapPlaceholder  = document.getElementById("heatmap-placeholder");
const heatmapTitle   = document.getElementById("heatmap-title");
const statMinLabel   = document.getElementById("stat-min-label");
const statMaxLabel   = document.getElementById("stat-max-label");
const statMeanLabel  = document.getElementById("stat-mean-label");
const statStdLabel   = document.getElementById("stat-std-label");
const stressLabel    = document.getElementById("stress-label");
const stressHint     = document.getElementById("stress-hint");
const temporalDeltaLabel = document.getElementById("temporal-delta-label");
const statMin        = document.getElementById("stat-min");
const statMax        = document.getElementById("stat-max");
const statMean       = document.getElementById("stat-mean");
const statStd        = document.getElementById("stat-std");
const statStress     = document.getElementById("stat-stress");
const stressBadge    = document.getElementById("stress-badge");
const stressBadgeMeta = stressBadge?.querySelector("span:last-child");
const diagSummary    = document.getElementById("diag-summary");
const diagClass      = document.getElementById("diag-class");
const diagConfidence = document.getElementById("diag-confidence");
const diagExplanation = document.getElementById("diag-explanation");
const diagTopFeatures = document.getElementById("diag-top-features");
const temporalTrend = document.getElementById("temporal-trend");
const temporalNdreDelta = document.getElementById("temporal-ndre-delta");
const temporalStressDelta = document.getElementById("temporal-stress-delta");
const temporalOnset = document.getElementById("temporal-onset");
const temporalNote = document.getElementById("temporal-note");
const errorBanner    = document.getElementById("error-banner");
const errorMsg       = document.getElementById("error-msg");
const analysisWarning = document.getElementById("analysis-warning");
const analysisWarningMsg = document.getElementById("analysis-warning-msg");
const historyBody    = document.getElementById("history-body");
const historyEmpty   = document.getElementById("history-empty");
const historyCount   = document.getElementById("history-count");
const modeHelp       = document.getElementById("mode-help");

const recentStressValues = [];
const DEFAULT_METRIC_LABELS = {
  heatmap_title: "NDRE Heatmap",
  min_label: "NDRE Min",
  max_label: "NDRE Max",
  mean_label: "Mean",
  std_label: "Std Dev",
  stress_label: "Stress Area",
  stress_hint: `pixels below ${(Number(stressThreshold?.value || 0.2)).toFixed(2)}`,
  temporal_delta_label: "NDRE Change",
};
const RGB_METRIC_LABELS = {
  heatmap_title: "Proxy Health Map",
  min_label: "Proxy Min",
  max_label: "Proxy Max",
  mean_label: "Proxy Mean",
  std_label: "Proxy Std Dev",
  stress_label: "Low Health Area",
  stress_hint: `proxy score below ${(Number(stressThreshold?.value || 0.2)).toFixed(2)}`,
  temporal_delta_label: "Proxy Change",
};
let activeMetricLabels = { ...DEFAULT_METRIC_LABELS };

fetchHistory();
applyMetricLabels(DEFAULT_METRIC_LABELS);
applyInputMode("hyperspectral");

// ── File handling ─────────────────────────────────────────────
browseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) bindFile(fileInput.files[0]);
});

dropZone.addEventListener("dragover", e => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const f = e.dataTransfer.files[0];
  if (f) bindFile(f);
});

clearBtn.addEventListener("click", resetFile);

function bindFile(f) {
  const mode = detectFileMode(f.name);
  if (!mode) {
    showError("Supported uploads: .npy, .jpg, .jpeg, .png, .webp.");
    return;
  }
  hideError();
  applyInputMode(mode);
  applyMetricLabels(mode === "rgb" ? RGB_METRIC_LABELS : DEFAULT_METRIC_LABELS);

  // Show file info bar
  fileName.textContent = f.name;
  fileSize.textContent = (f.size / 1024).toFixed(1) + " KB";
  fileInfo.classList.remove("hidden");

  if (mode === "rgb") {
    const reader = new FileReader();
    reader.onload = () => {
      originalImg.src = String(reader.result || "");
      originalImg.classList.remove("hidden");
      originalPlaceholder.classList.add("hidden");
    };
    reader.readAsDataURL(f);
    originalMeta.textContent = `${f.name} · ${(f.size / 1024).toFixed(1)} KB · RGB photo`;
  } else {
    // NPY files are not browser-renderable images, so keep placeholder and show metadata only.
    originalImg.classList.add("hidden");
    originalPlaceholder.classList.remove("hidden");
    originalMeta.textContent = `${f.name} · ${(f.size / 1024).toFixed(1)} KB · NPY cube`;
  }

  processBtn.disabled = false;
  hideAnalysisWarning();

  // Attach file to input element for later use
  processBtn._file = f;
  processBtn._fileMode = mode;
}

function resetFile() {
  fileInput.value = "";
  fileInfo.classList.add("hidden");
  originalImg.classList.add("hidden");
  originalPlaceholder.classList.remove("hidden");
  originalMeta.textContent = "— × — px · — bands";
  processBtn.disabled = true;
  processBtn._file = null;
  processBtn._fileMode = null;
  recentStressValues.length = 0;
  resetResults();
  applyMetricLabels(DEFAULT_METRIC_LABELS);
  applyInputMode("hyperspectral");
  hideError();
  hideAnalysisWarning();
}

// ── Process button ────────────────────────────────────────────
processBtn.addEventListener("click", async () => {
  const file = processBtn._file;
  if (!file) { showError("No file selected."); return; }
  const fileMode = processBtn._fileMode || detectFileMode(file.name) || "hyperspectral";

  // Loading state
  setButtonState("processing");
  hideError();
  resetResults();
  showProgress("Uploading…", 10);

  const formData = new FormData();
  formData.append("file", file);
  formData.append("nir_band", nirBand.value);
  formData.append("red_edge_band", reBand.value);
  formData.append("stress_threshold", stressThreshold?.value || "0.2");
  if (sampleIdInput?.value?.trim()) {
    formData.append("sample_id", sampleIdInput.value.trim());
  }
  if (plantIdInput?.value?.trim()) {
    formData.append("plant_id", plantIdInput.value.trim());
  }
  formData.append("auto_select_bands", autoBandSelect?.checked ? "true" : "false");
  formData.append("auto_calibrate_threshold", autoThreshold?.checked ? "true" : "false");

  try {
    showProgress("Sending to server…", 30);

    const res = await fetch(API_URL, {
      method: "POST",
      body: formData,
    });

    showProgress(fileMode === "rgb" ? "Analyzing foliage…" : "Processing bands…", 70);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      if (err?.error?.code === "UNSUPPORTED_BAND_INDEX") {
        const totalBands = Number(err?.error?.details?.total_bands || 0);
        if (totalBands > 0) {
          const fixedNir = Math.min(Number(nirBand.value || 1), totalBands);
          let fixedRe = Math.min(Number(reBand.value || 1), totalBands);
          if (fixedRe === fixedNir) {
            fixedRe = Math.max(1, fixedNir - 1);
          }
          nirBand.value = String(fixedNir);
          reBand.value = String(fixedRe);
        }
      }

      const msg =
        err?.error?.message ||
        err?.detail?.message ||
        err?.detail ||
        `HTTP ${res.status}`;
      throw new Error(msg);
    }

    const data = await res.json();
    showProgress("Rendering heatmap…", 95);

    renderResults(data);
    fetchHistory();
    showProgress("Done", 100);

    setTimeout(() => progressWrap.classList.add("hidden"), 800);
  } catch (err) {
    showError(err.message);
    progressWrap.classList.add("hidden");
  } finally {
    setButtonState("idle");
  }
});

// ── Render helpers ────────────────────────────────────────────
function renderResults(data) {
  const analysisMode = data.analysis_mode === "rgb_proxy" ? "rgb" : "hyperspectral";
  applyInputMode(analysisMode);
  applyMetricLabels(data.metric_labels || (analysisMode === "rgb" ? RGB_METRIC_LABELS : DEFAULT_METRIC_LABELS));

  if (data.selected_nir_band) {
    nirBand.value = String(data.selected_nir_band);
  }
  if (data.selected_red_edge_band) {
    reBand.value = String(data.selected_red_edge_band);
  }

  // Heatmap (if available)
  if (data.heatmap_base64) {
    heatmapImg.src = `data:image/png;base64,${data.heatmap_base64}`;
    heatmapImg.classList.remove("hidden");
    heatmapPlaceholder.classList.add("hidden");
  }

  // Source preview (NPY uploads)
  if (data.source_image_base64) {
    originalImg.src = `data:image/png;base64,${data.source_image_base64}`;
    originalImg.classList.remove("hidden");
    originalPlaceholder.classList.add("hidden");
  } else if (data.source_image_path) {
    const path = data.source_image_path.startsWith("/")
      ? data.source_image_path
      : `/${data.source_image_path}`;
    originalImg.src = path;
    originalImg.classList.remove("hidden");
    originalPlaceholder.classList.add("hidden");
  }

  // Original meta - support both old and new response formats
  const shape = data.cube_shape || data.image_shape;
  const width = data.image_width ?? shape?.width ?? shape?.height;  // cube_shape order: {height, width, bands}
  const height = data.image_height ?? shape?.height;
  let bands = data.total_bands ?? shape?.bands;
  
  // If cube_shape is array format [h, w, b], extract bands from third element
  if (Array.isArray(shape) && shape.length >= 3) {
    bands = shape[2];
  }

  const metaParts = [];
  if (width && height) metaParts.push(`${width} × ${height} px`);
  if (bands) metaParts.push(`${bands} bands`);
  
  const nirBandVal = data.bands_used?.nir_band ?? data.selected_nir_band;
  const reBandVal = data.bands_used?.red_edge_band ?? data.selected_red_edge_band;
  if (nirBandVal && reBandVal) {
    const mode = data.auto_band_selection_used ? "auto" : "manual";
    metaParts.push(`Bands NIR=${nirBandVal}, RE=${reBandVal} (${mode})`);
  }
  if (data.source_image_bands && data.source_image_bands.r) {
    const bands = data.source_image_bands;
    metaParts.push(`Preview RGB: R=${bands.r}, G=${bands.g}, B=${bands.b}`);
  }

  // Multiclass classification info
  const classification = data.classification || {};
  const healthStatus = classification.health_status || data.health_status || "unknown";
  const predictedClass = classification.predicted_class || data.predicted_class || "Unclassified";
  
  if (healthStatus && healthStatus !== "unknown") {
    metaParts.push(`Status: ${healthStatus}`);
  }
  if (predictedClass && predictedClass !== "Unclassified") {
    const conf = typeof classification.confidence === "number" 
      ? ` (${(classification.confidence * 100).toFixed(1)}%)`
      : typeof data.confidence === "number"
        ? ` (${(data.confidence * 100).toFixed(1)}%)`
        : "";
    metaParts.push(`${formatClassLabel(predictedClass)}${conf}`);
  }
  if (analysisMode === "rgb") {
    metaParts.push("RGB proxy workflow");
  }
  originalMeta.textContent = metaParts.join(" · ") || "— × — px · — bands";

  // Stats
  const s = data.ndre_stats;
  if (s) {
    statMin.textContent    = Number(s.min ?? 0).toFixed(4);
    statMax.textContent    = Number(s.max ?? 0).toFixed(4);
    statMean.textContent   = Number(s.mean ?? 0).toFixed(4);
    statStd.textContent    = Number(s.std ?? 0).toFixed(4);
  } else {
    [statMin, statMax, statMean, statStd].forEach(el => el.textContent = "—");
  }
  statStress.textContent = `${Number(data.stress_percentage ?? 0).toFixed(2)}%`;

  // Diagnosis - multiclass format
  const confidence = classification.confidence ?? data.confidence;
  const confidencePct = typeof confidence === "number"
    ? `${(confidence * 100).toFixed(1)}%`
    : "—";

  if (diagSummary) {
    diagSummary.textContent = data.diagnosis_summary || `${healthStatus} · ${formatClassLabel(predictedClass)} (${confidencePct})`;
  }
  if (diagClass) {
    diagClass.textContent = formatClassLabel(predictedClass);
    diagClass.className = `font-mono text-sm ${stressTypeClass(predictedClass)}`;
  }
  if (diagConfidence) {
    diagConfidence.textContent = confidencePct;
  }

  // Explanation summary (prefer backend beginner-friendly explanation)
  if (diagExplanation) {
    const explanationSummary = data.explanation_summary || classification.explanation_summary;
    const probs = data.class_probabilities || classification.class_probabilities || {};
    if (explanationSummary) {
      diagExplanation.textContent = explanationSummary;
      diagExplanation.style.fontFamily = "inherit";
      diagExplanation.style.fontSize = "0.85rem";
      diagExplanation.style.whiteSpace = "normal";
      diagExplanation.style.lineHeight = "1.5";
    } else if (Object.keys(probs).length > 0) {
      // Show probability distribution
      const probItems = Object.entries(probs)
        .sort((a, b) => b[1] - a[1])
        .map(([cls, prob]) => {
          const label = formatClassLabel(cls);
          const pct = (prob * 100).toFixed(1);
          const bar = "█".repeat(Math.round(prob * 20));
          return `${label}: ${pct}% ${bar}`;
        });
      diagExplanation.textContent = probItems.join("\n");
      diagExplanation.style.fontFamily = "monospace";
      diagExplanation.style.fontSize = "0.85rem";
      diagExplanation.style.whiteSpace = "pre";
      diagExplanation.style.lineHeight = "1.4";
    } else {
      diagExplanation.textContent = data.explanation || "Multiclass stress classification complete.";
      diagExplanation.style.fontFamily = "inherit";
      diagExplanation.style.whiteSpace = "normal";
    }
  }

  // Top contributing features (fallback to alternatives when unavailable)
  if (diagTopFeatures) {
    const topFeatures = Array.isArray(data.top_features) ? data.top_features.slice(0, 5) : [];
    const alternatives = data.top_alternatives || [];
    diagTopFeatures.innerHTML = "";

    if (topFeatures.length) {
      topFeatures.forEach((item, idx) => {
        const li = document.createElement("li");
        li.className = "flex items-start justify-between gap-3";

        const name = item.feature || `Feature ${idx + 1}`;
        const val = typeof item.value === "number" ? item.value.toFixed(4) : "—";
        const contrib = typeof item.contribution === "number" ? item.contribution.toFixed(4) : "—";
        const direction = String(item.direction || "").toLowerCase();
        const directionText = direction === "decreased" ? "decreased score" : "increased score";

        li.innerHTML = `
          <div class="flex-1">
            <p class="text-text">${idx + 1}. ${escapeHtml(name)}</p>
            <p class="text-muted text-[11px]">value ${val} · ${directionText}</p>
          </div>
          <span class="text-muted font-mono">${contrib}</span>
        `;
        diagTopFeatures.appendChild(li);
      });
    } else if (!alternatives.length) {
      const li = document.createElement("li");
      li.className = "text-muted";
      li.textContent = "No alternatives";
      diagTopFeatures.appendChild(li);
    } else {
      alternatives.forEach((item, idx) => {
        const li = document.createElement("li");
        li.className = "flex items-center justify-between gap-2";
        
        const className = item.class_name || `Class ${idx + 1}`;
        const prob = typeof item.probability === "number" 
          ? `${(item.probability * 100).toFixed(1)}%`
          : "—";
        
        li.innerHTML = `
          <span class="text-text">${idx + 1}. ${escapeHtml(formatClassLabel(className))}</span>
          <span class="text-muted font-mono">${prob}</span>
        `;
        diagTopFeatures.appendChild(li);
      });
    }
  }

  // Show inference summary in badge
  if (stressBadgeMeta) {
    const conf = typeof confidence === "number"
      ? ` · conf ${(confidence * 100).toFixed(1)}%`
      : "";
    stressBadgeMeta.textContent = `${healthStatus} · ${formatClassLabel(predictedClass)}${conf}`;
  }

  // Colour-code stress percentage
  const sp = Number(data.stress_percentage ?? 0);
  statStress.className = `font-mono text-xl ${sp > 50 ? "text-danger" : sp > 25 ? "text-warn" : "text-accent"}`;

  if (analysisWarningMsg && Number.isFinite(data.heatmap_vmin) && Number.isFinite(data.heatmap_vmax)) {
    const lo = Number(data.heatmap_vmin).toFixed(3);
    const hi = Number(data.heatmap_vmax).toFixed(3);
    showAnalysisWarning(`Heatmap contrast range: [${lo}, ${hi}]`);
  }

  updateStressWarning(sp, analysisMode);

  renderTemporalAnalysis(data.temporal_analysis || null);
}

function renderTemporalAnalysis(temporal) {
  if (!temporalTrend || !temporalNdreDelta || !temporalStressDelta || !temporalOnset || !temporalNote) return;

  if (!temporal) {
    temporalTrend.textContent = "—";
    temporalTrend.className = "font-mono text-sm text-muted";
    temporalNdreDelta.textContent = "—";
    temporalNdreDelta.className = "font-mono text-sm text-muted";
    temporalStressDelta.textContent = "—";
    temporalStressDelta.className = "font-mono text-sm text-muted";
    temporalOnset.textContent = "—";
    temporalOnset.className = "font-mono text-sm text-muted";
    temporalNote.textContent = "No temporal baseline yet.";
    return;
  }

  temporalTrend.textContent = formatClassLabel(temporal.trend_label || "stable");
  temporalTrend.className = `font-mono text-sm ${trendClass(temporal.trend_label)}`;

  temporalNdreDelta.textContent = formatSignedValue(temporal.ndre_mean_delta, 4);
  temporalNdreDelta.className = `font-mono text-sm ${deltaClass(temporal.ndre_mean_delta, false)}`;

  temporalStressDelta.textContent = formatSignedValue(temporal.stress_percentage_delta, 2, "%");
  temporalStressDelta.className = `font-mono text-sm ${deltaClass(temporal.stress_percentage_delta, true)}`;

  temporalOnset.textContent = temporal.onset_detected ? "Detected" : "Not detected";
  temporalOnset.className = `font-mono text-sm ${temporal.onset_detected ? "text-danger" : "text-accent"}`;

  if (!temporal.has_baseline) {
    temporalNote.textContent = temporal.no_baseline_reason || "First scan for this sample. No baseline available.";
    return;
  }

  const sampleText = temporal.sample_id ? `sample ${temporal.sample_id}` : "this sample";
  const onsetScore = typeof temporal.onset_score === "number" ? temporal.onset_score.toFixed(2) : "0.00";
  temporalNote.textContent = `${sampleText}: ${temporal.onset_reason || "No onset reason."} (score ${onsetScore}).`;
}

function resetResults() {
  heatmapImg.classList.add("hidden");
  heatmapPlaceholder.classList.remove("hidden");
  [statMin, statMax, statMean, statStd, statStress].forEach(el => el.textContent = "—");
  statStress.className = "font-mono text-xl text-warn";
  if (diagSummary) diagSummary.textContent = "—";
  if (diagClass) {
    diagClass.textContent = "—";
    diagClass.className = "font-mono text-sm text-accent";
  }
  if (diagConfidence) diagConfidence.textContent = "—";
  if (diagExplanation) diagExplanation.textContent = "—";
  if (diagTopFeatures) diagTopFeatures.innerHTML = '<li class="text-muted">—</li>';
  renderTemporalAnalysis(null);
  if (stressBadgeMeta) {
    stressBadgeMeta.textContent = activeMetricLabels.stress_hint || "Awaiting analysis";
  }
}

function updateStressWarning(stressPct, analysisMode = "hyperspectral") {
  if (analysisMode !== "hyperspectral") {
    recentStressValues.length = 0;
    return;
  }

  if (Number.isFinite(stressPct)) {
    recentStressValues.push(stressPct);
    if (recentStressValues.length > 5) {
      recentStressValues.shift();
    }
  }

  const highStressCount = recentStressValues.filter(v => v >= 95).length;
  if (highStressCount >= 3) {
    const n = Number(nirBand?.value || 0);
    const r = Number(reBand?.value || 0);
    const t = Number(stressThreshold?.value || 0.2);
    showAnalysisWarning(
      `Recent uploads are showing >=95% stress repeatedly. Band mapping may be unstable for these cubes. Keep Auto-select enabled and try lowering threshold from ${t.toFixed(2)}.`
    );
    if (!autoBandSelect?.checked && n <= 10 && r <= 10) {
      showAnalysisWarning(
        `Recent uploads are showing >=95% stress repeatedly. Current manual bands (${n}/${r}) may be unsuitable. Enable Auto-select bands.`
      );
    }
    return;
  }

  hideAnalysisWarning();
}

function detectFileMode(filename) {
  const name = String(filename || "").toLowerCase();
  if (name.endsWith(".npy")) return "hyperspectral";
  if ([".jpg", ".jpeg", ".png", ".webp"].some(ext => name.endsWith(ext))) return "rgb";
  return null;
}

function applyMetricLabels(labels) {
  activeMetricLabels = { ...labels };
  if (heatmapTitle) heatmapTitle.textContent = labels.heatmap_title || DEFAULT_METRIC_LABELS.heatmap_title;
  if (statMinLabel) statMinLabel.textContent = labels.min_label || DEFAULT_METRIC_LABELS.min_label;
  if (statMaxLabel) statMaxLabel.textContent = labels.max_label || DEFAULT_METRIC_LABELS.max_label;
  if (statMeanLabel) statMeanLabel.textContent = labels.mean_label || DEFAULT_METRIC_LABELS.mean_label;
  if (statStdLabel) statStdLabel.textContent = labels.std_label || DEFAULT_METRIC_LABELS.std_label;
  if (stressLabel) stressLabel.textContent = labels.stress_label || DEFAULT_METRIC_LABELS.stress_label;
  if (stressHint) stressHint.textContent = labels.stress_hint || DEFAULT_METRIC_LABELS.stress_hint;
  if (temporalDeltaLabel) temporalDeltaLabel.textContent = labels.temporal_delta_label || DEFAULT_METRIC_LABELS.temporal_delta_label;
}

function applyInputMode(mode) {
  const rgbMode = mode === "rgb";
  [nirBand, reBand, autoBandSelect, autoThreshold].forEach(el => {
    if (!el) return;
    el.disabled = rgbMode;
    el.classList.toggle("opacity-50", rgbMode);
    el.classList.toggle("cursor-not-allowed", rgbMode);
  });

  if (modeHelp) {
    modeHelp.textContent = rgbMode
      ? "Photos are converted into a 3-band NPY artifact behind the scenes, then analyzed with an RGB proxy health workflow."
      : "Keep Auto-select and Auto threshold enabled for unknown cubes. Manual values are used as fallback.";
  }
}

// ── UI state helpers ──────────────────────────────────────────
function setButtonState(state) {
  if (state === "processing") {
    processBtn.disabled = true;
    processBtn.textContent = "⏳ Processing…";
  } else {
    processBtn.disabled = false;
    processBtn.textContent = "▶ Process Image";
  }
}

function showProgress(label, pct) {
  progressWrap.classList.remove("hidden");
  progressLabel.textContent = label;
  progressPct.textContent   = pct + "%";
  progressBar.style.width   = pct + "%";
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorBanner.classList.remove("hidden");
}

function hideError() {
  errorBanner.classList.add("hidden");
  errorMsg.textContent = "";
}

function showAnalysisWarning(msg) {
  if (!analysisWarning || !analysisWarningMsg) return;
  analysisWarningMsg.textContent = msg;
  analysisWarning.classList.remove("hidden");
}

function hideAnalysisWarning() {
  if (!analysisWarning || !analysisWarningMsg) return;
  analysisWarning.classList.add("hidden");
  analysisWarningMsg.textContent = "";
}

// ── History section ──────────────────────────────────────────
async function fetchHistory() {
  if (!historyBody) return;

  try {
    const res = await fetch(HISTORY_API_URL, { method: "GET", cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const payload = await res.json();
    const items = Array.isArray(payload)
      ? payload
      : Array.isArray(payload?.items)
        ? payload.items
        : [];
    renderHistory(items);
  } catch (_) {
    renderHistory([]);
  }
}

function renderHistory(items) {
  if (!historyBody || !historyEmpty || !historyCount) return;

  historyBody.innerHTML = "";
  historyCount.textContent = `${items.length} record${items.length === 1 ? "" : "s"}`;

  if (!items.length) {
    historyEmpty.classList.remove("hidden");
    return;
  }

  historyEmpty.classList.add("hidden");

  for (const item of items) {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-surface/50 transition-colors duration-150";

    const confidenceText = typeof item.confidence === "number"
      ? `${(item.confidence * 100).toFixed(1)}%`
      : "—";

    const stressText = typeof item.stress_percentage === "number"
      ? `${item.stress_percentage.toFixed(2)}%`
      : "—";
    const trendText = item.trend_label ? formatClassLabel(item.trend_label) : "—";
    const onsetText = item.onset_detected ? "Yes" : "No";

    tr.innerHTML = `
      <td class="px-4 py-3 font-mono text-xs text-text">${escapeHtml(item.file_name || "—")}</td>
      <td class="px-4 py-3 font-mono text-xs text-muted">${formatDate(item.uploaded_at)}</td>
      <td class="px-4 py-3 font-mono text-xs ${healthClass(item.health_status)}">${escapeHtml(item.health_status || "unknown")}</td>
      <td class="px-4 py-3 font-mono text-xs text-text">${escapeHtml(item.predicted_class || "—")}</td>
      <td class="px-4 py-3 font-mono text-xs text-muted">${confidenceText}</td>
      <td class="px-4 py-3 font-mono text-xs ${stressClass(item.stress_percentage)}">${stressText}</td>
      <td class="px-4 py-3 font-mono text-xs ${trendClass(item.trend_label)}">${escapeHtml(trendText)}</td>
      <td class="px-4 py-3 font-mono text-xs ${item.onset_detected ? "text-danger" : "text-accent"}">${onsetText}</td>
    `;

    historyBody.appendChild(tr);
  }
}

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function healthClass(status) {
  const s = (status || "").toLowerCase();
  if (s === "healthy") return "text-accent";
  if (s === "at_risk") return "text-warn";
  if (s === "stressed") return "text-danger";
  return "text-muted";
}

function stressTypeClass(classLabel) {
  const cls = (classLabel || "").toLowerCase();
  if (cls.includes("healthy")) return "text-accent";
  if (cls.includes("nutrient")) return "text-warn";
  if (cls.includes("drought")) return "text-warn";
  if (cls.includes("disease")) return "text-danger";
  return "text-muted";
}

function formatClassLabel(clsName) {
  if (!clsName) return "Unknown";
  return clsName
    .split(/_/g)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function stressClass(stressPct) {
  if (typeof stressPct !== "number") return "text-muted";
  if (stressPct > 50) return "text-danger";
  if (stressPct > 25) return "text-warn";
  return "text-accent";
}

function trendClass(trend) {
  const t = (trend || "").toLowerCase();
  if (t === "improving") return "text-accent";
  if (t === "worsening") return "text-danger";
  if (t === "stable") return "text-muted";
  return "text-muted";
}

function deltaClass(value, negativeIsGood) {
  if (typeof value !== "number") return "text-muted";
  if (value === 0) return "text-muted";
  if (negativeIsGood) {
    return value < 0 ? "text-accent" : "text-danger";
  }
  return value > 0 ? "text-accent" : "text-danger";
}

function formatSignedValue(value, digits, suffix = "") {
  if (typeof value !== "number") return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}${suffix}`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
