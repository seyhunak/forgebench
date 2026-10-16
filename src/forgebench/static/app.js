/* ForgeBench · Hallmark UI · frontend logic */

const API = "";

// ---------- Error handling ----------
window.onerror = function(msg, url, line, col, error) {
  const extra = !error ? '' : '\n\nStack: ' + (error.stack || '').substring(0, 500);
  const div = document.createElement('div');
  div.style.cssText = 'position:fixed;top:1rem;left:1rem;right:1rem;background:#dc2626;color:#fff;padding:1rem;border-radius:6px;z-index:9999;font-family:monospace;font-size:0.875rem;';
  div.innerHTML = '<strong>ForgeBench JS Error:</strong> ' + msg + '<br>' + url + ':' + line + ':' + col + '<br><small>' + extra + '</small>';
  document.body.insertBefore(div, document.body.firstChild);
  console.error('JS Error:', msg, url, line, col, error);
  return false;
};


// Global cache for models.dev data
let modelsData = null;
let theme = localStorage.getItem("fb-theme") || "dark";

// Debug logger — silent unless the page is opened with ?debug in the URL.
let dlog = () => {};

// DOM elements
const els = {
  keyProvider: document.getElementById("key-provider"),
  keyInput: document.getElementById("key-input"),
  modelSelect: document.getElementById("model-select"),
  modelDetails: document.getElementById("model-details"),
  btnSaveKey: document.getElementById("btn-save-key"),
  btnVerifyKey: document.getElementById("btn-verify-key"),
  btnRemoveKey: document.getElementById("btn-remove-key"),
  keyMessage: document.getElementById("key-message"),
  statusKey: document.getElementById("status-key"),
  statusSource: document.getElementById("status-source"),
  statusModel: document.getElementById("status-model"),
  statusFile: document.getElementById("status-file"),
  // Setup panel
  setupMessage: document.getElementById("setup-message"),
  setupFile: document.getElementById("setup-file"),
  setupProviders: document.getElementById("setup-providers"),
  setupCustom: document.getElementById("setup-custom"),
  setupName: document.getElementById("setup-name"),
  setupValue: document.getElementById("setup-value"),
  btnSetupAdd: document.getElementById("btn-setup-add"),
  configSelect: document.getElementById("config-select"),
  runLimit: document.getElementById("run-limit"),
  runId: document.getElementById("run-id"),
  btnRun: document.getElementById("btn-run"),
  runMessage: document.getElementById("run-message"),
  runProgress: document.getElementById("run-progress"),
  progressText: document.getElementById("progress-text"),
  progressCounter: document.getElementById("progress-counter"),
  progressFill: document.getElementById("progress-fill"),
  runResult: document.getElementById("run-result"),
  resRunId: document.getElementById("res-run-id"),
  resAccuracy: document.getElementById("res-accuracy"),
  resMacroF1: document.getElementById("res-macro-f1"),
  resSchemaValidity: document.getElementById("res-schema-validity"),
  btnOpenRun: document.getElementById("btn-open-run"),
  runsGrid: document.getElementById("runs-grid"),
  // Run detail modal
  runModal: document.getElementById("run-modal"),
  runModalTitle: document.getElementById("run-modal-title"),
  runModalMeta: document.getElementById("run-modal-meta"),
  runModalBody: document.getElementById("run-modal-body"),
  btnModalClose: document.getElementById("btn-modal-close"),
  btnModalReport: document.getElementById("btn-modal-report"),
  btnModalPredictions: document.getElementById("btn-modal-predictions"),
  btnModalDownloadReport: document.getElementById("btn-modal-download-report"),
  btnModalDownloadPredictions: document.getElementById("btn-modal-download-predictions"),
  modeSingle: document.getElementById("mode-single"),
  modeCompare: document.getElementById("mode-compare"),
  singleView: document.getElementById("single-view"),
  compareView: document.getElementById("compare-view"),
  compareSelect: document.getElementById("compare-select"),
  btnCompare: document.getElementById("btn-compare"),
  compareViewContainer: document.getElementById("compare-view-container"),
  btnThemeToggle: document.getElementById("btn-theme-toggle"),
  // Dataset panel
  datasetSelect: document.getElementById("dataset-select"),
  datasetSplit: document.getElementById("dataset-split"),
  datasetInfo: document.getElementById("dataset-info"),
  datasetCasesContainer: document.getElementById("dataset-cases-container"),
  datasetTableBody: document.getElementById("dataset-table-body"),
  btnDownloadDataset: document.getElementById("btn-download-dataset"),
  datasetMessage: document.getElementById("dataset-message"),
  // Config panel
  configEditorSelect: document.getElementById("config-editor-select"),
  configEditor: document.getElementById("config-editor"),
  configEditorLoading: document.getElementById("config-editor-loading"),
  btnSaveConfig: document.getElementById("btn-save-config"),
  btnResetConfig: document.getElementById("btn-reset-config"),
  configMessage: document.getElementById("config-message"),
  // Task panel
  taskSelect: document.getElementById("task-select"),
  taskSplit: document.getElementById("task-split"),
  taskProvider: document.getElementById("task-provider"),
  taskModel: document.getElementById("task-model"),
  taskJudgeProvider: document.getElementById("task-judge-provider"),
  taskJudgeModel: document.getElementById("task-judge-model"),
  taskLimit: document.getElementById("task-limit"),
  btnValidateTask: document.getElementById("btn-validate-task"),
  btnRunTask: document.getElementById("btn-run-task"),
  taskMessage: document.getElementById("task-message"),
  taskProgress: document.getElementById("task-progress"),
  taskProgressText: document.getElementById("task-progress-text"),
  taskProgressCounter: document.getElementById("task-progress-counter"),
  taskProgressFill: document.getElementById("task-progress-fill"),
  taskResult: document.getElementById("task-result"),
  taskResRunId: document.getElementById("task-res-run-id"),
  taskResCases: document.getElementById("task-res-cases"),
  taskResValid: document.getElementById("task-res-valid"),
  taskBtnOpenRun: document.getElementById("task-btn-open-run"),
  taskRunsGrid: document.getElementById("task-runs-grid"),
  btnClearTaskRuns: document.getElementById("btn-clear-task-runs"),
};

// ---------- Theme ----------

function applyTheme() {
  const light = theme === "light";
  document.documentElement.classList.toggle("theme-light", light);
  const btn = els.btnThemeToggle;
  if (btn) {
    btn.dataset.theme = light ? "light" : "dark";
    btn.setAttribute("aria-pressed", String(light));
  }
}

els.btnThemeToggle.addEventListener("click", () => {
  theme = theme === "dark" ? "light" : "dark";
  localStorage.setItem("fb-theme", theme);
  applyTheme();
});

// ---------- Helpers ----------


function safeInnerHTML(el, html) {
  if (!el) return;
  el.innerHTML = html;
}

function safeText(el, text) {
  if (!el) return;
  el.textContent = text;
}

function show(el, cls = "") {
  el.style.display = "";
  el.className = el.className.replace(/\bmessage--\w+\b/g, "").trim();
  if (cls) el.classList.add(cls);
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}

function setMessage(el, text, type = "info") {
  el.textContent = text;
  el.className = `message message--${type}`;
  show(el);
}

async function fetchJSON(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// escapeHtml is built on textContent -> innerHTML, which leaves quotes alone;
// attribute values need the stricter form so a stray quote cannot break out.
function escapeAttr(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---------- Providers & Models (from models.dev) ----------

// Preferred default model per provider. Catalog order is arbitrary (OpenAI
// leads with an image model, OpenRouter with a fine-tune), so each provider
// gets a sensible starting point. Used only when the id exists in the catalog.
const PROVIDER_DEFAULT_MODELS = {
  openrouter: "openai/gpt-4o-mini",
  mistral: "open-mistral-nemo",
  openai: "gpt-4o-mini",
  anthropic: "claude-sonnet-4-5",
  google: "gemini-flash-latest",
  ollama: "llama3.1:8b",
};

function preferredModel(providerId, models) {
  const preferred = PROVIDER_DEFAULT_MODELS[providerId];
  if (preferred && models[preferred]) return preferred;
  const ids = Object.keys(models);
  return ids.length ? ids[0] : "";
}

function selectOption(select, value) {
  if (!select) return;
  const has = Array.from(select.options).some(o => o.value === value);
  select.value = has ? value : (select.options[0] ? select.options[0].value : "");
}

// ---------- Ollama: install / running check (local models have no catalog) ----------

let ollamaCache = null; // last /api/ollama/status payload

async function fetchOllamaStatus(force = false) {
  if (ollamaCache && !force) return ollamaCache;
  try {
    ollamaCache = await fetchJSON("/api/ollama/status");
  } catch (err) {
    ollamaCache = { binary: null, installed: false, running: false, host: "", models: [], detail: err.message };
  }
  return ollamaCache;
}

function ollamaModelMap() {
  const map = {};
  for (const m of (ollamaCache && ollamaCache.models) || []) map[m] = { id: m, name: m };
  return map;
}

// The status panel under the form: is Ollama installed, running, what's pulled?
async function syncOllamaPanel(providerId) {
  const box = document.getElementById("key-ollama");
  if (!box) return;
  if (providerId !== "ollama") {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  const st = await fetchOllamaStatus();
  let state = "missing";
  let text = "";
  if (st.running && st.models.length) {
    state = "running";
    const preview = st.models.slice(0, 3).join(", ");
    text = `Ollama is running on ${st.host} — ${st.models.length} local model(s): ${preview}` +
      (st.models.length > 3 ? ", …" : "");
  } else if (st.running) {
    state = "empty";
    text = "Ollama is running but has no models — pull one: ollama pull llama3.1:8b";
  } else if (st.installed) {
    state = "stopped";
    text = "Ollama is installed but not answering — start it with `ollama serve` (or the Ollama app).";
  } else {
    state = "missing";
    text = "Ollama not found — install: https://ollama.com/download (macOS: brew install ollama).";
  }
  box.dataset.state = state;
  box.textContent = text;
  box.hidden = false;
}

async function loadProvidersAndModels() {
  try {
    const [providers, models] = await Promise.all([
      fetchJSON("/api/providers"),
      fetchJSON("/api/models"),
    ]);
    modelsData = models;

    // Mock needs no key and is gone from these selectors (CLI/config only);
    // Ollama joins for BYOK + local model listing (see syncOllamaPanel).
    const providerList = providers.map(p => ({
      ...p,
      models: (modelsData[p.id] && modelsData[p.id].models) || {},
    }));

    safeInnerHTML(els.keyProvider, providerList
      .map(p => `<option value="${p.id}">${p.name}</option>`)
      .join(""));

    // OpenRouter is the default provider — one key, every hosted model.
    selectOption(els.keyProvider, "openrouter");
    populateModels(els.keyProvider.value);
  } catch (err) {
    setMessage(els.keyMessage, `Failed to load providers: ${err.message}`, "error");
  }
}

function populateModels(providerId) {
  let models = {};

  if (providerId === "ollama") {
    // No models.dev catalog — the daemon is the source of truth.
    models = ollamaModelMap();
    if (!Object.keys(models).length) {
      safeInnerHTML(els.modelSelect, '<option value="">(start Ollama to list local models)</option>');
      els.modelSelect.value = "";
      showModelDetails(providerId, "");
      return;
    }
  } else if (modelsData && modelsData[providerId]) {
    models = modelsData[providerId].models || {};
  }

  safeInnerHTML(els.modelSelect, Object.values(models)
    .map(m => `<option value="${m.id}">${m.name || m.id}</option>`)
    .join(""));

  const preferred = preferredModel(providerId, models);
  if (preferred) els.modelSelect.value = preferred;

  showModelDetails(providerId, els.modelSelect.value);
}

function showModelDetails(providerId, modelId) {
  const details = document.getElementById("model-details");
  if (!details) return;

  let model = null;
  let provider = null;

  if (providerId === "ollama" && modelId) {
    // Local models carry no published pricing — they run on your machine.
    model = { id: modelId, name: modelId, cost: { input: 0, output: 0 } };
    provider = { name: "Ollama", env: [] };
  } else if (modelsData && modelsData[providerId]) {
    provider = modelsData[providerId];
    model = provider.models && provider.models[modelId];
  }

  if (!model) {
    details.innerHTML = "<p>No model details available.</p>";
    return;
  }

  const cost = model.cost || {};
  const limit = model.limit || {};
  const modalities = model.modalities || {};

  details.innerHTML = `
    <p><strong>Provider:</strong> ${provider ? provider.name : "—"}</p>
    <p><strong>Model ID:</strong> <code>${model.id}</code></p>
    ${model.description ? `<p>${model.description}</p>` : ""}
    <div class="price-row">
      <div class="price-item"><span class="label">Input</span><br>$${(cost.input || 0).toFixed(2)}/M</div>
      <div class="price-item"><span class="label">Output</span><br>$${(cost.output || 0).toFixed(2)}/M</div>
      ${cost.cache_read != null ? `<div class="price-item"><span class="label">Cache Read</span><br>$${cost.cache_read.toFixed(2)}/M</div>` : ""}
    </div>
    <p><strong>Context:</strong> ${limit.context ? limit.context.toLocaleString() : "N/A"} tokens</p>
    <p><strong>Max Output:</strong> ${limit.output ? limit.output.toLocaleString() : "N/A"} tokens</p>
    <p><strong>Modalities:</strong> ${(modalities.input || []).join(", ")} → ${(modalities.output || []).join(", ")}</p>
    ${model.reasoning ? "<p><strong>Reasoning:</strong> Yes</p>" : ""}
    ${model.tool_call ? "<p><strong>Tool Calling:</strong> Yes</p>" : ""}
    ${model.structured_output ? "<p><strong>Structured Output:</strong> Yes</p>" : ""}
  `;
}

// ---------- Credentials ----------

async function loadCredentialStatus(provider) {
  try {
    const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
    const data = await fetchJSON(`/api/credentials${query}`);
    els.statusKey.textContent = data.key_masked || "(not set)";
    els.statusSource.textContent = data.source || "—";
    els.statusModel.textContent = data.model || "(not set)";
    els.statusFile.textContent = data.env_file || "—";

    // With no explicit provider, switch to whichever provider has a key.
    if (!provider && data.provider && els.keyProvider.value !== data.provider) {
      selectOption(els.keyProvider, data.provider);
      populateModels(els.keyProvider.value);
      if (els.keyProvider.value === "ollama") onProviderChange();
    }
  } catch (err) {
    setMessage(els.keyMessage, `Failed to load status: ${err.message}`, "error");
  }
}

async function onProviderChange() {
  const pid = els.keyProvider.value;
  populateModels(pid);
  loadCredentialStatus(pid);
  if (pid === "ollama") {
    await syncOllamaPanel(pid); // fetch install/running state first…
    if (els.keyProvider.value === pid) populateModels(pid); // …then list local models
  } else {
    syncOllamaPanel(pid); // hides the panel
  }
}

els.keyProvider.addEventListener("change", onProviderChange);

els.modelSelect.addEventListener("change", () => {
  showModelDetails(els.keyProvider.value, els.modelSelect.value);
});

els.btnSaveKey.addEventListener("click", async () => {
  const provider = els.keyProvider.value;
  const key = els.keyInput.value.trim();
  const model = els.modelSelect.value.trim();
  if (!key) {
    setMessage(els.keyMessage, "Paste a key first.", "error");
    return;
  }
  try {
    await fetchJSON("/api/credentials", {
      method: "POST",
      body: JSON.stringify({ key, model: model || undefined, provider }),
    });
    setMessage(els.keyMessage, "Saved to .env (chmod 600).", "ok");
    els.keyInput.value = "";
    await loadCredentialStatus(provider);
    dlog('Credential status loaded');
  } catch (err) {
    setMessage(els.keyMessage, `Save failed: ${err.message}`, "error");
  }
});

els.btnVerifyKey.addEventListener("click", async () => {
  const provider = els.keyProvider.value;
  try {
    const data = await fetchJSON("/api/credentials/verify", {
      method: "POST",
      body: JSON.stringify({ provider }),
    });
    if (provider === "ollama" && data.presented !== "error") {
      // Local Ollama's "key check" is a daemon check: when the daemon is up
      // (or the status cannot be proved down) it is the only success signal
      // the button can give, regardless of stale/missing `presented` fields.
      setMessage(els.keyMessage, `OK — ${data.detail}`, "ok");
    } else if (data.presented === "error") {
      setMessage(els.keyMessage, data.detail, "error");
    } else if (data.presented === "ok") {
      setMessage(els.keyMessage, `OK — ${data.detail}`, "ok");
    } else if (data.accepted === true) {
      setMessage(els.keyMessage, `Key OK — ${data.detail}`, "ok");
    } else if (data.accepted === false) {
      setMessage(els.keyMessage, `Key rejected — ${data.detail}`, "error");
    } else {
      setMessage(els.keyMessage, `Could not verify — ${data.detail}`, "info");
    }
  } catch (err) {
    setMessage(els.keyMessage, `Verify failed: ${err.message}`, "error");
  }
});

els.btnRemoveKey.addEventListener("click", async () => {
  const provider = els.keyProvider.value;
  try {
    await fetchJSON(`/api/credentials?provider=${encodeURIComponent(provider)}`, { method: "DELETE" });
    setMessage(els.keyMessage, "Key removed.", "ok");
    await loadCredentialStatus(provider);
    dlog('Credential status loaded');
  } catch (err) {
    setMessage(els.keyMessage, `Remove failed: ${err.message}`, "error");
  }
});

// ---------- Setup (environment variables) ----------

const ENV_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;

// Where a saved variable is read from, in the user's words.
const ENV_SOURCE_LABEL = {
  file: ".env",
  environment: "shell environment",
  not_set: "",
};

function envStatusChip(isSet, masked, source) {
  const state = isSet ? "set" : "unset";
  const label = isSet ? "set" : "not set";
  const where = ENV_SOURCE_LABEL[source] || "";
  const detail = isSet
    ? `<span class="env-value">${escapeHtml(masked || "")}</span>` +
      (where ? `<span class="env-source">${escapeHtml(where)}</span>` : "")
    : "";
  return `<span class="env-chip" data-state="${state}">${label}</span>${detail}`;
}

function envRow(name, modelName, head, valueInput, modelInput) {
  return `
    <article class="env-row" data-env-name="${escapeAttr(name)}"${modelName ? ` data-env-model-name="${escapeAttr(modelName)}"` : ""}>
      <div class="env-row__head">${head}</div>
      <div class="env-row__form">
        ${valueInput}
        <button class="button button--primary" data-env-action="value">Save</button>
        <button class="button button--danger" data-env-action="remove">Remove</button>
      </div>
      ${modelInput ? `<div class="env-row__form">${modelInput}<button class="button" data-env-action="model">Save model</button></div>` : ""}
    </article>`;
}

function renderEnvProviders(providers) {
  safeInnerHTML(els.setupProviders, providers.map((p) => envRow(
    p.key_var,
    p.model_var,
    `<span class="env-row__label">${escapeHtml(p.label)}</span>
     <code class="env-row__var">${escapeHtml(p.key_var)}</code>
     ${p.hint ? `<span class="env-hint">${escapeHtml(p.hint)}</span>` : ""}
     ${envStatusChip(p.key_set, p.key_masked, p.key_source)}`,
    `<input type="password" class="env-row__input" data-env-input="value" placeholder="new value…" autocomplete="off" spellcheck="false" aria-label="${escapeAttr(p.key_var)} value">`,
    `<code class="env-row__var">${escapeHtml(p.model_var)}</code>
     <input type="text" class="env-row__input" data-env-input="model" placeholder="(provider default)" autocomplete="off" spellcheck="false" aria-label="${escapeAttr(p.model_var)} value">`
  )).join(""));

  // Model ids are set as properties rather than attribute text, so an id
  // containing a quote can never break out of the markup.
  els.setupProviders.querySelectorAll(".env-row").forEach((row, index) => {
    const input = row.querySelector('[data-env-input="model"]');
    if (input) input.value = providers[index].model || "";
  });
}

function renderEnvCustom(custom) {
  if (!custom.length) {
    safeInnerHTML(els.setupCustom,
      '<p class="env-empty">Nothing else in <code>.env</code> yet. Add a variable below.</p>');
    return;
  }
  safeInnerHTML(els.setupCustom, custom.map((v) => envRow(
    v.name,
    "",
    `<code class="env-row__var">${escapeHtml(v.name)}</code>${envStatusChip(true, v.masked, v.source)}`,
    `<input type="password" class="env-row__input" data-env-input="value" placeholder="new value…" autocomplete="off" spellcheck="false" aria-label="${escapeAttr(v.name)} value">`,
    ""
  )).join(""));
}

async function loadEnv() {
  try {
    const data = await fetchJSON("/api/env");
    els.setupFile.textContent = data.env_file ||
      "(none yet — created in the first writable directory on save)";
    renderEnvProviders(data.providers || []);
    renderEnvCustom(data.custom || []);
  } catch (err) {
    setMessage(els.setupMessage, `Failed to load environment: ${err.message}`, "error");
  }
}

async function saveEnv(name, value) {
  await fetchJSON("/api/env", { method: "POST", body: JSON.stringify({ name, value }) });
  setMessage(els.setupMessage, `Saved ${name} to .env (chmod 600).`, "ok");
  await loadEnv();
  await loadCredentialStatus();
  dlog(`env saved: ${name}`);
}

async function envAction(row, action) {
  if (!row) return;
  const name = row.getAttribute("data-env-name");
  try {
    if (action === "remove") {
      await fetchJSON(`/api/env?name=${encodeURIComponent(name)}`, { method: "DELETE" });
      setMessage(els.setupMessage, `Removed ${name} from .env.`, "ok");
      await loadEnv();
      await loadCredentialStatus();
      return;
    }
    const target = action === "model" ? row.getAttribute("data-env-model-name") : name;
    const input = row.querySelector(`[data-env-input="${action === "model" ? "model" : "value"}"]`);
    const value = (input && input.value.trim()) || "";
    if (!target) return;
    if (!value) {
      setMessage(els.setupMessage, `Enter a value for ${target} first.`, "error");
      return;
    }
    if (action === "model") {
      // A model id is not a secret; show the result without re-typing it.
      await saveEnv(target, value);
    } else {
      await saveEnv(target, value);
      if (input) input.value = "";
    }
  } catch (err) {
    setMessage(els.setupMessage, `${action === "remove" ? "Remove" : "Save"} failed: ${err.message}`, "error");
  }
}

function wireEnvList(container) {
  if (!container) return;
  container.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-env-action]");
    if (!button) return;
    envAction(button.closest(".env-row"), button.getAttribute("data-env-action"));
  });
  container.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const input = event.target.closest("input[data-env-input]");
    if (!input) return;
    event.preventDefault();
    const action = input.getAttribute("data-env-input") === "model" ? "model" : "value";
    envAction(input.closest(".env-row"), action);
  });
}

wireEnvList(els.setupProviders);
wireEnvList(els.setupCustom);

els.btnSetupAdd.addEventListener("click", async () => {
  const name = (els.setupName.value || "").trim();
  const value = els.setupValue.value || "";
  if (!ENV_NAME_RE.test(name)) {
    setMessage(els.setupMessage, "Names use letters, digits and underscores, and cannot start with a digit.", "error");
    return;
  }
  if (!value.trim()) {
    setMessage(els.setupMessage, "Enter a value to save.", "error");
    return;
  }
  try {
    await saveEnv(name, value);
    els.setupName.value = "";
    els.setupValue.value = "";
  } catch (err) {
    setMessage(els.setupMessage, `Save failed: ${err.message}`, "error");
  }
});

// Enter anywhere in the add form saves it.
[els.setupName, els.setupValue].forEach((input) => {
  if (!input) return;
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      els.btnSetupAdd.click();
    }
  });
});

// ---------- Configs ----------

async function loadConfigs() {
  try {
    const configs = await fetchJSON("/api/configs");
    safeInnerHTML(els.configSelect, configs.map(c => `<option value="${c.path}">${c.name}</option>`).join(""));
    safeInnerHTML(els.configEditorSelect, configs.map(c => `<option value="${c.path}">${c.name}</option>`).join(""));
  } catch (err) {
    setMessage(els.runMessage, `Failed to load configs: ${err.message}`, "error");
  }
}

// ---------- Datasets ----------

async function loadDatasets() {
  try {
    const datasets = await fetchJSON("/api/datasets");
    safeInnerHTML(els.datasetSelect, datasets.map(d => `<option value="${d}">${d}</option>`).join(""));
    if (datasets.length > 0) {
      await loadDatasetDetails(datasets[0], "test");
    }
  } catch (err) {
    setMessage(els.datasetMessage, `Failed to load datasets: ${err.message}`, "error");
  }
}

els.datasetSelect.addEventListener("change", () => {
  loadDatasetDetails(els.datasetSelect.value, els.datasetSplit.value);
});

els.datasetSplit.addEventListener("change", () => {
  loadDatasetDetails(els.datasetSelect.value, els.datasetSplit.value);
});

async function loadDatasetDetails(name, split) {
  try {
    hide(els.datasetCasesContainer);
    hide(els.datasetMessage);

    const [info, splitData] = await Promise.all([
      fetchJSON(`/api/datasets/${name}`),
      fetchJSON(`/api/datasets/${name}/splits/${split}`),
    ]);

    // Show info
    safeInnerHTML(els.datasetInfo,  `
      <h3>${escapeHtml(info.name)}</h3>
      <p><strong>Version:</strong> ${escapeHtml(info.version)} &nbsp;|&nbsp; <strong>Task:</strong> ${escapeHtml(info.task)} &nbsp;|&nbsp; <strong>License:</strong> ${escapeHtml(info.license)}</p>
      <p><strong>Families:</strong> ${info.families.map(f => `<span style="background:var(--bg-input);padding:0.1rem 0.4rem;border-radius:4px;font-size:0.75rem;border:1px solid var(--border);">${escapeHtml(f)}</span>`).join(" ")}</p>
      <p><strong>Splits:</strong> ${Object.entries(info.splits).map(([s, c]) => `${escapeHtml(s)}: ${c}`).join(", ")}</p>
    `);

    // Show cases table
    const cases = splitData.cases || [];
    safeInnerHTML(els.datasetTableBody,  cases.map(c => {
      const input = c.input || {};
      return `
        <tr>
          <td class="code-mono">${escapeHtml(c.id)}</td>
          <td>${escapeHtml(c.scenario_family || "—")}</td>
          <td><span style="background:var(--bg-input);padding:0.1rem 0.4rem;border-radius:4px;font-size:0.75rem;border:1px solid var(--border);">${escapeHtml(c.expected?.category || "—")}</span></td>
          <td class="code-mono">${escapeHtml(input.bank_amount || "—")}</td>
          <td class="code-mono">${escapeHtml(input.ledger_amount || "—")}</td>
          <td class="code-mono">${escapeHtml(input.bank_reference || "—")}</td>
          <td class="code-mono">${escapeHtml(input.ledger_reference || "—")}</td>
          <td class="code-mono">${escapeHtml(input.bank_date || "—")}</td>
          <td class="code-mono">${escapeHtml(input.ledger_date || "—")}</td>
        </tr>
      `;
    }).join(""));

    show(els.datasetCasesContainer);
    els.btnDownloadDataset.onclick = () => {
      const blob = new Blob([JSON.stringify(splitData, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name}-${split}.json`;
      a.click();
      URL.revokeObjectURL(url);
    };
  } catch (err) {
    setMessage(els.datasetMessage, `Failed to load dataset: ${err.message}`, "error");
  }
}

// ---------- Config Editor ----------

let currentConfigPath = null;
let currentConfigContent = null;

els.configEditorSelect.addEventListener("change", async () => {
  currentConfigPath = els.configEditorSelect.value;
  await loadConfigEditor(currentConfigPath);
});

async function loadConfigEditor(path) {
  if (!path) return;
  show(els.configEditorLoading);
  hide(els.configEditor);
  hide(els.configMessage);

  try {
    const data = await fetchJSON(`/api/configs/${path}`);
    currentConfigContent = JSON.stringify(data, null, 2);
    els.configEditor.value = currentConfigContent;
    hide(els.configEditorLoading);
    show(els.configEditor);
  } catch (err) {
    hide(els.configEditorLoading);
    setMessage(els.configMessage, `Failed to load config: ${err.message}`, "error");
  }
}

els.btnResetConfig.addEventListener("click", () => {
  if (currentConfigContent !== null) {
    els.configEditor.value = currentConfigContent;
    setMessage(els.configMessage, "Reset to original.", "info");
  }
});

els.btnSaveConfig.addEventListener("click", async () => {
  if (!currentConfigPath) return;
  try {
    const payload = JSON.parse(els.configEditor.value);
    await fetchJSON(`/api/configs/${currentConfigPath}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    currentConfigContent = els.configEditor.value;
    setMessage(els.configMessage, "Config saved successfully.", "ok");
    await loadConfigs();
    dlog('Configs loaded');
  } catch (err) {
    setMessage(els.configMessage, `Save failed: ${err.message}`, "error");
  }
});

// ---------- Runs (card-based UI) ----------

async function loadRuns() {
  try {
    const runs = await fetchJSON("/api/runs");
    renderRunsGrid(runs);
    populateCompareSelect(runs);
  } catch (err) {
    console.error("Failed to load runs:", err);
  }
}

function renderRunsGrid(runs) {
  if (!runs || runs.length === 0) {
    safeInnerHTML(els.runsGrid, `<p style="color: var(--fg-muted); grid-column: 1/-1; text-align:center; padding: 2rem;">No runs yet. Start one in the <strong>Run</strong> tab.</p>`);
    return;
  }

  safeInnerHTML(els.runsGrid,  runs.map(run => {
    const m = run.metrics || {};
    const acc = m.accuracy != null ? (m.accuracy * 100).toFixed(1) : "—";
    const f1 = m.macro_f1 != null ? (m.macro_f1 * 100).toFixed(1) : "—";
    const valid = m.schema_validity != null ? (m.schema_validity * 100).toFixed(1) : "—";
    const provider = run.provider || {};
    const dataset = run.dataset || {};

    return `
      <article class="run-card" role="button" tabindex="0" onclick="viewRunReport('${escapeHtml(run.path)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();viewRunReport('${escapeHtml(run.path)}')}">
        <div class="run-card--actions">
          <button class="btn-delete-run" title="Delete run" onclick="event.stopPropagation(); deleteRun('${escapeHtml(run.path)}')">🗑️</button>
        </div>
        <div class="run-card--header">
          <div class="run-card--id">${escapeHtml(run.run_id)}</div>
          <span style="font-size:0.75rem;color:var(--fg-muted);">${escapeHtml(provider.name || 'unknown')}</span>
        </div>
        <div class="run-card--meta">
          <div>${escapeHtml(provider.model || 'unknown')}</div>
          <div>${escapeHtml(dataset.name || 'unknown')} v${escapeHtml(dataset.version || '?')}</div>
          <div>${run.created_at || '—'}</div>
        </div>
        <div class="run-card--metrics">
          <div class="metric-item"><div class="metric-item--value">${acc}</div><div class="metric-item--label">Accuracy</div></div>
          <div class="metric-item"><div class="metric-item--value">${f1}</div><div class="metric-item--label">Macro-F1</div></div>
          <div class="metric-item"><div class="metric-item--value">${valid}</div><div class="metric-item--label">Schema Valid</div></div>
        </div>
      </article>
    `;
  }).join(""));
}

window.deleteRun = async (runPath) => {
  if (!confirm(`Delete run "${escapeHtml(runPath)}"? This cannot be undone.`)) return;
  try {
    await fetchJSON(`/api/runs/${runPath}`, { method: "DELETE" });
    setMessage(els.runMessage, "Run deleted.", "ok");
    await loadRuns();
    dlog('Runs loaded');
  } catch (err) {
    setMessage(els.runMessage, `Delete failed: ${err.message}`, "error");
  }
};

function populateCompareSelect(runs) {
  safeInnerHTML(els.compareSelect, runs.map(r => `<option value="${r.path}">${r.run_id}</option>`).join(""));
}

window.viewRunReport = async (runPath) => {
  try {
    const [report, run] = await Promise.all([
      fetchJSON(`/api/runs/${runPath}/report`),
      fetchJSON(`/api/runs/${runPath}`).catch(() => null),
    ]);
    openRunModal(runPath, run, report);
  } catch (err) {
    setMessage(els.runMessage, `Failed to load report: ${err.message}`, "error");
  }
};

// ---------- Run detail modal ----------

let currentRun = null;

function pct(value) {
  return value != null ? (value * 100).toFixed(1) + "%" : "—";
}

function openRunModal(runPath, run, report) {
  const manifest = (run && run.manifest) || {};
  const provider = manifest.provider || {};
  const dataset = manifest.dataset || {};
  const m = (run && run.metrics) || {};

  currentRun = {
    path: runPath,
    markdown: (report && report.markdown) || "",
    html: (report && report.html) || "",
    predictions: null,
  };

  els.runModalTitle.textContent = (run && run.run_id) || runPath.replace(/^runs\//, "");
  els.runModalMeta.innerHTML = [
    provider.name || "unknown",
    provider.model || "unknown",
    `${dataset.name || "unknown"} v${dataset.version || "?"}`,
    `accuracy ${pct(m.accuracy)}`,
    `macro-F1 ${pct(m.macro_f1)}`,
    `schema valid ${pct(m.schema_validity)}`,
    manifest.created_at_utc || "",
  ]
    .filter(Boolean)
    .map((chip) => `<span class="modal-chip">${escapeHtml(chip)}</span>`)
    .join("");

  showModalReport();
  els.runModal.hidden = false;
  document.body.classList.add("modal-open");
  if (els.btnModalClose) els.btnModalClose.focus();
}

function closeRunModal() {
  if (!els.runModal || els.runModal.hidden) return;
  els.runModal.hidden = true;
  document.body.classList.remove("modal-open");
  currentRun = null;
}

function showModalReport() {
  if (!els.runModalBody) return;
  els.runModalBody.classList.remove("modal-body--table");
  // Use innerHTML to render the markdown report as HTML (escaped by the server).
  // Keep the raw markdown available for download via the .md file.
  els.runModalBody.innerHTML = (currentRun && currentRun.html) || (currentRun && currentRun.markdown) || "(no report)";
  els.btnModalReport.classList.add("is-active");
  els.btnModalPredictions.classList.remove("is-active");
}

async function loadCurrentPredictions() {
  if (!currentRun) return null;
  if (!currentRun.predictions) {
    currentRun.predictions = await fetchJSON(`/api/runs/${currentRun.path}/predictions`);
  }
  return currentRun.predictions;
}

async function showModalPredictions() {
  if (!currentRun) return;
  els.runModalBody.classList.add("modal-body--table");
  els.btnModalReport.classList.remove("is-active");
  els.btnModalPredictions.classList.add("is-active");
  els.runModalBody.innerHTML = '<p class="modal-empty">Loading predictions…</p>';
  try {
    renderPredictionsTable(els.runModalBody, await loadCurrentPredictions());
  } catch (err) {
    els.runModalBody.innerHTML = `<p class="modal-empty">Failed to load predictions: ${escapeHtml(err.message)}</p>`;
  }
}

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

els.btnModalReport.addEventListener("click", showModalReport);
els.btnModalPredictions.addEventListener("click", showModalPredictions);

els.btnModalDownloadReport.addEventListener("click", () => {
  if (!currentRun) return;
  downloadBlob(`${currentRun.path.replace(/\//g, "-")}.md`, currentRun.markdown || "", "text/markdown");
});

els.btnModalDownloadPredictions.addEventListener("click", async () => {
  if (!currentRun) return;
  try {
    const data = await loadCurrentPredictions();
    downloadBlob(
      `${currentRun.path.replace(/\//g, "-")}-predictions.json`,
      JSON.stringify(data, null, 2),
      "application/json"
    );
  } catch (err) {
    setMessage(els.runMessage, `Download failed: ${err.message}`, "error");
  }
});

els.runModal.addEventListener("click", (e) => {
  if (e.target.hasAttribute("data-modal-close")) closeRunModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && els.runModal && !els.runModal.hidden) {
    e.preventDefault();
    closeRunModal();
  }
});

function renderPredictionsTable(container, records) {
  if (!records || records.length === 0) {
    container.innerHTML = '<p class="modal-empty">No predictions found.</p>';
    return;
  }

  let html = `<table class="data-table">
    <thead>
      <tr>
        <th>Case ID</th>
        <th>Family</th>
        <th>Expected</th>
        <th>Predicted</th>
        <th>Correct</th>
        <th>OK</th>
        <th>Latency</th>
        <th>Error</th>
      </tr>
    </thead>
    <tbody>`;

  for (const r of records) {
    const correct = r.correct === true ? "✅" : r.correct === false ? "❌" : "—";
    const ok = r.ok === true ? "✅" : "❌";
    const error = r.error_kind || "—";
    html += `
      <tr>
        <td class="code-mono">${escapeHtml(r.case_id)}</td>
        <td>${escapeHtml(r.scenario_family || "—")}</td>
        <td>${escapeHtml(r.expected_category || "—")}</td>
        <td>${escapeHtml(r.category || "—")}</td>
        <td>${correct}</td>
        <td>${ok}</td>
        <td class="code-mono">${r.latency_ms != null ? r.latency_ms.toFixed(1) + " ms" : "—"}</td>
        <td class="code-mono" style="color: var(--danger);">${escapeHtml(error)}</td>
      </tr>
    `;
  }

  html += `    </tbody>
  </table>`;
  container.innerHTML = html;
}

// ---------- Run ----------

let progressInterval = null;

els.btnRun.addEventListener("click", async () => {
  const config = els.configSelect.value;
  const limit = parseInt(els.runLimit.value, 10) || undefined;
  const runId = els.runId.value.trim() || undefined;

  if (!config) {
    setMessage(els.runMessage, "Select a config first.", "error");
    return;
  }

  try {
    hide(els.runResult);
    hide(els.runProgress);
    hide(els.runMessage);
    els.btnRun.disabled = true;
    els.btnRun.textContent = "Running…";

    const data = await fetchJSON("/api/run", {
      method: "POST",
      body: JSON.stringify({ config, limit, run_id: runId }),
    });

    const runIdRes = data.run_id;
    show(els.runProgress);
    els.progressText.textContent = "Starting…";
    els.progressCounter.textContent = "0 / 0";
    els.progressFill.style.width = "0%";

    progressInterval = setInterval(async () => {
      try {
        const state = await fetchJSON(`/api/run/${runIdRes}/progress`);
        els.progressText.textContent = state.status === "running" ? "Running…" : "Processing…";
        const p = state.progress;
        if (p && p.total > 0) {
          els.progressCounter.textContent = `${p.done} / ${p.total}`;
          els.progressFill.style.width = `${(p.done / p.total) * 100}%`;
        }
        if (state.status === "done") {
          clearInterval(progressInterval);
          hide(els.runProgress);
          showRunResult(state.result);
          els.btnRun.disabled = false;
          els.btnRun.textContent = "Run benchmark";
          await loadRuns();
    dlog('Runs loaded');
        } else if (state.status === "error") {
          clearInterval(progressInterval);
          hide(els.runProgress);
          setMessage(els.runMessage, `Run failed: ${state.error}`, "error");
          els.btnRun.disabled = false;
          els.btnRun.textContent = "Run benchmark";
        }
      } catch (err) {
        // ignore polling errors
      }
    }, 1000);
  } catch (err) {
    setMessage(els.runMessage, `Run failed: ${err.message}`, "error");
    els.btnRun.disabled = false;
    els.btnRun.textContent = "Run benchmark";
  }
});

function showRunResult(result) {
  show(els.runResult);
  els.resRunId.textContent = result.run_id;
  const m = result.metrics || {};
  els.resAccuracy.textContent = m.accuracy != null ? (m.accuracy * 100).toFixed(1) + "%" : "—";
  els.resMacroF1.textContent = m.macro_f1 != null ? (m.macro_f1 * 100).toFixed(1) + "%" : "—";
  els.resSchemaValidity.textContent = m.schema_validity != null ? (m.schema_validity * 100).toFixed(1) + "%" : "—";
  els.btnOpenRun.onclick = () => {
    viewRunReport(result.run_id);
  };
}

// ---------- Mode toggle ----------

els.modeSingle.addEventListener("click", () => {
  els.modeSingle.classList.add("mode-button--active");
  els.modeCompare.classList.remove("mode-button--active");
  els.singleView.style.display = "";
  els.compareView.style.display = "none";
});

els.modeCompare.addEventListener("click", () => {
  els.modeCompare.classList.add("mode-button--active");
  els.modeSingle.classList.remove("mode-button--active");
  els.singleView.style.display = "none";
  els.compareView.style.display = "";
});

// ---------- Compare (HTML table) ----------

els.btnCompare.addEventListener("click", async () => {
  const selected = Array.from(els.compareSelect.selectedOptions).map(o => o.value);
  if (selected.length < 2) {
    setMessage(document.getElementById("compare-message"), "Select at least two runs to compare.", "error");
    return;
  }
  try {
    const data = await fetchJSON("/api/compare/structured", {
      method: "POST",
      body: JSON.stringify({ run_dirs: selected }),
    });
    renderComparisonTable(data);
    show(els.compareViewContainer);
  } catch (err) {
    setMessage(document.getElementById("compare-message"), `Compare failed: ${err.message}`, "error");
  }
});

function renderComparisonTable(data) {
  const runs = data.runs;
  const metricRows = data.metric_rows;

  let html = `
    <table class="comparison-table">
      <thead>
        <tr>
          <th class="comparison-table--run-col">Metric</th>
          ${runs.map(r => `<th>${escapeHtml(r.run_id)}</th>`).join("")}
          <th class="comparison-table--delta-col">Δ vs baseline</th>
        </tr>
      </thead>
      <tbody>
  `;

  for (const row of metricRows) {
    const deltaClass = row.delta > 0 ? "delta-positive" : row.delta < 0 ? "delta-negative" : "delta-neutral";
    const deltaSign = row.delta > 0 ? "+" : row.delta < 0 ? "" : "";
    html += `<tr><td><strong>${escapeHtml(row.label)}</strong></td>`;
    for (const val of row.values) {
      html += `<td>${val}</td>`;
    }
    html += `<td class="${deltaClass}">${deltaSign}${row.delta}</td></tr>`;
  }

  html += `      </tbody>
    </table>

    <div style="margin-top: 1rem;">
      <h4 style="margin-bottom: 0.5rem;">Runs</h4>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Provider / Model</th>
            <th>Dataset</th>
            <th>Cases</th>
            <th>Valid</th>
          </tr>
        </thead>
        <tbody>
          ${runs.map(r => `
            <tr>
              <td class="comparison-table--run-col">${escapeHtml(r.run_id)}</td>
              <td>${escapeHtml(r.provider_name)} / <code>${escapeHtml(r.provider_model)}</code></td>
              <td>${escapeHtml(r.dataset_name)} v${escapeHtml(r.dataset_version)}</td>
              <td>${r.n_cases}</td>
              <td>${r.n_valid}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>

    <div class="comparison-download">
      <button class="button button--quiet" onclick="downloadComparison('${runs.map(r => r.path).join(",")}')">Download Markdown</button>
    </div>
  `;

  safeInnerHTML(els.compareViewContainer, html);
}

window.downloadComparison = async (runDirs) => {
  try {
    const data = await fetchJSON("/api/compare", {
      method: "POST",
      body: JSON.stringify({ run_dirs: runDirs.split(",") }),
    });
    const blob = new Blob([data.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "comparison.md";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    setMessage(document.getElementById("compare-message"), `Download failed: ${err.message}`, "error");
  }
};

// ---------- Tasks ----------

/** The model the Tasks form should send for a provider (never empty). */
async function taskModelMap(providerId) {
  if (providerId === "ollama") {
    if (!ollamaCache) await fetchOllamaStatus();
    return ollamaModelMap();
  }
  const provider = modelsData && modelsData[providerId];
  return (provider && provider.models) || {};
}

// Ollama's daemon list mixes cloud aliases (:cloud) and models that cannot
// chat; prefer a local completion model, then a known general-purpose family.
function preferredOllamaModel(models) {
  const names = models.map(m => m.id);
  const caps = (ollamaCache && ollamaCache.capabilities) || {};
  const completions = names.filter(n => (caps[n] || []).includes("completion"));
  const local = completions.filter(n => !/:cloud$/.test(n));
  for (const token of ["nemotron", "qwen", "llama", "mistral", "phi", "gemma", "deepseek", "glm"]) {
    const found = local.find(n => n.toLowerCase().includes(token));
    if (found) return found;
  }
  return local[0] || completions[0] || names[0] || "";
}

// Fill the model select for a provider (local models for Ollama, catalog for
// everything else) and preselect its preferred model.
async function syncTaskModel(providerSelect, modelSelect) {
  if (!providerSelect || !modelSelect) return;
  const providerId = providerSelect.value;
  const models = await taskModelMap(providerId);
  const values = Object.values(models);
  safeInnerHTML(modelSelect, values
    .map(m => `<option value="${escapeAttr(m.id)}">${escapeHtml(m.name || m.id)}</option>`)
    .join(""));
  if (!values.length) return;
  const preferred = providerId === "ollama"
    ? preferredOllamaModel(values)
    : preferredModel(providerId, models);
  if (preferred) modelSelect.value = preferred;
}

async function loadTasks() {
  try {
    const taskNames = await fetchJSON("/api/tasks");
    els.taskSelect.innerHTML = '<option value="">Select a task</option>';
    for (const name of taskNames) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      els.taskSelect.appendChild(opt);
    }
    els.taskProvider.innerHTML = "";
    els.taskJudgeProvider.innerHTML = "";
    const providers = await fetchJSON("/api/providers");
    // Task runs need an adapter: the API marks storage-only providers
    // (Ollama) runnable: false, so they never appear as a run option.
    for (const p of providers.filter(prov => prov.runnable !== false)) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      els.taskProvider.appendChild(opt.cloneNode(true));
      els.taskJudgeProvider.appendChild(opt.cloneNode(true));
    }
    // OpenRouter is the default provider — prefill a model id that works.
    selectOption(els.taskProvider, "openrouter");
    selectOption(els.taskJudgeProvider, "openrouter");
    await syncTaskModel(els.taskProvider, els.taskModel);
    await syncTaskModel(els.taskJudgeProvider, els.taskJudgeModel);
    await loadTaskRuns();
  } catch (err) {
    setMessage(els.taskMessage, `Failed to load tasks: ${err.message}`, "error");
  }
}

async function validateTask() {
  const name = els.taskSelect.value;
  if (!name) {
    setMessage(els.taskMessage, "Select a task first.", "error");
    return;
  }
  try {
    const data = await fetchJSON(`/api/tasks/${name}`);
    const problems = data.problems?.length
      ? `<ul style="margin:0.5rem 0 0 1rem">${data.problems.map(p => `<li>${p}</li>`).join("")}</ul>`
      : "<em>none</em>";
    els.taskMessage.innerHTML = `
      <strong>${data.name} v${data.version}</strong><br>
      <strong>Valid:</strong> ${data.ok}<br>
      <strong>Input fields:</strong> ${data.input_fields.join(", ")}<br>
      <strong>Output fields:</strong> ${data.output_fields.join(", ")}<br>
      <strong>Scoring:</strong> ${data.scoring_methods.join(", ")}<br>
      <strong>Cases:</strong> ${JSON.stringify(data.n_cases)}<br>
      <strong>Problems:</strong> ${problems}
    `;
    show(els.taskMessage, data.ok ? "ok" : "error");
  } catch (err) {
    setMessage(els.taskMessage, `Validation failed: ${err.message}`, "error");
  }
}

async function startTaskRun() {
  const name = els.taskSelect.value;
  if (!name) {
    setMessage(els.taskMessage, "Select a task first.", "error");
    return;
  }
  const payload = {
    name,
    split: els.taskSplit.value,
    provider: els.taskProvider.value,
    model: els.taskModel.value.trim(),
    judge_provider: els.taskJudgeProvider.value,
    judge_model: els.taskJudgeModel.value.trim(),
    limit: els.taskLimit.value ? parseInt(els.taskLimit.value, 10) : undefined,
  };
  try {
    hide(els.taskResult);
    show(els.taskProgress);
    els.taskProgressText.textContent = "Running…";
    els.taskProgressFill.style.width = "0%";
    els.taskProgressCounter.textContent = "0 / 0";
    const data = await fetchJSON(`/api/tasks/${name}/run`, { method: "POST", body: JSON.stringify(payload) });
    pollTaskProgress(data.run_id);
  } catch (err) {
    hide(els.taskProgress);
    setMessage(els.taskMessage, `Run failed to start: ${err.message}`, "error");
  }
}

async function pollTaskProgress(runId) {
  let attempts = 0;
  const maxAttempts = 300;
  async function tick() {
    attempts++;
    try {
      const state = await fetchJSON(`/api/tasks/${encodeURIComponent(runId)}/progress`);
      if (state.progress) {
        const { done, total } = state.progress;
        const pct = total ? Math.round((done / total) * 100) : 0;
        els.taskProgressFill.style.width = `${pct}%`;
        els.taskProgressCounter.textContent = `${done} / ${total}`;
      }
      if (state.status === "done") {
        hide(els.taskProgress);
        showResult(state.result);
        await loadTasks();
        return;
      }
      if (state.status === "error") {
        hide(els.taskProgress);
        setMessage(els.taskMessage, `Task run failed: ${state.error}`, "error");
        return;
      }
      if (attempts >= maxAttempts) {
        hide(els.taskProgress);
        setMessage(els.taskMessage, "Run timed out. Check the server logs.", "error");
        return;
      }
      setTimeout(tick, 1000);
    } catch (err) {
      hide(els.taskProgress);
      setMessage(els.taskMessage, `Progress poll failed: ${err.message}`, "error");
    }
  }
  tick();
}

function showResult(result) {
  if (!result) return;
  show(els.taskResult);
  els.taskResRunId.textContent = result.run_id;
  els.taskResCases.textContent = result.metrics?.n_cases ?? "—";
  els.taskResValid.textContent = result.metrics?.n_valid ?? "—";
  els.taskBtnOpenRun.onclick = () => {
    viewRunReport(result.run_id);
  };
}

async function loadTaskRuns() {
  try {
    const runs = await fetchJSON("/api/tasks/runs");
    if (runs.length === 0) {
      els.taskRunsGrid.innerHTML = '<p style="color:var(--fg-muted);text-align:center;padding:1rem;">No task runs yet.</p>';
      return;
    }
    const rows = runs.map(r => {
      const m = r.metrics || {};
      return `<div class="run-card" role="button" tabindex="0" onclick="viewRunReport('${escapeHtml(r.path)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();viewRunReport('${escapeHtml(r.path)}')}"><div class="run-card--header"><div class="run-card--id">${escapeHtml(r.run_id)}</div><span style="font-size:0.75rem;color:var(--fg-muted);">${escapeHtml(r.task ?? '')}</span></div><div class="run-card--meta"><div>Split: ${escapeHtml(r.split)}</div><div>Cases: ${m.n_cases ?? '—'} | Valid: ${m.n_valid ?? '—'}</div><div>${r.created_at || '—'}</div></div></div>`;
    }).join("");
    els.taskRunsGrid.innerHTML = `<div style="display:flex;flex-direction:column;gap:0.5rem;">${rows}</div>`;
  } catch (err) {
    els.taskRunsGrid.innerHTML = `<p style="color:var(--fg-danger);">Failed to load task runs: ${err.message}</p>`;
  }
}

els.btnValidateTask.addEventListener("click", validateTask);
els.btnRunTask.addEventListener("click", startTaskRun);

els.btnClearTaskRuns.addEventListener("click", async () => {
  if (!confirm("Delete every custom-task run? This cannot be undone.")) return;
  try {
    const data = await fetchJSON("/api/tasks/runs", { method: "DELETE" });
    setMessage(els.taskMessage, `Cleared ${data.count} task run(s).`, "ok");
    await loadTaskRuns();
  } catch (err) {
    setMessage(els.taskMessage, `Clear failed: ${err.message}`, "error");
  }
});
els.taskProvider.addEventListener("change", async () => { await syncTaskModel(els.taskProvider, els.taskModel); });
els.taskJudgeProvider.addEventListener("change", async () => {
  await syncTaskModel(els.taskJudgeProvider, els.taskJudgeModel);
});

// ---------- Init ----------

async function init() {
  try {
    // Debug overlay — opt-in via ?debug so it never intrudes on the UI.
    if (new URLSearchParams(location.search).has("debug")) {
      const debug = document.createElement('div');
      debug.id = 'fb-debug';
      debug.style.cssText = 'position:fixed;bottom:1rem;left:1rem;right:1rem;background:#1e293b;color:#e2e8f0;padding:0.75rem;border-radius:6px;z-index:9999;font-family:monospace;font-size:0.75rem;max-height:200px;overflow-y:auto;border:1px solid #334155;';
      debug.innerHTML = '<strong style="display:flex;justify-content:space-between;align-items:center;"><span>🔧 ForgeBench Debug</span><button onclick="document.getElementById(\'fb-debug\').remove()" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:0.75rem;padding:0 0.25rem;">×</button></strong><br>';
      document.body.appendChild(debug);
      dlog = (msg) => { debug.innerHTML += '<br>▸ ' + msg; console.log('[FB]', msg); };
    }

    dlog('DOM validation starting...');
    // Verify critical DOM elements exist
    const critical = ['key-provider', 'key-input', 'model-select', 'model-details',
      'btn-save-key', 'btn-verify-key', 'btn-remove-key', 'key-message',
      'config-select', 'run-limit', 'run-id', 'btn-run', 'run-message',
      'runs-grid', 'run-modal', 'run-modal-title', 'run-modal-meta', 'run-modal-body',
      'btn-modal-close', 'btn-modal-report', 'btn-modal-predictions',
      'btn-modal-download-report', 'btn-modal-download-predictions',
      'mode-single', 'mode-compare', 'single-view', 'compare-view',
      'compare-select', 'btn-compare', 'compare-view-container',
      'dataset-select', 'dataset-split', 'dataset-info', 'dataset-cases-container',
      'dataset-table-body', 'btn-download-dataset', 'dataset-message',
      'config-editor-select', 'config-editor', 'config-editor-loading',
      'btn-save-config', 'btn-reset-config', 'config-message',
      'btn-theme-toggle',
      'task-select', 'task-split', 'task-provider', 'task-model',
      'task-judge-provider', 'task-judge-model', 'task-limit',
      'btn-validate-task', 'btn-run-task', 'task-message',
      'task-progress', 'task-progress-text', 'task-progress-counter',
      'task-progress-fill', 'task-result', 'task-res-run-id', 'task-res-cases',
      'task-res-valid', 'task-btn-open-run', 'task-runs-grid',
      'setup-message', 'setup-file', 'setup-providers', 'setup-custom',
      'setup-name', 'setup-value', 'btn-setup-add'];
    const missing = critical.filter(id => !document.getElementById(id));
    if (missing.length > 0) {
      throw new Error('Missing DOM elements: ' + missing.join(', '));
    }

    applyTheme();
    dlog('Theme applied');
    await loadProvidersAndModels();
    dlog('Providers and models loaded');
    await loadCredentialStatus();
    dlog('Credential status loaded');
    await loadEnv();
    dlog('Environment loaded');
    await loadConfigs();
    dlog('Configs loaded');
    await loadDatasets();
    dlog('Datasets loaded');
    await loadRuns();
    dlog('Runs loaded');
    await loadTasks();
    dlog('Tasks loaded');
  } catch (err) {
    const errEl = document.createElement('div');
    errEl.style.cssText = 'position:fixed;top:1rem;left:1rem;right:1rem;background:#dc2626;color:#fff;padding:1rem;border-radius:6px;z-index:9999;font-family:monospace;font-size:0.875rem;';
    errEl.innerHTML = '<strong>ForgeBench Error:</strong> ' + err.message + '<br><small>' + (err.stack || '').substring(0, 300) + '</small>';
    document.body.insertBefore(errEl, document.body.firstChild);
    console.error('Init failed:', err);
  }
}

init();
