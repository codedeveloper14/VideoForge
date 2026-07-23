from apiflask import Schema
from apiflask.fields import String


class StripeCheckoutInSchema(Schema):
    plan = String(required=True)


class StripePollQuerySchema(Schema):
    session_id = String(required=True)
    plan = String(load_default="")
