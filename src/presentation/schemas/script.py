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


class AnalyzeImageInSchema(Schema):
    image_base64 = String(required=True)
    mime_type = String(load_default="image/png")


class N8nProxyInSchema(Schema):
    guion = String(required=True)
    output_mode = String(load_default="con_prompts")
    prompt_mode = String(load_default="general")
    prompt_style = String(load_default="default")
    descripcion_estilo = String(load_default="")
    descripcion_referencia = String(load_default="")
    estilo = String(load_default="")
