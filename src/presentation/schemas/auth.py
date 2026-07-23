from apiflask import Schema
from apiflask.fields import Boolean, String
from apiflask.validators import Length


class LoginInSchema(Schema):
    username = String(required=True)
    password = String(required=True)


class RegisterInSchema(Schema):
    username = String(required=True, validate=Length(min=3, max=20))
    email = String(required=True)
    password = String(required=True, validate=Length(min=8))
    plan = String(load_default="basico")


class ChangePasswordInSchema(Schema):
    username = String(required=True)
    new_password = String(required=True, validate=Length(min=8))


class MeOutSchema(Schema):
    authenticated = Boolean()
    username = String()
