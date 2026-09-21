# Mindstix reachability readiness controller

This is a small namespace-scoped Kubernetes controller for learning. Every 10 seconds it:

1. Calls `https://mindstix.com` from inside its controller Pod.
2. Finds Pods in `k8s-live-demo` labeled `demo.mindstix.io/check-mindstix=true`.
3. Keeps only Pods whose `readinessGates` include `demo.mindstix.io/mindstix-reachable`.
4. Updates that custom Pod condition through the Kubernetes status API.

Kubernetes marks a Pod Ready only when all normal container readiness checks and every readiness-gate condition are `True`. The `web` Service then receives only Ready Pods as endpoints.

## 1. Build and load the controller image into kind

From this directory:

```bash
docker build -t mindstix-readiness-controller:0.1 .
kind load docker-image mindstix-readiness-controller:0.1 --name k8s-live-demo
```

`kind load` is necessary because the image exists on your machine, not in a public container registry.

## 2. Add the gate to the existing web Deployment

```bash
kubectl patch deployment web -n k8s-live-demo --type=strategic \
  --patch-file web-readiness-gate.yaml
kubectl -n k8s-live-demo get pods -w
```

The new web Pods initially show `0/1 Ready`. Kubernetes treats a missing custom readiness condition as `False`.

## 3. Deploy the controller

```bash
kubectl apply -f controller.yaml
kubectl -n k8s-live-demo rollout status deployment/mindstix-readiness-controller
kubectl -n k8s-live-demo logs deployment/mindstix-readiness-controller -f
```

When the HTTP request succeeds, the controller logs a `True` condition update and your web Pods become `1/1 Ready`.

## 4. Observe the result

```bash
kubectl -n k8s-live-demo describe pod -l app=demo-web
kubectl -n k8s-live-demo get endpointslice -l kubernetes.io/service-name=web
```

In the Pod `Conditions` section, look for:

```text
demo.mindstix.io/mindstix-reachable   True
```

The gate is part of overall readiness. If the Redis readiness probe fails, or this custom condition becomes `False`, the Pod is removed from the Service endpoints.

## 5. Demonstrate failure safely

Edit the controller Deployment and set `CHECK_URL` to `https://does-not-exist.invalid`; then apply it:

```bash
kubectl edit deployment mindstix-readiness-controller -n k8s-live-demo
kubectl -n k8s-live-demo rollout status deployment/mindstix-readiness-controller
kubectl -n k8s-live-demo get pods -l app=demo-web -w
```

Within the next polling cycle, the controller changes its condition to `False`; web Pods become `0/1 Ready`, while their NGINX containers keep running. Change the URL back to `https://mindstix.com` to recover.

## What makes this a controller?

This controller has a reconciliation loop: it observes Pods and the external URL, then updates Kubernetes status until each opted-in Pod reflects the latest external reachability result. It needs only namespace-level permissions to list Pods and patch `pods/status`; it cannot create or delete Pods.

For a production controller, add an event watch and work queue, metrics, leader election, retries with backoff, TLS/timeout policy, and use a custom resource definition when users need to configure checks declaratively.
