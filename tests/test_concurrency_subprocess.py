import multiprocessing
import time

from langcampaign.learners import exclusive_file_lock


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
