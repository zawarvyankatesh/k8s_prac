# KEDA Redis queue lab for kind

This lab demonstrates event-driven scaling. A Redis List named `jobs` is the event source; KEDA scales the `queue-worker` Deployment from zero to five replicas based on the queue length.

## What KEDA adds

KEDA installs an operator, metrics API adapter, admission webhook, and CRDs such as `ScaledObject`.

```text
Redis jobs queue → KEDA operator → KEDA external metric → generated HPA → queue-worker replicas
```

The `ScaledObject` in this lab says:

- `scaleTargetRef.name: queue-worker`: KEDA controls this Deployment's replica count.
- `minReplicaCount: 0`: workers are allowed to become zero.
- `maxReplicaCount: 5`: never create more than five workers.
- `pollingInterval: 5`: KEDA checks Redis every five seconds when scaling from zero.
- `listLength: "5"`: aim for roughly five queued jobs per worker.
- `activationListLength: "0"`: one or more jobs activates workers from zero.
- `cooldownPeriod: 20`: after work finishes, wait before allowing a scale-to-zero decision.

With 20 queued jobs, KEDA/HPA should request around four workers, subject to HPA timing and the max of five.

## Install KEDA once per cluster

Use the normal admin context, not `demo-reader-context`.

```bash
kubectl config use-context kind-k8s-live-demo

helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm upgrade --install keda kedacore/keda --namespace keda --create-namespace

kubectl get pods -n keda
kubectl get crd | grep keda
```

## Run the demo

```bash
kubectl apply -f keda-demo.yaml
kubectl get deploy,pods,scaledobject,hpa -n keda-demo -w
```

Initially, expect:

```text
redis          1/1
queue-worker   0/0
```

In another terminal:

```bash
chmod +x produce-jobs.sh
./produce-jobs.sh 20
```

KEDA detects the queued jobs, creates or updates an HPA for `queue-worker`, and scales the Deployment up. The worker Pods each remove a Redis job and deliberately take five seconds to process it, making scaling observable.

Inspect the decision:

```bash
kubectl get scaledobject redis-queue-worker -n keda-demo
kubectl get hpa -n keda-demo
kubectl describe scaledobject redis-queue-worker -n keda-demo
kubectl logs -n keda-demo -l app=queue-worker --prefix --tail=50
```

After the queue drains and the cooldown/HPA scale-down timing passes, workers return to zero.

## Important differences from HPA

| HPA alone | KEDA |
| --- | --- |
| Usually scales on CPU/memory or a separately exposed custom metric. | Natively understands event sources such as Redis, Kafka, SQS, Prometheus, and Cron. |
| Typically cannot wake a Deployment from zero using CPU, because zero Pods produce no CPU metric. | Detects events externally and can activate a Deployment from zero. |
| You manage the HPA directly. | You define a `ScaledObject`; KEDA creates/manages the HPA. |

Do not create another HPA for `queue-worker`; two autoscalers would fight over the same `replicas` field.

## Production concerns

1. Make workers idempotent. Retried messages must not cause duplicate side effects.
2. Use a durable queue and a dead-letter strategy; this Redis is intentionally ephemeral for a lab.
3. Set resource requests and limits so node capacity constrains scaling safely.
4. Use authentication and TLS for real Redis/Kafka/SQS endpoints. KEDA supports trigger authentication resources and provider workload identity.
5. Tune activation threshold, target queue length, polling, cooldown, and max replicas from real throughput measurements.

## Cleanup

```bash
kubectl delete namespace keda-demo
helm uninstall keda -n keda
kubectl delete namespace keda
```

Only uninstall KEDA when no other workload in the cluster uses it.
