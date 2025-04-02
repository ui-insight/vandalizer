import os
import time

from langchain.chains import ConversationalRetrievalChain, RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,  # pdf loading
    TextLoader,
)
from langchain.embeddings import OpenAIEmbeddings  # embeddings
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores import Chroma  # vector store

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ContractReviewManagerChained:
    llmManager = None
    review_vector_db = None
    embeddings = None
    root_path = ""

    def __init__(self) -> None:
        self.embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        self.review_vector_db = Chroma(
            embedding_function=self.embeddings, persist_directory="./review_vectordb",
        )

    def extract_sections(self, document) -> None:
        vectordb = self.load_contract(document)
        llm = ChatOpenAI(model_name="gpt-3.5-turbo", openai_api_key=OPENAI_API_KEY)
        retreiver = vectordb.as_retriever(search_kwargs={"k": 1})
        pdf_qa = ConversationalRetrievalChain.from_llm(llm, retreiver)

        pdf_qa(
            {
                "question": "Give me a list of all sections in the contract, formatted as a csv with a comma between each section.",
                "chat_history": "",
            },
        )

    def prepare_splits2(self, document):
        loader = PyPDFLoader(
            os.path.join(self.root_path, "static", "uploads", document),
        )
        loader.load()
        pages = loader.load_and_split()
        text_splitter = CharacterTextSplitter(chunk_size=15000, chunk_overlap=200)
        docs = text_splitter.split_documents(pages)
        ret_arr = []
        for doc in docs:
            ret_arr.append(doc.page_content)
        return ret_arr

    def prepare_splits(self, document):
        # self.load_documents()
        loader = PyPDFLoader(
            os.path.join(self.root_path, "static", "uploads", document),
        )
        docs = loader.load()
        # text_splitter = CharacterTextSplitter(chunk_size=15000, chunk_overlap=0)
        # docs = text_splitter.split_documents(loader.load())
        doc_string = ""
        for doc in docs:
            doc_string += doc.page_content + " "

        llm = ChatOpenAI(model_name="gpt-3.5-turbo-16k", openai_api_key=OPENAI_API_KEY)
        text = (
            "Given the following text: "
            + doc_string
            + ". Give me a list of all sections in the contract, formatted as a csv with a comma between each section."
        )
        return llm.predict(text)

    def get_compliance(self, document):
        time.time()
        prompt = "You are an expert in compliance, using the provided review guide and your knowledge of University rules and laws, review the the contract. Explain if anything is out of compliance. "
        llm = ChatOpenAI(model_name="gpt-3.5-turbo-16k", openai_api_key=OPENAI_API_KEY)
        retreiver = self.load_vectordb(document).as_retriever(search_kwargs={"k": 5})
        rqa = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retreiver,
            return_source_documents=True,
        )
        result = rqa(prompt)
        time.time()
        return result["result"]

    def load_vectordb(self, document):
        documents = []
        pdf_path = os.path.join(self.root_path, "reviewdata", "8DD3B6.pdf")
        loader = PyPDFLoader(pdf_path)
        documents.extend(loader.load())

        pdf_path2 = os.path.join(self.root_path, "static", "uploads", document)
        loader2 = PyPDFLoader(pdf_path2)
        documents.extend(loader2.load())

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunked_documents = text_splitter.split_documents(documents)
        return Chroma.from_documents(chunked_documents, embedding=self.embeddings)

    def load_documents(self) -> None:
        documents = []

        # self.delete_db()
        for file in os.listdir(os.path.join(self.root_path, "reviewdata")):
            if file.endswith(".pdf"):
                pdf_path = os.path.join(self.root_path, "reviewdata", file)
                loader = PyPDFLoader(pdf_path)
                documents.extend(loader.load())
            elif file.endswith((".docx", ".doc")):
                doc_path = os.path.join("static", "uploads", file)
                loader = Docx2txtLoader(doc_path)
                documents.extend(loader.load())
            elif file.endswith(".txt"):
                text_path = os.path.join("static", "uploads", file)
                loader = TextLoader(text_path)
                documents.extend(loader.load())

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunked_documents = text_splitter.split_documents(documents)
        self.review_vector_db = Chroma.from_documents(
            chunked_documents,
            embedding=self.embeddings,
            persist_directory="./review_vectordb",
        )
        self.review_vector_db.persist()

    def load_contract(self, document):
        loader = PyPDFLoader(
            os.path.join(self.root_path, "static", "uploads", document),
        )
        pages = loader.load()

        return Chroma.from_documents(
            pages,
            embedding=self.embeddings,
        )
