const pptxgen = require('/opt/homebrew/lib/node_modules/pptxgenjs');

const PAPER = "0D0F14";
const SURFACE = "14171E";
const LINE = "2A2F3A";
const INK = "EEF1F6";
const INK2 = "B8BCC8";
const MUTED = "8A8FA0";
const ACCENT = "3B82F6";
const ACCENT_T = "93C5FD";
const SUCCESS = "4ADE80";
const DANGER = "F87171";
const WHITE = "FFFFFF";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Seyhun Akyurek";
pres.company = "ForgeBench";
pres.title = "ForgeBench — Measure domain adaptation, not just model intelligence.";
pres.subject = "Reproducible, provider-agnostic benchmark harness for LLM domain tasks";

const W = 10;
const H = 5.625;

function darkSlide() { const s = pres.addSlide(); s.background = { color: PAPER }; return s; }
function lightSlide() { const s = pres.addSlide(); s.background = { color: "F6F8FC" }; return s; }

function footer(s, num, dark = true) {
  const fg = dark ? "6B7280" : "8A8FA0";
  s.addText("ForgeBench  ·  Measure domain adaptation, not just model intelligence.", {
    x: 0.6, y: H - 0.35, w: 6, h: 0.25,
    fontSize: 9, fontFace: "Inter", color: fg, margin: 0,
  });
  s.addText(String(num).padStart(2, "0"), {
    x: W - 1.0, y: H - 0.35, w: 0.4, h: 0.25,
    fontSize: 9, fontFace: "Inter", color: fg, align: "right", margin: 0,
  });
}

function title(s, text, x, y, w, color = INK, size = 34) {
  s.addText(text, { x, y, w, h: 1.4, fontSize: size, fontFace: "Space Grotesk", color, bold: true, margin: 0, valign: "top", charSpacing: -0.5 });
}
function body(s, text, x, y, w, color = INK2, size = 15) {
  s.addText(text, { x, y, w, h: 1.0, fontSize: size, fontFace: "Inter", color, margin: 0, valign: "top" });
}
function bullets(s, items, x, y, w, color = INK, size = 14, h = 3.0) {
  const arr = items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, fontSize: size } }));
  s.addText(arr, { x, y, w, h, fontSize: size, fontFace: "Inter", color, margin: 0, valign: "top", paraSpaceAfter: 4 });
}
function card(s, x, y, w, hh, fill = SURFACE, line = LINE) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h: hh, fill: { color: fill }, line: { color: line, width: 1 } });
}
function stat(s, n, label, x, y, w = 2.15, dark = true) {
  card(s, x, y, w, 1.7, dark ? SURFACE : "FFFFFF", dark ? LINE : "DCE3F0");
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h: 0.06, fill: { color: ACCENT }, line: { width: 0 } });
  s.addText(n, { x, y: y + 0.15, w, h: 0.9, fontSize: 40, fontFace: "Space Grotesk", color: dark ? WHITE : "15131F", bold: true, align: "center", valign: "middle", margin: 0 });
  s.addText(label, { x: x + 0.15, y: y + 1.05, w: w - 0.3, h: 0.5, fontSize: 10, fontFace: "Inter", color: dark ? MUTED : "5C5878", align: "center", margin: 0 });
}

// S1 — Title
{
  const s = darkSlide();
  s.addShape(pres.shapes.OVAL, { x: -1.5, y: 1.5, w: 6, h: 6, fill: { color: ACCENT, transparency: 88 }, line: { width: 0 } });
  s.addShape(pres.shapes.OVAL, { x: 6.5, y: -1, w: 5, h: 5, fill: { color: ACCENT, transparency: 92 }, line: { width: 0 } });
  s.addText("FORGEBENCH", { x: 0.7, y: 1.5, w: 9, h: 1.6, fontSize: 96, fontFace: "Space Grotesk", color: WHITE, bold: true, margin: 0, charSpacing: -4 });
  s.addText("Measure domain adaptation, not just model intelligence.", { x: 0.7, y: 3.0, w: 9, h: 0.8, fontSize: 26, fontFace: "Space Grotesk", color: ACCENT_T, margin: 0, charSpacing: -0.5 });
  s.addText("A reproducible, provider-agnostic benchmark harness that answers one question:\ndid customizing a model — a better prompt, few-shot examples, structured output,\na fine-tune — actually improve performance on a domain task, or did it just make\nthe pipeline more complicated?", { x: 0.7, y: 3.9, w: 8.6, h: 1.0, fontSize: 14, fontFace: "Inter", color: INK2, margin: 0, valign: "top" });
  s.addText("Seyhun Akyürek  ·  github.com/seyhunak/forgebench  ·  Apache-2.0", { x: 0.7, y: 5.05, w: 8.6, h: 0.3, fontSize: 11, fontFace: "Inter", color: MUTED, margin: 0 });
  footer(s, 1, true);
}

// S2 — Problem
{
  const s = lightSlide();
  title(s, "Did it actually get better,\nor just more complicated?", 0.7, 0.5, 8.6, "15131F", 30);
  body(s, "Teams ship prompt changes, few-shot examples, structured output, and new providers with no pinned baseline. Accuracy goes up in a demo; regressions hide in production. If you cannot point at a pinned baseline run, you do not know whether your last change helped.", 0.7, 1.9, 8.6, "5C5878", 14);
  const stats = [["?", "accuracy gains unverified in prod"],["0", "pinned baselines in most repos"],["3–5", "taps of config drift per change"],["1", "question ForgeBench answers"]];
  let x = 0.7;
  stats.forEach(([n, l]) => {
    stat(s, n, l, x, 3.0, 2.15, false);
    x += 2.25;
  });
  footer(s, 2, false);
}

// S3 — Solution
{
  const s = darkSlide();
  title(s, "What if you could prove it?", 0.7, 0.5, 8.6, INK, 32);
  body(s, "ForgeBench is a reproducible, provider-agnostic benchmark harness. Same fixed test set, same scoring code path, two runs, one compare — with metric deltas and the exact cases that flipped. Ground truth is never a model.", 0.7, 1.7, 8.6, INK2, 15);
  const bullets4 = [
    "No committed secrets — BYOK, keys read at call time, never in artifacts",
    "No private data needed — 9 synthetic datasets with rule-generated ground truth",
    "No GPU, no training — inference benchmarking only",
    "No silent failures — errors are data, scored and reported",
  ];
  bullets(s, bullets4, 0.7, 2.9, 8.6, INK, 14, 2.4);
  footer(s, 3, true);
}

// S4 — How it works
{
  const s = lightSlide();
  title(s, "How it works", 0.7, 0.5, 8.6, "15131F", 32);
  body(s, "One orchestration path, so every provider is scored by exactly the same code.", 0.7, 1.7, 8.6, "5C5878", 14);
  const steps = [
    ["1 · LOAD", "Validate YAML config + dataset manifest (SHA-256)."],
    ["2 · VALIDATE", "Pydantic schemas; missing env vars fail loudly."],
    ["3 · INFER", "provider.predict(case) across 6 providers + offline mock."],
    ["4 · SCORE", "accuracy, macro-F1, critical false-match, escalation recall, schema validity, latency, cost."],
    ["5 · RECORD", "predictions.jsonl + metrics.json + manifest.json + trace.jsonl + report.md"],
  ];
  let y = 2.3;
  steps.forEach(([h, d]) => {
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 8.6, h: 0.62, fill: { color: "FFFFFF" }, line: { color: "DCE3F0", width: 1 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 0.06, h: 0.62, fill: { color: ACCENT }, line: { width: 0 } });
    s.addText(h, { x: 0.95, y: y + 0.08, w: 1.6, h: 0.46, fontSize: 13, fontFace: "JetBrains Mono", color: ACCENT, bold: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 2.6, y: y + 0.08, w: 6.5, h: 0.46, fontSize: 12, fontFace: "Inter", color: "15131F", margin: 0, valign: "middle" });
    y += 0.72;
  });
  footer(s, 4, false);
}

// S5 — Architecture / tech stack
{
  const s = darkSlide();
  title(s, "Tech stack — small, boring, inspectable", 0.7, 0.4, 8.6, INK, 28);
  const cols = [
    ["Core", "Python 3.11+ · YAML + Pydantic\nTyper CLI · FastAPI + uvicorn\nhttpx · ruff · pytest\nJSONL/JSON/Markdown artifacts"],
    ["Platform", "Static SPA (no Node build)\nDark-first Cobalt theme\n6 providers + offline mock\nmodels.dev catalog sync"],
    ["Intelligence", "markdown-it-py · bleach\nG-Eval LLM-as-judge\nRAGAS-style RAG metrics\ntrace.jsonl waterfall"],
  ];
  let x = 0.7;
  cols.forEach(([h, d]) => {
    card(s, x, 1.6, 2.75, 3.2, SURFACE, LINE);
    s.addText(h, { x: x + 0.2, y: 1.8, w: 2.35, h: 0.4, fontSize: 16, fontFace: "Space Grotesk", color: ACCENT_T, bold: true, margin: 0 });
    s.addText(d, { x: x + 0.2, y: 2.3, w: 2.35, h: 2.4, fontSize: 12, fontFace: "Inter", color: INK2, margin: 0, valign: "top" });
    x += 3.05;
  });
  footer(s, 5, true);
}

// S6 — Real-world challenges / use cases
{
  const s = lightSlide();
  title(s, "Real-world challenges it solves", 0.7, 0.4, 8.6, "15131F", 28);
  const pairs = [
    ["Prompt / fine-tune A/B validation", "Same fixed test set, same scoring path, two runs, one compare with metric deltas + flipped cases."],
    ["Model & provider selection", "One config, six providers + deterministic offline mock — swap --provider/--model, keep everything else identical."],
    ["Regression gating in CI", "Pinned baseline vs. fresh candidate; fails the PR past tolerance (−0.05 accuracy by default)."],
    ["Regulated-domain evidence", "9 synthetic datasets, rule-generated ground truth, SHA-256 manifests — no customer data, auditable."],
    ["Risk-aware quality", "Critical false-match rate and escalation recall tracked separately from accuracy."],
    ["Safety / red-team scanning", "forgebench safety-scan over injection, jailbreak, PII, bias, toxicity — fully offline."],
  ];
  let y = 1.5;
  pairs.forEach(([h, d]) => {
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 8.6, h: 0.62, fill: { color: "FFFFFF" }, line: { color: "DCE3F0", width: 1 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 0.06, h: 0.62, fill: { color: ACCENT }, line: { width: 0 } });
    s.addText(h, { x: 0.95, y: y + 0.06, w: 2.6, h: 0.5, fontSize: 11, fontFace: "Space Grotesk", color: "15131F", bold: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 3.6, y: y + 0.06, w: 5.5, h: 0.5, fontSize: 10.5, fontFace: "Inter", color: "5C5878", margin: 0, valign: "middle" });
    y += 0.7;
  });
  footer(s, 6, false);
}

// S7 — Why LLMOps, not just eval
{
  const s = darkSlide();
  title(s, "Why this is LLMOps, not just an eval", 0.7, 0.4, 8.6, INK, 28);
  const items = [
    "Prompt versioning — prompts/<name>/vN.md, immutable, SHA-256 digest recorded per run",
    "Experiment-as-code — YAML configs, diffable in PRs, identical reruns",
    "Provider abstraction — one predict() contract across 6 providers + offline mock",
    "Structured-output discipline — schema_validity is a first-class metric, not an afterthought",
    "Risk-aware metrics — critical false-match rate + escalation recall separate from accuracy",
    "Observability — trace.jsonl waterfall: which step cost the time is an answer, not a guess",
  ];
  bullets(s, items, 0.7, 1.5, 8.6, INK, 13, 3.6);
  footer(s, 7, true);
}

// S8 — A minute in the life
{
  const s = lightSlide();
  title(s, "A minute in the life of ForgeBench", 0.7, 0.5, 8.6, "15131F", 28);
  const steps = [
    ["1 · SET KEY", "forgebench set-key openrouter (verified, masked, chmod 600)"],
    ["2 · RUN", "forgebench run --config baseline.yaml → run-id, metrics, trace"],
    ["3 · COMPARE", "forgebench compare <baseline> <candidate> → deltas + flipped cases"],
  ];
  let y = 1.9;
  steps.forEach(([h, d]) => {
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 8.6, h: 1.0, fill: { color: "FFFFFF" }, line: { color: "DCE3F0", width: 1 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 0.06, h: 1.0, fill: { color: ACCENT }, line: { width: 0 } });
    s.addText(h, { x: 0.95, y: y + 0.1, w: 1.6, h: 0.8, fontSize: 13, fontFace: "JetBrains Mono", color: ACCENT, bold: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 2.6, y: y + 0.1, w: 6.5, h: 0.8, fontSize: 12, fontFace: "Inter", color: "15131F", margin: 0, valign: "middle" });
    y += 1.15;
  });
  body(s, "Dashboard at localhost:8000 shows the same runs, metrics, and comparisons — the UI is a client of the same runner, never a parallel implementation.", 0.7, 5.0, 8.6, "5C5878", 11);
  footer(s, 8, false);
}

// S9 — What's in the box
{
  const s = darkSlide();
  title(s, "What's in the box", 0.7, 0.5, 8.6, INK, 30);
  const nums = [["6", "LLM providers"], ["9", "synthetic datasets"], ["100–200", "cases per split"], ["5", "core metrics"], ["0", "backend servers"], ["0", "GPU required"]];
  let x = 0.7;
  let row = 0;
  nums.forEach(([n, l], i) => {
    if (i === 3) { x = 0.7; row = 1; }
    stat(s, n, l, x, 1.9 + row * 2.0, 2.75, true);
    x += 3.05;
  });
  footer(s, 9, true);
}

// S10 — Built for regulated domains
{
  const s = lightSlide();
  title(s, "Built for regulated domains", 0.7, 0.5, 8.6, "15131F", 28);
  body(s, "Finance, healthcare, legal, insurance, payments, procurement — domains where accuracy alone hides the expensive errors. Nine synthetic datasets with rule-generated ground truth and SHA-256 manifests: no customer data, but auditable, reproducible results.", 0.7, 1.6, 8.6, "5C5878", 13);
  const domains = ["Finance", "Healthcare", "Legal", "Insurance", "Payments", "Procurement", "Support", "Content", "Safety"];
  let x = 0.7, y = 3.0;
  domains.forEach((d, i) => {
    if (i === 5) { x = 0.7; y = 3.85; }
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 1.6, h: 0.6, fill: { color: "FFFFFF" }, line: { color: "DCE3F0", width: 1 } });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 1.6, h: 0.05, fill: { color: ACCENT }, line: { width: 0 } });
    s.addText(d, { x, y: y + 0.12, w: 1.6, h: 0.36, fontSize: 12, fontFace: "Inter", color: "15131F", align: "center", valign: "middle", margin: 0 });
    x += 1.75;
  });
  footer(s, 10, false);
}

// S11 — FinOps
{
  const s = darkSlide();
  title(s, "FinOps — cost is a metric, not an afterthought", 0.7, 0.4, 8.6, INK, 26);
  const items = [
    "Estimated cost per 1,000 cases — headline metric alongside accuracy",
    "Dated price table (as_of per entry) — unknown models report 0 with a warning, never a fabricated number",
    "Live pricing sync from models.dev into the model picker — see price before you run",
    "Token-level attribution via trace.jsonl — cost per case, per step, per run",
    "Zero-cost path: offline mock + Ollama local + --limit N for smoke runs",
    "No training spend — inference benchmarking only",
  ];
  bullets(s, items, 0.7, 1.5, 8.6, INK, 13, 3.6);
  s.addText("Pick the cheapest model that clears the risk metrics — and prove it with a dated cost figure attached to the run.", { x: 0.7, y: 5.0, w: 8.6, h: 0.4, fontSize: 12, fontFace: "Inter", color: ACCENT_T, italic: true, margin: 0 });
  footer(s, 11, true);
}

// S12 — Roadmap
{
  const s = lightSlide();
  title(s, "From experiment to platform", 0.7, 0.5, 8.6, "15131F", 28);
  const items = [
    "Wire real APIs (DoorDash, Google Places, Plaid, Calendar, Spotify) as domain tasks",
    "RevenueCat + Clerk for access and subscriptions",
    "Agentic memory across sessions and intents",
    "City-level service catalogs beyond the 9 datasets",
    "Multi-agent orchestration on top of the runner",
    "Contributions welcome: new adapters, domains, metrics, reproduced runs",
  ];
  bullets(s, items, 0.7, 1.6, 8.6, "15131F", 13, 3.4);
  footer(s, 12, false);
}

// S13 — Open by default
{
  const s = darkSlide();
  title(s, "Open by default. Honest by rule.", 0.7, 0.4, 8.6, INK, 28);
  const pairs = [
    ["License", "Apache-2.0 — fork it, ship it."],
    ["Telemetry", "None. No events sent, no analytics."],
    ["Data", "No backend. Keys stay on device (chmod 600)."],
    ["Actions", "Real-world handoff only. Errors are data."],
    ["Keys", "Mistral · OpenAI · Anthropic · Google · OpenRouter · Ollama"],
    ["Stack", "Python · FastAPI · Typer · Pydantic · ruff · pytest"],
  ];
  let y = 1.5;
  pairs.forEach(([k, v]) => {
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 8.6, h: 0.55, fill: { color: SURFACE }, line: { color: LINE, width: 1 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y, w: 0.06, h: 0.55, fill: { color: ACCENT }, line: { width: 0 } });
    s.addText(k, { x: 0.95, y: y + 0.08, w: 1.5, h: 0.39, fontSize: 12, fontFace: "JetBrains Mono", color: ACCENT_T, bold: true, margin: 0, valign: "middle" });
    s.addText(v, { x: 2.5, y: y + 0.08, w: 6.6, h: 0.39, fontSize: 11.5, fontFace: "Inter", color: INK2, margin: 0, valign: "middle" });
    y += 0.65;
  });
  footer(s, 13, true);
}

// S14 — Thank you
{
  const s = darkSlide();
  s.addShape(pres.shapes.OVAL, { x: -1.5, y: 1.5, w: 6, h: 6, fill: { color: ACCENT, transparency: 88 }, line: { width: 0 } });
  s.addShape(pres.shapes.OVAL, { x: 6.5, y: -1, w: 5, h: 5, fill: { color: ACCENT, transparency: 92 }, line: { width: 0 } });
  s.addText("Thank you.", { x: 0.7, y: 1.7, w: 9, h: 1.4, fontSize: 72, fontFace: "Space Grotesk", color: WHITE, bold: true, margin: 0, charSpacing: -3 });
  s.addText("ForgeBench — Measure domain adaptation, not just model intelligence.", { x: 0.7, y: 3.2, w: 9, h: 0.7, fontSize: 22, fontFace: "Space Grotesk", color: ACCENT_T, margin: 0, charSpacing: -0.5 });
  s.addText("Seyhun Akyürek  ·  github.com/seyhunak/forgebench  ·  Apache-2.0", { x: 0.7, y: 4.1, w: 8.6, h: 0.3, fontSize: 12, fontFace: "Inter", color: MUTED, margin: 0 });
  footer(s, 14, true);
}

pres.writeFile({ fileName: "/Users/seyhunakyurek/Projects/forgebench/presentation/forgebench-pitch.pptx" })
  .then(() => console.log("WROTE pptx"))
  .catch((e) => { console.error(e); process.exit(1); });
