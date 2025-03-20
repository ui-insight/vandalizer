import openai
import time
import os
from app.utilities.document_readers import extract_text_from_doc

# from langfuse.decorators import observe
# from langfuse import Langfuse

from app.utilities.agents import extract_entities_with_agent

# langfuse = Langfuse()

# trace = langfuse.trace()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ExtractionManager3:
    root_path = ""

    def extract(self, extract_keys, pdf_paths, full_text=None):
        api_key = OPENAI_API_KEY

        # extractor = EntityExtractor(api_key)

        # if extract_keys is string convert to list by splitting on comma
        if isinstance(extract_keys, str):
            fields_to_extract = extract_keys.split(",")
        else:
            fields_to_extract = extract_keys
        # Extract entities

        print("Extracting keys: ", extract_keys, pdf_paths)

        start_time = time.time()
        openai.api_key = OPENAI_API_KEY
        doc_text = ""
        extractions = []
        start_time = time.time()
        if full_text is None:
            for pdf_path in pdf_paths:
                doc_text = extract_text_from_doc(doc_path=pdf_path)
                if doc_text:
                    # data = extractor.extract_entities(doc_text, fields_to_extract)
                    data = extract_entities_with_agent(
                        text=doc_text, keys=fields_to_extract
                    )
                    extractions = data
                    print("Data item: ", data)
                    print("Extracting: ", extractions)

        else:
            doc_text = full_text
            data = extract_entities_with_agent(text=doc_text, keys=fields_to_extract)
            # data = extractor.extract_entities(doc_text, fields_to_extract)
            extractions = data

        # model = "gpt-3.5-turbo-0125"
        # if len(prompt) > 50000:
        #    model = "gpt-4-turbo"

        print("Extraction: ", extractions)
        # print(data.model_dump_json(indent=2))

        print(f"Completion processing time: {time.time() - start_time:.2f} seconds")

        return extractions
