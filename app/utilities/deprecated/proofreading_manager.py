class ProofreadingManager:
    llmManager = None
    document_sections = []
    compliance_results = []

    def __init__(self, manager):
        self.llmManager = manager

    def get_spelling_corrections(self, document):
        print("Getting spelling corrections for document: " + document)
        prompt = "You are a professional editor, generate list of all spelling mistakes in the document. Format them as a csv, if there are none simply response: None"
        print("Prompt: " + prompt)
        document_sections = self.llmManager.ask_single_document(prompt, document)
        return document_sections

    def get_grammar_corrections(self, document):
        print("Getting grammar corrections for document: " + document)
        prompt = "You are a professional editor, generate list of all grammar and typographic mistakes or improvements in the document. Format them as a csv, if there are none simply response: None"
        print("Prompt: " + prompt)
        document_sections = self.llmManager.ask_single_document(prompt, document)
        return document_sections

    def get_suggestions(self, document):
        print("Getting suggestions for document: " + document)
        prompt = "Make at least 5 and no more than 20 suggestions for improvements in the grammar, formatting or structure of the document. Format them as a csv with no extra information."
        print("Prompt: " + prompt)
        document_sections = self.llmManager.ask_single_document(prompt, document)
        return document_sections

    def scan_document(self, document, scan):
        print("Getting suggestions for document: " + document)
        prompt = (
            "Scan the document for all: "
            + scan
            + ". Format them as a csv with no extra information."
        )
        print("Prompt: " + prompt)
        document_sections = self.llmManager.ask_single_document(prompt, document)
        return document_sections
