"""ForgeBench local dashboard: BYOK key entry, benchmark runs, result comparison.

Presentation only. Every action calls the same functions the terminal commands
use (``run_experiment``, ``credentials``, ``reporting``), so a run started from
the UI produces byte-identical artifacts to one started from the CLI.

Launch with ``forgebench dashboard`` (or ``streamlit run`` on this file).
"""

from __future__ import annotations

if __package__ in (None, ""):
    # Allow running this file directly (e.g. ``streamlit run src/forgebench/dashboard.py``
    # or ``python src/forgebench/dashboard.py``) by making the parent package
    # importable so relative imports resolve.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "forgebench"

from pathlib import Path

from .config import load_config
from .credentials import (
    delete_value,
    find_env_file,
    get_value,
    load_env_files,
    mask,
    set_value,
    source_of,
)
from .providers.mistral import verify_api_key
from .reporting import load_run, render_comparison, render_report
from .runner import run_experiment
from .schemas import PredictionRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = REPO_ROOT / "runs"


def list_configs(base: Path | None = None) -> list[Path]:
    """All experiment configs, deterministic order."""
    config_dir = (base or REPO_ROOT) / "configs"
    if not config_dir.is_dir():
        return []
    return sorted(config_dir.rglob("*.yaml"))


def list_runs(runs_root: Path | None = None) -> list[Path]:
    """Run directories that have a manifest, newest first.

    The manifest's ``created_at_utc`` is authoritative (runs written by
    different processes may have directory names that do not sort by time);
    the directory name is only a fallback.
    """
    root = runs_root or RUNS_ROOT
    if not root.is_dir():
        return []
    runs = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()]

    def sort_key(path: Path) -> tuple[str, str]:
        try:
            import json  # noqa: PLC0415

            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            created = str(manifest.get("created_at_utc") or "")
        except Exception:  # noqa: BLE001 - an unreadable manifest is still a run
            created = ""
        return (created, path.name)

    return sorted(runs, key=sort_key, reverse=True)


def read_predictions(run_dir: Path) -> list[PredictionRecord]:
    """Load one run's predictions for report rendering."""
    path = run_dir / "predictions.jsonl"
    if not path.exists():
        return []
    return [
        PredictionRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _key_tab() -> None:
    import streamlit as st

    # Clearing a widget's session value must happen before it is instantiated.
    if st.session_state.pop("_fb_clear_key", False):
        st.session_state["fb_key_input"] = ""
    message = st.session_state.pop("_fb_msg", None)

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Mistral API key")
        st.text_input(
            "Paste your API key",
            type="password",
            key="fb_key_input",
            help="Saved to the git-ignored .env with owner-only (0600) permissions. "
            "It never appears in configs, run artifacts, or Git.",
        )
        model = st.text_input(
            "Default model",
            key="fb_model_input",
            value=get_value("MISTRAL_MODEL") or "ministral-8b-2512",
        )
        save, verify, remove = st.columns(3)
        if save.button("Save", type="primary", use_container_width=True):
            entered = (st.session_state.get("fb_key_input") or "").strip()
            if not entered:
                st.warning("Paste a key first.")
            else:
                target = set_value("MISTRAL_API_KEY", entered)
                if model.strip():
                    set_value("MISTRAL_MODEL", model.strip())
                st.session_state["_fb_clear_key"] = True
                st.session_state["_fb_msg"] = f"Saved to {target} (chmod 600, git-ignored)."
                st.rerun()
        if verify.button("Verify", use_container_width=True):
            key_now = get_value("MISTRAL_API_KEY")
            if not key_now:
                st.warning("No key saved yet.")
            else:
                with st.spinner("Checking against api.mistral.ai ..."):
                    accepted, detail = verify_api_key(key_now)
                if accepted:
                    st.success(f"Key OK — {detail}")
                elif accepted is False:
                    st.error(f"Key rejected — {detail}")
                else:
                    st.info(f"Could not verify — {detail}")
        if remove.button("Remove", use_container_width=True):
            removed = delete_value("MISTRAL_API_KEY")
            st.success(f"Removed from {removed}" if removed else "No saved key to remove.")
        if message:
            st.success(message)
    with right:
        st.subheader("Status")
        key = get_value("MISTRAL_API_KEY")
        st.markdown(
            f"- **Key:** `{mask(key)}`\n"
            f"- **Source:** {source_of('MISTRAL_API_KEY')}\n"
            f"- **Model:** `{get_value('MISTRAL_MODEL') or '(not set)'}`\n"
            f"- **File:** `{find_env_file() or '(created in the working directory on save)'}`"
        )
        st.caption(
            "Environment variables take precedence over .env. Runs execute locally; "
            "only case inputs are sent to the model provider you configure."
        )


def _run_tab() -> None:
    import streamlit as st

    configs = list_configs()
    if not configs:
        st.info("No configs found under configs/.")
        return
    labels = [str(path.relative_to(REPO_ROOT)) for path in configs]
    selected = st.selectbox("Experiment config", labels)
    limit = st.number_input(
        "Case limit (0 = full split)", min_value=0, max_value=100_000, value=0, step=10
    )
    run_id = st.text_input("Run id (optional)", "", placeholder="auto: name-provider-timestamp")

    try:
        experiment = load_config(REPO_ROOT / selected)
    except Exception as exc:  # config problems must not kill the app
        st.error(f"Config error: {exc}")
        return

    needs_key = experiment.provider.name == "mistral" and not get_value("MISTRAL_API_KEY")
    if needs_key:
        st.warning("This config uses the Mistral provider — save an API key in the “API key” tab.")

    if st.button("Run benchmark", type="primary", disabled=needs_key):
        progress = st.progress(0.0)
        status = st.empty()

        def on_progress(done: int, total: int) -> None:
            progress.progress(done / total if total else 1.0)
            status.text(f"{done}/{total} cases")

        try:
            with st.spinner("Running ..."):
                result = run_experiment(
                    experiment,
                    output_root=RUNS_ROOT,
                    limit=limit or None,
                    run_id=run_id.strip() or None,
                    on_progress=on_progress,
                )
        except Exception as exc:
            progress.empty()
            st.error(f"Run failed: {exc}")
            return
        progress.progress(1.0)
        status.empty()
        metrics = result.metrics
        st.session_state["fb_selected_run"] = result.run_id
        st.success(
            f"Run **{result.run_id}** finished — accuracy {metrics.get('accuracy', 0):.3f}, "
            f"macro-F1 {metrics.get('macro_f1', 0):.3f}, "
            f"schema validity {metrics.get('schema_validity', 0):.3f}. "
            f"See the **Results** tab."
        )
        st.code(f"forgebench compare runs/{result.run_id} runs/<other-run>", language="bash")


def _results_tab() -> None:
    import streamlit as st

    runs = list_runs()
    if not runs:
        st.info("No runs yet — start one in the **Run** tab.")
        return
    names = [path.name for path in runs]
    preselect = st.session_state.get("fb_selected_run")
    index = names.index(preselect) if preselect in names else 0

    mode = st.radio("View", ["Single run report", "Compare runs"], horizontal=True)
    if mode == "Single run report":
        name = st.selectbox("Run", names, index=index)
        run_dir = RUNS_ROOT / name
        entry = load_run(str(run_dir))
        st.markdown(render_report(entry["manifest"], entry["metrics"], read_predictions(run_dir)))
        with st.expander("Raw metrics (JSON)"):
            st.json(entry["metrics"])
        with st.expander("Manifest (JSON)"):
            st.json(entry["manifest"])
    else:
        picks = st.multiselect("Runs — first selection is the baseline", names, default=names[:2])
        if len(picks) < 2:
            st.info("Select at least two runs to compare.")
            return
        entries = [load_run(str(RUNS_ROOT / name)) for name in picks]
        st.markdown(render_comparison(entries))
        st.caption(
            "Deltas compare the last run against the first. With small test sets, "
            "differences of a few points are noise — read the per-class tables."
        )


def render() -> None:
    """Entry point used by Streamlit when it executes this file."""
    import streamlit as st

    load_env_files()
    st.set_page_config(page_title="ForgeBench", page_icon="🔥", layout="wide")
    st.title("ForgeBench")
    st.caption("Measure domain adaptation, not just model intelligence.")
    key_tab, run_tab, results_tab = st.tabs(["🔑 API key", "▶️ Run", "📊 Results"])
    with key_tab:
        _key_tab()
    with run_tab:
        _run_tab()
    with results_tab:
        _results_tab()


if __name__ == "__main__":
    render()
