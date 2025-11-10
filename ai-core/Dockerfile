FROM python:3.12-slim
WORKDIR /app
COPY ai-core /app
RUN pip install -U pip && pip install -e .
EXPOSE 8000
CMD ["uvicorn","src.main:app_sio","--host","0.0.0.0","--port","8000"]
