# #!/usr/bin/env python3

# import os
# import re
# import sys
# from pathlib import Path
# from typing import Literal

# import dspy
# import pandas as pd
# from dspy.datasets import DataLoader

# from app.utilities.llm import InsightLM

# # from dsp.trackers.langfuse_tracker import LangfuseTracker
# # from langfuse.decorators import observe


# # For prod, change to pysqlite3

# if "dev" in os.uname().nodename or "prod" in os.environ.get("APP_ENV", "prod"):
#     sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
#     # Turn off caching
#     os.environ["DSP_CACHEBOOL"] = "false"
#     # create a cache directory in the current working directory
#     os.environ["DSP_CACHEDIR"] = os.path.join(os.getcwd(), "cache")


# # from langchain_openai import OpenAI, ChatOpenAI, OpenAIEmbeddings
# # from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
# import chromadb
# import dotenv
# from dsp.utils import deduplicate
# from dspy.evaluate import Evaluate
# from dspy.evaluate.metrics import (
#     answer_exact_match,
#     answer_exact_match_str,
#     answer_passage_match,
# )
# from dspy.retrieve.chromadb_rm import ChromadbRM
# from dspy.teleprompt import BootstrapFewShot
# from langchain.schema import Document
# from langchain.text_splitter import (
#     RecursiveCharacterTextSplitter,
# )
# from langchain_chroma import Chroma
# from langchain_openai import OpenAIEmbeddings
# from langchain_text_splitters import RecursiveCharacterTextSplitter

# dotenv.load_dotenv()

# # embedding_model = "text-embedding-3-large"
# # embedding = OpenAIEmbeddings(model=embedding_model)

# max_tokens = 1024 * 128
# # max_tokens = None


# # class CustomTracker(LangfuseTracker):

# #     def call(self, *args, **kwargs):
# #         # Call the super class method if needed
# #         super().call(**kwargs)

# #         # Unpack args if they are being used to pass i, o, etc.
# #         i = kwargs.get("i")
# #         o = kwargs.get("o")
# #         name = kwargs.get("name")
# #         o_content = o.choices[0].message.content if o else None

# #         # Log trace to Langfuse via low-level SDK
# #         trace = self.langfuse.trace(name="custom-tracker", input=i, output=o_content)
# #         trace.generation(
# #             input=i,
# #             output=o_content,
# #             name=name,
# #             metadata=kwargs,
# #             usage_details=o.usage,
# #             model=o.model,
# #         )


# def format_docs(docs):
#     return "\n\n".join(doc.page_content for doc in docs)


# def sanitize_filename(filename: str) -> str:
#     # Remove file extension
#     name_without_extension = Path(filename).stem

#     # Replace spaces and special characters with underscores
#     sanitized = re.sub(r"[^\w\-_\.]", "_", name_without_extension)

#     # Remove leading/trailing underscores
#     sanitized = sanitized.strip("_")

#     # Ensure the name starts with a letter or underscore
#     if not sanitized[0].isalpha() and sanitized[0] != "_":
#         sanitized = f"_{sanitized}"

#     # Limit the length (Chroma might have a maximum length for collection names)
#     max_length = 63  # Adjust this if Chroma has a different limit
#     return sanitized[:max_length]


# def validate_query_distinction_local(previous_queries, query) -> bool:
#     """Check if query is distinct from previous queries."""
#     if previous_queries == []:
#         return True
#     return not answer_exact_match_str(query, previous_queries, frac=0.8)


# def validate_context_and_answer_and_hops(example, pred, trace=None) -> bool:
#     if not answer_exact_match(example, pred):
#         return False

#     return answer_passage_match(example, pred)


# def all_queries_distinct(prev_queries):
#     query_distinct = True
#     for i, query in enumerate(prev_queries):
#         if validate_query_distinction_local(prev_queries[:i], query) is False:
#             query_distinct = False
#             break
#     return query_distinct


# class GenerateAnswer(dspy.Signature):
#     """Answer questions based on the provided context."""

#     context: str = dspy.InputField(desc="may contain relevant facts")
#     question: str = dspy.InputField()
#     answer: str = dspy.OutputField()


# class GenerateSearchQuery(dspy.Signature):
#     """Write a simple search query that will help answer a complex question."""

#     context: str = dspy.InputField(desc="may contain relevant facts")
#     question: str = dspy.InputField(desc="complex question")
#     query: str = dspy.OutputField(
#         desc="A Retrieval Augmented Generation (RAG) search query to retrieve relevant facts",
#     )


# class SimpleQA(dspy.Module):
#     def __init__(self) -> None:
#         super().__init__()
#         self.model = dspy.ChainOfThought("context, question -> answer")

#     def forward(self, question: str, full_text: str):
#         pred = self.model(context=full_text, question=question)
#         return dspy.Prediction(context=full_text, answer=pred.answer, question=question)


# # @observe()
# def simple_qa(question, full_text, model_type="openai/gpt-4o"):
#     llm = None
#     # langfuse = LangfuseTracker()
#     if model_type == "insight":
#         llm = InsightLM(max_tokens=max_tokens)
#         dspy.configure(lm=llm, trace=[])
#     else:
#         model = "openai/gpt-4o"
#         llm = dspy.LM(model=model)
#         dspy.configure(lm=llm, trace=[], temperature=0.7)
#     model = SimpleQA()
#     return model(question=question, full_text=full_text)


# class MultiHopQAModel(dspy.Module):
#     def __init__(self, passages_per_hop=2, max_hops=2) -> None:
#         super().__init__()

#         self.generate_query = [
#             dspy.ChainOfThought(GenerateSearchQuery, max_tokens=4 * 1024)
#             for _ in range(max_hops)
#         ]
#         self.retrieve = dspy.Retrieve(k=passages_per_hop)
#         self.max_hops = max_hops
#         self.generate_answer = dspy.ChainOfThought(GenerateAnswer, max_tokens=None)

#         # for evaluating assertions only
#         self.passed_suggestions = 0

#     def forward(self, question: str):
#         context = []
#         prev_queries = [question]

#         for hop in range(self.max_hops):
#             query = self.generate_query[hop](
#                 context=context,
#                 question=question,
#                 config={"temperature": 0.7 + 0.0001 * hop},
#             ).query
#             # prev_queries.append(query)
#             prev_queries = deduplicate([*prev_queries, query])
#             passages = self.retrieve(query).passages
#             context = deduplicate(context + passages)

#         if all_queries_distinct(prev_queries):
#             self.passed_suggestions += 1

#         pred = self.generate_answer(context=context, question=question)

#         return dspy.Prediction(context=context, answer=pred.answer, question=question)


# def dspy_model(
#     full_text: str,
#     collection_name: str,
#     persistent_directory: Path,
#     model_type: str,
# ):
#     # model_name = "gpt-4"
#     # model_name = "gpt-4-turbo"
#     model_name = "openai/gpt-4o"

#     text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=100)
#     docs = text_splitter.split_documents([Document(page_content=full_text)])


#     # Check if the collection already exists

#     chroma_client = chromadb.PersistentClient(path=persistent_directory.as_posix())
#     # for dev server
#     # chroma_client = chromadb.HttpClient(host="localhost", port=5028)

#     embedding_model = "text-embedding-3-large"
#     embedding = OpenAIEmbeddings(model=embedding_model)

#     Chroma.from_documents(
#         client=chroma_client,
#         collection_name=collection_name,
#         documents=docs,
#         persist_directory=persistent_directory.as_posix(),
#         embedding=embedding,
#     )

#     rm = ChromadbRM(
#         collection_name=collection_name,
#         persist_directory=persistent_directory.as_posix(),
#         client=chroma_client,
#         embedding_function=embedding.embed_documents,
#         k=3,
#     )

#     # langfuse = LangfuseTracker()
#     llm = None
#     if model_type == "insight":
#         llm = InsightLM(max_tokens=max_tokens)
#     else:
#         # model 32k tokens
#         llm = dspy.LM(model=model_name, max_tokens=max_tokens)
#         # llm = dspy.OpenAI(model=model_name, max_tokens=max_tokens)
#         # llm = dspy.OpenAI(model=model_name, max_tokens=4096)
#     dspy.configure(lm=llm, rm=rm, trace=[], temperature=0.7)

#     model = MultiHopQAModel(passages_per_hop=3, max_hops=5)
#     # check if the model is already compiled
#     if os.path.exists("compiled_program"):
#         model.load("compiled_program")

#     return model


# # @observe()
# def multi_qa(question, full_text, collection_name, persistent_directory, model_type):
#     model = dspy_model(full_text, collection_name, persistent_directory, model_type)
#     return model(question=question)


# class LLMFactJudge(dspy.Signature):
#     """Judge if the answer is factually correct based on the context."""

#     context: str = dspy.InputField(desc="Context for the prediction")
#     question: str = dspy.InputField(desc="Question to be answered")
#     answer: str = dspy.InputField(desc="Answer for the question")
#     factually_correct: str = dspy.OutputField(desc="Yes or No")
#     # factually_correct = dspy.OutputField(
#     #     desc="Is the answer factually correct based on the context?",
#     #     prefix="Factual[Yes/No]:",
#     # )


# class LLMAnswerJudge(dspy.Signature):
#     """Judge if the predicted answer is correct based on the true answer."""

#     predicted_answer: str = dspy.InputField(desc="Predicted answer")
#     true_answer: str = dspy.InputField(desc="True answer")
#     answer_correctness: Literal["Yes", "No"] = dspy.OutputField()
#     # answer_correctness = dspy.OutputField(
#     #     desc="Is the predicted answer correct based on the true answer?",
#     #     prefix="Yes or No:",
#     # )


# class LLMAnswerFeedbackJudge(dspy.Signature):
#     """Judge if the predicted answer is correct based on the context and provided feedback answer."""

#     predicted_answer = dspy.InputField(desc="Predicted answer")
#     feedback_answer = dspy.InputField(desc="Feedback answer")
#     feedback = dspy.InputField(desc="User feedback")
#     context = dspy.InputField(desc="Context for the prediction")
#     answer_correctness = dspy.OutputField(desc="Yes or No")


# correctness_judge = dspy.ChainOfThought(LLMAnswerJudge, max_tokens=max_tokens)
# factual_judge = dspy.ChainOfThought(LLMFactJudge, max_tokens=max_tokens)
# feedback_judge = dspy.ChainOfThought(LLMAnswerFeedbackJudge, max_tokens=max_tokens)


# def llm_judge_metric(example, pred, trace=None):
#     """Judge if the predicted answer is correct based on the true answer.
#     Judge if the answer is factually correct based on the context.
#     """
#     # Check if the predicted answer is correct based on the true answer
#     answer_correctness = correctness_judge(
#         predicted_answer=pred.answer,
#         true_answer=example.answer,
#     ).answer_correctness
#     answer_match = answer_correctness.lower() == "yes"

#     # Check if the answer is factually correct based on the context
#     factually_correct = factual_judge(
#         context=pred.context,
#         question=example.question,
#         answer=pred.answer,
#     ).factually_correct
#     fact_match = factually_correct.lower() == "yes"

#     # Check if the predicted answer is correct based on the context and provided feedback answer
#     feedback_answer = feedback_judge(
#         predicted_answer=pred.answer,
#         feedback_answer=example.answer,
#         feedback=example.feedback,
#         context=pred.context,
#     ).answer_correctness
#     feedback_match = feedback_answer.lower() == "yes"

#     if trace is None:  # if we're doing evaluation or optimization
#         return (answer_match + fact_match + feedback_match) / 3.0
#     # if we're doing bootstrapping, i.e. self-generating good demonstrations of each step
#     return answer_match and fact_match and feedback_match


# def background_retrain_model(feedback_list, root_path) -> None:
#     # Implement your model retraining code here

#     persistent_directory = Path(root_path) / "static" / "uploads"
#     collection_name = "chat_dspy_model"

#     # prompt_model = dspy.OpenAI(model="gpt-4o", max_tokens=None)
#     # task_model = MultiHopQAModel(
#     #     passages_per_hop=3,
#     #     max_hops=5,
#     # )

#     program = MultiHopQAModel(
#         passages_per_hop=3,
#         max_hops=5,
#     )
#     # create huggingface dataset from the feedback

#     feedback_data = []

#     embedding_model = "text-embedding-3-large"
#     embedding = OpenAIEmbeddings(model=embedding_model)

#     chroma_client = chromadb.PersistentClient(path=persistent_directory.as_posix())
#     rm = ChromadbRM(
#         collection_name=collection_name,
#         persist_directory=persistent_directory.as_posix(),
#         client=chroma_client,
#         embedding_function=embedding.embed_documents,
#         k=3,
#     )

#     model_name = "gpt-4o-mini"
#     # model_name = "gpt-4o"
#     llm = dspy.OpenAI(model=model_name, max_tokens=max_tokens)
#     # dspy.settings.configure(lm=llm, rm=rm, trace=[], temperature=0.7)
#     dspy.settings.configure(lm=llm, rm=rm, trace=[])

#     retriever = dspy.Retrieve(k=3)
#     for feedback in feedback_list:
#         # if feedback.feedback == "positive":
#         docs = []
#         docs.append(Document(page_content=feedback.context))

#         Chroma.from_documents(
#             collection_name="retrain_collection",
#             documents=docs,
#             persist_directory=persistent_directory.as_posix(),
#             embedding=embedding,
#         )
#         retrieved_context = retriever(feedback.question).passages
#         feedback_data.append(
#             {
#                 "question": feedback.question,
#                 "answer": feedback.answer,
#                 "feedback": feedback.feedback,
#                 "context": retrieved_context,
#             },
#         )

#     # for index, feedback in enumerate(feedback_data):
#     #     if feedback.get("feeback") == "positive":
#     #         retrieved_context = retriever(feedback.get("question")).passages
#     #         feedback_data[index]["context"] = retrieved_context

#     # dataset = Dataset.from_pandas(pd.DataFrame(feedback_data))
#     # trainset = dataset.train_test_split(test_size=0.2)["train"]
#     # valset = dataset.train_test_split(test_size=0.2)["test"]
#     pandas_dataset = pd.DataFrame(feedback_data)
#     dl = DataLoader()
#     dataset = dl.from_pandas(
#         pandas_dataset,
#         # input_keys=("question"),
#     )
#     splits = dl.train_test_split(dataset)
#     trainset = splits["train"]
#     valset = splits["test"]
#     trainset = [x.with_inputs("question") for x in trainset]
#     valset = [x.with_inputs("question") for x in valset]

#     NUM_THREADS = 4
#     kwargs = {"num_threads": NUM_THREADS, "display_progress": True}
#     # metric = answer_exact_match
#     metric = llm_judge_metric

#     evaluate = Evaluate(devset=trainset, metric=metric, **kwargs)

#     # baseline_train_score = evaluate(program, devset=trainset)
#     # print("Baseline train score: ", baseline_train_score)
#     # baseline_eval_score = evaluate(program, devset=valset)

#     # Compile

#     # eval_kwargs = dict(num_threads=16, display_progress=True, display_table=2)
#     # teleprompter = MIPROv2(
#     #     prompt_model=prompt_model,
#     #     task_model=task_model,
#     #     metric=metric,
#     #     num_candidates=N,
#     #     init_temperature=temperature,
#     #     verbose=True,
#     # )

#     teleprompter = BootstrapFewShot(
#         metric=metric,
#         # max_bootstrapped_demos=2,
#         # max_labeled_demos=2,
#     )
#     # teleprompter = BootstrapFewShotWithRandomSearch(
#     #     metric=metric,
#     #     # max_bootstrapped_demos=2,
#     #     # max_labeled_demos=2,
#     # )

#     compiled_program = teleprompter.compile(
#         program,
#         trainset=trainset,
#         # num_batches=batches,
#         # max_bootstrapped_demos=1,
#         # max_labeled_demos=2,
#         # eval_kwargs=eval_kwargs,
#     )

#     # TODO maybe use LabeledFewShot to optimize the prompt use both positive and negative feedback

#     # Evaluate the compiled program
#     evaluate(compiled_program, devset=trainset)
#     evaluate(compiled_program, devset=valset)

#     # save the model
#     compiled_program.save("compiled_program")
#     llm.inspect_history(n=5)
