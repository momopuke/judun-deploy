"""Read an active signed staging request and attest its live identity twice."""
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_oidc_client as oidc
import staging_deploy_request as agent
import feature_gate_policy as feature_policy
import feature_evidence as feature_evidence


def signed_target(commit):
    prefix = f"{commit}/staging/candidate"
    with TemporaryDirectory() as directory:
        _, target, _ = agent.signed_candidate(
            agent.fetch(prefix + ".json", 8192),
            agent.fetch(prefix + ".json.sig.b64", 1024),
            Path(directory), Path("keys/release_signing_public.pem"),
        )
    return {
        "target_artifact_id": target.artifact_id,
        "target_build_instance_id": target.build_instance_id,
        "expected_display_version": "v" + target.version,
        "expected_source_tree_sha256": target.source_tree_sha256,
        "expected_managed_file_count": target.file_count,
    }


def feature_readback(target, first, second, native):
    pending = {"feature_qa_status": "PENDING", "feature_receipt_sha256": "",
               "feature_plan_sha256": ""}
    try:
        if not (isinstance(first, list) and isinstance(second, list)
                and len(first) == len(second) == 2
                and native.get("native_qa_status") == "PASS"):
            return pending, []
        proof = {
            "identity": feature_policy.target_identity(target),
            "native_receipt_sha256": native["native_qa_receipt_sha256"],
            "plan_sha256": first[0]["feature_plan_sha256"],
            "feature_receipt_sha256": first[0]["feature_receipt_sha256"],
            "feature_qa_status": "EVIDENCE_READY_NOT_RELEASE_APPROVAL",
        }
        a = feature_evidence.stable_attestation(first[0], first[1], proof)
        b = feature_evidence.stable_attestation(second[0], second[1], proof)
        if a != b:
            return pending, []
        # Export only the exact fields needed for independent verification.
        fields = ("status", "manifest_status", "payment_mode", "version",
                  "artifact_id", "build_instance_id", "source_tree_sha256",
                  "native_qa_status", "native_qa_receipt_sha256", "native_qa_file_count",
                  "feature_qa_status", "feature_receipt_sha256", "feature_plan_sha256")
        return a, [{k: x[k] for k in fields} for x in (first[0], second[-1])]
    except (KeyError, ValueError, TypeError, AttributeError):
        return pending, []


def attest(commit):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Invalid staging commit")
    target = signed_target(commit)
    deadline = time.monotonic() + 480
    gateway_denials = 0
    while True:
        try:
            first = oidc.verify_candidate(target, include_native_qa=True, include_feature_qa=True)
            break
        except oidc.Denied:
            raise
        except HTTPError as error:
            if error.code == 403:
                # The health gateway also returns 403 when the local staging
                # process is restarting. Require a successful read after it.
                health_urls = {oidc.GATEWAY + oidc.PREFIX + path for path in oidc.PATHS}
                gateway_denials += 1
                if error.geturl() not in health_urls or gateway_denials >= 3:
                    raise
            if error.code == 401 or time.monotonic() >= deadline:
                raise
            time.sleep(15)
        except (ValueError, URLError, TimeoutError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError("Staging did not reach the signed target before timeout") from error
            time.sleep(15)

    started = time.monotonic()
    first_at = time.time()
    time.sleep(65)
    second = oidc.verify_candidate(target, include_native_qa=True, include_feature_qa=True)
    elapsed = time.monotonic() - started
    first_features, second_features = first.pop("feature_qa_builds", []), second.pop("feature_qa_builds", [])
    first_qa, second_qa = first.pop("native_qa"), second.pop("native_qa")
    native_qa = first_qa if first_qa == second_qa else oidc.native_qa_summary({}, target["expected_managed_file_count"])
    feature_qa, feature_builds = feature_readback(target, first_features, second_features, native_qa)
    if first != second or elapsed < 60:
        raise ValueError("Staging identities or interval do not match")
    if agent.request_commit(agent.fetch) != commit:
        raise ValueError("The staging request was superseded")
    receipt = {
        "schema": "judun.staging-request-readback.v1",
        "result": "PASS", "candidate_commit": commit, "run_id": os.environ["GITHUB_RUN_ID"],
        "first_at_epoch": first_at, "second_at_epoch": time.time(),
        "observed_seconds": round(elapsed, 3), "first": first, "second": second,
        "native_qa": native_qa, "native_qa_first": first_qa, "native_qa_second": second_qa,
        "feature_qa": feature_qa, "feature_qa_builds": feature_builds,
    }
    encoded = json.dumps(receipt, sort_keys=True)
    (Path(os.environ["RUNNER_TEMP"]) / "judun-staging-readback.json").write_text(encoded + "\n")
    print(encoded, flush=True)


if __name__ == "__main__":
    attest(sys.argv[1])
