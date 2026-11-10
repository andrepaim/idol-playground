from types import SimpleNamespace

import pytest

from progress import GenerationProgress, instrument_pipeline


class Clock:
    value = 0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def tracker(tmp_path, clock, events, **settings):
    return GenerationProgress(
        {"steps": 4, "num_gaussians": 262144, "cfg_strength": 3, **settings},
        lambda **event: events.append(event), tmp_path / "timings.json", cold=False, clock=clock,
    )


def test_eta_uses_completed_step_times_and_includes_remaining_stages(tmp_path):
    clock, events = Clock(), []
    progress = tracker(tmp_path, clock, events)
    progress.start("sampling")
    clock.advance(2)
    progress.sampling_step()
    assert events[-1]["eta_basis"] == "measured"
    assert events[-1]["eta_seconds"] == 11  # Three 2s steps, 4s decoding, 1s save.
    clock.advance(2)
    progress.sampling_step()
    assert events[-1]["eta_seconds"] == 9
    clock.advance(100)
    assert progress.snapshot()["eta_seconds"] == 5  # Never subtract time from work still ahead.
    progress.start("download")
    assert progress.snapshot()["eta_seconds"] is None


def test_successful_run_calibrates_future_estimates_for_step_and_gaussian_counts(tmp_path):
    clock, events = Clock(), []
    progress = tracker(tmp_path, clock, events)
    progress.start("sampling")
    clock.advance(8)
    progress.start("decode")
    clock.advance(4)
    progress.start("save")
    clock.advance(1)
    progress.finish()
    subsequent = tracker(tmp_path, clock, [], steps=10, num_gaussians=524288)
    subsequent.start("sampling")
    assert subsequent.estimates["sampling"] == 20
    assert subsequent.estimates["save"] == 2
    assert subsequent.estimates["decode"] == pytest.approx(4 * 2 ** 0.7)


@pytest.mark.parametrize("corrupt", ['[]', '{"eager_cfg":{"seconds_per_step":"oops"}}', 'broken'])
def test_bad_timing_cache_does_not_block_generation(tmp_path, corrupt):
    (tmp_path / "timings.json").write_text(corrupt)
    progress = tracker(tmp_path, Clock(), [])
    progress.start("sampling")
    assert progress.remaining() > 0


@pytest.mark.parametrize("cfg,optimize,passes", [(3, False, 2), (3, True, 1), (0, False, 1)])
def test_real_module_hooks_count_complete_sampling_steps_and_restore_pipeline(tmp_path, cfg, optimize, passes):
    import torch
    clock, events = Clock(), []
    progress = tracker(tmp_path, clock, events, cfg_strength=cfg)

    class Denoiser(torch.nn.Module):
        def forward(self, value):
            clock.advance(0.5)
            return value

    model = SimpleNamespace(
        optimize=optimize, denoiser=Denoiser(), preprocess=lambda x: x,
        image_encoder=lambda x: x, decode=lambda x: x,
    )
    original = (model.preprocess, model.image_encoder, model.decode)
    with instrument_pipeline(model, progress, lambda: None):
        value = model.image_encoder(model.preprocess("image"))
        for _ in range(4):
            for _ in range(passes):
                value = model.denoiser(value)
        assert model.decode(value) == "image"
    observed = [event["step"] for event in events if event["stage"] == "sampling"]
    assert observed == [0, 1, 2, 3, 4]
    assert len(model.denoiser._forward_hooks) == 0
    assert (model.preprocess, model.image_encoder, model.decode) == original
    with pytest.raises(RuntimeError, match="inference failed"):
        with instrument_pipeline(model, progress, lambda: None):
            raise RuntimeError("inference failed")
    assert len(model.denoiser._forward_hooks) == 0
    assert (model.preprocess, model.image_encoder, model.decode) == original
