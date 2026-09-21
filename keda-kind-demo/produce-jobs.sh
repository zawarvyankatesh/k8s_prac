#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="${NAMESPACE:-keda-demo}"
COUNT="${1:-20}"

if ! [[ "$COUNT" =~ ^[1-9][0-9]*$ ]]; then
  echo "Usage: $0 <positive-job-count>" >&2
  exit 2
fi

if ! "$KUBECTL" get service redis -n "$NAMESPACE" >/dev/null; then
  echo "Redis Service is not available in namespace '$NAMESPACE'. Apply keda-demo.yaml first." >&2
  exit 1
fi

echo "Adding $COUNT jobs to Redis list 'jobs'..."
"$KUBECTL" run queue-producer \
  --namespace "$NAMESPACE" \
  --rm -i \
  --restart=Never \
  --image=redis:7.4-alpine \
  --command -- /bin/sh -c "for i in \$(seq 1 $COUNT); do redis-cli -h redis LPUSH jobs job-\$i >/dev/null; done; redis-cli -h redis LLEN jobs"

echo "Jobs queued. Watch KEDA scale with:"
echo "  $KUBECTL get deploy,pods,hpa,scaledobject -n $NAMESPACE -w"
