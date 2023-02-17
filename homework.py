import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv
import exceptions

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
logger.addHandler(handler)
file_handler = RotatingFileHandler(
    'my_logger.log',
    maxBytes=50000000,
    backupCount=5
)
logger.addHandler(file_handler)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
file_handler.setFormatter(file_formatter)


def check_tokens():
    """Проверка наличия переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправка сообщения в чат."""
    logger.info('Попытка отправить сообщение')
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
    except telegram.error.TelegramError:
        logger.error('Не удалось отправить сообщение')
    else:
        logger.debug('Сообщение успешно отправлено')


def get_api_answer(timestamp):
    """Проверка запроса к API и декодирования из json."""
    timestamp = timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params,
        )
    except requests.exceptions.RequestException:
        raise exceptions.RequestAPIException('Ошибка запроса к сервису')
    if homework_statuses.status_code != HTTPStatus.OK:
        homework_statuses.raise_for_status()
    try:
        response = homework_statuses.json()
    except requests.JSONDecodeError:
        raise requests.JSONDecodeError(
            'Ошибка декодирования json'
        )
    return response


def check_response(response):
    """Проверка ответа на соответствие ожидаемому."""
    if not isinstance(response, dict):
        raise TypeError('Тип данных не соответствует ожидаемому (dict)')
    if 'homeworks' not in response:
        raise KeyError('В ответе не содержится ключ homeworks')
    answer = response.get('homeworks')
    if not isinstance(answer, list):
        raise TypeError('Тип данных не соответствует ожидаемому (list)')
    return answer


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' in homework:
        homework_name = homework['homework_name']
    else:
        raise KeyError('Не существует ключа homework_name')
    if 'status' in homework:
        status = homework['status']
    else:
        raise KeyError(f'Отсутствует статус домашней работы {status}')
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f'Невозможный статус домашней работы - {status}')
    verdict = HOMEWORK_VERDICTS.get(status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствуют переменные окружения')
        sys.exit('Отсутствуют переменные окружения')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - 60 * 60 * 24
    last_status = None
    first_message = 'Бот начал работу'
    send_message(bot, first_message)

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                last_homework = homeworks[0]
                message = parse_status(last_homework)
                if message != last_status:
                    send_message(bot, message)
                    last_status = message
                else:
                    logger.info('Статус домашней работы не изменился')
            else:
                logger.info('Домашних работ не найдено')
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            logger.error(error, exc_info=True)
            message = f'Сбой в работе программы: {error}'
            if last_status != message:
                send_message(bot, message)
                last_status = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
