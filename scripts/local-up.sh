#!/usr/bin/env bash
# Local env: minikube + replay runner. Needs docker, minikube, kubectl, helm.
set -euo pipefail
ctx=$(kubectl config current-context 2>/dev/null || echo none)
echo "kubectl context: $ctx"
minikube start --cpus 4 --memory 8g
[ "$(kubectl config current-context)" = "minikube" ] || { echo "Not on minikube context, aborting"; exit 1; }
eval "$(minikube docker-env)"
docker build -t fraudagent:local .
kubectl create ns fraudagent-local --dry-run=client -o yaml | kubectl apply -f -
kubectl -n fraudagent-local apply -f k8s/local/postgres.yaml
helm upgrade --install fraudagent helm/fraudagent -n fraudagent-local -f helm/fraudagent/values-local.yaml
kubectl -n fraudagent-local get pods
