import os, re, requests, sys, threading, xbmc, xbmcaddon

try:
    import http.server as ProxyServer
except ImportError:
    import BaseHTTPServer as ProxyServer

from resources.lib.base import settings
from resources.lib.base.constants import ADDON_ID, ADDON_PATH, ADDON_PROFILE
from resources.lib.base.log import log
from resources.lib.base.session import Session
from resources.lib.base.util import set_duration

class HTTPMonitor(xbmc.Monitor):
    def __init__(self, addon):
        super(HTTPMonitor, self).__init__()
        self.addon = addon

class HTTPRequestHandler(ProxyServer.BaseHTTPRequestHandler):
    def do_GET(self):
        URL = settings.get(key='_stream_hostname') + str(self.path)

        if ".mpd" in self.path:
            session = Session(cookies_key='_cookies')
            r = session.get(URL)

            xml = r.text

            xml = set_duration(xml=xml)

            self.send_response(r.status_code)

            r.headers['Content-Length'] = len(xml)

            for header in r.headers:
                if not 'Content-Encoding' in header:
                    self.send_header(header, r.headers[header])

            self.end_headers()

            try:
                xml = xml.encode('utf-8')
            except:
                pass

            try:
                self.wfile.write(xml)
            except:
                pass
        else:
            self.send_response(302)
            self.send_header('Location', URL)
            self.end_headers()

    def log_message(self, format, *args):
        return

class HTTPServer(ProxyServer.HTTPServer):
    def __init__(self, addon, server_address):
        ProxyServer.HTTPServer.__init__(self, server_address, HTTPRequestHandler)
        self.addon = addon

class RemoteControlBrowserService(xbmcaddon.Addon):
    def __init__(self):
        super(RemoteControlBrowserService, self).__init__()
        self.pluginId = ADDON_ID
        self.addonFolder = ADDON_PATH
        self.profileFolder = ADDON_PROFILE
        self.settingsChangeLock = threading.Lock()
        self.isShutdown = False
        self.HTTPServer = None
        self.HTTPServerThread = None

    def clearBrowserLock(self):
        """Clears the pidfile in case the last shutdown was not clean"""
        browserLockPath = os.path.join(self.profileFolder, 'browser.pid')
        try:
            os.remove(browserLockPath)
        except OSError:
            pass

    def reloadHTTPServer(self):
        with self.settingsChangeLock:
            self.startHTTPServer()

    def shutdownHTTPServer(self):
        with self.settingsChangeLock:
            self.stopHTTPServer()
            self.isShutdown = True

    def startHTTPServer(self):
        if self.isShutdown:
            return

        self.stopHTTPServer()

        try:
            self.HTTPServer = HTTPServer(self, ('', settings.getInt(key='_proxyserver_port')))
        except IOError as e:
            pass

        threadStarting = threading.Thread(target=self.HTTPServer.serve_forever)
        threadStarting.start()
        self.HTTPServerThread = threadStarting

    def stopHTTPServer(self):
        if self.HTTPServer is not None:
            self.HTTPServer.shutdown()
            self.HTTPServer = None
        if self.HTTPServerThread is not None:
            self.HTTPServerThread.join()
            self.HTTPServerThread = None