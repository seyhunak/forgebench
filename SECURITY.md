# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** via GitHub's "Report a
vulnerability" button (Security tab) or by contacting the maintainers
directly. Do not open a public issue for security-relevant reports.

You can expect an acknowledgment within a few days and an honest assessment
of scope and fix timeline.

## Scope notes

ForgeBench is an offline evaluation harness. By design it:

- reads API keys only from environment variables, never from committed files;
- never uploads dataset contents, predictions, or logs anywhere except the
  model provider you explicitly configure;
- writes run artifacts only to the local `runs/` directory (git-ignored).

If you add a provider that transmits data to a third party, document the
destination and data flow in the adapter's module docstring and the PR.

## Secrets hygiene

- Prefer `forgebench set-key`: it writes the key to the git-ignored `.env`
  with owner-only permissions (0600), verifies it against the API, and shows
  only a masked form afterwards (`set-key --show`).
- Never commit `.env`, keys, or raw request/response logs.
- Keys are read at call time from the environment (precedence) or `.env`;
  they are never written into configs, manifests, or run artifacts.
- Run artifacts under `runs/` can contain full model outputs. They are
  git-ignored by default; if you commit reference runs, review them first.
- `manifest.json` records configuration and versions, not credentials.
