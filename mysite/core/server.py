# Python stdlib imports
import sys
import logging
import os, os.path
 
# Third-party imports
import cherrypy
from cherrypy.process import wspbus, plugins
from cherrypy import _cplogging, _cperror
from django.conf import settings
from django.core.handlers.wsgi import WSGIHandler
from django.http import HttpResponseServerError
 
class CherryPyServer(object):
    def __init__(self):
        self.base_dir = os.path.join(os.path.abspath(os.getcwd()), "cpdjango")
 
        conf_path = os.path.join(self.base_dir, "..", "server.cfg")
        cherrypy.config.update(conf_path)
 
        # This registers a plugin to handle the Django app
        # with the CherryPy engine, meaning the app will
        # play nicely with the process bus that is the engine.
        DjangoAppPlugin(cherrypy.engine, self.base_dir).subscribe()
 
    def run(self):
        engine = cherrypy.engine
        engine.signal_handler.subscribe()
 
        if hasattr(engine, "console_control_handler"):
            engine.console_control_handler.subscribe()
 
        engine.start()
        engine.block()
 
class DjangoAppPlugin(plugins.SimplePlugin):
    def __init__(self, bus, base_dir):
        """
        CherryPy engine plugin to configure and mount
        the Django application onto the CherryPy server.
        """
        plugins.SimplePlugin.__init__(self, bus)
        self.base_dir = base_dir
 
    def start(self):
        self.bus.log("Configuring the Django application")
 
        # Well this isn't quite as clean as I'd like so
        # feel free to suggest something more appropriate
        from cpdjango.settings import *
        app_settings = locals().copy()
        del app_settings['self']
        settings.configure(**app_settings)
 
        self.bus.log("Mounting the Django application")
        cherrypy.tree.graft(HTTPLogger(WSGIHandler()))
 
        self.bus.log("Setting up the static directory to be served")
        # We server static files through CherryPy directly
        # bypassing entirely Django
        static_handler = cherrypy.tools.staticdir.handler(section="/", dir="static",
                                                          root=self.base_dir)
        cherrypy.tree.mount(static_handler, '/static')
 
class HTTPLogger(_cplogging.LogManager):
    def __init__(self, app):
        _cplogging.LogManager.__init__(self, id(self), cherrypy.log.logger_root)
        self.app = app
 
    def __call__(self, environ, start_response):
        """
        Called as part of the WSGI stack to log the incoming request
        and its response using the common log format. If an error bubbles up
        to this middleware, we log it as such.
        """
        try:
            response = self.app(environ, start_response)
            self.access(environ, response)
            return response
        except:
            self.error(traceback=True)
            return HttpResponseServerError(_cperror.format_exc())
 
    def access(self, environ, response):
        """
        Special method that logs a request following the common
        log format. This is mostly taken from CherryPy and adapted
        to the WSGI's style of passing information.
        """
        atoms = {'h': environ.get('REMOTE_ADDR', ''),
                 'l': '-',
                 'u': "-",
                 't': self.time(),
                 'r': "%s %s %s" % (environ['REQUEST_METHOD'], environ['REQUEST_URI'], environ['SERVER_PROTOCOL']),
                 's': response.status_code,
                 'b': str(len(response.content)),
                 'f': environ.get('HTTP_REFERER', ''),
                 'a': environ.get('HTTP_USER_AGENT', ''),
                 }
        for k, v in atoms.items():
            if isinstance(v, unicode):
                v = v.encode('utf8')
            elif not isinstance(v, str):
                v = str(v)
            # Fortunately, repr(str) escapes unprintable chars, \n, \t, etc
            # and backslash for us. All we have to do is strip the quotes.
            v = repr(v)[1:-1]
            # Escape double-quote.
            atoms[k] = v.replace('"', '\\"')
 
        try:
            self.access_log.log(logging.INFO, self.access_log_format % atoms)
        except:
            self.error(traceback=True)
 
if __name__ == '__main__':
    Server().run()