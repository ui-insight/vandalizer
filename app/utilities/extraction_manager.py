from langchain.llms import OpenAI
from langchain.document_loaders import PyPDFLoader # pdf loading
from langchain.embeddings import OpenAIEmbeddings # embeddings
from langchain.vectorstores import Chroma # vector store
from langchain.chains import ChatVectorDBChain # chatting with pdf
from langchain.document_loaders import Docx2txtLoader
from langchain.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.chat_models import ChatOpenAI
from langchain.chains import create_extraction_chain
import time

import os
import re
import csv
from io import StringIO


class ExtractionManager:
    llmManager = None;
    review_vector_db = None
    embeddings = None
    root_path = ""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(openai_api_key="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")
    
    def extract(self, document, value_string):
        loader = PyPDFLoader(os.path.join(self.root_path, "static", "uploads", document))
        docs = loader.load()
        #text_splitter = CharacterTextSplitter(chunk_size=15000, chunk_overlap=0)
        #docs = text_splitter.split_documents(loader.load())
        input = ""
        for doc in docs:
            input += doc.page_content + " "

        properties = {}
        for value in value_string.split(','):
            properties[value] = {"type": "string"}
        
        schema = {
            "properties": properties,
        }
        print(schema)

        llm = ChatOpenAI(model_name="gpt-3.5-turbo-16k", temperature=0, openai_api_key="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")
        chain=create_extraction_chain(schema, llm)

        result = chain.run(input)
        print(result)
        return result

    



    
        
        