FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8767

CMD ["python", "-m", "yingda", "serve", "--host", "0.0.0.0"]
