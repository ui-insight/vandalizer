#!/usr/bin/env python3

import os
import re
import pandas as pd
from pathlib import Path

from typing import List

from datasets import Dataset
from dspy.datasets import DataLoader

import sys


# For prod, change to pysqlite3


if "dev" in os.uname().nodename or "prod" in os.environ.get("APP_ENV", "prod"):
    import pysqlite3

    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
    # Turn off caching
    os.environ["DSP_CACHEBOOL"] = "false"
    # create a cache directory in the current working directory
    os.environ["DSP_CACHEDIR"] = os.path.join(os.getcwd(), "cache")

from app.models import Feedback

# from langchain_openai import OpenAI, ChatOpenAI, OpenAIEmbeddings
# from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain.schema import Document

import chromadb

import dspy
from dspy.evaluate import Evaluate
from dspy.teleprompt import MIPROv2, BootstrapFewShot, BootstrapFewShotWithRandomSearch

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
    "***REMOVED***"
)

# llm = OpenAI(openai_api_key=os.environ["OPENAI_API_KEY"])

embedding_model = "text-embedding-3-large"
embedding = OpenAIEmbeddings(model=embedding_model)

max_tokens = None


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
    query = dspy.OutputField(
        desc="A Retrieval Augmented Generation (RAG) search query to retrieve relevant facts"
    )


class MeaninglessQuestion(dspy.Signature):
    """Check if the question is meaningless."""

    question = dspy.InputField()
    meaningless = dspy.OutputField(desc="Yes or No")


class SimpleQA(dspy.Module):
    def __init__(self):
        super().__init__()
        self.model = dspy.ChainOfThought("context, question -> answer")
        self.meaningless = dspy.ChainOfThought(MeaninglessQuestion)

    def forward(self, question: str, full_text: str):
        # if self.meaningless(question=question).meaningless == "Yes":
        #     return dspy.Prediction(
        #         context=full_text,
        #         answer="I'm sorry, I can't answer that question.",
        #         question=question,
        #     )
        # else:
        #     pred = self.model(context=full_text, question=question)
        #     return dspy.Prediction(
        #         context=full_text, answer=pred.answer, question=question
        #     )

        pred = self.model(context=full_text, question=question)
        return dspy.Prediction(context=full_text, answer=pred.answer, question=question)


def simple_qa_model():
    model = "gpt-4o"
    llm = dspy.OpenAI(model=model)
    dspy.settings.configure(lm=llm, trace=[], temperature=0.7)
    model = SimpleQA()
    return model


class MultiHopQAModel(dspy.Module):
    def __init__(self, passages_per_hop=2, max_hops=2):
        super().__init__()

        self.generate_query = [
            dspy.ChainOfThought(GenerateSearchQuery) for _ in range(max_hops)
        ]
        self.retrieve = dspy.Retrieve(k=passages_per_hop)
        self.max_hops = max_hops
        self.generate_answer = dspy.ChainOfThought(GenerateAnswer)

        # for evaluating assertions only
        self.passed_suggestions = 0

    def forward(self, question: str):
        context = []
        prev_queries = [question]

        for hop in range(self.max_hops):
            query = self.generate_query[hop](
                context=context,
                question=question,
                config=dict(temperature=0.7 + 0.0001 * hop),
            ).query
            # prev_queries.append(query)
            prev_queries = deduplicate(prev_queries + [query])
            passages = self.retrieve(query).passages
            context = deduplicate(context + passages)

        if all_queries_distinct(prev_queries):
            self.passed_suggestions += 1

        pred = self.generate_answer(context=context, question=question)

        pred = dspy.Prediction(context=context, answer=pred.answer, question=question)
        return pred


class ProposalReview(dspy.Signature):
    """Review the proposal based on the question and provided context."""

    question = dspy.InputField()
    context = dspy.InputField(desc="may contain relevant facts")
    proposal = dspy.InputField()
    review = dspy.OutputField()


class ReviewerModel(dspy.Module):
    def __init__(self):
        super().__init__()
        self.model = dspy.ChainOfThought(ProposalReview)

    def forward(self, proposal: str, context: str, question: str):
        pred = self.model(proposal=proposal, context=context, question=question)
        return dspy.Prediction(context=context, answer=pred.review, question=question)


def proposal_review_model():
    model = "gpt-4o"
    llm = dspy.OpenAI(model=model)
    dspy.settings.configure(lm=llm, trace=[], temperature=0.7)
    model = ReviewerModel()
    return model


def dspy_model(
    full_text: str,
    collection_name: str,
    persistent_directory: Path,
):
    # model_name = "gpt-4"
    # model_name = "gpt-4-turbo"
    model_name = "gpt-4o"

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    docs = text_splitter.split_documents([Document(page_content=full_text)])

    print("collection_name: ", collection_name)

    # Check if the collection already exists

    chroma_client = chromadb.PersistentClient(path=persistent_directory.as_posix())
    # for dev server
    # chroma_client = chromadb.HttpClient(host="localhost", port=5028)

    Chroma.from_documents(
        client=chroma_client,
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

    # model 32k tokens
    llm = dspy.OpenAI(model=model_name, max_tokens=max_tokens)
    # llm = dspy.OpenAI(model=model_name, max_tokens=max_tokens)
    # llm = dspy.OpenAI(model=model_name, max_tokens=4096)
    dspy.settings.configure(lm=llm, rm=rm, trace=[], temperature=0.7)

    model = MultiHopQAModel(passages_per_hop=3, max_hops=5)
    # check if the model is already compiled
    if os.path.exists("compiled_program"):
        model.load("compiled_program")

    return model


class LLMFactJudge(dspy.Signature):
    """Judge if the answer is factually correct based on the context."""

    context = dspy.InputField(desc="Context for the prediction")
    question = dspy.InputField(desc="Question to be answered")
    answer = dspy.InputField(desc="Answer for the question")
    factually_correct = dspy.OutputField(desc="Yes or No")
    # factually_correct = dspy.OutputField(
    #     desc="Is the answer factually correct based on the context?",
    #     prefix="Factual[Yes/No]:",
    # )


class LLMAnswerJudge(dspy.Signature):
    """Judge if the predicted answer is correct based on the true answer."""

    predicted_answer = dspy.InputField(desc="Predicted answer")
    true_answer = dspy.InputField(desc="True answer")
    answer_correctness = dspy.OutputField(desc="Yes or No")
    # answer_correctness = dspy.OutputField(
    #     desc="Is the predicted answer correct based on the true answer?",
    #     prefix="Yes or No:",
    # )


class LLMAnswerFeedbackJudge(dspy.Signature):
    """Judge if the predicted answer is correct based on the context and provided feedback answer."""

    predicted_answer = dspy.InputField(desc="Predicted answer")
    feedback_answer = dspy.InputField(desc="Feedback answer")
    feedback = dspy.InputField(desc="User feedback")
    context = dspy.InputField(desc="Context for the prediction")
    answer_correctness = dspy.OutputField(desc="Yes or No")


correctness_judge = dspy.ChainOfThought(LLMAnswerJudge)
factual_judge = dspy.ChainOfThought(LLMFactJudge)
feedback_judge = dspy.ChainOfThought(LLMAnswerFeedbackJudge)


def llm_judge_metric(example, pred, trace=None):
    """
    Judge if the predicted answer is correct based on the true answer.
    Judge if the answer is factually correct based on the context.
    """
    # Check if the predicted answer is correct based on the true answer
    answer_correctness = correctness_judge(
        predicted_answer=pred.answer,
        true_answer=example.answer,
    ).answer_correctness
    answer_match = answer_correctness.lower() == "yes"

    # Check if the answer is factually correct based on the context
    factually_correct = factual_judge(
        context=pred.context,
        question=example.question,
        answer=pred.answer,
    ).factually_correct
    fact_match = factually_correct.lower() == "yes"

    # Check if the predicted answer is correct based on the context and provided feedback answer
    feedback_answer = feedback_judge(
        predicted_answer=pred.answer,
        feedback_answer=example.answer,
        feedback=example.feedback,
        context=pred.context,
    ).answer_correctness
    feedback_match = feedback_answer.lower() == "yes"

    if trace is None:  # if we're doing evaluation or optimization
        return (answer_match + fact_match + feedback_match) / 3.0
    else:  # if we're doing bootstrapping, i.e. self-generating good demonstrations of each step
        return answer_match and fact_match and feedback_match


def background_retrain_model(feedback_list, root_path):
    # Implement your model retraining code here
    print("Retraining the model with the following feedback:")

    persistent_directory = Path(root_path) / "static" / "uploads"
    collection_name = "chat_dspy_model"

    # prompt_model = dspy.OpenAI(model="gpt-4o", max_tokens=None)
    # task_model = MultiHopQAModel(
    #     passages_per_hop=3,
    #     max_hops=5,
    # )

    program = MultiHopQAModel(
        passages_per_hop=3,
        max_hops=5,
    )
    # create huggingface dataset from the feedback

    feedback_data = []

    chroma_client = chromadb.PersistentClient(path=persistent_directory.as_posix())
    rm = ChromadbRM(
        collection_name=collection_name,
        persist_directory=persistent_directory.as_posix(),
        client=chroma_client,
        embedding_function=embedding.embed_documents,
        k=3,
    )

    model_name = "gpt-4o-mini"
    # model_name = "gpt-4o"
    llm = dspy.OpenAI(model=model_name, max_tokens=max_tokens)
    # dspy.settings.configure(lm=llm, rm=rm, trace=[], temperature=0.7)
    dspy.settings.configure(lm=llm, rm=rm, trace=[])

    retriever = dspy.Retrieve(k=3)
    for feedback in feedback_list:
        # if feedback.feedback == "positive":
        docs = []
        docs.append(Document(page_content=feedback.context))

        Chroma.from_documents(
            collection_name="retrain_collection",
            documents=docs,
            persist_directory=persistent_directory.as_posix(),
            embedding=embedding,
        )
        retrieved_context = retriever(feedback.question).passages
        feedback_data.append(
            {
                "question": feedback.question,
                "answer": feedback.answer,
                "feedback": feedback.feedback,
                "context": retrieved_context,
            }
        )

    # for index, feedback in enumerate(feedback_data):
    #     if feedback.get("feeback") == "positive":
    #         retrieved_context = retriever(feedback.get("question")).passages
    #         feedback_data[index]["context"] = retrieved_context

    # dataset = Dataset.from_pandas(pd.DataFrame(feedback_data))
    # trainset = dataset.train_test_split(test_size=0.2)["train"]
    # valset = dataset.train_test_split(test_size=0.2)["test"]
    pandas_dataset = pd.DataFrame(feedback_data)
    dl = DataLoader()
    dataset = dl.from_pandas(
        pandas_dataset,
        # input_keys=("question"),
    )
    splits = dl.train_test_split(dataset)
    trainset = splits["train"]
    valset = splits["test"]
    trainset = [x.with_inputs("question") for x in trainset]
    valset = [x.with_inputs("question") for x in valset]

    NUM_THREADS = 4
    kwargs = dict(num_threads=NUM_THREADS, display_progress=True)
    # metric = answer_exact_match
    metric = llm_judge_metric

    evaluate = Evaluate(devset=trainset, metric=metric, **kwargs)

    # baseline_train_score = evaluate(program, devset=trainset)
    # print("Baseline train score: ", baseline_train_score)
    # baseline_eval_score = evaluate(program, devset=valset)

    # Compile
    N = 10  # The number of instructions and fewshot examples that we will generate and optimize over
    batches = 30  # The number of optimization trials to be run (we will test out a new combination of instructions and fewshot examples in each trial)
    temperature = 1.0  # The temperature configured for generating new instructions

    eval_kwargs = dict(num_threads=16, display_progress=True, display_table=2)
    # teleprompter = MIPROv2(
    #     prompt_model=prompt_model,
    #     task_model=task_model,
    #     metric=metric,
    #     num_candidates=N,
    #     init_temperature=temperature,
    #     verbose=True,
    # )

    teleprompter = BootstrapFewShot(
        metric=metric,
        # max_bootstrapped_demos=2,
        # max_labeled_demos=2,
    )
    # teleprompter = BootstrapFewShotWithRandomSearch(
    #     metric=metric,
    #     # max_bootstrapped_demos=2,
    #     # max_labeled_demos=2,
    # )

    compiled_program = teleprompter.compile(
        program,
        trainset=trainset,
        # num_batches=batches,
        # max_bootstrapped_demos=1,
        # max_labeled_demos=2,
        # eval_kwargs=eval_kwargs,
    )

    # TODO maybe use LabeledFewShot to optimize the prompt use both positive and negative feedback

    # Evaluate the compiled program
    bayesian_train_score = evaluate(compiled_program, devset=trainset)
    bayesian_eval_score = evaluate(compiled_program, devset=valset)
    print("Bayesian train score: ", bayesian_train_score)
    print("Bayesian eval score: ", bayesian_eval_score)

    # save the model
    compiled_program.save("compiled_program")
    llm.inspect_history(n=5)
