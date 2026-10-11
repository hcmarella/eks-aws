FROM python:3.12-slim
RUN useradd -u 10001 -m app
WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
USER 10001
CMD ["python", "cli.py"]
