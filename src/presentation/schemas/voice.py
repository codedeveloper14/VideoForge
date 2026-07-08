from apiflask import Schema
from apiflask.fields import String


class VozGenerarInSchema(Schema):
    project_name = String(load_default="")
    voice_id = String(load_default="")
    data = String(required=True)
