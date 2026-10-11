# Operations runbook (starter)
- Case stuck: check `step_events` for the last step, then `kubectl -n conductor-<env> logs job/agent-<case>-v<n>`. Re-run = delete the Job; ledger resumes from the last completed step.
- Bad release: `git revert` the tag-bump commit, sync in Argo CD.
- Poller lag: check `cdc_watermark` and the CronJob's last run.
- Always `kubectl config current-context` before apply/delete.
