# Measured evaluation

These results come from `reports/demo-results.json`, not example values. The reference dataset contains 4,000 independent simulated sensor observations, with a chronological 2,400/800/800 train/validation/test split. The simulator seed is 42 and test failure prevalence is 0.16375.

The logistic model achieved held-out PR-AUC 0.5800, precision 0.4253, recall 0.7176, F1 0.5341, and Brier score 0.09937. Its confusion matrix is 542 true negatives, 127 false positives, 37 false negatives, and 94 true positives. The baseline's PR-AUC was 0.16375 and its default decision threshold missed all failures; it was rejected by the promotion gate. The random forest's full measurements are retained alongside the logistic and baseline results in the JSON report and registry dashboard.

Thresholds are selected on validation F1 among thresholds meeting validation recall of at least 0.65. Forest depth is selected on validation PR-AUC from two predefined options. Preprocessing uses only training data. Candidate selection uses validation scores after predefined test gates pass; repeated experiments on the same test set should not be used to tune policy thresholds.

The shifted batch contains 1,200 simulated observations (seed 77) with increased temperature and vibration and lower pressure. Three of five input features crossed the predefined PSI/KS drift criteria. Histograms use common ranges and normalize to percentage of records so different batch sizes do not masquerade as distribution changes. PSI retains infinite edge bins so values outside the reference range are counted.

Prediction drift compares the same champion's probability distributions across batches. Delayed-label metrics are reported separately; drift by itself is not proof of performance degradation. Synthetic post-label performance is subject to the same simulation assumptions and should not be extrapolated to real assets.

## Serving measurement

The HTTP load test issued 200 requests at concurrency eight after a separate warm-up. All requests succeeded. This local SQLite run measured p50 31.17 ms, p95 394.71 ms, and throughput 54.76 requests/second. These figures include transport, scheduling, prediction, and database logging. They are different from the dashboard's compute timer, which stops before prediction persistence. Results depend on this workstation, other active services, and SQLite write contention; no cloud performance claim is made.

The raw HTTP measurement is in `reports/load-test.json`. The bootstrap's in-process measurement is explicitly marked as not HTTP latency. Re-run both to assess changes rather than copying these numbers into a production capacity estimate.

## Reproducibility and remaining validation

`python scripts/bootstrap.py` reproduces dataset generation, training, registration, baseline rejection, explicit demo promotion, drift detection, and delayed labels. `python -m pytest -q` checks contract violations, split isolation, invalid evaluation scores, registry/version lineage, protected releases, prediction validation, drift without deployment, and rollback. Browser tests inspect rendered charts, model registry, drift links, prediction lineage, protected label updates, and mobile layout.

This is a single-node portfolio demonstration. Real equipment validation needs a meaningful forecast horizon, asset-level and temporal holdouts, costs for false alarms/missed failures, calibrated decision policy, missing-sensor scenarios, and delayed-label selection analysis. Public hosting and production promotion reconciliation are not implemented.
