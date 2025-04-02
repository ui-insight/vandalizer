import nltk
import PyPDF2


# Load PDF
def chunk_pdf(pdf_path):
    pdf_file = open(pdf_path, "rb")
    pdf_reader = PyPDF2.PdfReader(pdf_file)

    # Extract text
    pdf_text = ""
    for page in range(len(pdf_reader.pages)):
        page_text = pdf_reader.pages[page].extract_text()
        pdf_text += page_text

    # Split text into paragraphs
    paragraphs = pdf_text.split("\n\n")

    # Tokenize paragraphs into sentences
    sentences = [nltk.sent_tokenize(p) for p in paragraphs]
    sentences = [s for sents in sentences for s in sents]

    # Tokenize sentences into words
    tokenized_sentences = [nltk.word_tokenize(sent) for sent in sentences]

    # Extract n-grams (phrases) from sentences
    n = 3
    ngrams = [list(nltk.ngrams(sent, n)) for sent in tokenized_sentences]

    phrases = [p for ng in ngrams for p in ng]

    three_word_phrases = [" ".join(phrase) for phrase in phrases if len(phrase) == 3]
    return sentences + three_word_phrases
