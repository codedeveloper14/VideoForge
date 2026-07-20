from apiflask import Schema
from apiflask.fields import String


class HealthOutSchema(Schema):
    status = String()
    app = String()
    version = String()
