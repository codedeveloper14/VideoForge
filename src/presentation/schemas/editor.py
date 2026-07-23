from apiflask import Schema
from apiflask.fields import Integer, String


class EditorBuscarImagenInSchema(Schema):
    query = String(required=True)
    n = Integer(load_default=4)
    serper_key = String(load_default="")
    pexels_key = String(load_default="")


class EditorCargarPlanQuerySchema(Schema):
    project = String(load_default="")


class EditorProxyImagenInSchema(Schema):
    url = String(required=True)
