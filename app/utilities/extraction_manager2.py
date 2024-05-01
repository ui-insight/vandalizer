
import time
import openai
from pypdf import PdfReader
import os
import re
import csv
from io import StringIO
import json

class ExtractionManager2:
    root_path = ""
    def getPrompt(self, context, features):
        return """Extract and save the relevant entities mentioned in the following passage together with their properties.
        """ + "\n".join(features) + """

        If a property is not present, represent it as "Not Found".

        Format the output as JSON, with a single string as the key and a single string as the value. Do not include any additional text. Do not nest json values.
        
        Passage: 

        """ + context + """
        Remember: Extract and save the relevant entities mentioned in the following passage together with their properties.
        """ + "\n".join(features) + """

        If a property is not present, represent it as "Not Found".

        Format the output as JSON, with a single string as the key and a single string as the value. Do not include any additional text. Do not nest json values.
       
        """

    def extract(self, extract_keys, pdf_path):
        start_time = time.time()
        openai.api_key = "***REMOVED***"
        pdf = PdfReader(os.path.join(self.root_path, "static", "uploads", pdf_path))
        number_of_pages = len(pdf.pages)
        full_text = ""
        for i in range(number_of_pages):
            full_text = full_text + pdf.pages[i].extract_text() + " "

        print(f"PDF processing time: {time.time() - start_time:.2f} seconds")
        start_time = time.time()

        prompt = self.getPrompt(full_text, extract_keys)

        print(f"Prompt processing time: {time.time() - start_time:.2f} seconds")
        start_time = time.time()

        completion = openai.chat.completions.create(model="gpt-4-turbo", 
                                                    response_format={"type": "json_object"},
                                                messages=[
                                                    {"role": "system", "content": "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage."},
                                                    {"role": "user", "content": prompt}],
                                                )
        output = completion.choices[0].message.content
        output = output.replace('\\n', '') 
        output = output.replace('```json', '')
        output = output.replace('```', '')
        print(output)

        print(f"Completion processing time: {time.time() - start_time:.2f} seconds")


        if "{" in output and "}" in output:
            output_data = json.loads(output.strip())
            return output_data
        else:
            print("Threw out: " + output)
            return

    



    
        
        