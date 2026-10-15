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

- Never commit `.env`, keys, or raw request/response logs.
- Run artifacts under `runs/` can contain full model outputs. They are
  git-ignored by default; if you commit reference runs, review them first.
- `manifest.json` records configuration and versions, not credentials.
