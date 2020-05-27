import time

from resources.lib.base import gui, settings
from resources.lib.base.constants import ADDON_ID
from resources.lib.base.exceptions import Error
from resources.lib.base.log import log
from resources.lib.base.session import Session
from resources.lib.base.util import check_key, combine_playlist, get_credentials, set_credentials, write_file
from resources.lib.constants import CONST_IMAGE_URL
from resources.lib.language import _

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

class APIError(Error):
    pass

class API(object):
    def new_session(self, force=False, channels=False):
        cookies = settings.get(key='_cookies')

        if len(cookies) > 0 and force == False:
            self._session = Session(cookies_key='_cookies')
            self.logged_in = True
            return

        self.logged_in = False

        creds = get_credentials()

        username = creds['username']
        password = creds['password']

        if not len(username) > 0:
            return

        if not len(password) > 0:
            password = gui.numeric(message=_.ASK_PASSWORD).strip()

            if not len(password) > 0:
                gui.ok(message=_.EMPTY_PASS, heading=_.LOGIN_ERROR_TITLE)
                return

        self.login(username=username, password=password, channels=channels)

    def login(self, username, password, channels=False):
        settings.remove(key='_cookies')
        self._session = Session(cookies_key='_cookies')

        session_url = '{api_url}/USER/SESSIONS/'.format(api_url=settings.get(key='_api_url'))

        session_post_data = {
            "credentialsStdAuth": {
                'username': username,
                'password': password,
                'remember': 'Y',
                'deviceRegistrationData': {
                    'deviceId': settings.get(key='_devicekey'),
                    'accountDeviceIdType': 'DEVICEID',
                    'deviceType' : 'PCTV',
                    'vendor' : settings.get(key='_browser_name'),
                    'model' : settings.get(key='_browser_version'),
                    'deviceFirmVersion' : settings.get(key='_os_name'),
                    'appVersion' : settings.get(key='_os_version')
                }
            },
        }

        resp = self._session.post(session_url, json=session_post_data)

        if resp.status_code != 200:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        try:
            data = resp.json()
        except:
            return

        if not data or not check_key(data, 'resultCode') or data['resultCode'] == 'KO':
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        if channels == True or settings.getInt(key='_channels_age') < int(time.time() - 86400):
            self.get_channels_for_user()
            self.vod_subscription()

        if settings.getBool(key='save_password', default=False):
            set_credentials(username=username, password=password)
        else:
            set_credentials(username=username, password='')

        self.logged_in = True

    def clear_session(self):
        settings.remove(key='_cookies')

        try:
            self._session.clear_cookies()
        except:
            pass

    def get_channels_for_user(self):
        channels_url = '{api_url}/TRAY/LIVECHANNELS?orderBy=orderId&sortOrder=asc&from=0&to=999&dfilter_channels=subscription'.format(api_url=settings.get(key='_api_url'))
        data = self.download(url=channels_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

        if data and check_key(data['resultObj'], 'containers'):
            settings.setInt(key='_channels_age', value=time.time())

            write_file(file="channels.json", data=data['resultObj']['containers'], isJSON=True)

            playlist = u'#EXTM3U\n'

            for row in data['resultObj']['containers']:
                channeldata = self.get_channel_data(row=row)
                path = 'plugin://{addonid}/?_=play_video&channel={channel}&id={asset}&type=channel&_l=.pvr'.format(addonid=ADDON_ID, channel=channeldata['channel_id'], asset=channeldata['asset_id'])
                playlist += u'#EXTINF:-1 tvg-id="{id}" tvg-chno="{channel}" tvg-name="{name}" tvg-logo="{logo}" group-title="TV" radio="false",{name}\n{path}\n'.format(id=channeldata['channel_id'], channel=channeldata['channel_number'], name=channeldata['label'], logo=channeldata['station_image_large'], path=path)

            write_file(file="tv.m3u8", data=playlist, isJSON=False)
            combine_playlist()

    def get_channel_data(self, row):
        asset_id = ''

        if check_key(row, 'assets'):
            for asset in row['assets']:
                if check_key(asset, 'videoType') and asset['videoType'] == 'SD_DASH_PR':
                    asset_id = asset['assetId']
                    break

        channeldata = {
            'channel_id': row['metadata']['channelId'],
            'channel_number': int(row['metadata']['orderId']),
            'description': '',
            'label': row['metadata']['channelName'],
            'station_image_large': '{images_url}/logo/{external_id}/256.png'.format(images_url=CONST_IMAGE_URL, external_id=row['metadata']['externalId']),
            'asset_id': asset_id
        }

        return channeldata

    def play_url(self, type, channel=None, id=None):
        playdata = {'path': '', 'license': '', 'token': ''}

        license = ''
        asset_id = ''
        militime = int(time.time() * 1000)

        if type == 'channel':
            play_url = '{api_url}/CONTENT/VIDEOURL/LIVE/{channel}/{id}/?deviceId={device_key}&profile=G02&time={time}'.format(api_url=settings.get(key='_api_url'), channel=channel, id=id, device_key=settings.get(key='_devicekey'), time=militime)
        else:
            if type == 'program':
                typestr = "PROGRAM"
            else:
                typestr = "VOD"

            program_url = '{api_url}/CONTENT/USERDATA/{type}/{id}'.format(api_url=settings.get(key='_api_url'), type=typestr, id=id)
            data = self.download(url=program_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

            if not data or not check_key(data['resultObj'], 'containers'):
                return playdata

            for row in data['resultObj']['containers']:
                if check_key(row, 'entitlement') and check_key(row['entitlement'], 'assets'):
                    for asset in row['entitlement']['assets']:
                        if type == 'program':
                            if check_key(asset, 'videoType') and check_key(asset, 'programType') and asset['videoType'] == 'SD_DASH_PR' and asset['programType'] == 'CUTV':
                                asset_id = asset['assetId']
                                break
                        else:
                            if check_key(asset, 'videoType') and check_key(asset, 'assetType') and asset['videoType'] == 'SD_DASH_PR' and asset['assetType'] == 'MASTER':
                                if check_key(asset, 'rights') and asset['rights'] == 'buy':
                                    gui.ok(message=_.NO_STREAM_AUTH, heading=_.PLAY_ERROR)
                                    return playdata

                                asset_id = asset['assetId']
                                break

            if len(str(asset_id)) == 0:
                return playdata

            play_url = '{api_url}/CONTENT/VIDEOURL/{type}/{id}/{asset_id}/?deviceId={device_key}&profile=G02&time={time}'.format(api_url=settings.get(key='_api_url'), type=typestr, id=id, asset_id=asset_id, device_key=settings.get(key='_devicekey'), time=militime)

        data = self.download(url=play_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

        if not data or not check_key(data['resultObj'], 'token') or not check_key(data['resultObj'], 'src') or not check_key(data['resultObj']['src'], 'sources') or not check_key(data['resultObj']['src']['sources'], 'src'):
            return playdata

        if check_key(data['resultObj']['src']['sources'], 'contentProtection') and check_key(data['resultObj']['src']['sources']['contentProtection'], 'widevine') and check_key(data['resultObj']['src']['sources']['contentProtection']['widevine'], 'licenseAcquisitionURL'):
            license = data['resultObj']['src']['sources']['contentProtection']['widevine']['licenseAcquisitionURL']

        path = data['resultObj']['src']['sources']['src']
        token = data['resultObj']['token']

        real_url = "{hostscheme}://{hostname}".format(hostscheme=urlparse(path).scheme, hostname=urlparse(path).hostname)
        proxy_url = "http://127.0.0.1:{proxy_port}".format(proxy_port=settings.get(key='_proxyserver_port'))

        settings.set(key='_stream_hostname', value=real_url)
        path = path.replace(real_url, proxy_url)

        playdata = {'path': path, 'license': license, 'token': token}

        return playdata

    def vod_subscription(self):
        subscription = []

        series_url = '{api_url}/TRAY/SEARCH/VOD?from=1&to=9999&filter_contentType=GROUP_OF_BUNDLES,VOD&filter_contentSubtype=SERIES,VOD&filter_contentTypeExtended=VOD&filter_excludedGenres=erotiek&filter_technicalPackages=10078,10081,10258,10255&dfilter_packages=matchSubscription&orderBy=activationDate&sortOrder=desc'.format(api_url=settings.get(key='_api_url'))
        data = self.download(url=series_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

        if not data or not check_key(data['resultObj'], 'containers'):
            return None

        for row in data['resultObj']['containers']:
            subscription.append(row['metadata']['contentId'])

        write_file(file='vod_subscription.json', data=subscription, isJSON=True)

    def vod_seasons(self, id):
        seasons = []

        program_url = '{api_url}/CONTENT/DETAIL/GROUP_OF_BUNDLES/{id}'.format(api_url=settings.get(key='_api_url'), id=id)
        data = self.download(url=program_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

        if not data or not check_key(data['resultObj'], 'containers'):
            return None

        for row in data['resultObj']['containers']:
            for currow in row['containers']:
                if check_key(currow, 'metadata') and check_key(currow['metadata'], 'season') and currow['metadata']['contentSubtype'] == 'SEASON':
                    seasons.append({'id': currow['metadata']['contentId'], 'seriesNumber': currow['metadata']['season'], 'desc': currow['metadata']['shortDescription'], 'image': currow['metadata']['pictureUrl']})

        return seasons

    def vod_season(self, id):
        season = []
        episodes = []

        program_url = '{api_url}/CONTENT/DETAIL/BUNDLE/{id}'.format(api_url=settings.get(key='_api_url'), id=id)
        data = self.download(url=program_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

        if not data or not check_key(data['resultObj'], 'containers'):
            return None

        for row in data['resultObj']['containers']:
            for currow in row['containers']:
                if check_key(currow, 'metadata') and check_key(currow['metadata'], 'season') and currow['metadata']['contentSubtype'] == 'EPISODE' and not currow['metadata']['episodeNumber'] in episodes:
                    asset_id = ''

                    for asset in currow['assets']:
                        if check_key(asset, 'videoType') and asset['videoType'] == 'SD_DASH_PR' and check_key(asset, 'assetType') and asset['assetType'] == 'MASTER':
                            asset_id = asset['assetId']
                            break

                    episodes.append(currow['metadata']['episodeNumber'])
                    season.append({'id': currow['metadata']['contentId'], 'assetid': asset_id, 'duration': currow['metadata']['duration'], 'title': currow['metadata']['episodeTitle'], 'episodeNumber': '{season}.{episode}'.format(season=currow['metadata']['season'], episode=currow['metadata']['episodeNumber']), 'desc': currow['metadata']['shortDescription'], 'image': currow['metadata']['pictureUrl']})

        return season

    def check_data(self, resp, json=True):
        if json == True:
            data = resp.json()

            if data and check_key(data, 'resultCode') and data['resultCode'] == 'KO':
                return False

            if not data or not check_key(data, 'resultCode') or not data['resultCode'] == 'OK' or not check_key(data, 'resultObj'):
                return False

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