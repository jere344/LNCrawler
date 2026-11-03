import threading
import time
from types import SimpleNamespace

from worker.main import Health, Heartbeat, Pinger
from worker.pipeline import Progress


class RecordingProd:
    def __init__(self):
        self.pings = []
        self.beats = []

    def ping(self, available, message):
        self.pings.append((available, message))

    def heartbeat(self, part_id, progress, stage, message):
        self.beats.append((part_id, stage))
        return "2026-11-02T03:30:00Z"


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_pinger_starts_and_joins_without_error():
    prod = RecordingProd()
    stop = threading.Event()
    pinger = Pinger(prod, SimpleNamespace(ping_interval_s=0.05), Health(), Progress(), stop)
    pinger.start()
    assert _wait_for(lambda: len(prod.pings) >= 2)
    stop.set()
    pinger.join(timeout=5)  # used to raise TypeError: 'Event' object is not callable
    assert not pinger.is_alive()


def test_heartbeat_starts_and_stops_without_error():
    prod = RecordingProd()
    heartbeat = Heartbeat(prod, "part-1", Progress(), threading.Event(), interval=0.01)
    heartbeat.start()
    assert _wait_for(lambda: len(prod.beats) >= 1)
    heartbeat.stop()
    assert not heartbeat.is_alive()


def test_heartbeat_exits_when_the_part_is_gone():
    class GoneProd(RecordingProd):
        def heartbeat(self, *args):
            from worker.prod import PartGone
            raise PartGone("part-1")

    cancel = threading.Event()
    heartbeat = Heartbeat(GoneProd(), "part-1", Progress(), cancel, interval=0.01)
    heartbeat.start()
    assert _wait_for(cancel.is_set)
    heartbeat.join(timeout=5)
    assert not heartbeat.is_alive()
