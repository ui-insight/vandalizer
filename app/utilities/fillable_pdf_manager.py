import os

import openai
# from app.utilities.uillm import UILLM
from uillm import UILLM

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class FillablePDFManager:
    def build_set_from_items(self, items):
        openai.api_key = OPENAI_API_KEY
        prompt = ""

        prompt = (
            """Given the following set of fields from a fillable pdf and their values::\n"""
            + str(items)
        )
        prompt += """Give me a json list of items to extract to fill these in. The format should be: {'fields': [{pdffieldname: "Human readable field name to be used to extract"}]}"""
        return UILLM.ask_question(prompt, is_json=True)
