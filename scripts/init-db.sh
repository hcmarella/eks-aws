#!/usr/bin/env bash
# Applies app/schema.sql (idempotent: CREATE TABLE IF NOT EXISTS) from a pod inside the cluster, because RDS is private.
set -euo pipefail
env=$1; ns=fraudagent-$env
echo "kubectl context: $(kubectl config current-context)"
kubectl -n "$ns" create configmap schema --from-file=app/schema.sql --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$ns" run db-init --rm -i --restart=Never --image=postgres:16 --overrides='{"spec":{"containers":[{"name":"db-init","image":"postgres:16","command":["sh","-c","psql \"$DATABASE_URL\" -f /s/schema.sql"],"env":[{"name":"DATABASE_URL","valueFrom":{"secretKeyRef":{"name":"fraudagent-db","key":"url"}}}],"volumeMounts":[{"name":"s","mountPath":"/s"}]}],"volumes":[{"name":"s","configMap":{"name":"schema"}}]}}'
