from resources.lib.base import settings, uaparser
from resources.lib.base.util import load_file
from resources.lib.constants import CONST_DEFAULT_API

def update_api_url():
    settingsJSON = load_file(file='settings.json', isJSON=True)

    try:
        settings.set(key='_api_url', value=settingsJSON['api_url'])
    except:
        settings.set(key='_api_url', value=CONST_DEFAULT_API)

def update_img_size():
    settingsJSON = load_file(file='settings.json', isJSON=True)

    try:
        settings.set(key='_img_size', value=settingsJSON['img_size'])
    except:
        settings.set(key='_img_size', value=CONST_DEFAULT_IMG_SIZE)

def update_os_browser():
    user_agent = settings.get(key='_user_agent')
    settings.set(key='_browser_name', value=uaparser.detect(user_agent)['browser']['name'])
    settings.set(key='_browser_version', value=uaparser.detect(user_agent)['browser']['version'])
    settings.set(key='_os_name', value=uaparser.detect(user_agent)['os']['name'])
    settings.set(key='_os_version', value=uaparser.detect(user_agent)['os']['version'])
