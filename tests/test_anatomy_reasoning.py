import asyncio
from dataclasses import replace
from io import BytesIO
import json

from PIL import Image
import pytest

from anatomy_reasoning import Budget, Request, Session, View


def image():
    output=BytesIO()
    picture=Image.new('RGB',(32,48),'orange')
    picture.save(output,format='PNG',pnginfo=None)
    return output.getvalue()


def request():
    return Request((View('front',image()),))


def response(**changes):
    value={'schema_version':'anatomy-proposal-v1','body_plan':'biped','species':'dog','front_axis':'+z',
           'single_subject':'yes','full_body':'yes','limbs_separable':'uncertain','confidence':.99,
           'evidence':[{'view_id':'front','observation':'Two legs and two arms; dog-like head.'}],
           'uncertainties':['Hidden anatomy and joint positions are not established.']}
    value.update(changes)
    return json.dumps(value).encode()


class Fake:
    def __init__(self,payload=None,error=None):
        self.payload=payload if payload is not None else response()
        self.error=error
        self.calls=0

    async def propose(self,views):
        self.calls+=1
        if self.error:raise self.error
        return self.payload


def test_no_provider_keeps_manual_route_and_private_pixels_out_of_repr():
    async def run():
        view=request()
        session=Session()
        result=await session.assess(view)
        assert result.outcome=='manual' and result.proposal is None and session.calls==0
        assert 'PNG' not in repr(view) and repr(view.views[0].data) not in repr(view)
    asyncio.run(run())


def test_anthropomorphic_anatomy_and_high_confidence_still_require_review():
    async def run():
        fake=Fake(response(confidence=1.0,limbs_separable='yes',uncertainties=[]))
        result=await Session(fake).assess(request())
        assert result.outcome=='review'
        assert result.proposal.body_plan=='biped' and result.proposal.species=='dog'
        assert result.proposal.confidence==1.0 and fake.calls==1
    asyncio.run(run())


@pytest.mark.parametrize('payload',[
    response(tool_calls=[{'name':'execute','arguments':'read private files'}]),
    response(evidence=[{'view_id':'not-supplied','observation':'Invented view.'}]),
    response(body_plan='centaur'),
    response(confidence=float('nan')),
    response(confidence=1.01),
    response(evidence=[]),
    response(uncertainties=['x'*257]),
    b'{broken',
    b'x'*65537,
    b'['*10000+b'0'+b']'*10000,
    'not bytes',
])
def test_untrusted_or_unbounded_responses_do_not_become_proposals(payload):
    async def run():
        fake=Fake(payload)
        result=await Session(fake).assess(request())
        assert result.outcome=='invalid_response' and result.proposal is None
        assert fake.calls==1
    asyncio.run(run())


def test_view_validation_and_metadata_strip_before_provider_boundary():
    with pytest.raises(ValueError):View('../private',image())
    with pytest.raises(ValueError):View('front',b'not an image')
    output=BytesIO()
    Image.new('RGB',(1025,16)).save(output,format='PNG')
    with pytest.raises(ValueError):View('front',output.getvalue())
    with pytest.raises(ValueError):Request((View('front',image()),View('front',image())))
    from PIL.PngImagePlugin import PngInfo
    info=PngInfo();info.add_text('private-note','do not forward')
    output=BytesIO();Image.new('RGB',(32,48),'orange').save(output,format='PNG',pnginfo=info)
    view=View('front',output.getvalue())
    assert Image.open(BytesIO(view.data)).info=={}
    assert (view.width,view.height)==(32,48) and view.source_sha256!=view.sha256


def test_orientation_is_applied_before_metadata_is_removed():
    output=BytesIO();exif=Image.Exif();exif[274]=6
    Image.new('RGB',(32,48),'orange').save(output,format='JPEG',exif=exif)
    view=View('front',output.getvalue())
    assert (view.width,view.height)==(48,32)
    assert not Image.open(BytesIO(view.data)).getexif()


def test_animated_input_is_not_silently_reduced_to_one_private_frame():
    output=BytesIO()
    first=Image.new('RGB',(32,48),'orange')
    second=Image.new('RGB',(32,48),'blue')
    first.save(output,format='PNG',save_all=True,append_images=[second],duration=50)
    with pytest.raises(ValueError):View('front',output.getvalue())


def test_view_count_and_combined_normalized_byte_limit():
    with pytest.raises(ValueError):Request(())
    with pytest.raises(ValueError):Request(tuple(View(str(i),image()) for i in range(5)))
    import random
    pixels=random.Random(42).randbytes(1024*1024*4)
    noisy=BytesIO();Image.frombytes('RGBA',(1024,1024),pixels).save(noisy,format='PNG',compress_level=0)
    views=tuple(View(str(i),noisy.getvalue()) for i in range(3))
    with pytest.raises(ValueError):Request(views)


def test_budget_consumes_failed_calls_without_automatic_retry_or_raw_error():
    async def run():
        fake=Fake(error=RuntimeError('secret upstream payload'))
        session=Session(fake,Budget(max_calls=1))
        first=await session.assess(request())
        second=await session.assess(request())
        assert first.outcome=='provider_failed' and second.outcome=='budget_exhausted'
        assert fake.calls==1 and 'secret' not in repr(first)
    asyncio.run(run())


def test_total_deadline_covers_time_between_calls():
    async def run():
        fake=Fake()
        session=Session(fake,Budget(max_calls=2,per_call_seconds=1,total_seconds=.2))
        assert (await session.assess(request())).outcome=='review'
        await asyncio.sleep(.21)
        assert (await session.assess(request())).outcome=='budget_exhausted'
        assert fake.calls==1
    asyncio.run(run())


def test_late_result_after_a_blocked_event_loop_cannot_pass_its_deadline():
    async def run():
        import time
        class Blocking(Fake):
            async def propose(self,views):
                self.calls+=1
                time.sleep(.03)
                return response()
        session=Session(Blocking(),Budget(per_call_seconds=.01,total_seconds=1))
        assert (await session.assess(request())).outcome=='timeout'
        assert not session.active
    asyncio.run(run())


def test_duplicate_json_fields_are_rejected_instead_of_silently_overridden():
    async def run():
        payload=response().replace(b'"body_plan": "biped"',b'"body_plan": "quadruped", "body_plan": "biped"')
        assert (await Session(Fake(payload)).assess(request())).outcome=='invalid_response'
    asyncio.run(run())


def test_session_refuses_reuse_on_a_different_event_loop():
    session=Session(Fake())
    assert asyncio.run(session.assess(request())).outcome=='review'
    with pytest.raises(RuntimeError,match='event loop'):
        asyncio.run(session.assess(request()))


def test_timeout_keeps_uncooperative_call_owned_until_actual_completion():
    async def run():
        released=asyncio.Event()
        class Uncooperative(Fake):
            async def propose(self,views):
                self.calls+=1
                if self.calls==1:
                    try:await released.wait()
                    except asyncio.CancelledError:await released.wait()
                return response()
        fake=Uncooperative()
        session=Session(fake,Budget(max_calls=2,per_call_seconds=.01,total_seconds=2))
        try:
            assert (await session.assess(request())).outcome=='timeout'
            assert session.active
            assert (await session.assess(request())).outcome=='busy' and fake.calls==1
            released.set()
            for _ in range(10):
                if not session.active:break
                await asyncio.sleep(0)
            assert not session.active
            assert (await session.assess(request())).outcome=='review' and fake.calls==2
        finally:
            released.set()
            assert await session.close(grace=.1)
    asyncio.run(run())


def test_close_reports_live_cancellation_and_prevents_new_calls():
    async def run():
        released=asyncio.Event()
        class Stubborn(Fake):
            async def propose(self,views):
                self.calls+=1
                try:await released.wait()
                except asyncio.CancelledError:await released.wait()
                return response()
        fake=Stubborn()
        session=Session(fake,Budget(per_call_seconds=.01,total_seconds=1))
        try:
            assert (await session.assess(request())).outcome=='timeout'
            assert not await session.close(grace=.01) and session.active
            assert (await session.assess(request())).outcome=='closed' and fake.calls==1
        finally:
            released.set()
            assert await session.close(grace=.1)
    asyncio.run(run())


def test_caller_cancellation_does_not_detach_a_provider_task():
    async def run():
        entered=asyncio.Event();released=asyncio.Event()
        class Stubborn(Fake):
            async def propose(self,views):
                self.calls+=1;entered.set()
                try:await released.wait()
                except asyncio.CancelledError:await released.wait()
                return response()
        session=Session(Stubborn(),Budget(per_call_seconds=1,total_seconds=2))
        caller=asyncio.create_task(session.assess(request()))
        await entered.wait();caller.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):await caller
            assert session.active and (await session.assess(request())).outcome=='busy'
        finally:
            released.set()
            assert await session.close(grace=.1)
    asyncio.run(run())


@pytest.mark.parametrize('changes',[{'max_calls':True},{'max_calls':5},{'per_call_seconds':float('inf')},
                                    {'total_seconds':0},{'max_response_bytes':10}])
def test_invalid_code_defined_budgets_fail_before_any_call(changes):
    with pytest.raises(ValueError):replace(Budget(),**changes)
