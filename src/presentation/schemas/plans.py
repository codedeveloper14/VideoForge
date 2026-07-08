from apiflask import Schema
from apiflask.fields import Boolean, Integer, String


class PlanOutSchema(Schema):
    id = String()
    name = String()
    emoji = String()
    price_usd = Integer()
    videos_per_day = Integer(allow_none=True)
    videos_per_month = Integer(allow_none=True)
    audio_hours_per_month = Integer(allow_none=True)
    shorts_per_month = Integer(allow_none=True)
    tts_mins_per_day = Integer(allow_none=True)
    max_video_minutes = Integer(allow_none=True)
    highlight = Boolean()
