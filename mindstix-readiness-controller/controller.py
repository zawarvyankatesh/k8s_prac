import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from kubernetes import client, config

NAMESPACE = os.getenv("NAMESPACE", "k8s-live-demo")
LABEL_SELECTOR = "demo.mindstix.io/check-mindstix=true"
CONDITION_TYPE = "demo.mindstix.io/mindstix-reachable"
URL = os.getenv("CHECK_URL", "https://mindstix.com")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "10"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def is_reachable():
    """Return whether the target responds successfully to an HTTPS request."""
    request = urllib.request.Request(URL, headers={"User-Agent": "mindstix-readiness-controller/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.status < 400, f"HTTP {response.status} from {URL}"
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code} from {URL}"
    except Exception as error:
        return False, f"Request failed: {error}"


def has_readiness_gate(pod):
    gates = pod.spec.readiness_gates or []
    return any(gate.condition_type == CONDITION_TYPE for gate in gates)


def condition_matches(pod, desired_status, desired_reason):
    for condition in pod.status.conditions or []:
        if condition.type == CONDITION_TYPE:
            return condition.status == desired_status and condition.reason == desired_reason
    return False


def patch_condition(api, pod, ok, message):
    status = "True" if ok else "False"
    reason = "MindstixReachable" if ok else "MindstixUnavailable"

    if condition_matches(pod, status, reason):
        return

    condition = {
        "type": CONDITION_TYPE,
        "status": status,
        "reason": reason,
        "message": message,
        "lastTransitionTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    # A strategic merge patch merges Pod conditions by their `type` field, so
    # this controller changes only its own condition.
    api.patch_namespaced_pod_status(
        name=pod.metadata.name,
        namespace=NAMESPACE,
        body={"status": {"conditions": [condition]}},
    )
    logging.info("%s: %s (%s)", pod.metadata.name, status, message)


def reconcile(api):
    ok, message = is_reachable()
    pods = api.list_namespaced_pod(NAMESPACE, label_selector=LABEL_SELECTOR).items
    for pod in pods:
        if has_readiness_gate(pod):
            patch_condition(api, pod, ok, message)


def main():
    config.load_incluster_config()
    api = client.CoreV1Api()
    logging.info("Starting controller: URL=%s namespace=%s", URL, NAMESPACE)
    while True:
        try:
            reconcile(api)
        except Exception:
            logging.exception("Reconciliation failed")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
