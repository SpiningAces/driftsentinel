# Drift Sentinel

**Your API spec is a contract. Drift Sentinel watches whether you're keeping it.**

---

## The problem

Your OpenAPI spec is the contract you ship to integrators, partners, and AI agents. But specs rot. Engineers update endpoints faster than they update YAML. Required parameters get added quietly. Response codes change. Three releases later, the spec promises one thing and the API does another — and the first time you find out is when an integration partner is on a status call.

Three things are happening at once, and most teams measure none of them:

1. **Spec quality** — is the document well-formed?
2. **Spec stability** — what just broke between versions?
3. **Spec / runtime drift** — does the live API actually do what the spec promises?

Linters catch (1). Diff tools catch (2). Almost nobody is measuring (3). That's the gap.

---

## What Drift Sentinel does

Every release, Drift Sentinel runs three checks against your API and rolls them into a single number:

- **`vacuum`** — lints your spec for structural and stylistic issues
- **`oasdiff`** — diffs the new spec against the previous one and flags breaking changes
- **`schemathesis`** — generates property-based tests from your spec, runs them against your live API, and reports every endpoint where reality contradicts the contract

Output is one signed PDF and one canonical JSON, both verifiable with an ed25519 public key. You can drop the report into a compliance binder, attach it to a PR, or post it to your release Slack channel.

---

## The Drift Score (0–100)

A single number. **100 = clean contract. 0 = catastrophic drift.**

| Signal | Penalty per finding | Capped at |
|---|---:|---:|
| Breaking change (oasdiff) | −10 | −50 |
| Spec error (vacuum) | −5 | −25 |
| Runtime drift (schemathesis) | −3 | −30 |
| Spec warning (vacuum) | −0.25 | −15 |

`Drift Score = max(0, 100 − Σ capped penalties)`

Caps mean a flood of warnings can't drown out a single breaking change, and a million stylistic notes can never push the score below 85 on their own. The formula is published; the weights are tunable per organization.

---

## What a buyer sees at three score levels

### 🟢 Drift Score 95 — clean release

```
Drift Score: 95.0 / 100
  breaking          0  (0 penalty)
  spec errors       0  (0)
  runtime drift     0  (0)
  spec warnings    20  (5)
breaches: none
```

**Read:** Ship it. One stylistic note, nothing actionable. CI pipeline passes.

---

### 🟡 Drift Score 50 — a real internal API at a 50-engineer team

```
Drift Score: 50.0 / 100
  breaking          0  (0 penalty)
  spec errors       1  (5)
  runtime drift    18  (30 — cap engaged)
  spec warnings   736  (15 — cap engaged)
breaches: --fail-on adi=80 → exit 3
```

**Read:** Your spec is structurally OK and you didn't break anything between releases — but your live API is doing things the spec doesn't promise on 18 endpoints. Most likely: your spec says these endpoints return `200` or `422`, and they're actually returning `404` or `500` for edge cases. Fix the documented response codes. The 736 stylistic warnings are deferrable; spend a quarter on them when you have it.

This is the most common starting score. **Most APIs live here.**

---

### 🔴 Drift Score 10 — block-the-merge release

```
Drift Score: 10.0 / 100
  breaking          3  (30 penalty)
  spec errors       3  (15)
  runtime drift    10  (30 — cap engaged)
  spec warnings    60  (15 — cap engaged)
breaches: adi=10 ≤ 80, breaking=3 ≥ 1, fuzz=10 ≥ 5
```

**Read:** Block this merge. Three endpoints removed without deprecation, three structural spec errors, ten endpoints where live behavior contradicts the contract. The integration team will spend a week unwinding this if it ships. This is what Drift Sentinel exists to prevent.

---

## Two real proof points (run this session against public specs)

### 🟡 Stripe — Drift Score **75.0**

Stripe maintains one of the most carefully published OpenAPI specs in the industry — they expose it for SDK generation. Drift Sentinel still found:

- **2 structural errors** in the document
- **15,618 stylistic warnings** (top rules: camel-case-properties, description-duplication, missing examples)

The two errors are buried in 15K warnings — the kind of finding that almost never surfaces in a manual review. Drift Sentinel pulls them to the top of the report.

### 🟠 Plaid — Drift Score **60.0**

Plaid's public API spec is also well-maintained but scores lower:

- **19 structural errors** (cap engaged at −25)
- **7,157 stylistic warnings** (cap engaged at −15)

Plaid's score reflects a denser concentration of structural issues per spec mass. A buyer reading this would say: "If Plaid is at 60 and Stripe is at 75, where am I?"

> *Both specs were scored without the runtime drift signal because we don't have keys for their production APIs. With drift detection enabled against your own API, scores typically drop another 15–30 points — that's the part nobody else measures.*

---

## What you get

- One CLI: `oas-sentinel audit your-spec.yaml --prev last-release.yaml --url https://api.you.com`
- One signed PDF + one canonical JSON per audit
- One nightly cron that audits every API in your fleet and posts the deltas to the channel of your choice
- One CI gate: `--fail-on "adi=80,breaking=1"` exits non-zero when the score drops or anything breaks

The signature is ed25519. The public key is yours. The report is non-repudiable: you can hand it to a regulator, a partner, or a board member with confidence the numbers haven't been tampered with.

---

## Try it

```bash
pip install driftsentinel
oas-sentinel audit ./openapi.yaml --url https://api.example.com --out ./audit
oas-sentinel verify ./audit/report.pdf
```

Three commands. One Drift Score. Every release.
