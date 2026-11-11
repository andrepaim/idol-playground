# Bounded anatomy proposal contract

Status: isolated M3.2 foundation. No provider is registered, no external request is made, and the [manual character workflow](character-workflow.md) remains the available route. This module is not integrated into the API, UI, stage acceptance or model workers. It does not complete M3 or the [routing evaluation](image-to-playable-validation.md).

## Inputs and proposals

`anatomy_reasoning.View` accepts a safe local view identifier and still PNG/JPEG/WebP bytes. Each input is at most 5 MiB, with both dimensions between 16 and 1024 pixels. It applies EXIF orientation, decodes the image and reencodes RGBA PNG with metadata cleared. It does not crop, resample, segment or convert ICC color profiles. Original caller bytes remain the caller's responsibility; both incoming and normalized hashes are available for lineage. Image bytes are excluded from object representations.

A frozen `Request` contains one to four views with distinct identifiers and at most 10 MiB of normalized image bytes. It supplies a fixed directive treating image text as untrusted evidence and allowing only a structured proposal. There is no user-controlled tool, command, path or prompt field.

The closed `anatomy-proposal-v1` schema bounds body plan, species, front axis, three suitability flags, finite confidence, evidence and uncertainty. Evidence must reference a supplied view identifier. Unknown fields, malformed/deep JSON, duplicate fields, oversized responses, unknown views and invalid numerical values are refused. Nested evidence and proposal collections are immutable after validation.

Body plan and species are distinct: a dog-like head on a two-legged humanoid may propose biped anatomy. No taxonomy lookup forces an anthropomorphic animal onto quadruped motion. Proposal evidence can describe hidden or conflicting anatomy; its correctness still needs evaluation and review.

Version 1 does not carry calibrated camera transforms or infer physical scale. Front-axis proposals therefore remain unverified; canonical-frame evidence and the existing manual scale/orientation fields must be resolved before downstream integration. Suitability values include uncertainty and are not silently converted into confirmed manual booleans.

Every valid proposal returns `review`, including confidence 1.0 with all suitability flags positive. Confidence is uncalibrated provider output. It never accepts a stage, selects an animation or executes code. Response text remains untrusted data. Contract tests that reject structured tool fields do not establish a real LLM's resistance to image prompt injection.

Without a provider:

```python
from anatomy_reasoning import Request, Session, View

request = Request((View("front", prepared_png_bytes),))
result = await Session().assess(request)
assert result.outcome == "manual"
```

## Calls, deadlines and cancellation

A provider is trusted, code-defined asynchronous Python implementing `propose(request) -> bytes`. No network/vendor implementation, credentials, account configuration or provider selection is included. A future adapter needs separate data-transfer/provider decisions and actual evaluation before integration.

Default session limits are one call, 15 seconds per call, 30 elapsed seconds from the first attempt and 64 KiB response bytes. Code-defined limits cannot exceed four calls, 60 seconds per call, 120 total seconds or 64 KiB per response. Failures and malformed responses consume a call. No automatic retry occurs; time between calls also consumes the total elapsed budget.

Each session belongs to one persistent event loop. A running call excludes a replacement. Timeout or caller cancellation requests provider-task cancellation; it does not establish that the task stopped. If cancellation is suppressed, the active guard remains until actual completion. `await session.close(grace=...)` closes admission, requests cancellation if needed, waits at most a bounded grace and returns whether the task has finished. A false result must be handled as pending work; closing does not reset the budget or launch another call.

Deadline checks also reject a result arriving after an event-loop stall. They cannot preempt synchronous blocking Python or arbitrary vendor work. Providers must cooperate with cancellation and avoid blocking the event loop. The guard tracks the coroutine, not unvalidated SDK threads, subprocesses or outstanding vendor requests. A real adapter must prove its underlying lifecycle and apply its own transport/token/billing limits. A call-count limit is not a dollar-cost guarantee.

Outcomes are `manual`, `review`, `invalid_response`, `provider_failed`, `budget_exhausted`, `timeout`, `busy` and `closed`. Errors expose stable outcome codes rather than private provider exception text. No logs or persistence are written.

## Validation scope

Meaningful tests first failed on the missing module. Review then produced failing regressions for deep JSON, late results after a blocked event loop and EXIF orientation; those failures were fixed. Fake providers establish manual fallback, mandatory review, evidence/schema rejection, byte/call/deadline limits, failure accounting, cancellation-resistant exclusion, explicit close and caller-cancellation ownership. Actual image decoding checks metadata removal, still-frame requirements and combined normalized byte limits.

This is data/async logic with no CUDA, model lifecycle, storage, API or UI changes. Repository Python/infrastructure, lint/docs/whitespace, relevant JavaScript checks, author review, current-main integration and required CI apply. Browser CI remains regression evidence for the existing app, not evidence of an enabled AI assessment flow. Actual provider accuracy, annotation comparison, latency/cost, contradictory-view routing and held-out anatomy evaluation remain untested. No external service or owner input is used by these tests.
