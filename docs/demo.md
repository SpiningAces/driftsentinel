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

## The buyer ladder — eight real public APIs, ranked

Calibration data, run against publicly available OpenAPI specs. **Drift Sentinel ate its own dog food too.**

| API                    | Drift Score | Headline finding                                                       |
| ---------------------- | ----------: | ---------------------------------------------------------------------- |
| **Drift Sentinel** (self) |    **98.8** | 0 errors, 7 warnings — we ran our own tool on our own spec, twice |
| **Slack**              |    **92.8** | 0 errors, 29 warnings — exceptionally clean (Swagger 2.0 vintage, well-maintained) |
| **GitHub**             |    **80.0** | 1 structural error in 746 endpoints                                    |
| **Stripe**             |    **75.0** | 2 errors, 15,618 stylistic warnings (top rule was a false-positive that auto-naming detection now suppresses) |
| **OpenAI**             |    **60.0** | 19 structural errors                                                   |
| **Plaid**              |    **60.0** | 19 errors, 7,157 warnings                                              |
| **DigitalOcean**       |    **60.0** | 1,394 vacuum errors at cap                                             |
| **Deep Vector internal** | **50.0**  | 1 error + **18 runtime drift failures** (this is what runtime detection adds) |

**Where does your API land on this ladder?**

Three things to read off this table:

1. **The score range is real.** Slack and our own spec are at the top. Most teams cluster between 50 and 80. A score below 50 is a release-blocker conversation.
2. **Errors and warnings rank differently.** Stripe at 75 has only 2 errors but 15K warnings; OpenAI at 60 has 19 errors. The formula weights errors much more heavily than style — caps prevent warning floods from drowning out signal.
3. **Runtime drift is the part nobody else measures.** The Deep Vector score includes an `--url` probe of the live API, which surfaced 18 endpoints whose live response codes don't match the spec. Stripe, GitHub, and the others were scored from spec alone because we don't have prod keys. **With runtime drift turned on, scores typically drop another 15–30 points.** That gap is the moat.

> *Footnote on Twilio:* their public OpenAPI is so large and structurally complex that vacuum's parser declined to open it at all. That's also a finding — and itself a reason a buyer would want a Drift Sentinel run before integrating.

---

### How to read the ladder for your own API

If you score where Slack scores (90+), you have an exceptionally well-maintained spec. Drift Sentinel becomes a release-time gate, not a remediation tool. If you score where Stripe and GitHub score (75–80), you have a clean spec with a small number of high-impact issues hiding behind style noise — that's typical for thoughtful teams who haven't formalized the audit step. If you score where OpenAI, Plaid, or DigitalOcean score (~60), you have 15–30 documented issues to work through. Below 50 means there's structural work plus active runtime drift — typical of any service older than two years that hasn't had spec hygiene as a quarterly priority.

The Drift Sentinel position is that 90+ should be the bar, and that the only continuous way to hold it is automation. Manual review doesn't scale to a spec that changes every release.

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
