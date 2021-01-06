FROM python:3.9.0a3-alpine3.10

COPY . /app
WORKDIR /app

RUN pip3 --disable-pip-version-check --no-cache-dir \
    install -r ./requirements.txt

CMD python /app/bot.py
