from dataclasses import dataclass

from pydantic_ai import RunContext
from pydantic_ai.agent import Agent

from app.utilities.document_manager import DocumentManager


@dataclass
class RagDeps:
    doc_manager: DocumentManager
    user_id: str


rag_agent = Agent(
    "openai:gpt-4o",
    deps_type=RagDeps,
    system_prompt="You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know.",
)


@rag_agent.tool
async def retrieve(
    context: RunContext[RagDeps], question: str, docs_ids: list[str] = []
):
    """
    Retrieve documents for a given question
    Args:
        context: The call context
        question: The question of the user
        docs_ids: A list of document IDs to search in (optional)

    Returns:
        A list of documents that match the question
    """
    results = context.deps.doc_manager.query_documents(
        context.deps.user_id, question, docs_ids
    )
    content = "Context: \n"
    for result in results:
        if result.get("metadata") is not None:
            content += f"Document title: {result['metadata'].get('document_name')}\n"
        content += f"Document content: {result['content']}\n\n"
    return content
