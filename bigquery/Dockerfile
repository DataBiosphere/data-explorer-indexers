FROM python:2

WORKDIR /app
COPY requirements.txt /app
RUN pip install -r /app/requirements.txt

COPY . /app

CMD python indexer.py
