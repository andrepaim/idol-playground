"""Stage-based, settings-aware ETA for the isolated mesh pipeline."""
import json
import math
import time

STAGES = ('preprocess', 'load', 'reconstruct', 'extract', 'simplify', 'texture', 'export')
BASE = {'preprocess': 8, 'load': 8, 'reconstruct': 4, 'extract': 20, 'simplify': 3, 'texture': 15, 'export': 1}


class MeshProgress:
    def __init__(self, settings, emit, history_path, clock=time.monotonic):
        self.settings, self.emit, self.history_path, self.clock = settings, emit, history_path, clock
        self.started = self.stage_started = clock()
        self.stage = None
        self.step = self.total_steps = None
        self.message = 'Starting mesh generation…'
        self.durations = {}
        self.scale = {stage: 1 for stage in STAGES}
        self.scale['extract'] = (settings['mesh_resolution'] / 192) ** 3
        self.scale['texture'] = (settings['texture_resolution'] / 1024) ** 2
        self.scale['export'] = settings['target_faces'] / 25000
        try:
            raw = json.loads(history_path.read_text())
            self.history = {k: v for k, v in raw.items() if k in STAGES and isinstance(v, (int, float)) and math.isfinite(v) and v > 0}
        except (OSError, ValueError, TypeError, AttributeError):
            self.history = {}
        self.estimates = {stage: self.history.get(stage, BASE[stage]) * self.scale[stage] for stage in STAGES}

    def event(self, event):
        stage = event.get('stage')
        if stage not in STAGES:
            return
        now = self.clock()
        if stage != self.stage:
            if self.stage in STAGES:
                self.durations[self.stage] = now - self.stage_started
            self.stage, self.stage_started = stage, now
            self.step = self.total_steps = None
        self.message = str(event.get('message', self.message))
        step, total = event.get('step'), event.get('total_steps')
        if isinstance(step, int) and isinstance(total, int) and 0 <= step <= total and total > 0:
            self.step, self.total_steps = step, total
            if step > 0:
                self.estimates[stage] = (now - self.stage_started) / step * total
        self.emit(stage=stage, message=self.message, step=self.step, total_steps=self.total_steps,
                  eta_basis='measured' if self.step else 'approximate', **self.snapshot())

    def snapshot(self):
        now = self.clock()
        eta = None
        if self.stage in STAGES:
            eta = max(0, self.estimates[self.stage] - (now - self.stage_started))
            eta += sum(self.estimates[stage] for stage in STAGES[STAGES.index(self.stage) + 1:])
        return {'elapsed_seconds': round(max(0, now - self.started), 1),
                'eta_seconds': None if eta is None else round(eta, 1)}

    def finish(self):
        if self.stage in STAGES:
            self.durations[self.stage] = self.clock() - self.stage_started
        try:
            history = {**self.history, **{stage: .3 * self.history.get(stage, duration / self.scale[stage])
                                         + .7 * duration / self.scale[stage]
                                         for stage, duration in self.durations.items()}}
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.history_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(history, indent=2))
            temporary.replace(self.history_path)
        except OSError:
            pass
        return {'stage_seconds': {stage: round(duration, 3) for stage, duration in self.durations.items()}}
