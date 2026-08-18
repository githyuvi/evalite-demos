"""Custom Accumulator: keep only the final turn's Score.

evalite's built-in DefaultAccumulator averages every turn's score, which
would penalize a conversation for needing a retry even if it ultimately
lands on a fully correct, well-justified answer. Real exam marking doesn't
work that way — only the final submitted answer counts, not earlier wrong
attempts — so this accumulator mirrors that: whichever turn ran last is
the conversation's score.
"""

from evalite import Score


class FinalTurnAccumulator:
    def initial(self):
        return None

    def update(self, state, turn_score: Score):
        return turn_score

    def finalize(self, state, total_turns: int) -> Score:
        if state is None:
            return Score(passed=False, value=0.0, reasoning="no turns executed")
        return Score(
            passed=state.passed,
            value=state.value,
            reasoning=f"Final turn score after {total_turns} turn(s): {state.reasoning}",
        )
