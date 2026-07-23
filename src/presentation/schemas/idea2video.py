from apiflask import Schema
from apiflask.fields import Integer, String


class Idea2VideoScriptInSchema(Schema):
    idea = String(load_default="")
    dur = Integer(load_default=60)
    style = String(load_default="cinematic")
    tone = String(load_default="inspirador")
    audience = String(load_default="general")


class Idea2VideoAutopilotInSchema(Schema):
    script = String(required=True)
    title = String(load_default="")
    voice_id = String(load_default="")
    ref_image = String(load_default=None, allow_none=True)
    mode = String(load_default="rapido")


class Idea2VideoImageQuerySchema(Schema):
    project = String(load_default="")
    file = String(load_default="")
