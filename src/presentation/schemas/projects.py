from apiflask import Schema
from apiflask.fields import Boolean, Dict, Float, Integer, List, Nested, String


class CreateProjectInSchema(Schema):
    nombre = String(required=True)


class CreateProjectOutSchema(Schema):
    ok = Boolean()
    nombre = String()
    ruta = String()


class ProjectOutSchema(Schema):
    nombre = String()
    ruta = String()
    videos = Integer()
    audios = Integer()
    creado = Float()


class ProjectQuerySchema(Schema):
    project = String(required=True)


class ImagenFileQuerySchema(Schema):
    project = String(required=True)
    file = String(required=True)


class VideoFinalQuerySchema(Schema):
    project = String(required=True)
    file = String(required=True)
    dl = String(load_default="0")


class SceneOutSchema(Schema):
    index = String()
    image = String(allow_none=True)
    video = String(allow_none=True)
    has_video = Boolean()


class ProjectContentOutSchema(Schema):
    scenes = List(Nested(SceneOutSchema))
    total = Integer()
    with_video = Integer()
    images_only = Integer()
    debug = Dict()


class VideosFinalOutSchema(Schema):
    videos = List(String())


class ProjectNameInSchema(Schema):
    nombre = String(load_default="")
    name = String(load_default="")


class ProjectRefInSchema(Schema):
    project = String(required=True)
