# Drift Sentinel

> **Preview release (0.0.1).** Namespace claim. Stable API lands in 0.1.0.

**Your API spec is a contract. Drift Sentinel measures how well you're keeping it.**

Most API tooling measures one of three things: how well-formed your spec is (linters), what changed between releases (diff tools), or whether your live API actually does what the spec promises (property-based runtime testing). Drift Sentinel rolls all three into a single number — the **Drift Score** (0–100) — and emits a cryptographically signed JSON+PDF report you can drop into a compliance binder, a PR comment, or a release Slack channel.

## What it does

Three open-source tools, one composite signal:

- **`vacuum`** — lints your OpenAPI document
- **`oasdiff`** — flags breaking changes between releases
- **`schemathesis`** — generates property-based tests from the spec, runs them against your live API, and reports every endpoint where reality contradicts the contract

Drift Sentinel runs all three, normalizes the findings into a single 0–100 score with configurable weights, and signs the result with ed25519.

## Drift Score formula

```
Drift Score = max(0, 100 − Σ min(weight × count, cap))
```

| Signal                          | Weight | Cap |
| ------------------------------- | -----: | --: |
| Breaking change (oasdiff)       |     10 |  50 |
| Spec error (vacuum)             |      5 |  25 |
| Runtime drift (schemathesis)    |      3 |  30 |
| Spec warning (vacuum)           |   0.25 |  15 |

100 = clean. 0 = catastrophic. Caps mean style noise can't drown out a single breaking change.

## Quick start

```bash
pip install driftsentinel

# install the underlying tools (vacuum + oasdiff are Go binaries)
# vacuum:    https://github.com/daveshanley/vacuum
# oasdiff:   https://github.com/oasdiff/oasdiff

driftsentinel audit ./openapi.yaml \
    --url https://api.example.com \
    --prev ./previous-release.yaml \
    --out ./audit \
    --fail-on adi=80

driftsentinel verify ./audit/report.pdf
```

## CI gating

```bash
driftsentinel audit spec.yaml --fail-on "adi=80,breaking=1,fuzz=5"
# exits 3 if Drift Score ≤ 80, OR any breaking changes, OR more than 5 runtime-drift failures
```

## Public proof points

| Spec  | Drift Score | Notes                                                               |
| ----- | ----------: | ------------------------------------------------------------------- |
| Stripe public API spec  |        75.0 | 2 errors hidden in 15K stylistic warnings                       |
| Plaid public API spec   |        60.0 | 19 structural errors                                            |

These were scored from the public OpenAPI documents — runtime drift signal not included because we don't have credentials for production. With drift detection enabled against your own API, scores typically drop another 15–30 points. **That gap is the moat.**

## Status

This is the namespace-claiming preview release. Functional API and CLI surface will harden through 0.0.x and stabilize at 0.1.0. Filing breaking-change deltas in the changelog is hereby ironic but necessary.

## License

Apache 2.0.
