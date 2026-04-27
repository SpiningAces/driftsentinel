#!/usr/bin/env python3
"""oas-sentinel — vacuum + oasdiff + schemathesis -> ed25519-signed JSON+PDF.

Usage:
  oas-sentinel keygen [--out ~/.secrets/api-sentinel]
  oas-sentinel audit SPEC [--prev PREV] [--url BASE] [--header H] [--out DIR]
  oas-sentinel verify report.pdf [--key PUBKEY.pub]
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import yaml
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization as sz
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted

DEFAULT_KEY = Path.home() / ".secrets" / "api-sentinel"
SEV = {0: "error", 1: "warn", 2: "info", 3: "hint"}

# ADI = API Drift Index. Score 100 = clean spec, 0 = catastrophic drift.
# Each category contributes a penalty bounded by its cap; total clamped to [0,100].
# Override via --config FILE (JSON with "weights" and/or "caps" keys).
ADI_DEFAULTS = {
    "weights": {"breaking": 10.0, "vacuum-error": 5.0, "fuzz": 3.0, "vacuum-warn": 0.25},
    "caps":    {"breaking": 50.0, "vacuum-error": 25.0, "fuzz": 30.0, "vacuum-warn": 15.0},
}


def run(cmd, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, env=env,
                          encoding="utf-8", errors="replace")


def detect_naming(spec: Path) -> str:
    """Inspect schema property + parameter names. Return 'snake', 'camel', or 'unknown'."""
    try:
        text = spec.read_text(encoding="utf-8")
        doc = yaml.safe_load(text) if spec.suffix in (".yaml", ".yml") else json.loads(text)
    except Exception:
        return "unknown"
    snake = camel = 0
    for sch in (doc.get("components", {}).get("schemas") or {}).values():
        for k in (sch.get("properties") or {}).keys() if isinstance(sch, dict) else []:
            if "_" in k and k.islower():
                snake += 1
            elif any(c.isupper() for c in k) and k[0:1].islower():
                camel += 1
    if snake + camel < 10:
        return "unknown"
    return "snake" if snake > camel * 1.5 else "camel" if camel > snake * 1.5 else "unknown"


def vacuum(spec: Path, out_dir: Path, auto_naming: bool = True) -> dict:
    out = out_dir / f"{spec.stem}.vacuum.json"
    naming = detect_naming(spec) if auto_naming else "unknown"
    ruleset = ""
    if naming == "snake":
        ruleset_path = out_dir / "snake-ruleset.yaml"
        ruleset_path.write_text("extends: [[spectral:oas, all]]\nrules:\n  camel-case-properties: off\n",
                                encoding="utf-8")
        ruleset = str(ruleset_path)
    r = run(["vacuum", "spectral-report", "-r", ruleset, str(spec), str(out)])
    if r.returncode not in (0, 1):
        raise RuntimeError(f"vacuum: {r.stderr.strip()}")
    findings = json.loads(out.read_text(encoding="utf-8") or "[]")
    return {
        "tool": "vacuum",
        "total": len(findings),
        "naming": naming,
        "by_severity": dict(Counter(SEV.get(f["severity"], "info") for f in findings)),
        "top_rules": Counter(f["code"] for f in findings).most_common(10),
        "report_path": str(out),
    }


def oasdiff(prev: Path, cur: Path) -> dict:
    r = run(["oasdiff", "breaking", "-f", "json", str(prev), str(cur)])
    try:
        items = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        items = []
    return {
        "tool": "oasdiff",
        "breaking_count": len(items),
        "breaking": [{"id": i.get("id"), "path": i.get("path"),
                      "op": i.get("operation"), "text": i.get("text")} for i in items],
    }


def schemathesis(spec: Path, base_url: str, header: str | None, out_dir: Path) -> dict:
    junit = out_dir / f"{spec.stem}.st.xml"
    cmd = ["schemathesis", "run", "-n", "1", "--include-method", "GET",
           "-u", base_url, "--max-failures", "50", "--warnings", "off",
           "--report-junit-path", str(junit), str(spec)]
    if header:
        cmd += ["-H", header]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    r = run(cmd, env=env)
    text = junit.read_text(encoding="utf-8") if junit.exists() else ""
    return {"tool": "schemathesis", "tests": text.count("<testcase "),
            "failures": text.count("<failure "), "exit_code": r.returncode,
            "report_path": str(junit)}


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_adi_config(path: str | None) -> tuple[dict, dict]:
    weights, caps = dict(ADI_DEFAULTS["weights"]), dict(ADI_DEFAULTS["caps"])
    if path and Path(path).exists():
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        weights.update(loaded.get("weights", {}))
        caps.update(loaded.get("caps", {}))
    return weights, caps


def compute_adi(results: dict, weights: dict, caps: dict) -> dict:
    counts = {
        "breaking":     results.get("oasdiff", {}).get("breaking_count", 0),
        "vacuum-error": results.get("vacuum", {}).get("by_severity", {}).get("error", 0),
        "fuzz":         results.get("schemathesis", {}).get("failures", 0),
        "vacuum-warn":  results.get("vacuum", {}).get("by_severity", {}).get("warn", 0),
    }
    penalties = {k: min(weights[k] * counts[k], caps[k]) for k in counts}
    score = max(0.0, min(100.0, 100.0 - sum(penalties.values())))
    return {"score": round(score, 1), "counts": counts,
            "penalties": {k: round(v, 2) for k, v in penalties.items()},
            "weights": weights, "caps": caps}


def load_or_make_key(stem: Path):
    priv, pub = stem.with_suffix(".key"), stem.with_suffix(".pub")
    if priv.exists():
        sk = sz.load_pem_private_key(priv.read_bytes(), password=None)
    else:
        stem.parent.mkdir(parents=True, exist_ok=True)
        sk = ed25519.Ed25519PrivateKey.generate()
        priv.write_bytes(sk.private_bytes(sz.Encoding.PEM, sz.PrivateFormat.PKCS8,
                                          sz.NoEncryption()))
        pub.write_bytes(sk.public_key().public_bytes(sz.Encoding.PEM,
                                                     sz.PublicFormat.SubjectPublicKeyInfo))
        # Rely on ~/.secrets parent-dir ACL on Windows; chmod 0o600 from
        # Git Bash strips the owner ACL and bricks the key.
    return sk, sk.public_key()


def write_pdf(path: Path, report: dict, sig: dict, pub_pem: bytes):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=LETTER)
    adi = report.get("adi", {})
    story = [Paragraph("API Sentinel Report", styles["Title"]), Spacer(1, 8),
             Paragraph(f"<b>ADI: {adi.get('score', 'n/a')}/100</b>", styles["Heading1"]),
             Paragraph(f"Generated: {report['generated_at']}", styles["Normal"]),
             Paragraph(f"Spec: {report['spec']}", styles["Normal"]),
             Paragraph(f"Host: {report['host']}", styles["Normal"]), Spacer(1, 12),
             Paragraph("ADI Breakdown", styles["Heading2"]),
             Preformatted(json.dumps(adi, indent=2), styles["Code"]), Spacer(1, 8)]
    for tool in ("vacuum", "oasdiff", "schemathesis"):
        if tool in report["results"]:
            story += [Paragraph(tool, styles["Heading2"]),
                      Preformatted(json.dumps(report["results"][tool], indent=2), styles["Code"]),
                      Spacer(1, 8)]
    story += [Paragraph("Signature (ed25519)", styles["Heading2"]),
              Preformatted(json.dumps({"signature": sig, "pubkey_pem": pub_pem.decode()},
                                      indent=2), styles["Code"])]
    doc.build(story)


def cmd_audit(args):
    spec = Path(args.spec).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {"vacuum": vacuum(spec, out_dir, auto_naming=not args.no_auto_naming)}
    if args.prev:
        results["oasdiff"] = oasdiff(Path(args.prev).resolve(), spec)
    if args.url:
        results["schemathesis"] = schemathesis(spec, args.url, args.header, out_dir)
    weights, caps = load_adi_config(args.config)
    adi = compute_adi(results, weights, caps)
    report = {
        "spec": str(spec),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": os.environ.get("COMPUTERNAME") or os.uname().nodename,
        "adi": adi,
        "results": results,
    }
    payload = canonical(report)
    sk, pk = load_or_make_key(Path(args.key))
    sig = {"alg": "ed25519", "sha256": hashlib.sha256(payload).hexdigest(),
           "sig": sk.sign(payload).hex()}
    pub_pem = pk.public_bytes(sz.Encoding.PEM, sz.PublicFormat.SubjectPublicKeyInfo)
    (out_dir / "report.json").write_bytes(payload)
    (out_dir / "report.sig.json").write_text(
        json.dumps({"signature": sig, "pubkey_pem": pub_pem.decode()}, indent=2))
    write_pdf(out_dir / "report.pdf", report, sig, pub_pem)
    summary = {k: {"failures": v.get("failures", v.get("breaking_count",
                   v.get("by_severity", {}).get("error", 0)))} for k, v in results.items()}
    counts = {
        "vacuum-error": results.get("vacuum", {}).get("by_severity", {}).get("error", 0),
        "vacuum-warn": results.get("vacuum", {}).get("by_severity", {}).get("warn", 0),
        "breaking": results.get("oasdiff", {}).get("breaking_count", 0),
        "fuzz": results.get("schemathesis", {}).get("failures", 0),
    }
    breaches = []
    for part in (args.fail_on or "").split(","):
        k, _, v = part.strip().partition("=")
        if not k or not v:
            continue
        if k == "adi":
            if adi["score"] <= float(v):
                breaches.append(f"adi={adi['score']} <= {v}")
        else:
            actual, threshold = counts.get(k, 0), int(v)
            if actual >= threshold:
                breaches.append(f"{k}={actual} >= {threshold}")
    print(json.dumps({"out_dir": str(out_dir), "adi": adi["score"],
                      "summary": summary, "breaches": breaches}, indent=2))
    if breaches:
        sys.exit(3)


def cmd_verify(args):
    pdf = Path(args.pdf).resolve()
    sig_blob = json.loads((pdf.parent / "report.sig.json").read_text())
    payload = (pdf.parent / "report.json").read_bytes()
    pem = Path(args.key).read_bytes() if args.key else sig_blob["pubkey_pem"].encode()
    pk = sz.load_pem_public_key(pem)
    try:
        pk.verify(bytes.fromhex(sig_blob["signature"]["sig"]), payload)
        print("OK: signature valid")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(2)


def cmd_keygen(args):
    load_or_make_key(Path(args.out))
    print(f"keys at {args.out}.key (priv) and {args.out}.pub (pub)")


def main():
    p = argparse.ArgumentParser(prog="oas-sentinel")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit")
    for flag, kw in [("spec", {}), ("--prev", {}), ("--url", {}), ("--header", {}),
                     ("--out", {"default": "./sentinel-out"}),
                     ("--key", {"default": str(DEFAULT_KEY)}),
                     ("--config", {"default": "",
                      "help": "JSON file with override 'weights' and/or 'caps' for ADI."}),
                     ("--fail-on", {"default": "",
                      "help": "comma list of CATEGORY=N (vacuum-error,vacuum-warn,breaking,fuzz,adi). "
                              "Exit 3 if any category >= N (or adi <= N for adi=)."})]:
        a.add_argument(flag, **kw)
    a.add_argument("--no-auto-naming", action="store_true",
                   help="Disable auto-detection of snake_case vs camelCase from spec.")
    a.set_defaults(fn=cmd_audit)
    v = sub.add_parser("verify")
    v.add_argument("pdf")
    v.add_argument("--key")
    v.set_defaults(fn=cmd_verify)
    k = sub.add_parser("keygen")
    k.add_argument("--out", default=str(DEFAULT_KEY))
    k.set_defaults(fn=cmd_keygen)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
