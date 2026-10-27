.PHONY: install ingest run query test eval clean

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

ingest:
	python -m scripts.ingest --reset

ingest-sample:
	python -m scripts.ingest --reset --only code_travail

run:
	uvicorn app.main:app --reload --port 8000

query:
	python -m scripts.query "$(Q)"

test:
	pytest -q

eval:
	python -m scripts.evaluate

clean:
	rm -rf data/chroma data/processed __pycache__
