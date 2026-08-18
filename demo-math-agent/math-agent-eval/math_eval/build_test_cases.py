"""Builds the list of ConversationTestCase objects run by run_eval.py.

Not YAML-driven: evalite's YAML test-set loader (evalite.testcase.loader)
only covers single-turn TestCase/TestSet. ConversationTestCase.driver and
.scorer take live Python objects (typed SkipValidation — see
evalite/testcase/conversation.py), so a multi-turn, per-question-scored eval
like this one is naturally expressed in Python instead.
"""

import json
import os

from evalite import ConversationTestCase

from .accumulator import FinalTurnAccumulator
from .driver import MathTutorDriver
from .questions import QUESTIONS
from .scorer import JEEConversationScorer

# TEST_CASES_-prefixed so every knob this module exposes is discoverable
# under one env var namespace, consistent with retry.py's
# RETRY_MAX_ATTEMPTS/RETRY_BASE_DELAY_SECONDS (gap #12) — previously these
# were hardcoded constants requiring a code edit + redeploy to tune.
MAX_RETRIES = int(os.environ.get("TEST_CASES_MAX_RETRIES", "2"))  # naive re-queries after a wrong/incomplete first attempt
ITERATIONS = int(os.environ.get("TEST_CASES_ITERATIONS", "3"))  # each question's whole conversation is repeated this many times


def build_test_cases(provider) -> list[ConversationTestCase]:
    cases: list[ConversationTestCase] = []
    for q in QUESTIONS:
        # question_text travels with the spec (not just section/answer) so
        # the scorer can find the *real* question on retry turns, where
        # ConversationRunner's `turn_input` is the driver's own feedback
        # message rather than the original question — see scorer.py's
        # docstring.
        spec_json = json.dumps({"section": q.section, "answer": q.answer_spec, "question_text": q.text})

        # One cache per question, shared by that question's driver and
        # scorer: conversation_runner.py always calls scorer.score() before
        # driver.should_continue()/next_message() for a given turn, so the
        # scorer's marking/judge calls populate the cache and the driver's
        # own diagnosis reuses them — one LLM call per turn instead of two
        # (which could otherwise also disagree with each other; see
        # step_validator.py's docstring).
        cache: dict = {}

        driver = MathTutorDriver(spec_json, provider, cache, max_retries=MAX_RETRIES)
        scorer = JEEConversationScorer(provider, cache)

        cases.append(
            ConversationTestCase(
                id=q.id,
                initial_message=q.text,
                expected_outcomes=[spec_json],
                driver=driver,
                scorer=scorer,
                accumulator=FinalTurnAccumulator(),
                max_turns=MAX_RETRIES + 1,
                iterations=ITERATIONS,
                tags=[f"section-{q.section}"],
            )
        )
    return cases
