class ProofreadingManager:
    llmManager = None
    document_sections = []
    compliance_results = []

    def __init__(self, manager) -> None:
        self.llmManager = manager

    def get_spelling_corrections(self, document):
        prompt = "You are a professional editor, generate list of all spelling mistakes in the document. Format them as a csv, if there are none simply response: None"
        return self.llmManager.ask_single_document(prompt, document)

    def get_grammar_corrections(self, document):
        prompt = "You are a professional editor, generate list of all grammar and typographic mistakes or improvements in the document. Format them as a csv, if there are none simply response: None"
        return self.llmManager.ask_single_document(prompt, document)

    def get_suggestions(self, document):
        prompt = "Make at least 5 and no more than 20 suggestions for improvements in the grammar, formatting or structure of the document. Format them as a csv with no extra information."
        return self.llmManager.ask_single_document(prompt, document)

    def scan_document(self, document, scan):
        prompt = (
            "Scan the document for all: "
            + scan
            + ". Format them as a csv with no extra information."
        )
        return self.llmManager.ask_single_document(prompt, document)
