from langchain.llms import OpenAI
from langchain.document_loaders import PyPDFLoader # pdf loading
from langchain.embeddings import OpenAIEmbeddings # embeddings
from langchain.vectorstores import Chroma # vector store
from langchain.chains import ChatVectorDBChain # chatting with pdf
import os
from langchain.document_loaders import Docx2txtLoader
from langchain.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import ConversationalRetrievalChain

class LLMManager:
    pdf_loaded = False
    vectordb = None
    root_path = ""
    embeddings = None

    def __init__(self):
        # Load in Vector Database
        self.embeddings = OpenAIEmbeddings(openai_api_key="***REMOVED***")
        self.vectordb = self.vectordb = Chroma(embedding_function=self.embeddings,
                                 persist_directory="./vectordb")
        print("There are", self.vectordb._collection.count(), "in the collection")

    def ask_openai(self):
        llm = OpenAI(openai_api_key="***REMOVED***")
        text = "What is the meaning of life?"
        llm.predict(text)
        pass
    
    def ask_document(self, question):
        #if self.pdf_loaded == False:
        #    self.load_documents()
        llm = OpenAI(openai_api_key="***REMOVED***")
        pdf_qa = ConversationalRetrievalChain.from_llm(llm, self.vectordb.as_retriever(search_kwargs={'k': 6}), return_source_documents=True)

        result = pdf_qa({"question": question, "chat_history": ""})
        return result["answer"]

    def load_pdf(self, pdf_path=""):
        loader = PyPDFLoader(os.path.join(self.root_path, "static", "uploads", pdf_path))
        loader.load()
        pages = loader.load_and_split()
        # New vector store code
        self.vectordb = Chroma.from_documents(
            pages,
            embedding=self.embeddings,
            persist_directory='./vectordb'
        )
        self.vectordb.persist()
        
        pass
    
    def stats(self):
        print("There are", self.vectordb._collection.count(), "in the collection")

    def delete_db(self):
        self.vectordb._collection.delete()

    def load_documents(self):
        documents = []
        self.delete_db()
        for file in os.listdir('app/data'):
            if file.endswith('.pdf'):
                pdf_path = os.path.join(self.root_path, "static", "uploads", file)
                loader = PyPDFLoader(pdf_path)
                documents.extend(loader.load())
            elif file.endswith('.docx') or file.endswith('.doc'):
                doc_path = os.path.join(self.root_path, "static", "uploads", file)
                loader = Docx2txtLoader(doc_path)
                documents.extend(loader.load())
            elif file.endswith('.txt'):
                text_path = os.path.join(self.root_path, "static", "uploads", file)
                loader = TextLoader(text_path)
                documents.extend(loader.load())

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=10)
        chunked_documents = text_splitter.split_documents(documents)
        self.vectordb = Chroma.from_documents(
            chunked_documents,
            embedding=self.embeddings,
            persist_directory='./vectordb'
        )
        self.vectordb.persist()
        