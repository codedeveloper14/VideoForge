from apiflask import Schema
from apiflask.fields import Boolean, String


class UpdateCheckOutSchema(Schema):
    current_version = String()
    latest_version = String(allow_none=True)
    update_available = Boolean()
    release_url = String(allow_none=True)
