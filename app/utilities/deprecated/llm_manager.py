import os

from langchain.chains import AnalyzeDocumentChain, ConversationalRetrievalChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.summarize import load_summarize_chain
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,  # pdf loading
    TextLoader,
)
from langchain.embeddings import OpenAIEmbeddings  # embeddings
from langchain.llms import OpenAI
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores import Chroma  # vector store

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class LLMManager:
    pdf_loaded = False
    vectordb = None
    singlevectordb = None
    root_path = ""
    embeddings = None
    single_document = False
    document_name = ""

    def __init__(self):
        # Load in Vector Database
        self.embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        self.vectordb = self.vectordb = Chroma(
            embedding_function=self.embeddings, persist_directory="./vectordb"
        )
        print("There are", self.vectordb._collection.count(), "in the collection")

    def ask_openai(self):
        llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY)
        text = "What is the meaning of life?"
        llm.predict(text)
        pass

    def ask_question_no_langchain(self, document_path, question):
        # Load the document from the given path
        full_path = os.path.join(self.root_path, "static", "uploads", document_path)
        loader = TextLoader(full_path)
        documents = loader.load()

        # Create a question-answering chain using OpenAI's language model
        llm = OpenAI()
        qa_chain = load_qa_chain(llm, chain_type="stuff")

        # Ask the question and get the answer
        answer = qa_chain.run(input_documents=documents, question=question)

        return answer

    def test_documents(self):
        llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY)

        query = "What is the title?"
        print(query)

        retreiver = self.vectordb.as_retriever(search_kwargs={"k": 1})
        # retreiver.get(where={'source': path1})
        print(retreiver.get_relevant_documents(query)[0])

        print("\n\n")
        pdf_qa = ConversationalRetrievalChain.from_llm(
            llm, retreiver, return_source_documents=True
        )

        result = pdf_qa({"question": query, "chat_history": ""})
        print("\n\n")
        print(result["answer"])

        query = "What is the title?"
        path = os.path.join(self.root_path, "static", "uploads", "6B66AA.pdf")
        print(query)
        retreiver = self.vectordb.as_retriever(search_kwargs={"source": path})
        print(retreiver.get_relevant_documents(query)[0])
        print("\n\n")
        pdf_qa = ConversationalRetrievalChain.from_llm(
            llm, retreiver, return_source_documents=True
        )

        result = pdf_qa({"question": query, "chat_history": ""})
        print(result["answer"])

    def ask_all_documents(self, space, question):
        llm = ChatOpenAI(model_name="gpt-3.5-turbo-16k", openai_api_key=OPENAI_API_KEY)
        pdf_qa = ConversationalRetrievalChain.from_llm(
            llm,
            self.vectordb.as_retriever(search_kwargs={"k": 6}),
            return_source_documents=True,
        )

        result = pdf_qa({"question": question, "chat_history": ""})
        return result["answer"]

    def ask_single_document(self, question, document, model_name="gpt-3.5-turbo-16k"):
        if self.document_name != document or self.singlevectordb is None:
            print("Loading document into LLM", document)
            loader = PyPDFLoader(
                os.path.join(self.root_path, "static", "uploads", document)
            )
            loader.load()
            pages = loader.load_and_split()
            # New vector store code
            if self.singlevectordb is not None:
                self.singlevectordb.delete_collection()
            self.singlevectordb = Chroma.from_documents(
                pages, embedding=self.embeddings
            )
            self.document_name = document
        else:
            print("Document already loaded into LLM", document)

        if model_name == "gpt-4" or model_name == "gpt-3.5-turbo-16k":
            llm = ChatOpenAI(model_name=model_name, openai_api_key=OPENAI_API_KEY)
        else:
            llm = OpenAI(model_name=model_name, openai_api_key=OPENAI_API_KEY)

        pdf_qa = ConversationalRetrievalChain.from_llm(
            llm, self.singlevectordb.as_retriever(search_kwargs={"k": 1})
        )

        result = pdf_qa({"question": question, "chat_history": ""})
        return result["answer"]

    def summarize_document(self, document, model_name="text-davinci-003"):
        loader = PyPDFLoader(
            os.path.join(self.root_path, "static", "uploads", document)
        )
        loader.load()
        pages = loader.load()
        llm = OpenAI(model_name=model_name, openai_api_key=OPENAI_API_KEY)
        summary_chain = load_summarize_chain(llm, chain_type="map_reduce")
        summarize_document_chain = AnalyzeDocumentChain(
            combine_docs_chain=summary_chain
        )
        str = ""
        for page in pages:
            str += page + " "

        summarize_document_chain.run(str)

    def ask_single_document_chained(self, question, document):
        loader = PyPDFLoader(
            os.path.join(self.root_path, "static", "uploads", document)
        )
        loader.load()
        pages = loader.load()
        llm = OpenAI(model_name="text-davinci-003", openai_api_key=OPENAI_API_KEY)
        qa_chain = load_qa_chain(llm, chain_type="map_reduce")
        qa_document_chain = AnalyzeDocumentChain(combine_docs_chain=qa_chain)
        str = ""
        for page in pages:
            str += page + " "

        qa_document_chain.run(input_document=str, question=question)

    def load_pdf(self, document=""):
        loader = PyPDFLoader(
            os.path.join(self.root_path, "static", "uploads", document.path)
        )
        loader.load()
        pages = loader.load_and_split()
        # New vector store code
        self.vectordb = Chroma.from_documents(
            pages,
            embedding=self.embeddings,
            persist_directory="./datastores/" + document.space,
        )
        self.vectordb.persist()

        pass

    def stats(self):
        print("There are", self.vectordb._collection.count(), "in the collection")

    def delete_db(self):
        self.vectordb.delete_collection()
        self.vectordb.persist()

    def load_documents(self):
        documents = []
        self.delete_db()
        for file in os.listdir("app/data"):
            if file.endswith(".pdf"):
                pdf_path = os.path.join(self.root_path, "static", "uploads", file)
                loader = PyPDFLoader(pdf_path)
                documents.extend(loader.load())
            elif file.endswith(".docx") or file.endswith(".doc"):
                doc_path = os.path.join(self.root_path, "static", "uploads", file)
                loader = Docx2txtLoader(doc_path)
                documents.extend(loader.load())
            elif file.endswith(".txt"):
                text_path = os.path.join(self.root_path, "static", "uploads", file)
                loader = TextLoader(text_path)
                documents.extend(loader.load())

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=10)
        chunked_documents = text_splitter.split_documents(documents)
        self.vectordb = Chroma.from_documents(
            chunked_documents, embedding=self.embeddings, persist_directory="./vectordb"
        )
        self.vectordb.persist()
