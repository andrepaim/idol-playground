"""Bounded local image preparation and explicit manual anatomy review."""
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Literal
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from character_coordinator import Decision

MAX_UPLOAD = 20 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_EDGE = 1024


class InputSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmed: StrictBool = False
    crop: list[StrictInt] | None = Field(default=None,min_length=4,max_length=4)

    @model_validator(mode='after')
    def valid_crop(self):
        if self.crop is not None:
            x0,y0,x1,y1 = self.crop
            if x0 < 0 or y0 < 0 or x1-x0 < 16 or y1-y0 < 16:
                raise ValueError('Choose a crop at least 16 pixels wide and high, within the image.')
        return self


class AnatomySettings(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    body_plan: Literal['unknown','biped','quadruped','swimmer','unsupported'] = 'unknown'
    species: Literal['person','dog','cat','fish','shark','other'] = 'other'
    front_axis: Literal['+z','-z','+x','-x'] = '+z'
    scale_m: float = Field(default=1.0,gt=0,le=100,strict=True)
    single_subject: StrictBool = False
    full_body: StrictBool = False
    limbs_separable: StrictBool = False
    confirmed: StrictBool = False


def inspect_image(data):
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('Choose a nonempty PNG, JPEG or WebP image up to 20 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ('PNG','JPEG','WEBP') or getattr(image,'n_frames',1) != 1:
                    raise ValueError('Choose a still PNG, JPEG or WebP image.')
                width,height = image.size
                if min(width,height) < 16 or width*height > MAX_PIXELS:
                    raise ValueError('Choose an image at least 16 pixels per side and at most 25 million pixels.')
                if image.getexif().get(274) in (5,6,7,8):
                    width,height = height,width
                result = {'width':width,'height':height,'format':image.format}
            with Image.open(BytesIO(data)) as image:
                image.verify()
            return result
    except (OSError,UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning,SyntaxError) as error:
        raise ValueError('The image could not be decoded safely. Choose another still image.') from error


def checked_input(settings,info):
    value = InputSettings.model_validate(settings).model_dump(mode='json')
    if value['crop'] is not None and (value['crop'][2] > info['width'] or value['crop'][3] > info['height']):
        raise ValueError('Keep the crop inside the oriented image.')
    return value


def _write(path,data):
    descriptor = os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'wb') as stream:
        stream.write(data)


def _bounded(path,limit):
    with Path(path).open('rb') as stream:
        data=stream.read(limit+1)
    if len(data)>limit:
        raise ValueError('Stage artifact exceeds its input-validation limit.')
    return data


def run_input(config,workspace):
    with Path(config['source']).open('rb') as stream:
        data = stream.read(MAX_UPLOAD+1)
    if sha256(data).hexdigest() != config['sha256']:
        raise ValueError('Original upload changed before preparation.')
    info = inspect_image(data)
    settings = checked_input(config['parameters'],info)
    crop = settings['crop'] or [0,0,info['width'],info['height']]
    with Image.open(BytesIO(data)) as source:
        prepared = ImageOps.exif_transpose(source).convert('RGBA').crop(tuple(crop))
        prepared.thumbnail((MAX_EDGE,MAX_EDGE),Image.Resampling.LANCZOS)
        prepared.info.clear()
        output = BytesIO();prepared.save(output,format='PNG')
        report = {'schema_version':1,'source':info,'parameters':settings,'crop':crop,
                  'prepared_width':prepared.width,'prepared_height':prepared.height}
    _write(workspace/'original.bin',data)
    _write(workspace/'prepared.png',output.getvalue())
    _write(workspace/'input.json',json.dumps(report,sort_keys=True,allow_nan=False).encode())


def validate_input(context,paths):
    data = _bounded(paths['original.bin'],MAX_UPLOAD)
    info = inspect_image(data)
    settings = checked_input(context.parameters,info)
    report = json.loads(_bounded(paths['input.json'],64*1024))
    with Image.open(paths['prepared.png']) as prepared:
        if prepared.format != 'PNG' or prepared.mode != 'RGBA' or not 0 < max(prepared.size) <= MAX_EDGE:
            return Decision('reject',{'code':'invalid_prepared_image'})
        if prepared.info:
            return Decision('reject',{'code':'unexpected_preview_metadata'})
        dimensions = prepared.size
        prepared.verify()
    expected = {'schema_version':1,'source':info,'parameters':settings,
                'crop':settings['crop'] or [0,0,info['width'],info['height']],
                'prepared_width':dimensions[0],'prepared_height':dimensions[1]}
    if report != expected:
        return Decision('reject',{'code':'input_report_mismatch'})
    return Decision('accept' if settings['confirmed'] else 'review',
                    {'code':'image_confirmed' if settings['confirmed'] else 'confirm_subject_and_crop','prepared_size':list(dimensions)})


def run_assessment(config,workspace):
    settings = AnatomySettings.model_validate(config['parameters']).model_dump(mode='json')
    image_hash = sha256(_bounded(config['image'],8*1024*1024)).hexdigest()
    _write(workspace/'assessment.json',json.dumps({'schema_version':1,'source':'manual',**settings,'image_sha256':image_hash},
                                               sort_keys=True,allow_nan=False).encode())


def validate_assessment(context,paths):
    settings = AnatomySettings.model_validate(context.parameters).model_dump(mode='json')
    image_hash = sha256(_bounded(context.inputs['input:prepared.png'],8*1024*1024)).hexdigest()
    report = json.loads(_bounded(paths['assessment.json'],64*1024))
    if report != {'schema_version':1,'source':'manual',**settings,'image_sha256':image_hash}:
        return Decision('reject',{'code':'assessment_report_mismatch'})
    if settings['body_plan'] == 'unsupported':
        return Decision('reject',{'code':'unsupported_body_plan'})
    accepted = settings['body_plan'] != 'unknown' and all(settings[name] for name in ('confirmed','single_subject','full_body','limbs_separable'))
    return Decision('accept' if accepted else 'review',{'code':'manual_anatomy_confirmed' if accepted else 'review_anatomy_and_visibility',
                                                     'source':'manual','body_plan':settings['body_plan']})
