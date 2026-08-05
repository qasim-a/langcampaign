import multiprocessing
import json
import time
from uuid import uuid4

from langcampaign.learners import exclusive_file_lock
from langcampaign.profile import load_or_create_profile
from langcampaign.protocol import decode_request, dispatch
from langcampaign.receipts import execute_idempotent
from tests.fixtures import mission_content_payload, setup_payload


def _hold(path, entered, release):
    descriptor = __import__("os").open(path, __import__("os").O_RDWR | __import__("os").O_CREAT, 0o600)
    try:
        with exclusive_file_lock(descriptor):
            entered.set()
            release.wait(5)
    finally:
        __import__("os").close(descriptor)


def _enter(path, entered):
    descriptor = __import__("os").open(path, __import__("os").O_RDWR | __import__("os").O_CREAT, 0o600)
    try:
        with exclusive_file_lock(descriptor):
            entered.set()
    finally:
        __import__("os").close(descriptor)


def _idempotent_mutation(root, operation_id, start):
    start.wait(5)

    def action():
        with open(__import__("pathlib").Path(root) / "domain-count.txt", "a", encoding="utf-8") as stream:
            stream.write("mutation\n")
        return {"success": True, "data": {"revision": 1}}

    execute_idempotent(__import__("pathlib").Path(root), operation_id, "pause", {"campaign_id": "a"}, action)


def _protocol_call(root, operation, input_data, operation_id=None):
    root = __import__("pathlib").Path(root)
    profile = load_or_create_profile(root)
    request = decode_request(json.dumps({
        "protocol_version": 1, "operation": operation,
        "operation_id": operation_id, "input": input_data,
    }).encode())
    action = lambda: dispatch(request, root / "learners", profile.learner_id)
    return execute_idempotent(root, operation_id, operation, input_data, action) if request.mutation else action()


def _assessment_process(root, input_data, operation_id, start, results):
    start.wait(5)
    try:
        results.put(_protocol_call(root, "submit-assessment", input_data, operation_id))
    except Exception as error:
        results.put({"error": type(error).__name__})


def test_exclusive_file_lock_serializes_real_processes(tmp_path):
    lock = tmp_path / "cross-process.lock"
    first_entered = multiprocessing.Event()
    release = multiprocessing.Event()
    second_entered = multiprocessing.Event()
    first = multiprocessing.Process(target=_hold, args=(lock, first_entered, release))
    second = multiprocessing.Process(target=_enter, args=(lock, second_entered))
    first.start()
    assert first_entered.wait(3)
    second.start()
    time.sleep(0.1)
    assert not second_entered.is_set()
    release.set()
    first.join(3)
    second.join(3)
    assert first.exitcode == 0
    assert second.exitcode == 0
    assert second_entered.is_set()


def test_duplicate_operation_mutates_once_across_real_processes(tmp_path):
    start = multiprocessing.Event()
    operation_id = "8d626be1-4a80-4426-b06e-d17fb3f9bb19"
    processes = [
        multiprocessing.Process(target=_idempotent_mutation, args=(tmp_path, operation_id, start))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(5)
        assert process.exitcode == 0
    assert (tmp_path / "domain-count.txt").read_text().splitlines() == ["mutation"]


def test_duplicate_assessment_is_one_domain_mutation_across_processes(tmp_path):
    setup = setup_payload()
    setup.pop("learner_id")
    setup["campaign"]["id"] = "campaign-a"
    setup["first_content"] = mission_content_payload()
    _protocol_call(tmp_path, "setup", setup, str(uuid4()))
    revision = 0
    for _ in range(2):
        response = _protocol_call(tmp_path, "advance-mission", {
            "campaign_id": "campaign-a", "mission_id": "delayed-arrival",
            "attempt_number": 1, "expected_revision": revision,
        }, str(uuid4()))
        revision = response["data"]["revision"]
    assessment = {
        "campaign_id": "campaign-a", "mission_id": "delayed-arrival",
        "attempt_number": 1, "expected_revision": revision,
        "criterion_scores": [{"criterion_id": "delay", "score": 80}, {"criterion_id": "time", "score": 80}],
        "independent": True, "modality": "text", "result_statement": "Independent response",
    }
    operation_id = str(uuid4())
    start, results = multiprocessing.Event(), multiprocessing.Queue()
    processes = [multiprocessing.Process(target=_assessment_process, args=(tmp_path, assessment, operation_id, start, results)) for _ in range(2)]
    for process in processes: process.start()
    start.set()
    for process in processes:
        process.join(5)
        assert process.exitcode == 0
    responses = [results.get(timeout=2) for _ in processes]
    assert all(response.get("success") is True for response in responses)
    assert {response["data"]["revision"] for response in responses} == {revision + 1}
