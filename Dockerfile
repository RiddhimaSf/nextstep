# Single-stage build — deliberate choice, not a shortcut. Multi-stage
# builds solve bloated-image problems from heavy compiled dependencies
# or a separate frontend build step; this app is pure Python with a
# plain pip install, so a single stage is the right-sized match for
# actual complexity, same "boring infrastructure" principle applied
# throughout this sprint (Chroma over a managed vector DB, a flat file
# over Postgres for idempotency).
FROM python:3.12-slim

WORKDIR /app

# Non-root user — Docker containers run as root by default, which is
# more privilege than this app needs. Creating and switching to a
# regular user limits what could be done if the running app were ever
# compromised, standard low-cost hardening.
RUN useradd -m appuser

# Dependencies copied and installed BEFORE the rest of the code, so
# Docker's build cache can skip reinstalling them on every rebuild when
# only application code changes, not dependencies (same reasoning
# covered conceptually on Day 2, now actually applied).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code.
COPY . .
RUN python -m rag.ingest
# Ensure the non-root user owns the app directory (needed since files
# were copied in as root before the USER switch below).
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

# Health check — Streamlit exposes a built-in health endpoint at
# /_stcore/health (this app's own /health concept from Day 6's brief
# maps onto Streamlit's existing mechanism, since Streamlit isn't a
# FastAPI service with a custom /health route the way the generic
# template assumes).
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"

# The real run command for this app — not the FastAPI/uvicorn command
# from the generic starter template, since this is a Streamlit app.
CMD ["python", "-m", "streamlit", "run", "crisis.py", "--server.port=8501", "--server.address=0.0.0.0"]