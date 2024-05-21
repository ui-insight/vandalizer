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
    loaded_doc = ""

    def load_document(self, root_path, document_path):
        full_path = os.path.join(root_path, "static", "uploads", document_path)
        self.loaded_doc = extract_text_from_pdf(full_path)

    def ask_question_to_loaded_document(self, item):
        openai.api_key = "***REMOVED***"
        prompt = ""
        print("asking question")
        if len(item.text_blocks) > 0:
            prompt = """Given the following document, and the attached additional context, answer the following question:\nQuestion:\n""" + item.searchphrase 
            
            for block in item.text_blocks:
                prompt += "\n\nContext:\n" + block
            
            prompt += "\n\nDocument:\n" + self.loaded_doc
            print(prompt)
        else:
            print("no text blocks")
            prompt = """Given the following document, answer the following question:\nQuestion:\n""" + item.searchphrase + "\Document:\n" + self.loaded_doc
        
        completion = openai.chat.completions.create(model="gpt-4o", 
                                              messages=[{"role": "user", "content": prompt}],
                                             )
        return completion.choices[0].message.content
    
    def ask_question_to_document(self, root_path, document_path, question):
        full_path = os.path.join(root_path, "static", "uploads", document_path)
        
        openai.api_key = "***REMOVED***"
        prompt = """Given the following document, answer the following question:""" + question + "\n" + extract_text_from_pdf(full_path)
        completion = openai.chat.completions.create(model="gpt-4o", 
                                              messages=[{"role": "user", "content": prompt}],
                                             )
        return completion.choices[0].message.content
    
    