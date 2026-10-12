"""Scheduled retraining of a new explicitly approved dataset. Never promotes models."""

import time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from modelforge.storage import state, db, sql, audit
from modelforge.pipelines.train_pipeline import approved_training

while True:
    dataset = state("approved_dataset")
    last = state("last_trained_dataset")
    if dataset and dataset != last:
        try:
            approved_training()
            with db() as conn:
                sql(
                    conn,
                    "INSERT INTO state VALUES (?,?) ON CONFLICT (key) DO UPDATE SET value=excluded.value",
                    ("last_trained_dataset", dataset),
                )
        except Exception as error:
            audit(
                "scheduled_training_failed", {"error": str(error), "dataset": dataset}
            )
    time.sleep(60)
