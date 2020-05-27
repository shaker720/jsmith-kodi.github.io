CONST_BASE_URL = 'https://www.tv-anywhere.nl'

CONST_BASE_HEADERS = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.9,nl;q=0.8',
    'Cache-Control': 'no-cache',
    'DNT': '1',
    'Origin': CONST_BASE_URL,
    'Pragma': 'no-cache',
    'Referer': CONST_BASE_URL + '/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}

CONST_EPG = 'https://jsmith-epg.github.io/t.epg.xml.zip'
CONST_MINIMALEPG = 'https://jsmith-epg.github.io/t.epg.xml.zip'
CONST_RADIO = 'https://jsmith-epg.github.io/radio.m3u8'
CONST_SETTINGS = 'https://jsmith-epg.github.io/t.settings.json'
CONST_VOD = 'https://jsmith-epg.github.io/t.vod.json'