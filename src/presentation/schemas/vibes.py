from apiflask import Schema
from apiflask.fields import Integer, String


class VibesAccountInSchema(Schema):
    account = String(load_default="vibes-default")


class VibesLogQuerySchema(Schema):
    offset = Integer(load_default=0)
    project = String(load_default="")


class VibesDetenerInSchema(Schema):
    project = String(load_default="")


class VibesVideosQuerySchema(Schema):
    project = String(load_default="")


class VibesVideoQuerySchema(Schema):
    project = String(load_default="")
    file = String(required=True)
    dl = String(load_default="0")


class VibesAbrirCarpetaInSchema(Schema):
    project = String(load_default="")
