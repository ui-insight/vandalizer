import time
import openai
from pypdf import PdfReader
import os
import re
import csv
from io import StringIO
import json


from app.utilities.document_readers import extract_text_from_doc


class ExtractionManager2:
    root_path = ""

    def getPrompt(self, context, features):
        return (
            """Your job is to extract a list of entities from document(s). These are the entities you need to extract, no more. Entities:
        """
            + "\n".join(features)
            + """

        If a property is not present, represent it as "Not Found".

        Format the output as JSON, with the entity name as the key and a single string as the value. Make sure the entity name is exactly as it is listed. Do not include any additional text. Do not nest json values format it as {"entity": "value"}.
        
        Passage: 

        """
            + context
        )

    def extract(self, extract_keys, pdf_paths, full_text=None):
        start_time = time.time()
        openai.api_key = "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"
        doc_text = ""
        if full_text is None:
            for pdf_path in pdf_paths:
                doc_text = extract_text_from_doc(doc_path=pdf_path)

            print(f"PDF processing time: {time.time() - start_time:.2f} seconds")
        else:
            doc_text = full_text
        start_time = time.time()

        print(
            "Extracting entities from document(s): ", doc_text, pdf_paths, extract_keys
        )
        prompt = self.getPrompt(doc_text, extract_keys)
        # model = "gpt-3.5-turbo-0125"
        # if len(prompt) > 50000:
        #    model = "gpt-4-turbo"
        model = "gpt-4o"

        print(f"Prompt processing time: {time.time() - start_time:.2f} seconds")
        start_time = time.time()

        completion = openai.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        output = completion.choices[0].message.content
        output = output.replace("\\n", "")
        output = output.replace("```json", "")
        output = output.replace("```", "")
        print(output)

        print(f"Completion processing time: {time.time() - start_time:.2f} seconds")

        if "{" in output and "}" in output:
            output_data = json.loads(output.strip())
            return output_data
        else:
            print("Threw out: " + output)
            return
