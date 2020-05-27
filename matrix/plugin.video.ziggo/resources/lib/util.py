import re


from resources.lib.base import settings
from resources.lib.base.util import load_file
from resources.lib.constants import CONST_DEFAULT_CLIENTID

def get_image(prefix, content):
    best_image = 0
    image_url = ''

    for images in content:
        if (prefix + '-xlarge') in images['assetTypes']:
            return images['url']
        elif (prefix + '-large') in images['assetTypes']:
            if best_image < 2:
                best_image = 2
                image_url = images['url']
        elif (prefix + '-medium') in images['assetTypes']:
            if best_image < 1:
                best_image = 1
                image_url = images['url']

    return image_url

def get_play_url(content):
    for stream in content:
        if  'streamingUrl' in stream and 'contentLocator' in stream and 'assetTypes' in stream and 'Orion-DASH' in stream['assetTypes']:
            return {'play_url': stream['streamingUrl'], 'locator': stream['contentLocator']}

    return {'play_url': '', 'locator': ''}

def remove_ac3(xml):
    try:
        result = re.findall(r'<AdaptationSet(?:(?!</AdaptationSet>)[\S\s])+</AdaptationSet>', xml)

        for match in result:
            if "codecs=\"ac-3\"" in match:
                xml = xml.replace(match, "")
    except:
        pass

    return xml

def update_settings():
    settingsJSON = load_file(file='settings.json', isJSON=True)

    try:
        license_url = '{base_url}/{country_code}/{language_code}'.format(base_url=settingsJSON['settings']['urls']['base'], country_code=settingsJSON['settings']['countryCode'], language_code=settingsJSON['settings']['languageCode'])

        settings.set(key='_search_url', value=settingsJSON['settings']['routes']['search'])
        settings.set(key='_session_url', value=settingsJSON['settings']['routes']['session'])
        settings.set(key='_token_url', value=settingsJSON['settings']['routes']['refreshToken'])
        settings.set(key='_channels_url', value=settingsJSON['settings']['routes']['channels'])
        settings.set(key='_token_url',  value='{license_url}/web/license/token'.format(license_url=license_url))
        settings.set(key='_widevine_url', value='{license_url}/web/license/eme'.format(license_url=license_url))
        settings.set(key='_listings_url', value=settingsJSON['settings']['routes']['listings'])
        settings.set(key='_mediaitems_url', value=settingsJSON['settings']['routes']['mediaitems'])
        settings.set(key='_mediagroupsfeeds_url', value=settingsJSON['settings']['routes']['mediagroupsfeeds'])
        settings.set(key='_watchlist_url', value=settingsJSON['settings']['routes']['watchlist'])
    except:
        pass

    try:
        client_id = settingsJSON['client_id']
    except:
        client_id = CONST_DEFAULT_CLIENTID

    settings.set(key='_client_id', value=client_id)