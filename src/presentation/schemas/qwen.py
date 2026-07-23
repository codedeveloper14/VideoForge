from apiflask import Schema
from apiflask.fields import Integer, String


class QwenAccountInSchema(Schema):
    account = String(required=True)


class QwenRegenerarInSchema(Schema):
    video_name = String(required=True)
    project_name = String(load_default="")
    prompt = String(load_default="Cinematic slow zoom")
    size = String(load_default="1280x720")


class QwenLogQuerySchema(Schema):
    offset = Integer(load_default=0)
    project = String(load_default="")


class QwenDetenerInSchema(Schema):
    project = String(load_default="")


class QwenVideosQuerySchema(Schema):
    project = String(load_default="")


class QwenVideoQuerySchema(Schema):
    project = String(load_default="")
    file = String(required=True)
    dl = String(load_default="0")


class QwenAbrirCarpetaInSchema(Schema):
    project = String(load_default="")
