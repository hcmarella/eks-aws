"""Turns case_outbox rows into Kubernetes Jobs. job_spec() is pure and unit-tested; the cluster calls are NOT tested here."""
import os, time


def job_spec(case_id: str, data_version: int, image: str, namespace: str, sa: str = "agent-sa") -> dict:
    name = f"agent-{case_id}-v{data_version}".lower().replace("_", "-")[:63]
    return {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": name, "namespace": namespace, "labels": {"app": "agent-job", "case": case_id}},
        "spec": {
            "backoffLimit": 1, "activeDeadlineSeconds": 6 * 3600, "ttlSecondsAfterFinished": 86400,
            "template": {"spec": {
                "serviceAccountName": sa, "restartPolicy": "Never",
                "securityContext": {"runAsNonRoot": True, "runAsUser": 10001},
                "containers": [{"name": "agent", "image": image,
                                "command": ["python", "cli.py", "--case", case_id],
                                "securityContext": {"readOnlyRootFilesystem": True, "allowPrivilegeEscalation": False},
                                "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}, "limits": {"cpu": "2", "memory": "4Gi"}}}],
            }},
        },
    }


def main():  # pragma: no cover - needs cluster + DB
    import psycopg
    from kubernetes import client, config
    config.load_incluster_config()
    batch = client.BatchV1Api()
    ns, image = os.environ["NAMESPACE"], os.environ["AGENT_IMAGE"]
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as db:
        while True:
            rows = db.execute("UPDATE case_outbox SET status='dispatched' WHERE (case_id,data_version) IN "
                              "(SELECT case_id,data_version FROM case_outbox WHERE status='new' LIMIT 10 FOR UPDATE SKIP LOCKED) "
                              "RETURNING case_id,data_version").fetchall()
            for cid, ver in rows:
                batch.create_namespaced_job(ns, job_spec(cid, ver, image, ns))
            time.sleep(15)


if __name__ == "__main__":
    main()
