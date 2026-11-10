"""Stage timing and temporary hooks around the pinned Idol pipeline."""

from contextlib import contextmanager
import json
import math
import time

STAGES = ("load", "preprocess", "encode", "sampling", "decode", "save")
MESSAGES = {
    "load": "Loading Idol and its image encoders onto your GPU…",
    "preprocess": "Removing the background and framing your object…",
    "encode": "Analyzing the image's shape, color, and appearance…",
    "sampling": "Generating the 3D structure…",
    "decode": "Building the Gaussian splat and refining its appearance…",
    "save": "Saving the PLY, prepared image, and camera…",
}


class GenerationProgress:
    def __init__(self, settings, emit, history_path, *, cold, optimize=False, clock=time.monotonic):
        self.settings, self.emit, self.history_path, self.clock = settings, emit, history_path, clock
        self.started = self.stage_started = clock()
        self.stage = None
        self.step = 0
        self.durations = {}
        self.profile = ("optimized" if optimize else "eager") + ("_cfg" if settings["cfg_strength"] > 0 else "_plain")
        self.history = {}
        try:
            history = json.loads(history_path.read_text()).get(self.profile, {})
            self.history = {key: value for key, value in history.items()
                            if isinstance(value, (int, float)) and math.isfinite(value) and value > 0}
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        scale = settings["num_gaussians"] / 262144
        self.estimates = {
            "load": self.history.get("load", 12) if cold else 0,
            "preprocess": self.history.get("preprocess", 3),
            "encode": self.history.get("encode", 4),
            "sampling": self.history.get("seconds_per_step", 2.6 if settings["cfg_strength"] > 0 else 1.3) * settings["steps"],
            "decode": self.history.get("decode_base", 4) * scale ** 0.7,
            "save": self.history.get("save_base", 1) * scale,
        }

    def start(self, stage, message=None):
        now = self.clock()
        if self.stage in STAGES and self.stage != stage:
            self.durations[self.stage] = now - self.stage_started
        self.stage, self.stage_started = stage, now
        self.publish(message)

    def sampling_step(self):
        self.step += 1
        self.estimates["sampling"] = (self.clock() - self.stage_started) / self.step * self.settings["steps"]
        self.publish()

    def remaining(self):
        if self.stage not in STAGES:
            return None
        index = STAGES.index(self.stage)
        current = max(0, self.estimates[self.stage] - (self.clock() - self.stage_started))
        return current + sum(self.estimates[s] for s in STAGES[index + 1:])

    def publish(self, message=None):
        self.emit(
            stage=self.stage,
            message=message or MESSAGES.get(self.stage, "Preparing your generation…"),
            step=self.step if self.stage == "sampling" else None,
            total_steps=self.settings["steps"],
            eta_seconds=None if self.remaining() is None else round(self.remaining(), 1),
            eta_basis="measured" if self.step else "approximate",
        )

    def snapshot(self):
        return {"eta_seconds": None if self.remaining() is None else round(self.remaining(), 1),
                "elapsed_seconds": round(max(0, self.clock() - self.started), 1)}

    def finish(self):
        if self.stage in STAGES:
            self.durations[self.stage] = self.clock() - self.stage_started
        scale = self.settings["num_gaussians"] / 262144
        measured = {key: self.durations[key] for key in ("load", "preprocess", "encode") if key in self.durations}
        if "sampling" in self.durations:
            measured["seconds_per_step"] = self.durations["sampling"] / self.settings["steps"]
        if "decode" in self.durations:
            measured["decode_base"] = self.durations["decode"] / scale ** 0.7
        if "save" in self.durations:
            measured["save_base"] = self.durations["save"] / scale
        try:
            all_history = json.loads(self.history_path.read_text()) if self.history_path.exists() else {}
            previous = all_history.get(self.profile, {})
            all_history[self.profile] = {**previous, **{
                key: 0.3 * previous[key] + 0.7 * value if key in previous else value
                for key, value in measured.items()
            }}
            temporary = self.history_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(all_history, indent=2))
            temporary.replace(self.history_path)
        except (OSError, ValueError, TypeError, AttributeError):
            pass  # Timing history must never turn a successful generation into a failure.
        self.stage = "complete"
        return {"stage_seconds": {key: round(value, 3) for key, value in self.durations.items()},
                "sampling_steps_completed": self.step}


@contextmanager
def instrument_pipeline(pipeline, progress, synchronize):
    """Observe existing inference without replacing the SDK's sampling algorithm."""
    original = {name: getattr(pipeline, name) for name in ("preprocess", "image_encoder", "decode")}
    calls = 0
    calls_per_step = 2 if progress.settings["cfg_strength"] > 0 and not pipeline.optimize else 1

    def preprocess(*args, **kwargs):
        progress.start("preprocess")
        result = original["preprocess"](*args, **kwargs)
        synchronize()
        return result

    def encode(*args, **kwargs):
        progress.start("encode")
        result = original["image_encoder"](*args, **kwargs)
        synchronize()
        progress.start("sampling")
        return result

    def after_forward(module, args, result):
        nonlocal calls
        calls += 1
        if calls % calls_per_step == 0:
            synchronize()  # Count completed GPU work, rather than queued kernel launches.
            progress.sampling_step()

    def decode(*args, **kwargs):
        progress.start("decode")
        result = original["decode"](*args, **kwargs)
        synchronize()
        return result

    hook = pipeline.denoiser.register_forward_hook(after_forward)
    pipeline.preprocess, pipeline.image_encoder, pipeline.decode = preprocess, encode, decode
    try:
        yield
    finally:
        hook.remove()
        for name, value in original.items():
            setattr(pipeline, name, value)
