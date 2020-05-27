import _strptime

import datetime, json, pytz, requests, string, sys, time, xbmc, xbmcplugin

from fuzzywuzzy import fuzz
from resources.lib.api import API
from resources.lib.base import plugin, gui, signals, inputstream, settings
from resources.lib.base.exceptions import Error
from resources.lib.base.log import log
from resources.lib.base.util import check_key, convert_datetime_timezone, date_to_nl_dag, date_to_nl_maand, get_credentials, load_file
from resources.lib.language import _
from resources.lib.util import get_image, get_play_url

try:
    unicode
except NameError:
    unicode = str

api = API()
ADDON_HANDLE = int(sys.argv[1])
backend = ''
query_channel = []

@plugin.route('')
def home(**kwargs):
    if settings.getBool(key='_first_boot') == True:
        first_boot()

    folder = plugin.Folder()

    if not plugin.logged_in:
        folder.add_item(label=_(_.LOGIN, _bold=True), path=plugin.url_for(func_or_url=login))
    else:
        folder.add_item(label=_(_.LIVE_TV, _bold=True),  path=plugin.url_for(func_or_url=live_tv))
        folder.add_item(label=_(_.CHANNELS, _bold=True), path=plugin.url_for(func_or_url=replaytv))

        if settings.getBool('showMoviesSeries') == True:
            folder.add_item(label=_(_.SERIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='series', label=_.SERIES, kids=0, start=0))
            folder.add_item(label=_(_.MOVIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='movies', label=_.MOVIES, kids=0, start=0))
            folder.add_item(label=_(_.HBO_SERIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='hboseries', label=_.HBO_SERIES, kids=0, start=0))
            folder.add_item(label=_(_.HBO_MOVIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='hbomovies', label=_.HBO_MOVIES, kids=0, start=0))
            folder.add_item(label=_(_.KIDS_SERIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='kids', label=_.KIDS_SERIES, kids=1, start=0))
            folder.add_item(label=_(_.KIDS_MOVIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='kids', label=_.KIDS_MOVIES, kids=2, start=0))

        folder.add_item(label=_(_.WATCHLIST, _bold=True), path=plugin.url_for(func_or_url=watchlist))
        folder.add_item(label=_(_.SEARCH, _bold=True), path=plugin.url_for(func_or_url=search_menu))

    folder.add_item(label=_.SETTINGS, path=plugin.url_for(func_or_url=settings_menu))

    return folder

#Main menu items
@plugin.route()
def login(**kwargs):
    creds = get_credentials()
    username = gui.input(message=_.ASK_USERNAME, default=creds['username']).strip()

    if not len(username) > 0:
        gui.ok(message=_.EMPTY_USER, heading=_.LOGIN_ERROR_TITLE)
        return

    password = gui.input(message=_.ASK_PASSWORD, hide_input=True).strip()

    if not len(password) > 0:
        gui.ok(message=_.EMPTY_PASS, heading=_.LOGIN_ERROR_TITLE)
        return

    api.login(username=username, password=password, channels=True)
    plugin.logged_in = api.logged_in
    check_entitlements()

    gui.refresh()

@plugin.route()
def live_tv(**kwargs):
    folder = plugin.Folder(title=_.LIVE_TV)

    for row in get_live_channels(addon=settings.getBool(key='enable_simple_iptv')):
        folder.add_item(
            label = row['label'],
            info = {'plot': row['description']},
            art = {'thumb': row['image']},
            path = row['path'],
            playable = row['playable'],
        )

    return folder

@plugin.route()
def replaytv(**kwargs):
    folder = plugin.Folder(title=_.CHANNELS)

    folder.add_item(
        label = _.PROGSAZ,
        info = {'plot': _.PROGSAZDESC},
        path = plugin.url_for(func_or_url=replaytv_alphabetical),
    )

    for row in get_replay_channels():
        folder.add_item(
            label = row['label'],
            info = {'plot': row['description']},
            art = {'thumb': row['image']},
            path = row['path'],
            playable = row['playable'],
        )

    return folder

@plugin.route()
def replaytv_alphabetical(**kwargs):
    folder = plugin.Folder(title=_.PROGSAZ)
    label = _.OTHERTITLES

    folder.add_item(
        label = label,
        info = {'plot': _.OTHERTITLESDESC},
        path = plugin.url_for(func_or_url=replaytv_list, label=label, start=0, character='other'),
    )

    for character in string.ascii_uppercase:
        label = _.TITLESWITH + character

        folder.add_item(
            label = label,
            info = {'plot': _.TITLESWITHDESC + character},
            path = plugin.url_for(func_or_url=replaytv_list, label=label, start=0, character=character),
        )

    return folder

@plugin.route()
def replaytv_list(character, label='', start=0, **kwargs):
    start = int(start)
    folder = plugin.Folder(title=label)

    data = load_file(file='list_replay.json', isJSON=True)

    if not data:
        gui.ok(message=_.NO_REPLAY_TV_INFO, heading=_.NO_REPLAY_TV_INFO)
        return folder

    if not check_key(data, character):
        return folder

    processed = process_replaytv_list(data=data[character], start=start)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'count') and len(data[character]) > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=replaytv_list, character=character, label=label, start=processed['count']),
        )

    return folder

@plugin.route()
def replaytv_by_day(label='', image='', description='', station='', **kwargs):
    folder = plugin.Folder(title=label)

    for x in range(0, 7):
        curdate = datetime.date.today() - datetime.timedelta(days=x)

        itemlabel = ''

        if x == 0:
            itemlabel = _.TODAY + " - "
        elif x == 1:
            itemlabel = _.YESTERDAY + " - "

        if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
            itemlabel += date_to_nl_dag(curdate=curdate) + curdate.strftime(" %d ") + date_to_nl_maand(curdate=curdate) + curdate.strftime(" %Y")
        else:
            itemlabel += curdate.strftime("%A %d %B %Y").capitalize()

        folder.add_item(
            label = itemlabel,
            info = {'plot': description},
            art = {'thumb': image},
            path = plugin.url_for(func_or_url=replaytv_content, label=itemlabel, day=x, station=station),
        )

    return folder

@plugin.route()
def replaytv_item(ids=None, label=None, start=0, **kwargs):
    start = int(start)
    first = label[0]

    folder = plugin.Folder(title=label)

    if first.isalpha():
        data = load_file(file=first + "_replay.json", isJSON=True)
    else:
        data = load_file(file='other_replay.json', isJSON=True)

    if not data:
        return folder

    processed = process_replaytv_list_content(data=data, ids=ids, start=start)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'totalrows') and check_key(processed, 'count') and processed['totalrows'] > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=replaytv_item, ids=ids, label=label, start=processed['count']),
        )

    return folder

@plugin.route()
def replaytv_content(label, day, station='', start=0, **kwargs):
    day = int(day)
    start = int(start)
    folder = plugin.Folder(title=label)

    data = load_file(file=station + "_replay.json", isJSON=True)

    if not data:
        gui.ok(_.DISABLE_ONLY_STANDARD, _.NO_REPLAY_TV_INFO)
        return folder

    totalrows = len(data)
    processed = process_replaytv_content(data=data, day=day, start=start)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'count') and totalrows > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=replaytv_content, label=label, day=day, station=station, start=processed['count']),
        )

    return folder

@plugin.route()
def vod(file, label, kids=0, start=0, **kwargs):
    kids = int(kids)
    start = int(start)
    folder = plugin.Folder(title=label)

    data = load_file(file='vod.json', isJSON=True)[file]

    if not data:
        return folder

    processed = process_vod_content(data=data, start=start, series=kids, type=label)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'count') and len(data) > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=vod, file=file, label=label, kids=kids, start=processed['count']),
        )

    return folder

@plugin.route()
def vod_series(label, description, image, seasons, mediagroupid=None, **kwargs):
    folder = plugin.Folder(title=label)

    items = []
    context = []

    seasons = json.loads(seasons)

    if mediagroupid:
        context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=mediagroupid, type='group')), ))

    for season in seasons:
        items.append(plugin.Item(
            label = _.SEASON + " " + unicode(season['seriesNumber']),
            info = {'plot': description},
            art = {'thumb': image},
            path = plugin.url_for(func_or_url=vod_season, label=label, id=season['id'], mediagroupid=mediagroupid),
            context = context,
        ))

    folder.add_items(items)

    return folder

@plugin.route()
def vod_season(label, id, mediagroupid=None, **kwargs):
    folder = plugin.Folder(title=label)

    season_url = '{mediaitems_url}/?byParentId={id}&includeAdult=true&range=0-1000&sort=seriesEpisodeNumber|ASC'.format(mediaitems_url=settings.get(key='_mediaitems_url'), id=id)
    data = api.download(url=season_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

    if not data or not check_key(data, 'mediaItems'):
        return folder

    processed = process_vod_season(data=data, mediagroupid=mediagroupid)

    if processed:
        folder.add_items(processed)

    return folder

@plugin.route()
def search_menu(**kwargs):
    folder = plugin.Folder(title=_.SEARCHMENU)
    label = _.NEWSEARCH

    folder.add_item(
        label = label,
        info = {'plot': _.NEWSEARCHDESC},
        path = plugin.url_for(func_or_url=search),
    )

    folder.add_item(
        label= label + " (Online)",
        path=plugin.url_for(func_or_url=online_search)
    )

    for x in range(1, 10):
        searchstr = settings.get(key='_search' + unicode(x))

        if searchstr != '':
            type = settings.get(key='_search_type' + unicode(x))
            label = searchstr + type

            if type == " (Online)":
                path = plugin.url_for(func_or_url=online_search, query=searchstr)
            else:
                path = plugin.url_for(func_or_url=search, query=searchstr)

            folder.add_item(
                label = label,
                info = {'plot': _(_.SEARCH_FOR, query=searchstr)},
                path = path,
            )

    return folder

@plugin.route()
def search(query=None, **kwargs):
    items = []

    if not query:
        query = gui.input(message=_.SEARCH, default='').strip()

        if not query:
            return

        for x in reversed(list(range(2, 10))):
            settings.set(key='_search' + unicode(x), value=settings.get(key='_search' + unicode(x - 1)))
            settings.set(key='_search_type' + unicode(x), value=settings.get(key='_search_type' + unicode(x - 1)))

        settings.set(key='_search1', value=query)
        settings.set(key='_search_type1', value='')

    folder = plugin.Folder(title=_(_.SEARCH_FOR, query=query))

    data = load_file(file='list_replay.json', isJSON=True)
    processed = process_replaytv_search(data=data, start=0, search=query)
    items += processed['items']

    if settings.getBool('showMoviesSeries') == True:
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['series'], start=0, series=0, search=query, type=_.SERIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['movies'], start=0, series=0, search=query, type=_.MOVIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['hboseries'], start=0, series=0, search=query, type=_.HBO_SERIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['hbomovies'], start=0, series=0, search=query, type=_.HBO_MOVIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['kids'], start=0, series=1, search=query, type=_.KIDS_SERIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['kids'], start=0, series=2, search=query, type=_.KIDS_MOVIES)
        items += processed['items']

    items[:] = sorted(items, key=_sort_replay_items, reverse=True)
    items = items[:25]

    folder.add_items(items)

    return folder

@plugin.route()
def online_search(query=None, **kwargs):
    if not query:
        query = gui.input(message=_.SEARCH, default='').strip()

        if not query:
            return

        for x in reversed(list(range(2, 10))):
            settings.set(key='_search' + unicode(x), value=settings.get(key='_search' + unicode(x - 1)))
            settings.set(key='_search_type' + unicode(x), value=settings.get(key='_search_type' + unicode(x - 1)))

        settings.set(key='_search1', value=query)
        settings.set(key='_search_type1', value=' (Online)')

    folder = plugin.Folder(title=_(_.SEARCH_FOR, query=query))

    data = api.online_search(search=query, vod=settings.getBool('showMoviesSeries'))

    if data:
        processed = process_online_search(data=data)

        if processed:
            folder.add_items(processed)

    return folder

@plugin.route()
def settings_menu(**kwargs):
    folder = plugin.Folder(title=_.SETTINGS)

    folder.add_item(label=_.CHECK_ENTITLEMENTS, path=plugin.url_for(func_or_url=check_entitlements))
    folder.add_item(label=_.INSTALL_WV_DRM, path=plugin.url_for(func_or_url=plugin._ia_install))
    folder.add_item(label=_.SET_IPTV, path=plugin.url_for(func_or_url=plugin._set_settings_iptv))
    folder.add_item(label=_.SET_KODI, path=plugin.url_for(func_or_url=plugin._set_settings_kodi))
    folder.add_item(label=_.DOWNLOAD_SETTINGS, path=plugin.url_for(func_or_url=plugin._download_settings))
    folder.add_item(label=_.DOWNLOAD_EPG, path=plugin.url_for(func_or_url=plugin._download_epg))
    folder.add_item(label=_.RESET_SESSION, path=plugin.url_for(func_or_url=logout, delete=False))
    folder.add_item(label=_.RESET, path=plugin.url_for(func_or_url=plugin._reset))

    if plugin.logged_in:
        folder.add_item(label=_.LOGOUT, path=plugin.url_for(func_or_url=logout))

    folder.add_item(label="Addon " + _.SETTINGS, path=plugin.url_for(func_or_url=plugin._settings))

    return folder

@plugin.route()
def logout(delete=True, **kwargs):
    if delete == True:
        if not gui.yes_no(message=_.LOGOUT_YES_NO):
            return

        settings.remove(key='_username')
        settings.remove(key='_pswd')

    settings.remove(key='_access_token')
    api.new_session(force=True, channels=True)
    plugin.logged_in = api.logged_in
    gui.refresh()

@plugin.route()
@plugin.login_required()
def play_video(type=None, id=None, locator=None, catchup=None, duration=0, **kwargs):
    properties = {}
    label = ''
    info = {}
    art = {}

    if not type or not len(type) > 0:
        return False

    if (catchup and len(catchup) > 0) or type=='program':
        if catchup and len(catchup) > 0:
            id = catchup

        properties['seekTime'] = 1
        type = 'program'

    if not id or not len(id) > 0:
        return False

    if type == "program":
        listings_url = "{listings_url}/{id}".format(listings_url=settings.get(key='_listings_url'), id=id)
        data = api.download(url=listings_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

        if not data or not check_key(data, 'program') or not check_key(data['program'], 'videoStreams'):
            gui.ok(message=_.STREAM_NOT_AVAILABLE, heading=_.STREAM_NOT_FOUND)
            return False

        urldata = get_play_url(content=data['program']['videoStreams'])

        if not urldata or not check_key(urldata, 'play_url') or not check_key(urldata, 'locator'):
            gui.ok(message=_.STREAM_NOT_AVAILABLE, heading=_.STREAM_NOT_FOUND)
            return False

        playdata = api.play_url(type='program', path=urldata['play_url'], locator=urldata['locator'])

        if check_key(data['program'], 'duration'):
            duration = int(data['program']['duration'])
        elif check_key(data, 'startTime') and check_key(data, 'endTime'):
            duration = int(int(data['endTime']) - int(data['startTime'])) // 1000

        label = data['program']['title']
        info = { 'plot': data['program']['description'], 'duration': duration, 'mediatype': 'video'}
        art = {'thumb': get_image("boxart", data['program']['images'])}
    elif type == "vod":
        playdata = api.play_url(type='vod', path=id)
    elif type == "channel":
        if not locator or not len(locator) > 0:
            return False

        playdata = api.play_url(type='channel', path=id, locator=locator)

    if not check_key(playdata, 'path') or not check_key(playdata, 'license') or not check_key(playdata, 'token') or not check_key(playdata, 'locator'):
        return False

    user_agent = settings.get(key='_user_agent')
    creds = get_credentials()

    CDMHEADERS = {
        'User-Agent': user_agent,
        'X-Client-Id': settings.get(key='_client_id') + '||' + user_agent,
        'X-OESP-Token': settings.get(key='_access_token'),
        'X-OESP-Username': creds['username'],
        'X-OESP-License-Token': settings.get(key='_drm_token'),
        'X-OESP-DRM-SchemeIdUri': 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed',
        'X-OESP-Content-Locator': playdata['locator'],
    }

    settings.setInt(key='_stream_duration', value=duration)

    listitem = plugin.Item(
        properties = properties,
        label = label,
        info = info,
        art = art,
        playable = True,
        path = playdata['path'],
        headers = CDMHEADERS,
        inputstream = inputstream.Widevine(
            license_key = playdata['license'],
            media_renewal_url = plugin.url_for(func_or_url=renew_token, id=playdata['path'], type=type, locator=playdata['locator']),
            media_renewal_time = 60,
        ),
    )

    return listitem

@plugin.route()
@plugin.login_required()
def switchChannel(channel_uid, **kwargs):
    xbmc.executebuiltin('PlayMedia(pvr://channels/tv/{allchan}/{backend}_{channel_uid}.pvr)'.format(allchan=xbmc.getLocalizedString(19287), backend=backend, channel_uid=channel_uid))

@plugin.route()
@plugin.login_required()
def renew_token(id=None, type=None, locator=None, **kwargs):
    api.get_play_token(locator=locator)

    id = id.replace("/manifest.mpd", "/")
    id = id.replace("/Manifest?device=Orion-Replay-DASH", "/")

    listitem = plugin.Item(
        path = id,
    )

    newItem = listitem.get_li()

    xbmcplugin.addDirectoryItem(ADDON_HANDLE, id, newItem)
    xbmcplugin.endOfDirectory(ADDON_HANDLE, cacheToDisc=False)
    time.sleep(0.1)

@plugin.route()
def check_entitlements(**kwargs):
    if plugin.logged_in:
        user_agent = settings.get(key='_user_agent')
        media_groups_url = '{mediagroups_url}/lgi-nl-vod-myprime-movies?byHasCurrentVod=true&range=1-1&sort=playCount7%7Cdesc'.format(mediagroups_url=settings.get('_mediagroupsfeeds_url'))
        data = api.download(url=media_groups_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

        if not data or not check_key(data, 'entryCount'):
            gui.ok(message=_.NO_MOVIES_SERIES, heading=_.CHECKED_ENTITLEMENTS)
            settings.setBool(key='showMoviesSeries', value=False)
            return

        media_item_url = '{mediaitem_url}/{mediaitem_id}'.format(mediaitem_url=settings.get(key='_mediaitems_url'), mediaitem_id=data['mediaGroups'][0]['id'])
        data = api.download(url=media_item_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=False)

        if not data or not check_key(data, 'videoStreams'):
            gui.ok(message=_.NO_MOVIES_SERIES, heading=_.CHECKED_ENTITLEMENTS)
            settings.setBool(key='showMoviesSeries', value=False)
            return

        urldata = get_play_url(content=data['videoStreams'])

        if not urldata or not check_key(urldata, 'play_url') or not check_key(urldata, 'locator'):
            gui.ok(message=_.NO_MOVIES_SERIES, heading=_.CHECKED_ENTITLEMENTS)
            settings.setBool(key='showMoviesSeries', value=False)
            return

        token = api.get_play_token(locator=urldata['locator'], force=True)

        if not token or not len(token) > 0:
            gui.ok(message=_.NO_MOVIES_SERIES, heading=_.CHECKED_ENTITLEMENTS)
            settings.setBool(key='showMoviesSeries', value=False)
            return

        gui.ok(message=_.YES_MOVIES_SERIES, heading=_.CHECKED_ENTITLEMENTS)
        settings.setBool(key='showMoviesSeries', value=True)

    return

@plugin.route()
def add_to_watchlist(id, type, **kwargs):
    if api.add_to_watchlist(id=id, type=type) == True:
        gui.notification(_.ADDED_TO_WATCHLIST)
    else:
        gui.notification(_.ADD_TO_WATCHLIST_FAILED)

@plugin.route()
def remove_from_watchlist(id, **kwargs):
    if api.remove_from_watchlist(id=id) == True:
        gui.refresh()
        gui.notification(_.REMOVED_FROM_WATCHLIST)
    else:
        gui.notification(_.REMOVE_FROM_WATCHLIST_FAILED)

@plugin.route()
def watchlist(**kwargs):
    folder = plugin.Folder(title=_.WATCHLIST)

    data = api.list_watchlist()

    if data and check_key(data, 'entries'):
        processed = process_watchlist(data=data)

        if processed:
            folder.add_items(processed)

    return folder

@plugin.route()
def watchlist_listing(label, description, image, id, search=False, **kwargs):
    folder = plugin.Folder(title=label)

    data = api.watchlist_listing(id)

    if search == False:
        id  = None

    if data and check_key(data, 'listings'):
        processed = process_watchlist_listing(data=data, id=id)

        if processed:
            folder.add_items(processed)

    return folder

@signals.on(signals.BEFORE_DISPATCH)
def before_dispatch():
    api.new_session()
    plugin.logged_in = api.logged_in

#Support functions
def first_boot():
    if gui.yes_no(message=_.SET_IPTV):
        try:
            plugin._set_settings_iptv()
        except:
            pass
    if gui.yes_no(message=_.SET_KODI):
        try:
            plugin._set_settings_kodi()
        except:
            pass

    settings.setBool(key='_first_boot', value=False)

def get_live_channels(addon=False):
    global backend, query_channel

    channels = []
    rows = load_file(file='channels.json', isJSON=True)

    if rows:
        if addon == True:
            query_addons = json.loads(xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id": 1, "method": "Addons.GetAddons", "params": {"type": "xbmc.pvrclient"}}'))
            addons = query_addons['result']['addons']
            backend = addons[0]['addonid']

            query_channel = json.loads(xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "PVR.GetChannels", "params": {"channelgroupid": "alltv", "properties" :["uniqueid"]},"id": 1}'))

        for row in rows:
            channeldata = api.get_channel_data(row=row)
            urldata = get_play_url(content=channeldata['stream'])

            if urldata and check_key(urldata, 'play_url') and check_key(urldata, 'locator'):
                path = plugin.url_for(play_video, type='channel', id=urldata['play_url'], locator=urldata['locator'], _is_live=True)
                playable = True

                if addon == True and 'result' in query_channel:
                    if 'channels' in query_channel['result']:
                        pvrchannels = query_channel['result']['channels']

                        for channel in pvrchannels:
                            if channel['label'] == channeldata['label']:
                                channel_uid = channel['uniqueid']
                                path = plugin.url_for(switchChannel, channel_uid=channel_uid)
                                playable = False
                                break

                channels.append({
                    'label': channeldata['label'],
                    'channel': channeldata['channel_id'],
                    'chno': channeldata['channel_number'],
                    'description': channeldata['description'],
                    'image': channeldata['station_image_large'],
                    'path':  path,
                    'playable': playable,
                })

        channels[:] = sorted(channels, key=_sort_live)

    return channels

def get_replay_channels():
    channels = []
    rows = load_file(file='channels.json', isJSON=True)

    if rows:
        for row in rows:
            channeldata = api.get_channel_data(row=row)

            channels.append({
                'label': channeldata['label'],
                'channel': channeldata['channel_id'],
                'chno': channeldata['channel_number'],
                'description': channeldata['description'],
                'image': channeldata['station_image_large'],
                'path': plugin.url_for(func_or_url=replaytv_by_day, image=channeldata['station_image_large'], description=channeldata['description'], label=channeldata['label'], station=channeldata['channel_id']),
                'playable': False,
            })

        channels[:] = sorted(channels, key=_sort_live)

    return channels

def process_online_search(data):
    items_vod = []
    items_program = []
    vod_links = {}

    if settings.getBool('showMoviesSeries') == True:
        vod_data = load_file(file='vod.json', isJSON=True)

        for vod_type in list(vod_data):
            for row in vod_data[vod_type]:
                if not check_key(row, 'id'):
                    continue

                vod_links[row['id']] = {}

                if check_key(row, 'seasons'):
                    vod_links[row['id']]['seasons'] = row['seasons']

                if check_key(row, 'duration'):
                    vod_links[row['id']]['duration'] = row['duration']

                if check_key(row, 'desc'):
                    vod_links[row['id']]['desc'] = row['desc']

    for currow in list(data):
        if currow == "moviesAndSeries":
            if settings.getBool('showMoviesSeries') != True:
                continue

            type = 'vod'
        else:
            type = 'program'

        for row in data[currow]['entries']:
            context = []

            if not check_key(row, 'id') or not check_key(row, 'title'):
                continue

            id = row['id']
            label = row['title']

            mediatype = ''
            description = ''
            duration = 0
            program_image_large = ''

            if check_key(row, 'images'):
                get_image("boxart", row['images'])

            playable = False
            path = ''

            if check_key(vod_links, row['id']) and check_key(vod_links[row['id']], 'desc'):
                description = vod_links[row['id']]['desc']

            if type == 'vod':
                label += " (Movies and Series)"
            else:
                label += " (ReplayTV)"

            if check_key(row, 'groupType') and row['groupType'] == 'show':
                if check_key(row, 'episodeMatch') and check_key(row['episodeMatch'], 'seriesEpisodeNumber') and check_key(row['episodeMatch'], 'secondaryTitle'):
                    if len(description) == 0:
                        description += label

                    season = ''

                    if check_key(row, 'seriesNumber'):
                        season = "S" + row['seriesNumber']

                    description += " Episode Match: {season}E{episode} - {secondary}".format(season=season, episode=row['episodeMatch']['seriesEpisodeNumber'], secondary=row['episodeMatch']['secondaryTitle'])

                if type == 'vod':
                    if not check_key(vod_links, row['id']) or not check_key(vod_links[row['id']], 'seasons'):
                        continue

                    context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=id, type='group')), ))
                    path = plugin.url_for(func_or_url=vod_series, label=label, description=description, image=program_image_large, seasons=json.dumps(vod_links[row['id']]['seasons']), mediagroupid=id)
                else:
                    context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=id, type='group')), ))
                    path = plugin.url_for(func_or_url=watchlist_listing, label=label, description=description, image=program_image_large, id=id, search=True)
            else:
                context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=id, type='group')), ))

                if check_key(row, 'duration'):
                    duration = int(row['duration'])
                elif check_key(row, 'episodeMatch') and check_key(row['episodeMatch'], 'startTime') and check_key(row['episodeMatch'], 'endTime'):
                    duration = int(int(row['episodeMatch']['endTime']) - int(row['episodeMatch']['startTime'])) // 1000
                    id = row['episodeMatch']['id']
                elif check_key(vod_links, row['id']) and check_key(vod_links[row['id']], 'duration'):
                    duration = vod_links[row['id']]['duration']

                path = plugin.url_for(func_or_url=play_video, type=type, id=id, duration=duration, _is_live=False)
                playable = True
                mediatype = 'video'

            item = plugin.Item(
                label = label,
                info = {
                    'plot': description,
                    'duration': duration,
                    'mediatype': mediatype,
                },
                art = {'thumb': program_image_large},
                path = path,
                playable = playable,
                context = context
            )

            if type == "vod":
                items_vod.append(item)
            else:
                items_program.append(item)

    num = min(len(items_program), len(items_vod))
    items = [None]*(num*2)
    items[::2] = items_program[:num]
    items[1::2] = items_vod[:num]
    items.extend(items_program[num:])
    items.extend(items_vod[num:])

    return items

def process_replaytv_list(data, start=0):
    start = int(start)
    items = []
    count = 0
    item_count = 0
    time_now = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds())

    for row in sorted(data):
        currow = data[row]

        if item_count == 51:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 'orig') or not check_key(currow, 'ids'):
            continue

        if check_key(currow, 'a') and check_key(currow, 'e') and (time_now < int(currow['a']) or time_now > int(currow['e'])):
            continue

        label = currow['orig']

        items.append(plugin.Item(
            label = label,
            path = plugin.url_for(func_or_url=replaytv_item, ids=json.dumps(currow['ids']), label=label, start=0),
        ))

        item_count += 1

    return {'items': items, 'count': count}

def process_replaytv_search(data, start=0, search=None):
    start = int(start)
    items = []
    count = 0
    item_count = 0
    time_now = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds())

    for row in data:
        letter_row = data[row]

        for row2 in letter_row:
            currow = data[row][row2]

            if item_count == 51:
                break

            if count < start:
                count += 1
                continue

            count += 1

            if not check_key(currow, 'orig') or not check_key(currow, 'ids'):
                continue

            if check_key(currow, 'a') and check_key(currow, 'e') and (time_now < int(currow['a']) or time_now > int(currow['e'])):
                continue

            label = currow['orig'] + ' (ReplayTV)'

            fuzz_set = fuzz.token_set_ratio(label, search)
            fuzz_partial = fuzz.partial_ratio(label, search)
            fuzz_sort = fuzz.token_sort_ratio(label, search)

            if (fuzz_set + fuzz_partial + fuzz_sort) > 160:
                items.append(plugin.Item(
                    label = label,
                    properties = {"fuzz_set": fuzz_set, "fuzz_sort": fuzz_sort, "fuzz_partial": fuzz_partial, "fuzz_total": fuzz_set + fuzz_partial + fuzz_sort},
                    path = plugin.url_for(func_or_url=replaytv_item, ids=json.dumps(currow['ids']), label=label, start=0),
                ))

                item_count += 1

    return {'items': items, 'count': count}

def process_replaytv_content(data, day=0, start=0):
    day = int(day)
    start = int(start)
    curdate = datetime.date.today() - datetime.timedelta(days=day)

    startDate = convert_datetime_timezone(datetime.datetime(curdate.year, curdate.month, curdate.day, 0, 0, 0), "Europe/Amsterdam", "UTC")
    endDate = convert_datetime_timezone(datetime.datetime(curdate.year, curdate.month, curdate.day, 23, 59, 59), "Europe/Amsterdam", "UTC")
    startTime = startDate.strftime("%Y%m%d%H%M%S")
    endTime = endDate.strftime("%Y%m%d%H%M%S")

    items = []
    count = 0
    item_count = 0

    for row in data:
        context = []
        currow = data[row]

        if item_count == 51:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 's') or not check_key(currow, 't') or not check_key(currow, 'c') or not check_key(currow, 'e'):
            continue

        startsplit = unicode(currow['s'].split(' ', 1)[0])
        endsplit = unicode(currow['e'].split(' ', 1)[0])

        if not startsplit.isdigit() or not len(startsplit) == 14 or startsplit < startTime or not endsplit.isdigit() or not len(endsplit) == 14 or startsplit >= endTime:
            continue

        startT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(startsplit, "%Y%m%d%H%M%S")))
        startT = convert_datetime_timezone(startT, "UTC", "Europe/Amsterdam")
        endT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(endsplit, "%Y%m%d%H%M%S")))
        endT = convert_datetime_timezone(endT, "UTC", "Europe/Amsterdam")

        if endT < (datetime.datetime.now(pytz.timezone("Europe/Amsterdam")) - datetime.timedelta(days=7)):
            continue

        label = startT.strftime("%H:%M") + " - " + currow['t']
        description = ''
        program_image_large = ''

        if check_key(currow, 'desc'):
            description = currow['desc']

        duration = int((endT - startT).total_seconds())

        if check_key(currow, 'i'):
            program_image_large = currow['i']

        context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=row, type='item')), ))

        items.append(plugin.Item(
            label = label,
            info = {
                'plot': description,
                'duration': duration,
                'mediatype': 'video',
            },
            art = {'thumb': program_image_large},
            path = plugin.url_for(func_or_url=play_video, type='program', id=row, duration=duration, _is_live=False),
            playable = True,
            context = context
        ))

        item_count += 1

    return {'items': items, 'count': count}

def process_replaytv_list_content(data, ids, start=0):
    start = int(start)
    items = []
    count = 0
    item_count = 0

    ids = json.loads(ids)
    totalrows = len(ids)

    for id in ids:
        context = []
        currow = data[id]

        if item_count == 51:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 's') or not check_key(currow, 't') or not check_key(currow, 'c') or not check_key(currow, 'e'):
            continue

        startsplit = unicode(currow['s'].split(' ', 1)[0])
        endsplit = unicode(currow['e'].split(' ', 1)[0])

        if not startsplit.isdigit() or not len(startsplit) == 14 or not endsplit.isdigit() or not len(endsplit) == 14:
            continue

        startT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(startsplit, "%Y%m%d%H%M%S")))
        startT = convert_datetime_timezone(startT, "UTC", "Europe/Amsterdam")
        endT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(endsplit, "%Y%m%d%H%M%S")))
        endT = convert_datetime_timezone(endT, "UTC", "Europe/Amsterdam")

        if startT > datetime.datetime.now(pytz.timezone("Europe/Amsterdam")) or endT < (datetime.datetime.now(pytz.timezone("Europe/Amsterdam")) - datetime.timedelta(days=7)):
            continue

        if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
            itemlabel = '{weekday} {day} {month} {yearhourminute} '.format(weekday=date_to_nl_dag(startT), day=startT.strftime("%d"), month=date_to_nl_maand(startT), yearhourminute=startT.strftime("%Y %H:%M"))
        else:
            itemlabel = startT.strftime("%A %d %B %Y %H:%M ").capitalize()

        itemlabel += currow['t'] + " (" + currow['cn'] + ")"

        description = ''
        program_image_large = ''

        if check_key(currow, 'desc'):
            description = currow['desc']

        duration = int((endT - startT).total_seconds())

        if check_key(currow, 'i'):
            program_image_large = currow['i']

        context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=id, type='item')), ))

        items.append(plugin.Item(
            label = itemlabel,
            info = {
                'plot': description,
                'duration': duration,
                'mediatype': 'video',
            },
            art = {'thumb': program_image_large},
            path = plugin.url_for(func_or_url=play_video, type='program', id=id, duration=duration, _is_live=False),
            playable = True,
            context = context
        ))

        item_count = item_count + 1

    return {'items': items, 'totalrows': totalrows, 'count': count}

def process_vod_content(data, start=0, series=0, search=None, type=None):
    start = int(start)
    series = int(series)
    items = []
    count = 0
    item_count = 0

    for row in data:
        context = []
        currow = row

        if item_count == 50:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 'id') or not check_key(currow, 'title'):
            continue

        id = currow['id']
        label = currow['title']

        if search:
            fuzz_set = fuzz.token_set_ratio(label,search)
            fuzz_partial = fuzz.partial_ratio(label,search)
            fuzz_sort = fuzz.token_sort_ratio(label,search)

            if (fuzz_set + fuzz_partial + fuzz_sort) > 160:
                properties = {"fuzz_set": fuzz.token_set_ratio(label,search), "fuzz_sort": fuzz.token_sort_ratio(label,search), "fuzz_partial": fuzz.partial_ratio(label,search), "fuzz_total": fuzz.token_set_ratio(label,search) + fuzz.partial_ratio(label,search) + fuzz.token_sort_ratio(label,search)}
                label = label + " (" + type + ")"
            else:
                continue

        description = ''
        program_image_large = ''
        duration = 0
        properties = []

        if check_key(currow, 'desc'):
            description = currow['desc']

        if check_key(currow, 'duration'):
            duration = int(currow['duration'])

        if check_key(currow, 'image'):
            program_image_large = currow['image']

        if not check_key(currow, 'type'):
            continue

        if currow['type'] == "show":
            if check_key(currow, 'seasons') and series != 2:
                path = plugin.url_for(func_or_url=vod_series, label=label, description=description, image=program_image_large, seasons=json.dumps(currow['seasons']), mediagroupid=id)
                info = {'plot': description}
                playable = False
                context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=id, type='group')), ))
            else:
                continue
        else:
            if series != 1:
                path = plugin.url_for(func_or_url=play_video, type='vod', id=id, duration=duration, _is_live=False)
                info = {'plot': description, 'duration': duration, 'mediatype': 'video'}
                playable = True
                context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=id, type='group')), ))
            else:
                continue

        items.append(plugin.Item(
            label = label,
            properties = properties,
            info = info,
            art = {'thumb': program_image_large},
            path = path,
            playable = playable,
            context = context
        ))

        item_count += 1

    return {'items': items, 'count': count}

def process_vod_season(data, mediagroupid=None):
    items = []

    if sys.version_info >= (3, 0):
        data['mediaItems'] = list(data['mediaItems'])

    for row in data['mediaItems']:
        context = []
        label = ''
        description = ''
        program_image_large = ''
        duration = 0

        if not check_key(row, 'title') or not check_key(row, 'id'):
            continue

        if check_key(row, 'description'):
            description = row['description']

        if check_key(row, 'earliestBroadcastStartTime'):
            startsplit = int(row['earliestBroadcastStartTime']) // 1000

            startT = datetime.datetime.fromtimestamp(startsplit)
            startT = convert_datetime_timezone(startT, "UTC", "UTC")

            if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
                label = date_to_nl_dag(startT) + startT.strftime(" %d ") + date_to_nl_maand(startT) + startT.strftime(" %Y %H:%M ") + row['title']
            else:
                label = (startT.strftime("%A %d %B %Y %H:%M ") + row['title']).capitalize()
        else:
            label = row['title']

        if check_key(row, 'duration'):
            duration = int(row['duration'])

        if check_key(row, 'images'):
            program_image_large = get_image("boxart", row['images'])

        if check_key(row, 'videoStreams'):
            urldata = get_play_url(content=row['videoStreams'])

            if urldata and check_key(urldata, 'play_url') and check_key(urldata, 'locator'):
                if mediagroupid:
                    context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=mediagroupid, type='group')), ))

                items.append(plugin.Item(
                    label = label,
                    info = {
                        'plot': description,
                        'duration': duration,
                        'mediatype': 'video',
                    },
                    art = {'thumb': program_image_large},
                    path = plugin.url_for(func_or_url=play_video, type='vod', id=row['id'], duration=duration, _is_live=False),
                    playable = True,
                    context = context
                ))

    return items

def process_watchlist(data):
    items = []

    for row in data['entries']:
        context = []

        if check_key(row, 'mediaGroup') and check_key(row['mediaGroup'], 'medium') and check_key(row['mediaGroup'], 'id'):
            currow = row['mediaGroup']
            id = currow['id']
        elif check_key(row, 'mediaItem') and check_key(row['mediaItem'], 'medium') and check_key(row['mediaItem'], 'mediaGroupId'):
            currow = row['mediaItem']
            id = currow['mediaGroupId']
        else:
            continue

        if not check_key(currow, 'title'):
            continue

        context.append((_.REMOVE_FROM_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=remove_from_watchlist, id=id)), ))

        if check_key(currow, 'isReplayTv') and currow['isReplayTv'] == "false":
            if settings.getBool('showMoviesSeries') == False:
                continue

            type = 'vod'
        else:
            type = 'program'

        mediatype = ''
        duration = ''
        description = ''
        program_image_large = ''
        playable = False
        path = ''

        if check_key(currow, 'description'):
            description = currow['description']

        if check_key(currow, 'images'):
            program_image_large = get_image("boxart", currow['images'])

        if currow['medium'] == 'TV':
            if not check_key(currow, 'seriesLinks'):
                path = plugin.url_for(func_or_url=watchlist_listing, label=currow['title'], description=description, image=program_image_large, id=id, search=False)
            else:
                path = plugin.url_for(func_or_url=vod_series, label=currow['title'], description=description, image=program_image_large, seasons=json.dumps(currow['seriesLinks']))
        elif currow['medium'] == 'Movie':
            if check_key(currow, 'duration'):
                duration = int(currow['duration'])
            elif check_key(currow, 'startTime') and check_key(currow, 'endTime'):
                duration = int(int(currow['endTime']) - int(currow['startTime'])) // 1000
            else:
                duration = 0

            path = plugin.url_for(func_or_url=play_video, type=type, id=currow['id'], duration=duration, _is_live=False)
            playable = True
            mediatype = 'video'

        items.append(plugin.Item(
            label = currow['title'],
            info = {
                'plot': description,
                'duration': duration,
                'mediatype': mediatype,
            },
            art = {'thumb': program_image_large},
            path = path,
            playable = playable,
            context = context
        ))

    return items

def process_watchlist_listing(data, id=None):
    items = []

    channeldata = {}
    stations = load_file(file='channels.json', isJSON=True)

    if stations:
        for row in stations:
            channeldata[row['stationSchedules'][0]['station']['id']] = row['stationSchedules'][0]['station']['title']

    for row in data['listings']:
        context = []

        if not check_key(row, 'program'):
            continue

        currow = row['program']

        if not check_key(currow, 'title') or not check_key(row, 'id'):
            continue

        duration = 0

        if check_key(row, 'endTime') and check_key(row, 'startTime'):
            startsplit = int(row['startTime']) // 1000
            endsplit = int(row['endTime']) // 1000
            duration = endsplit - startsplit

            startT = datetime.datetime.fromtimestamp(startsplit)
            startT = convert_datetime_timezone(startT, "UTC", "UTC")
            endT = datetime.datetime.fromtimestamp(endsplit)
            endT = convert_datetime_timezone(endT, "UTC", "UTC")

            if endT < (datetime.datetime.now(pytz.timezone("UTC")) - datetime.timedelta(days=7)):
                continue

            if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
                label = '{weekday} {day} {month} {yearhourminute} '.format(weekday=date_to_nl_dag(startT), day=startT.strftime("%d"), month=date_to_nl_maand(startT), yearhourminute=startT.strftime("%Y %H:%M"))
            else:
                label = startT.strftime("%A %d %B %Y %H:%M ").capitalize()

            label += currow['title']
        else:
            label = currow['title']

        if check_key(channeldata, row['stationId']):
            label += ' ({station})'.format(station=channeldata[row['stationId']])

        if id:
            context.append((_.ADD_TO_WATCHLIST, 'RunPlugin({context_url})'.format(context_url=plugin.url_for(func_or_url=add_to_watchlist, id=id, type="group")), ))

        description = ''
        image = ''

        if check_key(currow, 'description'):
            description = currow['description']

        if check_key(currow, 'duration'):
            duration = int(currow['duration'])

        if check_key(currow, 'images'):
            image = get_image("boxart", currow['images'])

        items.append(plugin.Item(
            label = label,
            info = {
                'plot': description,
                'duration': duration,
                'mediatype': 'video',
            },
            art = {'thumb': image},
            path = plugin.url_for(func_or_url=play_video, type="program", id=row['id'], duration=duration, _is_live=False),
            playable = True,
            context = context
        ))

    return items

def _sort_live(element):
    return element['chno']

def _sort_replay_items(element):
    return element.get_li().getProperty('fuzz_total')