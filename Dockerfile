FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home crm
COPY app ./app
COPY scripts ./scripts
USER crm
EXPOSE 8000
CMD ["python", "-m", "app.run"]
