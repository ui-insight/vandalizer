from langchain.document_loaders import PyPDFLoader  # pdf loading
from langchain.embeddings import OpenAIEmbeddings  # embeddings
from langchain.chat_models import ChatOpenAI
from langchain.chains import create_extraction_chain
from langchain.callbacks import get_openai_callback

import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ExtractionManager:
    llmManager = None
    review_vector_db = None
    embeddings = None
    root_path = ""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

    def extract(self, document, value_string):
        loader = PyPDFLoader(
            os.path.join(self.root_path, "static", "uploads", document)
        )
        docs = loader.load()
        # text_splitter = CharacterTextSplitter(chunk_size=15000, chunk_overlap=0)
        # docs = text_splitter.split_documents(loader.load())
        input = ""
        for doc in docs:
            input += doc.page_content + " "

        properties = {}
        for value in value_string.split(","):
            properties[value] = {"type": "string"}

        schema = {
            "properties": properties,
        }
        print(schema)

        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo-16k", temperature=0, openai_api_key=OPENAI_API_KEY
        )

        with get_openai_callback() as cb:
            chain = create_extraction_chain(schema, llm, verbose=True)

            result = chain.run(input)
            print(cb)
            print(result)
            return result
