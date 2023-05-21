from sanic import Sanic, Request, Websocket
from sanic.response import text, html
from sanic_ext import Extend
from geoip import geolite2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import exceptions
import asyncio
import traceback
import json
import logging
import time
import re
import pycountry

SANIC_SOCKET="unix:/tmp/visitors.sanic"

VISITORS_BOT_TOKEN=""

TRAFFIC_BOT_TOKEN=""

visitors_bot = Bot(token=VISITORS_BOT_TOKEN)
visitors_d = Dispatcher(bot=visitors_bot)

traffic_bot = Bot(token=TRAFFIC_BOT_TOKEN)
traffic_d = Dispatcher(bot=traffic_bot)

app = Sanic("visitors")
app.config.FORWARDED_SECRET = ""
app.config.CORS_ORIGINS = "*"
app.config.CORS_AUTOMATIC_OPTIONS = True
Extend(app)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('visitors')
#log.addHandler(logging.FileHandler("visitors.log"))

try:
    users = json.load(open('users.json'))
except:
    traceback.print_exc()
    users = {}

if 'v' not in users: users['v'] = {}
if 't' not in users: users['t'] = {}

try:
    traffic = json.load(open('traffic.json'))
except:
    traceback.print_exc()
    traffic = {}

def save_users():
    json.dump(users, open('users.json', 'w'))

def save_traffic():
    json.dump(traffic, open('traffic.json', 'w'))

async def start_handler_traffic(event: types.Message):
    uid = str(event.from_user.id)
    if uid not in users['t']:
        users['t'][uid] = dict(event.from_user)
        save_users()

        await event.answer(
            f"Hello, {event.from_user.get_mention(as_html=True)} 👋! You will receive reports every hour.",
            parse_mode=types.ParseMode.HTML,
        )

async def start_visitors():
    try:
        await visitors_d.start_polling()
    finally:
        await visitors_d.close()

async def start_traffic():
    try:
        traffic_d.register_message_handler(start_handler_traffic, commands={"start", "restart"})
        await traffic_d.start_polling()
    finally:
        await traffic_d.close()

@app.listener("before_server_start")
async def initialize(app, loop):
    asyncio.create_task(start_visitors())
    asyncio.create_task(start_traffic())


async def send_message(bot, user_id, text, reply_markup=None, disable_web_page_preview=True):
    try:
        await bot.send_message(user_id, text,
            parse_mode=types.ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)
    except exceptions.BotBlocked:
        log.error(f"Target [ID:{user_id}]: blocked by user")
    except exceptions.ChatNotFound:
        log.error(f"Target [ID:{user_id}]: invalid user ID")
    except exceptions.RetryAfter as e:
        log.error(f"Target [ID:{user_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
        await asyncio.sleep(e.timeout)
        return await send_message(bot, user_id, text, reply_markup, disable_web_page_preview)  # Recursive call
    except exceptions.UserDeactivated:
        log.error(f"Target [ID:{user_id}]: user is deactivated")
    except exceptions.TelegramAPIError:
        log.exception(f"Target [ID:{user_id}]: failed")
    else:
        log.info(f"Target [ID:{user_id}]: success")
        return True
    return False


async def broadcaster(bot, users, msg, reply_markup=None, disable_web_page_preview=True):
    count = 0
    try:
        for user_id in users:
            if await send_message(bot, int(user_id), msg, reply_markup, disable_web_page_preview):
                count += 1
            await asyncio.sleep(.05)  # 20 messages per second (Limit: 30 messages per second)
    finally:
        log.info(f"{count} messages successful sent.")

    return count


@app.post("/a/v")
async def visitor(request):
    country = ''
    try:
        country = geolite2.lookup(request.remote_addr).country
        country = pycountry.countries.get(alpha_2=country).name
    except:
        pass
    msg = request.head.decode('utf-8').replace(f';secret="{app.config.FORWARDED_SECRET}"', '')
    msg += '\n\n' + request.body.decode('utf-8') + '\n' + country

    keyboard_markup = types.InlineKeyboardMarkup(row_width=2)

    keyboard_markup.row(types.InlineKeyboardButton(request.remote_addr, callback_data=request.remote_addr))

    asyncio.create_task(broadcaster(visitors_bot, users['v'], msg, reply_markup=keyboard_markup))
    return text('')

async def whois(cmd):
    proc = await asyncio.create_subprocess_shell('whois '+cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    if stdout:
        return stdout.decode()
    if stderr:
        return stderr.decode()

@visitors_d.callback_query_handler()
@visitors_d.message_handler()
async def inline_kb_answer_callback_handler(query):
    try:
        answer_data = query.data
    except:
        answer_data = query.text
    # always answer callback queries, even if you have nothing to say
    await query.answer(f'whois {answer_data}')
    if answer_data.startswith('http'):
        answer_data = answer_data.split('://')[1].split('/')[0]
    if not re.fullmatch(r'\b[A-Za-z0-9.-]+\b', answer_data):
        text = f'WHOIS bot. Enter domain name or IP address.'
    else:
        text = await whois(answer_data)

    l = 0
    while l < len(text):
        await visitors_bot.send_message(query.from_user.id, text[l:l+3000], disable_web_page_preview=True)
        l += 3000

    await visitors_bot.send_message(int(list(users['v'].keys())[0]), answer_data + '\n' + str(dict(query.from_user)))

def format_bytes(sz, nb=False):
    if sz < 1024: return bytes
    suffixes = ('KB', 'MB', 'GB')
    for index, suf in enumerate(suffixes):
        dv = 1024 ** (index + 1)
        if sz > dv:
            res = str(round(sz / dv, 2)) + ('&nbsp;' if nb else ' ') + suf
    return res

@app.get("/a/traffic/<title>")
async def ftraffic(request, title):
    rx = request.args.get("rx")
    tx = request.args.get("tx")

    today = time.strftime('%d.%m.%Y', time.gmtime(time.time()))
    yesterday = time.strftime('%d.%m.%Y', time.gmtime(time.time()-86400))

    if title not in traffic: traffic[title] = {}

    if today not in traffic[title]:
        traffic[title][today] = {}
        traffic[title][today]['rx'] = 0
        traffic[title][today]['tx'] = 0

    try:
        prx = traffic[title]['prx']
        ptx = traffic[title]['ptx']
    except:
        prx = 0
        ptx = 0

    hrx = int(rx) - int(prx)
    htx = int(tx) - int(ptx)

    if hrx < 0: hrx = int(rx)
    if htx < 0: htx = int(tx)

    try:
        seconds = int(time.time() - traffic[title]['t'])
    except:
        seconds = 0

    traffic[title]['prx'] = rx
    traffic[title]['ptx'] = tx
    traffic[title]['t'] = time.time()


    traffic[title][today]['rx'] += hrx
    traffic[title][today]['tx'] += htx


    msg = f"<b>{title}</b>\n\n"
    msg += f"{seconds} sec" if seconds < 60 else f"{round(seconds / 60)} min"
    msg += f"\nRX: {format_bytes(hrx)}\nTX: {format_bytes(htx)}\n"

    msg += f"\n{today}"
    msg += f"\nRX: {format_bytes(traffic[title][today]['rx'])}\nTX: {format_bytes(traffic[title][today]['tx'])}\n"
    if yesterday in traffic[title]:
         msg += f"\n{yesterday} {tpersent(yesterday)}%"
         msg += f"\nRX: {format_bytes(traffic[title][yesterday]['rx'])}\nTX: {format_bytes(traffic[title][yesterday]['tx'])}\n"


    asyncio.create_task(broadcaster(traffic_bot, users['t'], msg))
    save_traffic()
    return text('')


def tpersent(cdate):
    tx = 0
    for title in traffic:
        try:
            tx += traffic[title][cdate]['tx']
        except:
            pass
    limit = 300 * 10 ** 9
    return round(tx*100/limit)



@app.get("/a/traffic")
async def ltraffic(request):
    dates = {}
    for title in traffic:
        for cdate in traffic[title]:
            if type(traffic[title][cdate]) == dict: dates[cdate] = True
    res = '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    res += '<title>Traffic</title></head><body>'
    for cdate in dates:
        pr = tpersent(cdate)
        res += '<div style="border: 1px solid black">'
        res += f'<div style="position: absolute; width: {pr}%; background-color: #fa5c5c; z-index: -1; opacity: 0.5; ">&nbsp;</div>'
        res += f'<span style="min-width: 150px; display: inline-block">{cdate} {pr}% </span>'
        for title in traffic:
            try:

                res += f"{title}&nbsp;{format_bytes(traffic[title][cdate]['rx'], 1)}/{format_bytes(traffic[title][cdate]['tx'], 1)} "
            except:
                pass
        res += "</div><br>\n"
    res += '</body></html>'
    return html(res)

if __name__ == '__main__':
    hp = SANIC_SOCKET.split(':')
    if hp[0] == 'unix':
        app.run(unix=hp[1], access_log=False, debug=True)
    else:
        app.run(host=hp[0], port=int(hp[1]), access_log=False)