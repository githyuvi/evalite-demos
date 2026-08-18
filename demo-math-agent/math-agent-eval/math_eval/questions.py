"""Test questions sourced from JEE (Advanced) 2025 Paper 1, Mathematics —
`math-solver-agent/2025_1_English.pdf` (the official final answer key).

Two questions picked from each of the paper's four sections, chosen to
cover every marking-scheme shape in the paper:

  Section 1 (Q1, Q2)   — single correct option.  Full +3 / 0 / -1.
  Section 2 (Q5, Q6)   — one or more correct options, partial credit.
                         Full +4 / partial +1..+3 / 0 / -2.
  Section 3 (Q8, Q9)   — numerical value. Q9's answer is an accepted
                         RANGE ([1.15, 1.25]), Q8's is exact (105).
                         Full +4 / 0 (no negative marking).
  Section 4 (Q14, Q15) — match-the-list, single correct combination.
                         Full +4 / 0 / -1.

`answer_spec` is intentionally minimal — just the ground truth needed by
`marking.score_answer`. The point values themselves live in
`marking.SECTION_RUBRIC`, keyed by section number, so they aren't
duplicated per question.
"""

from dataclasses import dataclass


@dataclass
class Question:
    id: str
    section: int
    text: str
    answer_spec: dict


QUESTIONS: list[Question] = [
    Question(
        id="section1_q1",
        section=1,
        text=(
            "Let R denote the set of all real numbers. Let a_i, b_i in R for "
            "i in {1, 2, 3}. Define the functions f: R -> R, g: R -> R, and "
            "h: R -> R by\n"
            "f(x) = a1 + 10x + a2*x^2 + a3*x^3 + x^4\n"
            "g(x) = b1 + 3x + b2*x^2 + b3*x^3 + x^4\n"
            "h(x) = f(x + 1) - g(x + 2)\n\n"
            "If f(x) != g(x) for every x in R, then the coefficient of x^3 in "
            "h(x) is\n"
            "(A) 8\n(B) 2\n(C) -4\n(D) -6\n\n"
            "Choose the correct option and show your full step-by-step "
            "working, ending with a final line 'Answer: <option letter>'."
        ),
        answer_spec={"type": "single", "correct": "C"},
    ),
    Question(
        id="section1_q2",
        section=1,
        text=(
            "Three students S1, S2, and S3 are given a problem to solve. "
            "Consider the following events:\n"
            "U: At least one of S1, S2, and S3 can solve the problem.\n"
            "V: S1 can solve the problem, given that neither S2 nor S3 can "
            "solve the problem.\n"
            "W: S2 can solve the problem and S3 cannot solve the problem.\n"
            "T: S3 can solve the problem.\n\n"
            "For any event E, let P(E) denote the probability of E. If "
            "P(U) = 1/2, P(V) = 1/10, and P(W) = 1/12, then P(T) is equal to\n"
            "(A) 13/36\n(B) 1/3\n(C) 19/60\n(D) 1/4\n\n"
            "Choose the correct option and show your full step-by-step "
            "working, ending with a final line 'Answer: <option letter>'."
        ),
        answer_spec={"type": "single", "correct": "A"},
    ),
    Question(
        id="section2_q5",
        section=2,
        text=(
            "Let L1 be the line of intersection of the planes given by the "
            "equations 2x + 3y + z = 4 and x + 2y + z = 5. Let L2 be the "
            "line passing through the point P(2, -1, 3) and parallel to L1. "
            "Let M denote the plane given by the equation 2x + y - 2z = 6. "
            "Suppose that the line L2 meets the plane M at the point Q. Let "
            "R be the foot of the perpendicular drawn from P to the plane M.\n\n"
            "Then which of the following statements is/are TRUE?\n"
            "(A) The length of the line segment PQ is 9*sqrt(3)\n"
            "(B) The length of the line segment QR is 15\n"
            "(C) The area of triangle PQR is (3/2)*sqrt(234)\n"
            "(D) The acute angle between the line segments PQ and PR is "
            "arccos(1 / (2*sqrt(3)))\n\n"
            "One or more options may be correct. Show your full step-by-step "
            "working, ending with a final line 'Answer: <option letter(s), "
            "comma-separated>' listing every option you believe is correct."
        ),
        answer_spec={"type": "multi", "correct": ["A", "C"]},
    ),
    Question(
        id="section2_q6",
        section=2,
        text=(
            "Let N denote the set of all natural numbers, and Z denote the "
            "set of all integers. Consider the functions f: N -> Z and "
            "g: Z -> N defined by\n"
            "f(n) = (n+1)/2 if n is odd, (4-n)/2 if n is even\n"
            "g(n) = 3 + 2n if n >= 0, -2n if n < 0\n"
            "Define (g o f)(n) = g(f(n)) for all n in N, and "
            "(f o g)(n) = f(g(n)) for all n in Z.\n\n"
            "Then which of the following statements is/are TRUE?\n"
            "(A) g o f is NOT one-one and g o f is NOT onto\n"
            "(B) f o g is NOT one-one but f o g is onto\n"
            "(C) g is one-one and g is onto\n"
            "(D) f is NOT one-one but f is onto\n\n"
            "One or more options may be correct. Show your full step-by-step "
            "working, ending with a final line 'Answer: <option letter(s), "
            "comma-separated>' listing every option you believe is correct."
        ),
        answer_spec={"type": "multi", "correct": ["A", "D"]},
    ),
    Question(
        id="section3_q8",
        section=3,
        text=(
            "Let the set of all relations R on the set {a, b, c, d, e, f}, "
            "such that R is reflexive and symmetric, and R contains exactly "
            "10 elements, be denoted by S.\n\n"
            "Then the number of elements in S is ____.\n\n"
            "Show your full step-by-step working, ending with a final line "
            "'Answer: <integer>'."
        ),
        answer_spec={"type": "numeric", "exact": 105},
    ),
    Question(
        id="section3_q9",
        section=3,
        text=(
            "For any two points M and N in the XY-plane, let vector(MN) "
            "denote the vector from M to N, and vector(0) denote the zero "
            "vector. Let P, Q and R be three distinct points in the "
            "XY-plane. Let S be a point inside the triangle PQR such that "
            "vector(SP) + 5*vector(SQ) + 6*vector(SR) = vector(0).\n\n"
            "Let E and F be the mid-points of the sides PR and QR, "
            "respectively. Then the value of\n"
            "(length of the line segment EF) / (length of the line segment ES)\n"
            "is ____.\n\n"
            "If your answer has more than two decimal places, "
            "truncate/round it off to TWO decimal places. Show your full "
            "step-by-step working, ending with a final line "
            "'Answer: <numeric value>'."
        ),
        answer_spec={"type": "numeric", "range": [1.15, 1.25]},
    ),
    Question(
        id="section4_q14",
        section=4,
        text=(
            "Consider the following frequency distribution:\n"
            "Value:      4  5   8   9  6  12  11\n"
            "Frequency:  5  f1  f2  2  1  1   3\n\n"
            "Suppose that the sum of the frequencies is 19 and the median "
            "of this frequency distribution is 6.\n\n"
            "For the given frequency distribution, let alpha denote the "
            "mean deviation about the mean, beta denote the mean deviation "
            "about the median, and sigma^2 denote the variance.\n\n"
            "Match each entry in List-I to the correct entry in List-II.\n\n"
            "List-I:\n"
            "(P) 7*f1 + 9*f2 is equal to\n"
            "(Q) 19*alpha is equal to\n"
            "(R) 19*beta is equal to\n"
            "(S) 19*sigma^2 is equal to\n\n"
            "List-II:\n"
            "(1) 146\n(2) 47\n(3) 48\n(4) 145\n(5) 55\n\n"
            "Which option gives the correct match?\n"
            "(A) P->5, Q->3, R->2, S->4\n"
            "(B) P->5, Q->2, R->3, S->1\n"
            "(C) P->5, Q->3, R->2, S->1\n"
            "(D) P->3, Q->2, R->5, S->4\n\n"
            "Choose the correct option and show your full step-by-step "
            "working, ending with a final line 'Answer: <option letter>'."
        ),
        answer_spec={"type": "single", "correct": "C"},
    ),
    Question(
        id="section4_q15",
        section=4,
        text=(
            "Let R denote the set of all real numbers. For a real number x, "
            "let [x] denote the greatest integer less than or equal to x "
            "(the floor function). Let n denote a natural number.\n\n"
            "Match each entry in List-I to the correct entry in List-II.\n\n"
            "List-I:\n"
            "(P) The minimum value of n for which the function "
            "f(x) = floor((10x^3 - 45x^2 + 60x + 35) / n) is continuous on "
            "the interval [1, 2], is\n"
            "(Q) The minimum value of n for which "
            "g(x) = (2n^2 - 13n - 15)(x^3 + 3x), x in R, is an increasing "
            "function on R, is\n"
            "(R) The smallest natural number n which is greater than 5, "
            "such that x = 3 is a point of local minima of "
            "h(x) = (x^2 - 9)^n * (x^2 + 2x + 3), is\n"
            "(S) Number of x0 in R such that "
            "l(x) = sum_{k=0}^{4} (sin|x-k| + cos|x-k+1/2|), x in R, is NOT "
            "differentiable at x0, is\n\n"
            "List-II:\n"
            "(1) 8\n(2) 9\n(3) 5\n(4) 6\n(5) 10\n\n"
            "Which option gives the correct match?\n"
            "(A) P->1, Q->3, R->2, S->5\n"
            "(B) P->2, Q->1, R->4, S->3\n"
            "(C) P->5, Q->1, R->4, S->3\n"
            "(D) P->2, Q->3, R->1, S->5\n\n"
            "Choose the correct option and show your full step-by-step "
            "working, ending with a final line 'Answer: <option letter>'."
        ),
        answer_spec={"type": "single", "correct": "B"},
    ),
]
