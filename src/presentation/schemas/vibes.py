from apiflask import Schema
from apiflask.fields import Boolean, Integer, String


class VibesAccountInSchema(Schema):
    account = String(load_default="vibes-default")


class VibesIniciarInSchema(Schema):
    project_name = String(required=True)
    prompt = String(required=True)
    slots = Integer(load_default=1)
    aspect_ratio = String(load_default="9:16")
    resolution = String(load_default="480p")
    prompt_model = String(load_default="gemini-2.5-flash")
    image_model = String(load_default="midjen-base")
    video_model = String(load_default="midjen-short")
    batch_variation = Boolean(load_default=True)
    timeout = Integer(load_default=300)
    reference_image = String(load_default="")


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
