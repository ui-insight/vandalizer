import os
from pathlib import Path
import openai
import chardet
from PyPDF2 import PdfReader
from app.utilities.prompt_optimization import dspy_model

# 128K is the max context length for the GPT-4o model
# we use less than this to be safe
max_context_length = 90000


def detect_encoding(file_path):
    with open(file_path, "rb") as file:
        result = chardet.detect(file.read())
    return result["encoding"]


def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text


# TODO we might need to rename the class
class OpenAIInterface:
    loaded_doc = ""

    def load_document(self, root_path, document_path):
        full_path = os.path.join(root_path, "static", "uploads", document_path)
        self.loaded_doc = extract_text_from_pdf(full_path)

    def ask_question_to_loaded_document(self, item):
        openai.api_key = "sk-proj-Tdb51ojrv5lwDtPH9S3tT3BlbkFJ6ty7hYO3Ow8weqXu6UjM"
        prompt = ""
        print("asking question")
        if len(item.text_blocks) > 0:
            prompt = (
                """Given the following document, and the attached additional context, answer the following question. Return the result as nicely formatted html.\nQuestion:\n"""
                + item.searchphrase
            )

            for block in item.text_blocks:
                prompt += "\n\nContext:\n" + block

            prompt += "\n\nDocument:\n" + self.loaded_doc
            # print(prompt)
        else:
            print("no text blocks")
            prompt = (
                """Given the following document, answer the following question. Return the result as nicely formatted html.:\nQuestion:\n"""
                + item.searchphrase
                + "\Document:\n"
                + self.loaded_doc
            )

        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content

    def ask_question_to_documents(self, root_path, documents, question):

        full_text = ""
        for document in documents:
            full_path = os.path.join(root_path, "static", "uploads", document.path)
            full_text += "\n\nDocument:" + extract_text_from_pdf(full_path) + " "

        # TODO add the dspy model here (route based on the length of the documents, if larger call dspy model, if smaller call the chat model)

        openai.api_key = "sk-proj-Tdb51ojrv5lwDtPH9S3tT3BlbkFJ6ty7hYO3Ow8weqXu6UjM"
        prompt = (
            """Given the following document(s), answer the following question. Return the result as nicely formatted html with supportive information as if to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting. Question:"""
            + question
            + "\n"
            + full_text
        )
        total_context_length = len(prompt) + len(full_text)

        print("total context length: ", total_context_length)
        if total_context_length > max_context_length:
            print("using dspy model")
            print("question: ", question)

            # TODO call the dspy model here
            # return "The document(s) are too large to process, please contact support for assistance."
            persistent_directory = Path(root_path) / "static" / "uploads"
            collection_name = "chat_dspy_model"
            model = dspy_model(full_text, collection_name, persistent_directory)
            response, queries = model(question=question)
            output_prompt = (
                (
                    """Format the following answer to the given question as a nicely formatted html with supportive information to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting. Do not add ```html before your response. Do not add 'Question' and 'Answer' heading or title in your response, but only respond only with the formatted html code for the answer.\n\n Question: """
                )
                + question
                + "\n\nAnwsers: "
                + response.answer
            )
            print("dspy response: ", response.answer)
            completion = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": output_prompt}],
            )
            print("llm formatted response: ", completion.choices[0].message.content)
            return completion.choices[0].message.content
        else:
            completion = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
            )
            return completion.choices[0].message.content
