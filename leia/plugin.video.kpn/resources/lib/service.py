import xbmc, xbmcaddon

from resources.lib.base import settings
from resources.lib.base.constants import ADDON_PROFILE
from resources.lib.base.util import change_icon, check_iptv_link, find_free_port, get_system_arch, renew_epg, settings_download, update_user_agent
from resources.lib.proxy import HTTPMonitor, RemoteControlBrowserService
from resources.lib.util import update_api_url, update_img_size, update_os_browser

def daily():
    update_user_agent()
    update_os_browser()
    update_api_url()
    update_img_size()
    check_iptv_link()

def hourly():
    settings_download()
    renew_epg()

def startup():
    system, arch = get_system_arch()
    settings.set(key="_system", value=system)
    settings.set(key="_arch", value=arch)

    settings.setInt(key='_proxyserver_port', value=find_free_port())

    hourly()
    daily()
    change_icon()
    
    if settings.getBool(key='enable_simple_iptv') == True:
        try:
            IPTV_SIMPLE = xbmcaddon.Addon(id="pvr.iptvsimple")

            if IPTV_SIMPLE.getSetting("epgPath") == (ADDON_PROFILE + "epg.xml") and IPTV_SIMPLE.getSetting("m3uPath") == (ADDON_PROFILE + "playlist.m3u8"):
                user_agent = settings.get(key='_user_agent')

                if IPTV_SIMPLE.getSetting("userAgent") != user_agent:
                    IPTV_SIMPLE.setSetting("userAgent", user_agent)
                    
                    xbmc.executeJSONRPC('{{"jsonrpc":"2.0","id":1,"method":"Addons.SetAddonEnabled","params":{{"addonid":"{}","enabled":false}}}}'.format(IPTV_SIMPLE_ADDON_ID))
                    xbmc.sleep(2000)
                    xbmc.executeJSONRPC('{{"jsonrpc":"2.0","id":1,"method":"Addons.SetAddonEnabled","params":{{"addonid":"{}","enabled":true}}}}'.format(IPTV_SIMPLE_ADDON_ID))
        except:
            pass

def main():
    startup()
    service = RemoteControlBrowserService()
    service.clearBrowserLock()
    monitor = HTTPMonitor(service)
    service.reloadHTTPServer()

    k = 0
    z = 0
    l = 0

    while not xbmc.Monitor().abortRequested():
        if monitor.waitForAbort(1):
            break
    
        if k == 60:
            k = 0
            z += 1

        if z == 60:
            z = 0
            l += 1

            hourly()

        if l == 24:
            l = 0

            daily()

        k += 1        

    service.shutdownHTTPServer()