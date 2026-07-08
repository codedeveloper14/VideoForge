from apiflask import Schema
from apiflask.fields import Boolean, List, String


class GuionGuardarInSchema(Schema):
    project_name = String(required=True)
    texto = String(required=True)
    prompts = String(load_default="")


class GuionCargarQuerySchema(Schema):
    project = String(load_default="")


class GuionCargarOutSchema(Schema):
    texto = String()
    prompts = String()
    existe = Boolean()


class AudioCargarQuerySchema(Schema):
    project = String(load_default="")


class AudioCargarOutSchema(Schema):
    existe = Boolean()
    archivos = List(String())
    principal = String(allow_none=True)


class AudioArchivoQuerySchema(Schema):
    project = String(required=True)
    file = String(required=True)
