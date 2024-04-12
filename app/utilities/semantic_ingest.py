import chromadb
from chromadb.config import Settings
import os
from app import app
from app.models import SmartDocument
from app.utilities import pdf_helper
import nltk

class SemanticIngest:
    def search(self, search_term, document):
        client = chromadb.HttpClient(host='localhost', port=5028)
        collection = client.get_collection(name=document.uuid)
        results = collection.query(
            query_texts=[search_term],
            n_results=20,
        )
        return results
    
    def delete(self, document):
        client = chromadb.HttpClient(host='localhost', port=5028)
        client.delete_collection(name=document.uuid)

    def ingest(self, document):
        client = chromadb.HttpClient(host='localhost', port=5028)
        collection = client.create_collection(name=document.uuid)
        
        print("Ingesting " + str(document.uuid))
        path = os.path.join(app.root_path, 'static', 'uploads', f"{document.uuid}.pdf")
        chunks = pdf_helper.chunk_pdf(path)
        metadatas = []
        ids = []

        for i, chunk in enumerate(chunks):
            metadatas.append({'source':  str(document.uuid)})
            ids.append("Part: " + str(i))

        collection.add(
            documents = chunks,
            metadatas = metadatas,
            ids = ids
        )