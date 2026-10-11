# Using this repo as the template for a new agent
1. Copy the repo; rename `conductor` in chart name, ECR repo, namespaces, Terraform locals.
2. Replace `app/pipeline/stages.py` bodies and `config/pipeline.yaml`; keep ledger-first writes and capped loops.
3. Keep `MODEL_RUNNER` injection so tests run on replay with no model.
4. Fill the access sheet, then follow README "Moving to AWS".
