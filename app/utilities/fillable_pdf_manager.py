import os
import openai
import chardet
from PyPDF2 import PdfReader
from app.utilities.uillm import UILLM


class FillablePDFManager:
    def build_set_from_items(self, items):
        openai.api_key = "sk-proj-Tdb51ojrv5lwDtPH9S3tT3BlbkFJ6ty7hYO3Ow8weqXu6UjM"
        prompt = ""

        prompt = (
            """Given the following set of fields from a fillable pdf and their values::\n"""
            + str(items)
        )
        prompt += """Give me a json list of items to extract to fill these in. The format should be: {'fields': [{pdffieldname: "Human readable field name to be used to extract"}]}"""
        return UILLM.ask_question(prompt, is_json=True)
