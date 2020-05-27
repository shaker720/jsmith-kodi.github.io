import re, time

from resources.lib.base import gui, settings
from resources.lib.base.constants import ADDON_ID
from resources.lib.base.exceptions import Error
from resources.lib.base.log import log
from resources.lib.base.session import Session
from resources.lib.base.util import check_key, combine_playlist, get_credentials, set_credentials, write_file
from resources.lib.constants import CONST_BASE_URL
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

        login_url = '{base_url}/inloggen'.format(base_url=CONST_BASE_URL)

        resp = self.download(url=login_url, type="get", code=None, data=None, json_data=False, data_return=True, return_json=False, retry=False, check_data=False)

        if resp.status_code != 200 and resp.status_code != 302:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        if self.check_data(resp=resp) == False:
            resp.encoding = 'utf-8'
            frmtoken = re.findall(r'name=\"form\[_token\]\"\s+value=\"([\S]*)\"', resp.text)

            session_post_data = {
                "form[password]": password,
                "form[email]": username,
                "form[login]": '',
                'form[_token]': frmtoken[0],
            }

            resp = self.download(url=login_url, type="post", code=None, data=session_post_data, json_data=False, data_return=True, return_json=False, retry=False, check_data=False)

            if (resp.status_code != 200 and resp.status_code != 302) or self.check_data(resp=resp) == False:
                gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
                self.clear_session()
                return

        data = self.download(url='{base_url}/api/info'.format(base_url=CONST_BASE_URL), type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=False, check_data=True)

        if not data or not check_key(data, 'sessionToken') or not check_key(data, 'emp'):
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        settings.set(key='_session_token', value=data['sessionToken'])
        settings.set(key='_emp_url', value=data['emp']['url'])
        settings.set(key='_emp_customer', value=data['emp']['customer'])
        settings.set(key='_emp_businessunit', value=data['emp']['businessunit'])

        if channels == True or settings.getInt(key='_channels_age') < int(time.time() - 86400):
            self.get_channels_for_user(channels=data['channels'])

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

    def get_channels_for_user(self, channels):
        settings.setInt(key='_channels_age', value=time.time())

        write_file(file="channels.json", data=channels, isJSON=True)

        data = u'#EXTM3U\n'

        for row in channels:
            channeldata = self.get_channel_data(rows=channels, row=row)
            path = 'plugin://{addonid}/?_=play_video&channel={channel}&type=channel&_l=.pvr'.format(addonid=ADDON_ID, channel=channeldata['channel_id'])
            data += u'#EXTINF:-1 tvg-id="{id}" tvg-chno="{channel}" tvg-name="{name}" tvg-logo="{logo}" group-title="TV" radio="false",{name}\n{path}\n'.format(id=channeldata['channel_id'], channel=channeldata['channel_number'], name=channeldata['label'], logo=channeldata['station_image_large'], path=path)

        write_file(file="tv.m3u8", data=data, isJSON=False)
        combine_playlist()

    def get_channel_data(self, rows, row):
        channeldata = {
            'channel_id': rows[row]['id'],
            'channel_number': int(rows[row]['displayOrder']) + 1,
            'description': '', 'label': rows[row]['title'],
            'station_image_large': rows[row]['logos']['guide']
        }

        return channeldata

    def play_url(self, type, channel=None, id=None):
        playdata = {'path': '', 'license': '', 'token': '', 'sessionid': ''}

        if not type or not len(type) > 0:
            return playdata

        if type == 'channel' and channel:
            channel_url = 'https://www.tv-anywhere.nl/api/guide/details/{channel}'.format(channel=channel)
            data = self.download(url=channel_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

            if not data or not check_key(data, 'id'):
                return playdata

            id = data['id']

        if not id:
            return playdata

        self._session.headers.update({'Authorization': 'Bearer ' + settings.get(key='_session_token')})

        session_post_data = {
            "DispatchTime": time.time(),
            "BusinessUnit": settings.get(key='_emp_businessunit'),
            "Customer": settings.get(key='_emp_customer'),
            "Payload": {
                'Timestamp': time.time(),
                'EventType': 'Playback.Aborted',
                'OffsetTime': time.time(),
            },
            "SessionId": settings.get(key='_play_session_id'),
            "ClockOffset": 0,
        }

        eventsink_send_url = '{emp_url}/eventsink/send'.format(emp_url=settings.get(key='_emp_url'))
        self.download(url=eventsink_send_url, type="post", code=None, data=session_post_data, json_data=True, data_return=False, return_json=False, retry=False, check_data=False)

        session_post_data = {
            "drm": "CENC",
            "format": "DASH",
            "type": "application/dash+xml",
        }

        play_url_path = '{emp_url}/v1/customer/{emp_customer}/businessunit/{emp_businessunit}/entitlement/channel/{channel}/program/{id}/play'.format(emp_url=settings.get(key='_emp_url'), emp_customer=settings.get(key='_emp_customer'), emp_businessunit=settings.get(key='_emp_businessunit'), channel=channel, id=id)
        data = self.download(url=play_url_path, type="post", code=[200], data=session_post_data, json_data=True, data_return=True, return_json=True, retry=True, check_data=True)

        if not data or check_key(data, 'message') or not check_key(data, 'cencConfig') or not check_key(data, 'mediaLocator') or not check_key(data, 'playSessionId'):
            return playdata

        license = data['cencConfig']['com.widevine.alpha']
        path = data['mediaLocator']
        sessionid = data['playSessionId']
        token = data['playToken']

        settings.set(key='_play_session_id', value=sessionid)

        session_post_data = {
            "BusinessUnit": settings.get(key='_emp_businessunit'),
            "Customer": settings.get(key='_emp_customer'),
            "SessionId": settings.get(key='_play_session_id'),
        }

        eventsink_init_url = '{emp_url}/eventsink/init'.format(emp_url=settings.get(key='_emp_url'))
        self.download(url=eventsink_init_url, type="post", code=None, data=session_post_data, json_data=True, data_return=False, return_json=False, retry=False, check_data=False)

        real_url = "{hostscheme}://{hostname}".format(hostscheme=urlparse(path).scheme, hostname=urlparse(path).hostname)
        proxy_url = "http://127.0.0.1:{proxy_port}".format(proxy_port=settings.get(key='_proxyserver_port'))

        settings.set(key='_stream_hostname', value=real_url)
        path = path.replace(real_url, proxy_url)

        playdata = {'path': path, 'license': license, 'token': token, 'sessionid': sessionid}

        return playdata

    def check_data(self, resp, json=False):
        resp.encoding = 'utf-8'
        frmtoken = re.findall(r'name=\"form\[_token\]\"\s+value=\"([\S]*)\"', resp.text)

        if frmtoken and len(frmtoken) > 0:
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