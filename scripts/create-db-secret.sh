#!/usr/bin/env bash
# Builds the in-cluster secret `conductor-db` from the RDS-managed Secrets Manager secret. Nothing is written to git.
# Usage: scripts/create-db-secret.sh <env> <db_secret_arn> <db_endpoint>
set -euo pipefail
env=$1; arn=$2; host=$3; ns=conductor-$env
echo "kubectl context: $(kubectl config current-context)"; read -r -p "Continue? [y/N] " a; [ "$a" = y ]
sec=$(aws secretsmanager get-secret-value --secret-id "$arn" --query SecretString --output text)
user=$(echo "$sec" | python3 -c 'import sys,json;print(json.load(sys.stdin)["username"])')
pw=$(echo "$sec" | python3 -c 'import sys,json,urllib.parse as u;print(u.quote(json.load(sys.stdin)["password"],safe=""))')
kubectl create ns "$ns" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$ns" create secret generic conductor-db --from-literal=url="postgresql://$user:$pw@$host:5432/postgres?sslmode=require" --dry-run=client -o yaml | kubectl apply -f -
