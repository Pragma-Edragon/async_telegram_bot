FROM python:3.8.0

COPY . /app
WORKDIR /app

RUN pip3 --no-cache-dir \
    install -r ./requirements.txt

CMD python /app/bot.py
