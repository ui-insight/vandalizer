#!/usr/bin/env python3

import os
import re
import pandas as pd
from pathlib import Path

from typing import List

from datasets import Dataset

# from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain.schema import Document

from app.models import Feedback

# from langchain_openai import OpenAI, ChatOpenAI, OpenAIEmbeddings

import chromadb

import dspy
from dspy.evaluate import Evaluate
from dspy.teleprompt import MIPROv2

from dsp.utils import deduplicate

from dspy.retrieve.chromadb_rm import ChromadbRM
from dspy.evaluate.metrics import (
    answer_exact_match,
    answer_exact_match_str,
    answer_passage_match,
)

from langchain.text_splitter import (
    RecursiveCharacterTextSplitter,
)

from langchain_community.document_loaders import PyPDFLoader


from langchain_openai import OpenAIEmbeddings


from pathlib import Path
import dotenv


dotenv.load_dotenv()
os.environ["OPENAI_API_KEY"] = (
    "sk-proj-Tdb51ojrv5lwDtPH9S3tT3BlbkFJ6ty7hYO3Ow8weqXu6UjM"
)


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def sanitize_filename(filename: str) -> str:
    # Remove file extension
    name_without_extension = Path(filename).stem

    # Replace spaces and special characters with underscores
    sanitized = re.sub(r"[^\w\-_\.]", "_", name_without_extension)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    # Ensure the name starts with a letter or underscore
    if not sanitized[0].isalpha() and sanitized[0] != "_":
        sanitized = f"_{sanitized}"

    # Limit the length (Chroma might have a maximum length for collection names)
    max_length = 63  # Adjust this if Chroma has a different limit
    sanitized = sanitized[:max_length]

    return sanitized


def validate_query_distinction_local(previous_queries, query):
    """check if query is distinct from previous queries"""
    if previous_queries == []:
        return True
    if answer_exact_match_str(query, previous_queries, frac=0.8):
        return False
    return True


def validate_context_and_answer_and_hops(example, pred, trace=None):
    if not answer_exact_match(example, pred):
        return False

    if not answer_passage_match(example, pred):
        return False

    return True


def all_queries_distinct(prev_queries):
    query_distinct = True
    for i, query in enumerate(prev_queries):
        if validate_query_distinction_local(prev_queries[:i], query) == False:
            query_distinct = False
            break
    return query_distinct


class GenerateAnswer(dspy.Signature):
    """Answer questions based on the provided context."""

    context = dspy.InputField(desc="may contain relevant facts")
    question = dspy.InputField()
    answer = dspy.OutputField()


class GenerateSearchQuery(dspy.Signature):
    """Write a simple search query that will help answer a complex question."""

    context = dspy.InputField(desc="may contain relevant facts")
    question = dspy.InputField(desc="complex question")
    query = dspy.OutputField(desc="A search query/question to retrieve relevant facts")


class MultiHopQAModel(dspy.Module):
    def __init__(self, passages_per_hop=2, max_hops=2):
        super().__init__()

        self.generate_query = [
            dspy.ChainOfThought(GenerateSearchQuery) for _ in range(max_hops)
        ]
        self.retrieve = dspy.Retrieve(k=passages_per_hop)
        # TODO add pappg as the main context
        # self.main_context =
        self.generate_answer = dspy.ChainOfThought(GenerateAnswer)
        self.max_hops = max_hops
        # self.critic = dspy.ChainOfThought("answer->critic")

        # for evaluating assertions only
        self.passed_suggestions = 0

    def forward(self, question):
        context = []
        prev_queries = [question]

        for hop in range(self.max_hops):
            query = self.generate_query[hop](context=context, question=question).query
            # prev_queries.append(query)
            prev_queries = deduplicate(prev_queries + [query])
            passages = self.retrieve(query).passages
            context = deduplicate(context + passages)

        if all_queries_distinct(prev_queries):
            self.passed_suggestions += 1

        pred = self.generate_answer(context=context, question=question)
        pred = dspy.Prediction(context=context, answer=pred.answer)
        return pred, prev_queries


# llm = OpenAI(openai_api_key=os.environ["OPENAI_API_KEY"])

embedding_model = "text-embedding-3-large"
embedding = OpenAIEmbeddings(model=embedding_model)


def get_document_splits(document: str, file_path: Path, persistent_directory: Path):
    # get the file_path from the user's storage

    loader = PyPDFLoader(file_path.as_posix())
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    return splits


def get_retriever(document: str, file_path, persistent_directory: Path):
    splits = get_document_splits(document, file_path)
    collection_name = sanitize_filename(document)

    vectordb = Chroma.from_documents(
        persist_directory=persistent_directory,
        collection_name=collection_name,
        documents=splits,
        embedding=embedding,
    )

    retriever = vectordb.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 3},
    )
    return retriever


def dspy_model(
    full_text: str,
    collection_name: str,
    persistent_directory: Path,
):
    # model_name = "gpt-4"
    # model_name = "gpt-4-turbo"
    model_name = "gpt-4o"
    # Example questions
    # "What are the rules around personnel funding?"
    # "What are the required sections of the proposal?"
    # "What are the required sections of the proposal and what are their page limits?"

    # pdf_directory = storage_path.as_posix()

    # print("Resolved pdf_directory: ", pdf_directory)
    # print("Files in directory: ", os.listdir(pdf_directory))

    # loader = DirectoryLoader(pdf_directory, glob="*.pdf", loader_cls=PyPDFLoader)

    # # Load the documents
    # docs = loader.load()

    # collection_name = sanitize_collection_name(document.filename)

    # docs = [Document(page_content=full_text, metadata={"source": "user_input"})]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = text_splitter.split_documents([Document(page_content=full_text)])

    print("collection_name: ", collection_name)

    # Check if the collection already exists

    chroma_client = chromadb.PersistentClient(path=persistent_directory.as_posix())
    # existing_collections = chroma_client.list_collections()
    # collection_exists = any(col.name == collection_name for col in existing_collections)

    # # TODO check if the collection exists using the count of uploaded documents. If the count is different, recreate the collection
    # if not collection_exists:
    # print(f"Creating new collection '{collection_name}'")
    Chroma.from_documents(
        collection_name=collection_name,
        documents=docs,
        persist_directory=persistent_directory.as_posix(),
        embedding=embedding,
    )

    rm = ChromadbRM(
        collection_name=collection_name,
        persist_directory=persistent_directory.as_posix(),
        client=chroma_client,
        embedding_function=embedding.embed_documents,
        k=3,
    )

    # model
    # llm = dspy.OpenAI(model=model_name, max_tokens=max_tokens)
    llm = dspy.OpenAI(model=model_name, max_tokens=None)
    dspy.settings.configure(lm=llm, rm=rm, trace=[], temperature=0.7)

    model = MultiHopQAModel(passages_per_hop=3, max_hops=5)

    return model


def background_retrain_model(feedback_list, root_path):
    # Implement your model retraining code here
    print("Retraining the model with the following feedback:")

    persistent_directory = Path(root_path) / "static" / "uploads"
    collection_name = "chat_dspy_model"

    prompt_model = dspy.OpenAI(model="gpt-4o", max_tokens=None)
    task_model = MultiHopQAModel(
        passages_per_hop=3,
        max_hops=5,
    )

    program = MultiHopQAModel(
        passages_per_hop=3,
        max_hops=5,
    )
    # create huggingface dataset from the feedback

    feedback_data = []

    for feedback in feedback_list:
        if feedback.feedback == "positive":
            feedback_data.append(
                {
                    "question": feedback.question,
                    "answer": feedback.response,
                }
            )

    dataset = Dataset.from_pandas(pd.DataFrame(feedback_data))
    trainset = dataset.train_test_split(test_size=0.2)["train"]
    valset = dataset.train_test_split(test_size=0.2)["test"]

    metric = dspy.evaluate.answer_exact_match

    NUM_THREADS = 4
    kwargs = dict(num_threads=NUM_THREADS, display_progress=True)
    evaluate = Evaluate(devset=valset, metric=metric, **kwargs)

    baseline_train_score = evaluate(program, devset=trainset)
    baseline_eval_score = evaluate(program, devset=valset)

    # Compile
    N = 10  # The number of instructions and fewshot examples that we will generate and optimize over
    batches = 30  # The number of optimization trials to be run (we will test out a new combination of instructions and fewshot examples in each trial)
    temperature = 1.0  # The temperature configured for generating new instructions

    eval_kwargs = dict(num_threads=16, display_progress=True, display_table=0)
    teleprompter = MIPROv2(
        prompt_model=prompt_model,
        task_model=task_model,
        metric=metric,
        num_candidates=N,
        init_temperature=temperature,
        verbose=True,
    )
    compiled_program = teleprompter.compile(
        program,
        trainset=trainset,
        valset=valset,
        num_batches=batches,
        max_bootstrapped_demos=1,
        max_labeled_demos=2,
        eval_kwargs=eval_kwargs,
    )

    # Evaluate the compiled program
    bayesian_train_score = evaluate(compiled_program, devset=trainset)
    bayesian_eval_score = evaluate(compiled_program, devset=valset)

    # save the model
    compiled_program.save("compiled_program")
