from langchain.llms import OpenAI
from langchain.document_loaders import PyPDFLoader # pdf loading
from langchain.embeddings import OpenAIEmbeddings # embeddings
from langchain.vectorstores import Chroma # vector store
from langchain.chains import ChatVectorDBChain # chatting with pdf
import os
import csv
from io import StringIO
from app.utilities.llm_manager import LLMManager


class ContractReviewManager:
    llmManager = None;
    document_sections = [];
    compliance_results = [];
    review_vector_db = None
    embeddings = None

    def __init__(self, manager):
        self.llmManager = manager
    
    

    def scan(self, document):
        self.compliance_results = []
        return self.fetch_sections(document)

    def fetch_sections(self, document):
        document_sections = self.llmManager.ask_all_documents("Consider the document: " + document + ". Give me a list of all sections in the contract, formatted as a csv with a comma between each section.")
        print(document_sections)
        return document_sections.split(',')

    def get_compliance(self, document, section):
        prompt = "You are an expert in compliance, using the provided review guide and your knowledge of University rules and laws, considering the " + section + " section  of the document " + document + ". Tell me why or why not it is in compliance. Only answer if you know the answer, otherwise just return the word unsure"
        result = self.llmManager.ask_all_documents(prompt)
        return section, result



    
        
        