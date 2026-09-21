FROM python:3.12-alpine

WORKDIR /app
RUN pip install --no-cache-dir kubernetes==32.0.1
COPY controller.py .

CMD ["python", "controller.py"]
