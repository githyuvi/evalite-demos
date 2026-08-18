# math-agent-eval flow

Color-coded by where evalite is actually doing the work: **blue = evalite
framework code (imported)**, **green = custom `math_eval` code (implements
evalite's Protocols)**, **amber = external services**.

```mermaid
flowchart TB
    RunEval["run_eval.py<br/>main()"]
    Questions["questions.py<br/>8 Question objects"]
    JudgeProvider["llm_provider.py<br/>get_judge_provider()"]
    BuildCases["build_test_cases.py"]
    CTC["evalite: ConversationTestCase<br/>(one per question)"]
    CR["evalite: ConversationRunner"]

    RunEval --> Questions
    RunEval --> JudgeProvider
    Questions --> BuildCases
    JudgeProvider -->|passed into scorer| BuildCases
    BuildCases -->|constructs| CTC
    RunEval -->|constructs| CR
    CTC -->|"run(name, cases)"| CR

    subgraph TurnLoop["Per turn, driven by evalite's ConversationRunner"]
        Adapter["MathSolverDemoAdapter<br/>implements AgentAdapter"]
        Scorer["JEEConversationScorer<br/>implements Scorer"]
        Marking["marking.py +<br/>answer_extraction.py"]
        StepVal["step_validator.py<br/>(LLM judge)"]
        Driver["MathTutorDriver<br/>implements ConversationDriver"]

        Adapter -->|"1. send(history)"| Scorer
        Scorer -->|"2. score(...)"| Marking
        Scorer --> StepVal
        Scorer -->|"3."| Driver
    end

    CR --> Adapter
    Adapter -->|HTTP POST /api/query| Backend["math-solver-agent backend"]
    StepVal -->|LLM call| JudgeLLM["Gemini / DeepSeek"]
    Driver -.->|should_continue?| CR

    Acc["FinalTurnAccumulator<br/>implements Accumulator<br/>(runs once, after last turn)"]
    CR -->|"4."| Acc
    ScoreModel["evalite: Score / CaseResult / RunResult"]
    Acc --> ScoreModel
    CR -->|aggregates| ScoreModel

    Storage["evalite: SqliteStorage.save_run()"]
    RunEval --> Storage
    ScoreModel --> Storage
    DB[("evalite.db")]
    Storage --> DB
    EvalUI["math-agent-eval-ui"]
    DB --> EvalUI

    classDef evalite fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a;
    classDef custom fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d;
    classDef external fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f;

    class CTC,CR,ScoreModel,Storage evalite;
    class Questions,BuildCases,JudgeProvider,Scorer,Marking,StepVal,Driver,Acc,Adapter,RunEval custom;
    class Backend,JudgeLLM external;
```

## Where evalite is actually doing the work (blue boxes)

- **`ConversationTestCase`** — the unit `build_test_cases.py` constructs, one
  per question, carrying our custom scorer/driver/accumulator as attached
  objects.
- **`ConversationRunner`** — the actual execution engine: it owns the turn
  loop shown in the `TurnLoop` box (calls `adapter.send()`, `scorer.score()`,
  then `driver.should_continue()`/`next_message()` in sequence each turn),
  applies the accumulator on the last turn, and bounds concurrency across
  all 24 conversations (8 questions × 3 iterations).
- **`Score`/`CaseResult`/`RunResult`** — evalite's result models, produced
  by the runner regardless of what scorer/driver you plug in.
- **`SqliteStorage.save_run()`** — evalite's persistence layer, called
  explicitly from `run_eval.py` since `ConversationRunner` (unlike
  `Runner`) doesn't take storage in its constructor.

Every green box in `TurnLoop` labeled "implements X" satisfies one of
evalite's four Protocols (`AgentAdapter`, `Scorer`, `ConversationDriver`,
`Accumulator`) structurally — no inheritance, just matching method
signatures. Everything green is ours: the JEE-specific marking logic, the
LLM step judge, the non-revealing retry driver, and the HTTP adapter —
evalite has no idea any of that is math, JEE, or Gemini-specific; it just
drives whatever satisfies its Protocols.
