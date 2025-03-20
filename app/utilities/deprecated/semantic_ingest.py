import sys
sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

import chromadb
import os
from app import app
from app.utilities import pdf_helper

class SemanticIngest:
    def search(self, search_term, document):
        try: 
            client = chromadb.HttpClient(host='localhost', port=5028)
            collection = client.get_collection(name=document.uuid)
            results = collection.query(
                query_texts=[search_term],
                n_results=20,
            )
            return results
        except:
            return []
    
    def delete(self, document):
        
        try:
            client = chromadb.HttpClient(host='localhost', port=5028)
            client.delete_collection(name=document.uuid)
        except:
            pass

    def check_for_collection(self, document):
        try:
            client = chromadb.HttpClient(host='localhost', port=5028)
            collection = client.get_collection(name=document.uuid)
            return True
        except:
            return False

    def ingest(self, document):
        try:
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
        except:
            pass