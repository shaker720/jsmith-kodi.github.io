import re, requests, time

from resources.lib.base import gui, settings
from resources.lib.base.constants import ADDON_ID
from resources.lib.base.exceptions import Error
from resources.lib.base.log import log
from resources.lib.base.session import Session
from resources.lib.base.util import check_key, combine_playlist, get_credentials, set_credentials, write_file
from resources.lib.language import _
from resources.lib.util import get_image, get_play_url

try:
    from urllib.parse import urlparse, quote
except ImportError:
    from urllib import quote
    from urlparse import urlparse

class APIError(Error):
    pass

class API(object):
    def new_session(self, force=False, channels=False):
        access_token = settings.get(key='_access_token')
        creds = get_credentials()

        username = creds['username']
        password = creds['password']

        if len(access_token) > 0 and len(username) > 0 and force==False:
            user_agent = settings.get(key='_user_agent')

            HEADERS = {
                'User-Agent':  user_agent,
                'X-Client-Id': settings.get(key='_client_id') + "||" + user_agent,
                'X-OESP-Token': access_token,
                'X-OESP-Username': username,
            }

            self._session = Session(headers=HEADERS)
            self.logged_in = True
            return

        self.logged_in = False

        if not len(username) > 0:
            return

        if not len(password) > 0:
            password = gui.numeric(message=_.ASK_PASSWORD).strip()

            if not len(password) > 0:
                gui.ok(message=_.EMPTY_PASS, heading=_.LOGIN_ERROR_TITLE)
                return

        self.login(username=username, password=password, channels=channels)

    def login(self, username, password, channels=False):
        settings.remove(key='_access_token')
        user_agent = settings.get(key='_user_agent')

        HEADERS = {
            'User-Agent':  user_agent,
            'X-Client-Id': settings.get(key='_client_id') + "||" + user_agent,
            'X-OESP-Token': '',
            'X-OESP-Username': username,
        }

        self._session = Session(headers=HEADERS)
        data = self.download(url=settings.get(key='_session_url'), type="post", code=[200], data={"username": username, "password": password}, json_data=True, data_return=True, return_json=True, retry=True, check_data=False)

        if not data or not check_key(data, 'oespToken'):
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            return

        settings.set(key='_access_token', value=data['oespToken'])
        self._session.headers.update({'X-OESP-Token': data['oespToken']})

        if channels == True or settings.getInt(key='_channels_age') < int(time.time() - 86400):
            self.get_channels_for_user(location=data['locationId'])

        if settings.getBool(key='save_password', default=False):
            set_credentials(username=username, password=password)
        else:
            set_credentials(username=username, password='')

        self.logged_in = True

    def get_channels_for_user(self, location):
        channels_url = '{channelsurl}?byLocationId={location}&includeInvisible=true&personalised=true'.format(channelsurl=settings.get('_channels_url'), location=location)
        data = self.download(url=channels_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

        if data and check_key(data, 'entryCount') and check_key(data, 'channels'):
            settings.setInt(key='_channels_age', value=time.time())

            write_file(file="channels.json", data=data['channels'], isJSON=True)

            playlist = u'#EXTM3U\n'

            for row in sorted(data['channels'], key=lambda r: float(r.get('channelNumber', 'inf'))):
                channeldata = self.get_channel_data(row=row)
                urldata = get_play_url(content=channeldata['stream'])

                if urldata and check_key(urldata, 'play_url') and check_key(urldata, 'locator'):
                    path = 'plugin://{addonid}/?_=play_video&type=channel&id={play_url}&locator={locator}&_l=.pvr'.format(addonid=ADDON_ID, play_url=quote(urldata['play_url']), locator=quote(urldata['locator']))

                    playlist += u'#EXTINF:-1 tvg-id="{id}" tvg-chno="{channel}" tvg-name="{name}" tvg-logo="{logo}" group-title="TV" radio="false",{name}\n{path}\n'.format(id=channeldata['channel_id'], channel=channeldata['channel_number'], name=channeldata['label'], logo=channeldata['station_image_large'], path=path)

            write_file(file="tv.m3u8", data=playlist, isJSON=False)
            combine_playlist()

    def get_channel_data(self, row):
        channeldata = {
            'channel_id': row['stationSchedules'][0]['station']['id'],
            'channel_number': row['channelNumber'],
            'description': row['stationSchedules'][0]['station']['description'],
            'label': row['stationSchedules'][0]['station']['title'],
            'station_image_large': get_image("station-logo", row['stationSchedules'][0]['station']['images']),
            'stream': row['stationSchedules'][0]['station']['videoStreams']
        }

        return channeldata

    def play_url(self, type, path=None, locator=None):
        playdata = {'path': '', 'license': '', 'token': '', 'locator': ''}

        if not type or not len(type) > 0:
            return playdata

        if type == 'vod':
            if not path or not len(path) > 0:
                return playdata

            mediaitems_url = '{mediaitems_url}/{path}'.format(mediaitems_url=settings.get(key='_mediaitems_url'), path=path)
            data = self.download(url=mediaitems_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

            if not data or not check_key(data, 'videoStreams'):
                return playdata

            urldata = get_play_url(content=data['videoStreams'])

            if urldata and check_key(urldata, 'play_url') and check_key(urldata, 'locator'):
                path = urldata['play_url']
                locator = urldata['locator']

        if not path or not locator or not len(path) > 0 or not len(locator) > 0:
            return playdata

        license = settings.get('_widevine_url')

        token = self.get_play_token(locator=locator, force=True)

        if not token or not len(token) > 0:
            gui.ok(message=_.NO_STREAM_AUTH, heading=_.PLAY_ERROR)
            return playdata

        token = 'WIDEVINETOKEN'

        token_regex = re.search(r"(?<=;vxttoken=)(.*?)(?=/)", path)

        if token_regex and token_regex.group(1) and len(token_regex.group(1)) > 0:
            path = path.replace(token_regex.group(1), token)
        else:
            if 'sdash/' in path:
                spliturl = path.split('sdash/', 1)

                if len(spliturl) == 2:
                    path = '{urlpart1}sdash;vxttoken={token}/{urlpart2}?device=Orion-Replay-DASH'.format(urlpart1=spliturl[0], token=token, urlpart2=spliturl[1])
            else:
                spliturl = path.rsplit('/', 1)

                if len(spliturl) == 2:
                    path = '{urlpart1};vxttoken={token}/{urlpart2}'.format(urlpart1=spliturl[0], token=token, urlpart2=spliturl[1])

        real_url = "{hostscheme}://{hostname}".format(hostscheme=urlparse(path).scheme, hostname=urlparse(path).hostname)
        proxy_url = "http://127.0.0.1:{proxy_port}".format(proxy_port=settings.get(key='_proxyserver_port'))

        settings.set(key='_stream_hostname', value=real_url)
        path = path.replace(real_url, proxy_url)

        playdata = {'path': path, 'license': license, 'token': token, 'locator': locator}

        return playdata

    def get_play_token(self, locator, force=False):
        if settings.getInt(key='_drm_token_age') < int(time.time() - 50) and (settings.getInt(key='_tokenrun') == 0 or settings.getInt(key='_tokenruntime') < int(time.time() - 30)):
            force = True

        if locator != settings.get(key='_drm_locator') or settings.getInt(key='_drm_token_age') < int(time.time() - 90) or force == True:
            settings.setInt(key='_tokenrun', value=1)
            settings.setInt(key='_tokenruntime', value=time.time())

            data = self.download(url=settings.get(key='_token_url'), type="post", code=[200], data={"contentLocator": locator}, json_data=True, data_return=True, return_json=True, retry=True, check_data=False)

            if not data or not check_key(data, 'token'):
                settings.setInt(key="_tokenrun", value=0)
                return None

            settings.set(key='_drm_token', value=data['token'])
            settings.setInt(key='_drm_token_age', value=time.time())
            settings.set(key='_drm_locator', value=locator)
            settings.setInt(key="_tokenrun", value=0)

            return data['token']

        return settings.get(key='_drm_token')

    def add_to_watchlist(self, id, type):
        if type == "item":
            mediaitems_url = '{listings_url}/{id}'.format(listings_url=settings.get(key='_listings_url'), id=id)
            data = self.download(url=mediaitems_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

            if not data or not check_key(data, 'mediaGroupId'):
                return False

            id = data['mediaGroupId']

        watchlist_url = '{watchlist_url}/entries'.format(watchlist_url=settings.get(key='_watchlist_url'))
        data = self.download(url=watchlist_url, type="post", code=[204], data={"mediaGroup": {'id': id}}, json_data=True, data_return=False, return_json=False, retry=True, check_data=False)

        return data

    def list_watchlist(self):
        data = self.download(url=settings.get(key='_watchlist_url'), type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

        if not data or not check_key(data, 'entries'):
            return False

        return data

    def remove_from_watchlist(self, id):
        remove_url = '{watchlist_url}/entries/{id}'.format(watchlist_url=settings.get(key='_watchlist_url'), id=id)
        data = self.download(url=remove_url, type="delete", code=[204], data=None, json_data=False, data_return=False, return_json=False, retry=True, check_data=False)

        return data

    def watchlist_listing(self, id):
        end = int(time.time() * 1000)
        start = end - (7 * 24 * 60 * 60 * 1000)

        mediaitems_url = '{media_items_url}?&byMediaGroupId={id}&byStartTime={start}~{end}&range=1-250&sort=startTime%7Cdesc'.format(media_items_url=settings.get(key='_listings_url'), id=id, start=start, end=end)
        data = self.download(url=mediaitems_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

        if not data or not check_key(data, 'listings'):
            return False

        return data

    def online_search(self, search, vod=True):
        end = int(time.time() * 1000)
        start = end - (7 * 24 * 60 * 60 * 1000)

        vodstr = ''

        if vod == True:
            vodstr = '%2CmoviesAndSeries'

        search_url = '{search_url}?byBroadcastStartTimeRange={start}~{end}&numItems=25&byCatalog=tvPrograms{vodstr}&byEntitled=true&personalised=true&q={search}'.format(search_url=settings.get(key='_search_url'), start=start, end=end, vodstr=vodstr, search=quote(search))
        data = self.download(url=search_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

        if not data or not check_key(data, 'tvPrograms') or not check_key(data['tvPrograms'], 'entries'):
            return False

        if vod == True:
            if not data or not check_key(data, 'moviesAndSeries') or not check_key(data['moviesAndSeries'], 'entries'):
                return False

        return data

    def check_data(self, resp, json=False):
        return True

    def download(self, url, type, code=None, data=None, json_data=True, data_return=True, return_json=True, retry=True, check_data=True):
        if type == "post" and data:
            if json_data == True:
                resp = self._session.post(url, json=data)
            else:
                resp = self._session.post(url, data=data)
        else:
            resp = getattr(self._session, type)(url)

        if (code and not resp.status_code in code) or (check_data == True and self.check_data(resp=resp) == False):
            if retry != True:
                return None

            self.new_session(force=True)

            if self.logged_in != True:
                return None

            if type == "post" and data:
                if json_data == True:
                    resp = self._session.post(url, json=data)
                else:
                    resp = self._session.post(url, data=data)
            else:
                resp = getattr(self._session, type)(url)

            if (code and not resp.status_code in code) or (check_data == True and self.check_data(resp=resp) == False):
                return None

        if data_return == True:
            try:
                if return_json == True:
                    return resp.json()
                else:
                    return resp
            except:
                return None

        return True