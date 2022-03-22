import os
import pickle

import re
import aiohttp
from bs4 import BeautifulSoup

import config
from utils import exeptions
from utils.json_files import JsonFile
from utils.notify_to_user import notify_user
import aiogram.utils.markdown as md


def _orioks_parse_requests(raw_html: str, section: str) -> list:
    bs_content = BeautifulSoup(raw_html, "html.parser")
    table_raw = bs_content.select('.table.table-condensed.table-thread tr:not(:first-child)')
    requests = []
    for tr in table_raw:
        _thread_id = int(re.findall(r'\d+$', tr.find_all('td')[2].select_one('a')['href'])[0])
        requests.append({
            'thread_id': _thread_id,
            'status': tr.find_all('td')[1].text,
            'new_messages': int(tr.find_all('td')[7].select_one('b').text),
            'about': {
                'name': tr.find_all('td')[3].text,
                'url': config.ORIOKS_PAGE_URLS['masks']['requests'][section].format(id=_thread_id),
            },
        })
    return requests


async def get_orioks_requests(user_telegram_id: int, section: str) -> list:
    path_to_cookies = os.path.join(config.BASEDIR, 'users_data', 'cookies', f'{user_telegram_id}.pkl')
    async with aiohttp.ClientSession() as session:
        cookies = pickle.load(open(path_to_cookies, 'rb'))
        async with session.get(config.ORIOKS_PAGE_URLS['notify']['requests'][section], cookies=cookies) as resp:
            raw_html = await resp.text()
    return _orioks_parse_requests(raw_html=raw_html, section=section)


async def get_requests_to_msg(diffs: list) -> str:
    message = ''
    for diff in diffs:
        if diff['type'] == 'new_status':
            message += md.text(
                md.text(
                    md.text('📄'),
                    md.text('Новые изменения по Вашей заявке'),
                    md.hbold(f"«{diff['about']['name']}»"),
                    sep=' '
                ),
                md.text(
                    md.text('Изменён статус заявки на:'),
                    md.hcode(diff['current_status']),
                    sep=' ',
                ),
                md.text(),
                md.text(
                    md.text('Подробности по ссылке:'),
                    md.text(diff['about']['url']),
                    sep=' ',
                ),
                sep='\n',
            )
        elif diff['type'] == 'new_message':
            message += md.text(
                md.text(
                    md.text('📄'),
                    md.text('Новые изменения по Вашей заявке'),
                    md.hbold(f"«{diff['about']['name']}»"),
                    sep=' '
                ),
                md.text(
                    md.text('Получено личное сообщение от [людей, которые отвечают на заявки (хз как их зовут)]'),
                    md.text(
                        md.text('Количество новых сообщений:'),
                        md.hcode(diff['current_messages']),
                        sep=' ',
                    ),
                    sep=' ',
                ),
                md.text(),
                md.text(
                    md.text('Подробности по ссылке:'),
                    md.text(diff['about']['url']),
                    sep=' ',
                ),
                sep='\n',
            )
        message += '\n' * 2
    return message


def compare(old_list: list, new_list: list) -> list:
    diffs = []
    for old, new in zip(old_list, new_list):
        if old['thread_id'] != new['thread_id']:
            raise exeptions.FileCompareError
        if old['status'] != new['status']:
            diffs.append({
                'type': 'new_status',  # or `new_message`
                'current_status': new['status'],
                'about': new['about'],
            })
        elif new['new_messages'] > old['new_messages']:
            diffs.append({
                'type': 'new_message',  # or `new_status`
                'current_messages': new['new_messages'],
                'about': new['about'],
            })
    return diffs


async def _user_requests_check_with_subsection(user_telegram_id: int, section: str):
    requests_list = await get_orioks_requests(user_telegram_id=user_telegram_id, section=section)
    student_json_file = config.STUDENT_FILE_JSON_MASK.format(id=user_telegram_id)
    path_users_to_file = os.path.join(config.BASEDIR, 'users_data', 'tracking_data',
                                      'requests', section, student_json_file)
    if student_json_file not in os.listdir(os.path.dirname(path_users_to_file)):
        JsonFile.save(data=requests_list, filename=path_users_to_file)
        return False

    old_json = JsonFile.open(filename=path_users_to_file)
    if len(requests_list) != len(old_json):
        JsonFile.save(data=requests_list, filename=path_users_to_file)
        return False
    try:
        diffs = compare(old_list=old_json, new_list=requests_list)
    except exeptions.FileCompareError:
        JsonFile.save(data=requests_list, filename=path_users_to_file)
        return False

    if len(diffs) > 0:
        msg_to_send = await get_requests_to_msg(diffs=diffs)
        await notify_user(user_telegram_id=user_telegram_id, message=msg_to_send)
    JsonFile.save(data=requests_list, filename=path_users_to_file)
    return True


async def user_requests_check(user_telegram_id: int):
    for section in ('questionnaire', 'doc', 'reference'):
        await _user_requests_check_with_subsection(user_telegram_id=user_telegram_id, section=section)
