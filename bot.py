import asyncio
import aiohttp
import redis
from collections import OrderedDict
from aiogram.utils.exceptions import ValidationError
from bs4 import BeautifulSoup as bs
from aiogram import Bot, Dispatcher, types, executor
from os import environ
from datetime import timedelta
from logging import config, getLogger
from pathlib import Path
from os import path, getpid
import psutil

BASE_DIR = Path(__file__).resolve().parent

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console_basic': {
            'format': '%(asctime)s [%(levelname)s] P%(process)d <%(filename)s:%(lineno)d'
                      ', %(funcName)s()> %(name)s: %(message)s',
        },
        'file_text': {
            'format': '%(asctime)s (+%(relativeCreated)d) [%(levelname)s] P%(process)d T%(thread)d'
                      ' <%(pathname)s:%(lineno)d, %(funcName)s at %(module)s> \'%(name)s\': %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'console_basic',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': path.join(BASE_DIR, 'logs', path.join(f"{psutil.Process(getpid()).name()}.log")),
            'mode': 'wt',
            'encoding': 'utf-8',
            'formatter': 'file_text',
        },
    },
    'loggers': {
        '': {
            'level': 'INFO',
            'handlers': ['console', 'file', ],
        },
        'application': {
            'level': 'INFO',
            'handlers': ['console', 'file', ],
            'propagate': False,
        },
    },
}

config.dictConfig(LOGGING_CONFIG)

log = getLogger('application')

try:
    """
    Creating bot instance.
    If token is None: raise error
    """
    bot = Bot(token=environ.get('TOKEN'))
except ValidationError as _:
    raise KeyError('TOKEN variable must be set.')

try:
    db = redis.Redis(host=environ.get('HOST', default='localhost'),
                     port=environ.get('PORT', default=6379), db=0)
    db.ping()
    log.info('Database launched successfully')
except KeyError:
    raise
except redis.exceptions.ConnectionError:
    raise

# Creating dispatcher for handling messages
dispatcher = Dispatcher(bot)


# handler for help and start
@dispatcher.message_handler(commands=['help', 'start'])
async def send_welcome(message: types.Message):
    if message.is_command() and message.text == '/help':
        await message.reply("List of available commands:\n "
                            "1. /help: Showing this message.\n"
                            "2. /start: Starting bot query for your session.\n"
                            "3. /weather <Your city or country>: Finding information about weather in "
                            "your country or city.\n"
                            "4. /top <film genre>: Will show top10 films of current genre."
                            "\tAvailable chooses: \n"
                            "Horrors, Fantastic, Shooters, Thrillers, Comedy's, Melodramas, Dramas")
    else:
        if db.get("{}".format(message.from_user.id)) is not None:
            await message.reply("You've already started bot!\n"
                                "Your session will expire in: "
                                "{} seconds.".format(db.ttl(message.from_user.id)))
            return
        db.setex(
            message.from_user.id,
            timedelta(days=10),
            value="active"
        )
        log.info('User: {username} registered with ID: {id}'.format(
            username=message.from_user.username, id=message.from_user.id
        ))
        await message.reply("Hello! 😺 \n"
                            "My name is Riven and that's my async bot!\n"
                            "To see list of available commands type: /help")


async def parse_request_data(data: dict):
    try:
        country_info = ["{} ({})".format(d['name'], d['sys']['country'])
                        for d in data['list']]
        print("city:", country_info)
        city_id = data['list'][0]['id']
        return None, city_id
    except Exception as e:
        return e, None


async def request_data(session: aiohttp.ClientSession, country: str):
    """
    Function working with openweathermap API.
    You need to register here:
    http://api.openweathermap.org

    1. Getting ID of current country for
    more accurate data output
    2. Getting json data of all we need.
    temperature objects are in KL. We need
    to cast them to CEL.

    :param session:
    :param country:
    :return:
    """
    APIkey = '53f4373fef33cde69e10ab393fa04219'
    url = "http://api.openweathermap.org/data/2.5/find?q={}&type=like&APPID={}".format(country, APIkey)
    async with session.get(url, allow_redirects=True) as response:
        data = await response.json()
    _, parsed_data = await parse_request_data(data)

    url_withId = "http://api.openweathermap.org/data/2.5/weather?q={city},{regID}&appid={APIkey}".format(
        city=country, regID=parsed_data, APIkey=APIkey
    )
    async with session.get(url_withId, allow_redirects=True) as response:
        data_withId = await response.json()
        return data_withId['weather'][0]['description'], \
               (data_withId['main']['temp_min'] - 273, 15), \
               (data_withId['main']['temp_max'] - 273, 15)


@dispatcher.message_handler(commands=['weather'])
async def get_weather(message: types.Message):
    """
        country store string object. Representation of message.text
    of user input. If no country (empty input) - sending info about this
    and return

        else:
    creating async session and getting:
    weather, temp_min, temp_max from API

    :param message:
    :return:
    """
    country = (message.text[len('/weather'):]).replace(' ', '').strip()
    if len(country) == 0:
        await message.reply('Sorry, but no country or city was specified! :(')
        return
    async with aiohttp.ClientSession() as session:
        weather, temp_min, temp_max = await request_data(session, country)
    log.info('User with username: {username} and ID: {id} requested weather.'.format(
        username=message.from_user.username, id=message.from_user.id
    ))
    await message.reply(f"Weather for {country}:\n"
                        f"Description: {weather},\n"
                        f"Maximum temperature: {round(temp_max[0], 2)},\n"
                        f"Minimum temperature: {round(temp_min[0], 2)}")


async def pregMatch(string: str, comp_dict: OrderedDict):
    """
    Function created for matching
    value from orderedDict.
    If you need to grab
    most similar string
    from OD object:
    this function is for you!

    :param string:
    :param comp_dict:
    :return:
    """
    match = []
    for key in comp_dict.keys():
        count = 0
        for str_letters, letters in zip(string[len('/top'):].replace(' ', '').strip(), key):
            if str_letters == letters:
                # getting percents here
                # if letters match:
                # ABC ABZ => count:
                # 1. count = 100/3 = 33.3(3)
                # 2. count = 33.3(3) + 33.3(3) ~= 66.7
                count += (100 / len(key))
        # appending for finding max value
        # 'cause it may be:
        # if > 0.5% == return
        # [ 0.55, 0.65, 0.96 ]
        match.append(count)
    return list(comp_dict.values())[match.index(max(*match))] or None


async def films_data(url: str, session: aiohttp.ClientSession):
    async with session.get(url, allow_redirects=False) as response:
        data = await response.read()
    film_names = []
    soup = bs(data, 'lxml')
    for places in range(1, 21):
        film_names.append(
            soup.find('tr', {'id': f'top250_place_{places}'}).find('a', {'class': 'all'}).text
        )
    return film_names


@dispatcher.message_handler(commands=['top'])
async def top_films_with_genre(message: types.Message):
    """
    Horrors: id1,
    Fantastic: id2,
    Shooters: id3,
    Thrillers: id4,
    Comedy's: id6,
    Melodramas: id7,
    Dramas: id8
    :param message:
    :return:
    """
    if message.is_command() and len(message.text) == 0:
        await message.reply("There is no filter for films object. Sending top 20 random films!")
        return
    films = OrderedDict()
    films['horrors'] = '1'
    films['fantastic'] = '2'
    films['shooters'] = '3'
    films['thrillers'] = '4'
    films['comedy'] = '6'
    films['melodramas'] = '7'
    films['dramas'] = '8'
    async with aiohttp.ClientSession() as session:
        data = await pregMatch(message.text.lower(), films)
        url = "https://www.kinopoisk.ru/top/id_genre/{id}/".format(id=data)
        list_data = await films_data(url, session)
        print(list_data)
    await message.reply(
        "Films by your request:\n\n" + ",\n".join(list_data)
    )


if __name__ == '__main__':
    executor.start_polling(dispatcher, skip_updates=True, timeout=10)
