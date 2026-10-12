"""Generate a complete measured local demonstration. No real equipment data is used."""

import sys, json, secrets, os, time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from modelforge.config import RUNTIME, ROOT
from modelforge.data.ingest import simulate, save_dataset
from modelforge.training.train import train
from modelforge.registry.promote import promote, gate
from modelforge.monitoring.drift import monitor
from modelforge.storage import models, audit

reference = save_dataset(
    simulate(4000, 42), {"generator": "simulator-v1", "seed": 42, "shifted": False}
)
shifted = save_dataset(
    simulate(1200, 77, True), {"generator": "simulator-v1", "seed": 77, "shifted": True}
)
outputs = train(reference["id"])
baseline = next(m for m in outputs if m["kind"] == "fixed-baseline")
rejected = promote(baseline["id"], approved=True)
print("BASELINE PROMOTION REJECTED:", json.dumps(rejected))
approved = [
    m for m in models() if m["dataset"] == reference["id"] and gate(m)["passed"]
]
if not approved:
    raise RuntimeError(
        "No candidate passed the quality gates. Review the report; do not weaken gates to deploy."
    )
# Choose using validation, never held-out test scores. Bootstrap is an explicit local demo approval.
best = max(approved, key=lambda m: m["validation"]["pr_auc"])
promotion = promote(best["id"], approved=True)
if not promotion["passed"]:
    raise RuntimeError(str(promotion))
drift = monitor(reference["id"], shifted["id"])
from modelforge.serving.main import predict, label
from modelforge.serving.schemas import Reading, Label
from modelforge.config import FEATURES

latencies = []
sample = simulate(100, 199, True)
for _, row in sample.iterrows():
    start = time.perf_counter()
    result = predict(Reading(**row[FEATURES].to_dict()))
    latencies.append((time.perf_counter() - start) * 1000)
    label(Label(prediction_id=result["prediction_id"], failure=int(row.failure)))
from modelforge.monitoring.performance import performance
from modelforge.storage import state

report = {
    "dataset": reference,
    "shifted_dataset": shifted,
    "models": outputs,
    "champion": best["id"],
    "gate_rejection": rejected,
    "promotion": promotion,
    "drift": drift,
    "delayed_labels": performance(best["id"]),
    "http_latency_measured": False,
    "measured_inprocess_full_call_p95_ms": sorted(latencies)[
        int((len(latencies) - 1) * 0.95)
    ],
    "note": "Synthetic local smoke benchmark; not a real-world equipment forecast.",
}
(root / "reports").mkdir(exist_ok=True)
(root / "reports/demo-results.json").write_text(json.dumps(report, indent=2))
(RUNTIME / "demo-results.json").write_text(json.dumps(report, indent=2))
(RUNTIME / "admin-token.txt").write_text(secrets.token_urlsafe(32))
print(
    json.dumps(
        {
            "champion": best["kind"],
            "version": best["registry_version"],
            "metrics": best["metrics"],
            "drift_detected": drift["drift_detected"],
            "report": "reports/demo-results.json",
        },
        indent=2,
    )
)
print("Administrator token saved privately to runtime/admin-token.txt (not printed).")
