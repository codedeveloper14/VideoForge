from apiflask import Schema
from apiflask.fields import Integer, String


class GrokAccountInSchema(Schema):
    account = String(required=True)


class GrokRegenerarInSchema(Schema):
    video_name = String(load_default="")
    project_name = String(load_default="")
    prompt = String(load_default="Cinematic slow zoom")
    aspect_ratio = String(load_default="2:3")
    video_length = Integer(load_default=6)
    resolution = String(load_default="480p")


class GrokLogQuerySchema(Schema):
    offset = Integer(load_default=0)
    project = String(load_default="")


class GrokDetenerInSchema(Schema):
    project = String(load_default="")


class GrokVideosQuerySchema(Schema):
    project = String(load_default="")


class GrokVideoQuerySchema(Schema):
    project = String(load_default="")
    file = String(required=True)
    dl = String(load_default="0")


class GrokAbrirCarpetaInSchema(Schema):
    project = String(load_default="")
