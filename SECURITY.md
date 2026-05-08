# Security Policy

## Status

ARI is currently an experimental local-first prototype.

The repository may change rapidly and should not yet be treated as production-ready infrastructure.

## Design Philosophy

The system intentionally prefers:

- local-first execution
- explainable orchestration
- approval-gated external actions
- minimal unnecessary exposure

## Current Safety Boundaries

By default, ARI should not:

- send emails automatically
- submit job applications automatically
- message third parties automatically
- perform purchases or payments
- execute uncontrolled external actions

External actions should remain approval-gated unless explicitly expanded by the operator.

## Secrets

Do not commit:

- `.env`
- API keys
- authentication secrets
- database dumps
- personal exports
- private credentials

Use `.env.example` as the baseline template.

## Reporting

If you discover a security issue, avoid posting secrets or exploit details publicly in issues.

Open a private communication path with the repository owner instead.
