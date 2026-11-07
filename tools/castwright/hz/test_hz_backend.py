"""
Tests for HzBackend.synth_batch when a batch item comes back with no audio.

hz itself is stubbed (no GPU, no model): the batch and retry runners return canned results.
Run from this directory: python -m pytest test_hz_backend.py
"""
import types

import numpy as np
import pytest

import hz_backend as hb

VOICE = object()
TEXT = "Ample Time: Night Ten is still a student and has no real life experience."

_api = types.SimpleNamespace(
    TTSConfig=lambda max_steps, streaming: types.SimpleNamespace(max_steps=max_steps),
    map_language=lambda name: name,
    BatchRunner=None,
)


class _Runner:
    """Returns one canned clone_batch result list per call, in order."""

    def __init__(self, *returns):
        self.prompt_builder = types.SimpleNamespace(
            build_clone_prompt=lambda text, voice, lang, flag: types.SimpleNamespace(
                embd=np.zeros((1, 20))))
        self._returns = list(returns)
        self.calls = []

    def clone_batch(self, tasks):
        self.calls.append(tasks)
        return self._returns.pop(0)


def _result(frames, audio):
    return types.SimpleNamespace(codes=[0] * frames, audio=np.asarray(audio, dtype=np.float32))


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setattr(hb, "_import_hz", lambda: _api)
    b = hb.HzBackend()
    b._engine = object()
    return b


def test_empty_item_is_rerendered_alone(backend):
    empty = _result(0, [])
    good = _result(40, np.ones(960))
    batch = _Runner([empty, good])
    retry = _Runner([_result(40, np.full(960, 0.5))])
    backend._runner = batch
    backend._retry_runner = retry

    wavs, sr = backend.synth_batch([(TEXT, VOICE, "english"), ("Second line.", VOICE, "english")])

    assert sr == hb.SAMPLE_RATE
    assert len(batch.calls) == 1
    assert len(retry.calls) == 1
    assert retry.calls[0][0][0] == TEXT
    assert np.allclose(wavs[0], 0.5)
    assert np.allclose(wavs[1], 1.0)


def test_empty_item_still_empty_after_retry_raises(backend):
    batch = _Runner([_result(0, [])])
    retry = _Runner([_result(0, [])])
    backend._runner = batch
    backend._retry_runner = retry

    with pytest.raises(RuntimeError, match="hz produced no audio for batch item 0") as exc:
        backend.synth_batch([(TEXT, VOICE, "english")])

    msg = str(exc.value)
    assert f"({len(TEXT)} chars)" in msg
    assert repr(TEXT[:60]) in msg
    assert len(retry.calls) == 1


def test_unspeakable_fragment_becomes_a_short_pause(backend):
    backend._runner = _Runner([_result(0, []), _result(40, np.ones(960))])
    backend._retry_runner = _Runner([_result(0, [])])

    wavs, sr = backend.synth_batch([("T", VOICE, "english"), ("Second line.", VOICE, "english")])

    assert len(wavs[0]) == int(sr * hb.SILENT_PAUSE_S)
    assert not wavs[0].any()
    assert len(wavs[1]) == 960
