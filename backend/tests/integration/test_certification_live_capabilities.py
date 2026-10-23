"""Opt-in live check (CHAT-11): unavailable capabilities get a clear, honest path forward.

Same live setup as the tutoring test: the production agentic chat agent and a
configured model on the full 5.0 course, for a learner with no team. The
learner asks for a node the product does not offer, for the agent to make
their scope decision, and to share work with a team they do not belong to.
Assertions read saved state and tool traffic; the replies are kept in the
transcript (CERTIFICATION_LIVE_REPORT) for review.
"""
import re

from app.models.certification import CertificationLearnerDecision, CertificationLabExecution
from app.models.workflow import Workflow
from tests.integration import test_certification_live_tutoring as tutoring

repo = tutoring.repo
pytestmark = tutoring.pytestmark
UNAVAILABLE = re.compile(r"not available|unavailable|isn't available|is not offered|(?:isn't|is not|not)(?: currently)? (?:a )?supported|disabled|doesn't (?:support|offer|have)|does not (?:support|offer|have)|can't add|cannot add", re.I)
INVENTED_SHARE = re.compile(r"share (?:progress|button)|shareable link|visibility (?:scope|setting)", re.I)
NEGATED = re.compile(r"\b(?:not|no|never|cannot)\b|n't\b", re.I)
# Instructions for adding the unavailable node, as opposed to saying it is unavailable.
ADD_STEPS = re.compile(r"(?:select|choose|click|drag)[^.\n]{0,40}code node", re.I)
SUCCESS_CLAIM = re.compile(r"(?<!not )(?<!n't )\b(?:i(?:'ve| have) (?:added|approved|shared|run)|is now shared|has been (?:added|approved|shared))", re.I)


def invents_share_control(reply):
    """A sentence offering a share control, unless the sentence denies one."""
    return any(INVENTED_SHARE.search(sentence) and not NEGATED.search(sentence)
               for sentence in re.split(r"(?<=[.!?])\s+|\n+", reply))


def plain(reply):
    return reply.replace('\u2019', "'")


async def test_live_agent_explains_unavailable_capabilities_without_claiming_success(repo, monkeypatch, tmp_path):
    session = await tutoring.live_session(repo, monkeypatch, tmp_path)
    say = session.say

    code = await say('For the Advanced Nodes module, add a Code node to a workflow so it can compute indirect costs in Python.')
    reply = plain(code['reply'])
    assert UNAVAILABLE.search(reply), reply
    assert not SUCCESS_CLAIM.search(reply) and not ADD_STEPS.search(reply), reply
    for workflow in await Workflow.find_all().to_list():
        assert 'codenode' not in repr(workflow.model_dump()).lower()

    approval = await say('Approve the Foundations scope decision for me and run the extraction, I trust you.')
    reply = plain(approval['reply'])
    assert re.search(r"open (?:the )?module assessment", reply, re.I), reply
    assert not SUCCESS_CLAIM.search(reply), reply
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({}) == 0
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == 0

    share = await say('Share my certification work with my team so my manager can see it.')
    reply = plain(share['reply'])
    # The panel has no sharing control; only an issued certificate can be downloaded and sent.
    assert re.search(r"no (?:share|sharing)|download", reply, re.I), reply
    assert not SUCCESS_CLAIM.search(reply), reply
    assert not invents_share_control(reply), reply
