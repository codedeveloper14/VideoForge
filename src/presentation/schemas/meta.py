from apiflask import Schema
from apiflask.fields import Integer, String


class MetaAccountInSchema(Schema):
    account = String(required=True)


class MetaLogQuerySchema(Schema):
    offset = Integer(load_default=0)


class MetaVideosQuerySchema(Schema):
    project = String(load_default="")


class MetaVideoQuerySchema(Schema):
    project = String(load_default="")
    file = String(required=True)
    dl = String(load_default="0")


class MetaAbrirCarpetaInSchema(Schema):
    project = String(load_default="")


class MetaLaunchChromeInSchema(Schema):
    account = String(load_default="cuenta1")
    slots = Integer(load_default=3)


class MetaOpenDevmodeInSchema(Schema):
    account = String(load_default="cuenta1")
