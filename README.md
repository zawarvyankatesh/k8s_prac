# Kubernetes live demo: NGINX + Redis

Use a disposable cluster with `kubectl`, a default StorageClass, and enough resources to run two NGINX Pods and one Redis Pod. The only application images are `nginx:stable-alpine` and `redis:7-alpine`. NGINX serves a small page and reports its Pod hostname; Redis is a separate stateful demonstration. **The web page does not read or write Redis.** This keeps the demo to two images and avoids presenting a fake integrated visit counter.

Run commands from this directory. Namespace is `k8s-live-demo`. Apply the files **in order**, pausing after each. Files 05 and 06 are complete replacements for the `web` Deployment, each carrying forward the previous features. Do not apply the whole directory in one command: the duplicate Deployment manifests are teaching steps.

## 0. Namespace and page

```bash
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-page.yaml
kubectl -n k8s-live-demo get configmap demo-page
```

The ConfigMap supplies HTML and NGINX configuration. `/whoami` returns the container hostname; in a Kubernetes Pod that is its Pod name.

## 1. Deployment and controllers

```bash
kubectl apply -f 02-nginx-deployment.yaml
kubectl -n k8s-live-demo rollout status deployment/web
kubectl -n k8s-live-demo get deploy,replicaset,pods -o wide
kubectl -n k8s-live-demo scale deployment/web --replicas=3
kubectl -n k8s-live-demo get deploy,replicaset,pods -w
```

Stop the watch with Ctrl+C. Then delete *one* web Pod (copy an actual name from the preceding output):

```bash
kubectl -n k8s-live-demo delete pod <web-pod-name>
kubectl -n k8s-live-demo get pods -w
```

Explain: Deployment declares desired state; Deployment controller manages ReplicaSets; ReplicaSet controller replaces a missing Pod. Stop the watch. Return to 2 replicas before the next Deployment file:

```bash
kubectl -n k8s-live-demo scale deployment/web --replicas=2
```

## 2. Service, discovery, and load distribution

```bash
kubectl apply -f 03-web-service.yaml
kubectl -n k8s-live-demo get service web
kubectl -n k8s-live-demo get endpointslice -l kubernetes.io/service-name=web
kubectl -n k8s-live-demo port-forward service/web 8080:80
```

In a second terminal open `http://localhost:8080`. Press **Ask the Service again** several times, or run `for i in 1 2 3 4 5 6 7 8; do curl -s localhost:8080/whoami; done`. Observe Pod names. Distribution can be uneven; `port-forward service/...` chooses one backing Pod for the lifetime of that forwarding session. To demonstrate Service balancing, run this instead from inside the cluster, with each `wget` as a separate connection:

```bash
kubectl -n k8s-live-demo exec deploy/web -- sh -c 'for i in 1 2 3 4 5 6 7 8; do wget -qO- http://web/whoami; done'
```

Note: since the `exec` command runs inside one of the web Pods, it sends requests through Service DNS `web`, which can select either web Pod. Stop port-forward with Ctrl+C when finished.

## 3. StatefulSet, stable identity, and PVC

```bash
kubectl apply -f 04-redis-statefulset.yaml
kubectl -n k8s-live-demo rollout status statefulset/redis
kubectl -n k8s-live-demo get pods,pvc,service -o wide
kubectl -n k8s-live-demo exec redis-0 -- redis-cli SET presenter Vy
kubectl -n k8s-live-demo exec redis-0 -- redis-cli SAVE
kubectl -n k8s-live-demo exec redis-0 -- redis-cli GET presenter
kubectl -n k8s-live-demo delete pod redis-0
kubectl -n k8s-live-demo rollout status statefulset/redis
kubectl -n k8s-live-demo exec redis-0 -- redis-cli GET presenter
```

Expected: `Vy` survives the Pod replacement. Redis returns as `redis-0` with claim `data-redis-0`. The headless Service gives the Pod a stable name `redis-0.redis-headless.k8s-live-demo.svc.cluster.local`. PVC provisioning needs a default StorageClass (or a matching preprovisioned PV). If Redis remains Pending, inspect `kubectl -n k8s-live-demo describe pvc data-redis-0` and `kubectl get storageclass`.

Do not scale this standalone Redis to several replicas: that would create independent Redis instances, not a replicated database. This example has no password and should stay inside a disposable demo cluster.

## 4. Readiness and liveness probes

```bash
kubectl apply -f 05-web-probes.yaml
kubectl -n k8s-live-demo rollout status deployment/web
kubectl -n k8s-live-demo describe pod -l app=demo-web
kubectl -n k8s-live-demo get endpointslice -l kubernetes.io/service-name=web
```

Explain: readiness controls whether a Pod is sent Service traffic; liveness causes kubelet to restart an unhealthy container. Both HTTP probes call `/healthz`. Redis already has a `redis-cli ping` readiness probe. The rollout creates a new ReplicaSet; compare before and after with `kubectl -n k8s-live-demo get rs`.

## 5. Preferred Pod anti-affinity

```bash
kubectl apply -f 06-web-affinity.yaml
kubectl -n k8s-live-demo rollout status deployment/web
kubectl -n k8s-live-demo get pods -l app=demo-web -o wide
kubectl get nodes
```

This is a *preference* to spread web Pods by `kubernetes.io/hostname`, not a hard rule. With multiple worker nodes they usually spread; on a single-node kind cluster they can still run together. The scheduler places new Pods; existing Pods are not automatically moved.

## 6. RBAC

```bash
kubectl apply -f 07-rbac.yaml
kubectl auth can-i list pods -n k8s-live-demo --as=system:serviceaccount:k8s-live-demo:demo-reader
kubectl auth can-i delete pods -n k8s-live-demo --as=system:serviceaccount:k8s-live-demo:demo-reader
kubectl auth can-i list pods -n default --as=system:serviceaccount:k8s-live-demo:demo-reader
```

Expected: `yes`, `no`, `no`. This Role is limited to Pods in the demo namespace. The ServiceAccount exists for authorization testing; the web application does not need Kubernetes API access. Your own kubeconfig needs permission to impersonate a ServiceAccount for `--as` to work.

## 7. Ingress

First verify `kubectl get ingressclass`. This file selects `ingressClassName: nginx`, so an installed and accessible Ingress controller with class `nginx` is required. If your controller uses a different class, change that field. An Ingress resource by itself does **not** install a controller or create an external address.

```bash
kubectl apply -f 08-ingress.yaml
kubectl -n k8s-live-demo describe ingress web
```

Send `Host: demo.local` to the **actual address and port of your Ingress controller**:

```bash
curl -H 'Host: demo.local' http://<controller-address>/whoami
```

If `demo.local` resolves to that controller on your machine, open `http://demo.local/` in a browser. In kind, the controller may need its own installation and host port mapping. If there is no controller during the session, show the manifest and use the Service port-forward from step 2 for the working web page.

## Cleanup

```bash
kubectl delete namespace k8s-live-demo
```

Deleting the namespace deletes its PVC too. The behavior of the backing volume after deletion depends on its StorageClass reclaim policy. This demo is intentionally disposable.

## Presenter flow

`kubectl apply` → API server stores desired state → Deployment/StatefulSet controllers reconcile → scheduler chooses a node → kubelet starts containers → readiness gates Service endpoints → Ingress controller routes incoming HTTP. RBAC controls which API actions an identity may perform; it does not grant web traffic access.

References: [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/), [StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/), [probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/), [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/), [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/), [Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/).
