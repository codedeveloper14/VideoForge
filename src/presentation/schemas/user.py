from apiflask import Schema
from apiflask.fields import Dict, Float, String


class UserProfileOutSchema(Schema):
    username = String()
    email = String()
    plan = String()
    plan_name = String()
    subscription_date = String(allow_none=True)
    usage = Dict()
    limits = Dict()
    payment = Dict()


class PaymentOutSchema(Schema):
    plan = String()
    amount_usd = Float()
    paid_at = String()
    session_id = String(allow_none=True)
