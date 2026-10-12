# Operating the demonstration

Keep all services bound to localhost. The API's administrator token is required for training, dataset approval, promotion, rollback, label ingestion, and drift report generation. Read-only views and predictions are accessible locally. The dashboard holds the token in memory and does not persist it to browser storage.

The MLflow UI is exposed only on localhost. Prometheus scrapes prediction counters and latency histograms; request counts include the model ID. The dashboard's compute latency excludes HTTP transport and database logging. The HTTP load-test report measures the entire request, including logging. Neither measurement represents production throughput or hardware sizing.

Dataset validation rejects missing/extra fields, duplicates, nonfinite values, out-of-range sensors, and class-deficient training sets. A prediction without a champion returns 503. Training errors are recorded in pipeline status; a failed training job never changes the champion. Labels cannot silently overwrite a previously recorded outcome.

Model rollback is explicit. Monitor the prior deployment after rollback; passing historical minimums does not establish that a prior model is suitable for a new distribution. Post-label metrics may be biased if labels arrive selectively.

Before cloud deployment, add identity/authentication for operational reads, rate limits, storage quotas, a durable task queue, distributed promotion locking, model integrity verification, encrypted storage, backups, and operational alerts. A monitoring alert is a proposal to investigate, not proof of model degradation. Public cloud hosting is optional and is not configured in this repository.
