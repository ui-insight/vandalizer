# import os

# from langchain.callbacks import get_openai_callback
# from langchain.chains import ConversationalRetrievalChain
# from langchain.chat_models import ChatOpenAI
# from langchain.document_loaders import PyPDFLoader  # pdf loading
# from langchain.embeddings import OpenAIEmbeddings  # embeddings
# from langchain.llms import OpenAI
# from langchain.text_splitter import CharacterTextSplitter
# from langchain.vectorstores import Chroma  # vector store

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# class PromptLabManager:
#     llmManager = None
#     review_vector_db = None
#     embeddings = None
#     root_path = ""

#     def __init__(self) -> None:
#         self.embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

#     def run(self, model, promptChain, documents, vector):
#         ## LLM
#         if model in {"gpt-4", "gpt-3.5-turbo-16k", "gpt-3.5-turbo"}:
#             llm = ChatOpenAI(model_name=model, openai_api_key=OPENAI_API_KEY)
#         else:
#             llm = OpenAI(model_name=model, openai_api_key=OPENAI_API_KEY)

#         ## Document Loading and Vector Creation

#         with get_openai_callback() as cb:
#             documentdb = self.load_vectordb(documents)
#             pdf_qa = ConversationalRetrievalChain.from_llm(
#                 llm,
#                 documentdb.as_retriever(search_kwargs={"k": len(documents)}),
#                 verbose=True,
#             )
#             result = pdf_qa({"question": promptChain, "chat_history": ""})

#             return result["answer"], str(cb)

#     ##########################################
#     ## Document Loading and Vector Creation ##
#     ##########################################
#     def load_vectordb(self, documents):
#         split_documents = []
#         for document in documents:
#             pdf_path = os.path.join(self.root_path, "static", "uploads", document)
#             loader = PyPDFLoader(pdf_path)
#             split_documents.extend(loader.load())

#         text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
#         chunked_documents = text_splitter.split_documents(split_documents)
#         return Chroma.from_documents(chunked_documents, embedding=self.embeddings)

#     def load_text_chunks(self, documents) -> None:
#         loader = PyPDFLoader(
#             os.path.join(self.root_path, "static", "uploads", document),
#         )
#         docs = loader.load()
#         # text_splitter = CharacterTextSplitter(chunk_size=15000, chunk_overlap=0)
#         # docs = text_splitter.split_documents(loader.load())
#         doc_string = ""
#         for doc in docs:
#             doc_string += doc.page_content + " "
