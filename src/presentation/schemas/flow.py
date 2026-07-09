from apiflask import Schema
from apiflask.fields import Integer


class FlowProfileDumpQuerySchema(Schema):
    idx = Integer(load_default=0)
