#!/usr/bin/env bash
# Usage: scripts/promote.sh <dev|qa|prod> <git-sha>   -> edits values file; open a PR with the result.
set -euo pipefail
env=$1; sha=$2; f=helm/conductor/values-$env.yaml
sed -i -E "s|^(\s*tag:).*|\1 \"$sha\"|" "$f"
git diff --stat "$f"
