from apiflask import Schema
from apiflask.fields import Boolean, Integer, String


class HelpSubmitInSchema(Schema):
    type = String(load_default="")
    category = String(load_default="")
    title = String(required=True)
    description = String(load_default="")
    email = String(load_default="")


class DocInSchema(Schema):
    type = String(load_default="video")
    category = String(load_default="General")
    title = String(load_default="")
    description = String(load_default="")
    url = String(load_default="")
    content = String(load_default="")
    thumbnail_url = String(load_default="")
    duration_label = String(load_default="")
    tags = String(load_default="")
    sort_order = Integer(load_default=0)
    is_published = Boolean(load_default=True)
