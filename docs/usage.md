# Drift Sentinel — Usage

This document covers the `driftsentinel` CLI in detail. For the customer-facing pitch, see [README](../README.md). For the demo writeup with the buyer ladder, see [docs/demo.md](demo.md).

## Install

```bash
pip install driftsentinel
```

You also need two Go binaries:

- **vacuum** — `https://github.com/daveshanley/vacuum`
- **oasdiff** — `https://github.com/oasdiff/oasdiff`

Both are single-binary downloads from the project releases page. Drift Sentinel calls them as subprocesses.

## Subcommands

```
driftsentinel keygen [--out PATH]            # generate ed25519 keypair
driftsentinel audit  SPEC [options]          # run the three-tool audit
driftsentinel verify REPORT.pdf [--key PEM]  # verify report signature
```

The CLI is also available as `oas-sentinel` for backward compatibility with pre-rename installs.

## `audit`

```
driftsentinel audit ./openapi.yaml \
    --prev   ./previous-release.yaml      \
    --url    https://api.example.com      \
    --header "Authorization: Bearer ..."  \
    --out    ./audit                      \
    --config ./drift-weights.json         \
    --fail-on "adi=80,breaking=1"
```

| Flag                | Purpose                                                                                |
| ------------------- | -------------------------------------------------------------------------------------- |
| `SPEC` (positional) | Path to OpenAPI 3 spec (JSON or YAML).                                                 |
| `--prev`            | Previous version of the spec. Enables `oasdiff` breaking-change detection.             |
| `--url`             | Base URL for the live API. Enables `schemathesis` runtime-drift testing.               |
| `--header`          | Repeatable. Sent on every schemathesis request (auth, gate keys, etc.).                |
| `--out`             | Output directory for `report.json`, `report.pdf`, `report.sig.json`, and per-tool reports. |
| `--config`          | JSON file overriding default ADI weights and caps (see *Configuration*).               |
| `--fail-on`         | Comma list of `category=N`. Exits 3 if any threshold breached.                         |
| `--key`             | Path stem for the ed25519 keypair. Defaults to `~/.secrets/api-sentinel`.              |
| `--no-auto-naming`  | Disable auto-detection of snake_case vs camelCase. Use the strict default ruleset.     |

### Output

- **`report.json`** — Canonical JSON, sorted keys, the artifact that gets signed.
- **`report.sig.json`** — Detached signature. Contains the ed25519 sig, SHA-256 of `report.json`, and the public key in PEM.
- **`report.pdf`** — Human-readable rendering with the Drift Score, ADI breakdown, per-tool detail, and the signature embedded as the appendix.
- **Per-tool reports** — `<spec>.vacuum.json`, `<spec>.st.xml`. The wrapper consumes these; you can re-read them yourself.

### Exit codes

- `0` — audit completed, no breaches
- `1` — audit failed (subprocess error, missing tool, malformed spec)
- `3` — audit completed but `--fail-on` thresholds breached

## `verify`

```
driftsentinel verify ./audit/report.pdf
```

Reads `report.json` and `report.sig.json` from the same directory, verifies the ed25519 signature, prints `OK: signature valid` and exits 0. Exits 2 with a descriptive message if the signature does not match.

You can pass a different public key with `--key path/to/pubkey.pub` if you don't trust the bundled key.

## `keygen`

```
driftsentinel keygen --out ~/.secrets/api-sentinel
```

Writes `~/.secrets/api-sentinel.key` (PKCS8 PEM, ed25519 private) and `~/.secrets/api-sentinel.pub` (SubjectPublicKeyInfo PEM, public). The audit subcommand auto-generates this pair on first run if absent.

> ⚠️ **Windows note.** Do not run `chmod 0o600` on the private key from Git Bash. Git Bash's POSIX-mode translator strips the owner ACL and bricks the file. Drift Sentinel relies on the parent directory's ACL on Windows.

## ADI formula

```
ADI = max(0, 100 − Σ min(weight × count, cap))
```

Default weights and caps:

| Category       | Weight | Cap | Source        |
| -------------- | -----: | --: | ------------- |
| `breaking`     |     10 |  50 | oasdiff       |
| `vacuum-error` |      5 |  25 | vacuum        |
| `fuzz`         |      3 |  30 | schemathesis  |
| `vacuum-warn`  |   0.25 |  15 | vacuum        |

## Configuration

Override weights or caps with `--config FILE` pointing to JSON:

```json
{
  "weights": {
    "breaking": 15.0,
    "fuzz": 5.0
  },
  "caps": {
    "vacuum-warn": 5.0
  }
}
```

Only specified keys are overridden; everything else stays at defaults.

## CI gating

```bash
driftsentinel audit ./openapi.yaml \
    --prev ./previous.yaml \
    --url https://api.example.com \
    --fail-on "adi=80,breaking=1,fuzz=5"
```

Exits 3 if Drift Score ≤ 80, **or** any breaking changes, **or** more than 5 runtime-drift failures. Compose categories as needed.

In a GitHub Actions step:

```yaml
- name: Drift Sentinel audit
  run: |
    pip install driftsentinel
    driftsentinel audit ./openapi.yaml \
        --prev ./openapi.previous.yaml \
        --fail-on "adi=80,breaking=1"
```

## Library API

Drift Sentinel ships a small public Python API for embedding the score in your own tooling:

```python
import driftsentinel as ds

# Compute a score from raw counts
adi = ds.compute_adi(
    results={
        "oasdiff": {"breaking_count": 0},
        "vacuum": {"by_severity": {"error": 1, "warn": 736}},
        "schemathesis": {"failures": 18},
    },
    **ds.ADI_DEFAULTS,
)

print(adi["score"])  # 50.0
print(adi["counts"])
print(adi["penalties"])
```

`compute_adi` returns a dict with `score`, `counts`, `penalties`, and the `weights`/`caps` actually used.
