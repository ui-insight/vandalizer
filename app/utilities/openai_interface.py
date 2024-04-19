import os
import openai
import chardet
from PyPDF2 import PdfReader

def detect_encoding(file_path):
        with open(file_path, 'rb') as file:
            result = chardet.detect(file.read())
        return result['encoding']

def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text

class OpenAIInterface:
    

    def ask_question_to_document(self, root_path, document_path, question):
        full_path = os.path.join(root_path, "static", "uploads", document_path)
        
        openai.api_key = "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"
        prompt = """Given the following document, answer the following question:""" + question + "\n" + extract_text_from_pdf(full_path)
        completion = openai.chat.completions.create(model="gpt-3.5-turbo-0125", 
                                              messages=[{"role": "user", "content": prompt}],
                                             )
        return completion.choices[0].message.content
    
    