from apiflask import Schema
from apiflask.fields import Integer, Raw, String


class WhiskLoginInSchema(Schema):
    profile = Integer(load_default=0)
    account_id = Integer(load_default=0)
    cookie = String(load_default="")


class WhiskSetSubjectInSchema(Schema):
    image = String(load_default="")
    ext = String(load_default="jpg")


class WhiskRunPromptsInSchema(Schema):
    prompts = Raw(load_default="")  # lista o string, ambos aceptados
    slots = Integer(load_default=1)
    repeat = Integer(load_default=1)
    output_dir = String(load_default="")
