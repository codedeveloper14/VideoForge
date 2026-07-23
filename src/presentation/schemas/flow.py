from apiflask import Schema
from apiflask.fields import Integer, String


class FlowProfileDumpQuerySchema(Schema):
    idx = Integer(load_default=0)


class FlowImagesQuerySchema(Schema):
    dir = String(load_default="")


class FlowMtimeQuerySchema(Schema):
    dir = String(load_default="")
    file = String(load_default="")


class FlowImageQuerySchema(Schema):
    dir = String(load_default="")
    file = String(load_default="")
