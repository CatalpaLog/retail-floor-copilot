.PHONY: install init test eval api web

install:
	python -m pip install -r requirements.txt

init:
	python scripts/init_db.py

test:
	pytest -q

eval:
	python scripts/run_eval.py

api:
	uvicorn app.api:app --reload

web:
	streamlit run ui/streamlit_app.py
