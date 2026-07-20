from apiflask import Schema
from apiflask.fields import Integer, List, String


class GentubeRunPromptsInSchema(Schema):
    prompts = List(String(), load_default=list)
    slots = Integer(load_default=1)
    repeat = Integer(load_default=1)
    output_dir = String(load_default="")
    ratio = String(load_default="1:1")
    quality = String(load_default="standard")
    browser_mode = String(load_default="chromium")
