from apiflask import Schema
from apiflask.fields import Integer, String


class UsageCheckInSchema(Schema):
    type = String(load_default="video")
    amount = Integer(load_default=1)


class UsageRecordInSchema(Schema):
    videos = Integer(load_default=0)
    tts_chars = Integer(load_default=0)
