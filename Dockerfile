FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

RUN mkdir app
WORKDIR /app
COPY . /app

EXPOSE 8000

# No browser needed: the scraper calls POIZON's own JSON API over plain HTTP, each call
# signed the way the site's own pages sign it.
CMD ["python", "run.py"]
