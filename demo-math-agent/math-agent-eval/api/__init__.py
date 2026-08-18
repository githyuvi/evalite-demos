"""FastAPI app serving math-agent-eval's own SQLite results.

Unified backend: this used to live as a separate FastAPI app/venv under
math-agent-eval-ui/backend (reaching into this project's evalite.db and
math_eval package via a sys.path hack, since the two projects didn't share
a virtualenv). It has been moved in-project so `math-agent-eval` is both
the eval CLI (`python -m math_eval.run_eval`) and the API server that
serves those results — no more cross-project sys.path reach-around;
`math_eval` is imported as an ordinary sibling package.
"""
