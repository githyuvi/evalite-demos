# evalite-demos

Example applications showing how to use [evalite](https://github.com/githyuvi/evalite),
a lightweight, fully customizable framework for evaluating LLM systems.
Each demo is a self-contained project with its own agent under test, its
own evalite-based eval suite, and its own README.

## What's here

- [`demo-math-agent`](demo-math-agent) — a math/physics chatbot agent
  (FastAPI backend + plain HTML/JS frontend), a multi-turn evalite eval
  suite scored against a real JEE (Advanced) 2025 answer key, and an API +
  viewer for the results. See its [README](demo-math-agent/README.md) for
  setup and how the pieces fit together.

More demos will be added here over time.
