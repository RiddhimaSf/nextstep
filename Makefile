.PHONY: eval eval-judge eval-p0

eval:
	python -m evals.run

eval-judge:
	python -m evals.run --llm-judge

eval-p0:
	python -m evals.run --severity P0