FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8095
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

EXPOSE 8095

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8095/health', timeout=5)" || exit 1

CMD ["python", "server.py"]
