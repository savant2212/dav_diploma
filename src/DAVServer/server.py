#!/usr/bin/env python2
#Copyright (c) 1999-2005 Christian Scholz (cs@comlounge.net)
#
#This library is free software; you can redistribute it and/or
#modify it under the terms of the GNU Library General Public
#License as published by the Free Software Foundation; either
#version 2 of the License, or (at your option) any later version.
#
#This library is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#Library General Public License for more details.
#
#You should have received a copy of the GNU Library General Public
#License along with this library; if not, write to the Free
#Software Foundation, Inc., 59 Temple Place - Suite 330, Boston,
#MA 02111-1307, USA
from DAVServer.dbauth import DbAuthHandler

"""
Python WebDAV Server.

This is an example implementation of a DAVserver using the DAV package.

"""

from os import environ
import getopt, sys, os
import logging

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger('pywebdav')

from BaseHTTPServer import HTTPServer
from SocketServer import ThreadingMixIn

try:
    import DAV
except ImportError:
    print 'DAV package not found! Please install into site-packages or set PYTHONPATH!'
    sys.exit(2)

from DAV.utils import VERSION, AUTHOR
__version__ = VERSION
__author__  = AUTHOR

from fileauth import DAVAuthHandler
from myhandler import DBFSHandler
from daemonize import startstop
from DAV.INI_Parse import Configuration

LEVELS = {'debug': logging.DEBUG,
          'info': logging.INFO,
          'warning': logging.WARNING,
          'error': logging.ERROR,
          'critical': logging.CRITICAL}

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

def runserver(
         port = 8008, host='localhost',
         verbose = False,
         noauth = False,
         user = '',
         password = '',
         handler = DbAuthHandler,
         directory = "/tmp/davstorage",
         server = ThreadedHTTPServer):

    directory = directory.strip()
    directory = directory.rstrip('/')
    host = host.strip()

    if not os.path.isdir(directory):
        log.error("%s is not a valid directory" % directory)
        return 233
    # basic checks against wrong hosts
    if host.find('/') != -1 or host.find(':') != -1:
        log.error('Malformed host %s' % host)
        return sys.exit(233)

    # dispatch directory and host to the filesystem handler
    # This handler is responsible from where to take the data
    #handler.IFACE_CLASS = DBFSHandler('sqlite:///%s/db/devel.db' % (os.getcwd()), 'http://%s:%s/' % (host, port), verbose )
    handler.IFACE_CLASS = DBFSHandler('postgres://davstorage:davstorage@localhost/davstorage', 'http://%s:%s/' % (host, port), directory, verbose )
    
    handler.IFACE_CLASS.setup()
    # put some extra vars
    handler.verbose = verbose
    if handler._config.DAV.getboolean('lockemulation') is False:
        log.info('Deactivated LOCK, UNLOCK (WebDAV level 2) support')

    handler.IFACE_CLASS.mimecheck = True
    if handler._config.DAV.getboolean('mimecheck') is False:
        handler.IFACE_CLASS.mimecheck = False
        log.info('Disabled mimetype sniffing (All files will have type application/octet-stream)')

    # initialize server on specified port
    runner = server( (host, port), handler )
    print('Listening on %s (%i)' % (host, port))

    try:
        runner.serve_forever()
    except KeyboardInterrupt:
        log.info('Killed by user')

usage = """PyWebDAV server (version %s)
Standalone WebDAV server

Make sure to activate LOCK, UNLOCK using parameter -J if you want
to use clients like Windows Explorer or Mac OS X Finder that expect
LOCK working for write support.

Usage: ./server.py [OPTIONS]
Parameters:
    -c, --config    Specify a file where configuration is specified. In this
                    file you can specify options for a running server.
                    For an example look at the config.ini in this directory.
    -H, --host      Host where to listen on (default: localhost)
    -P, --port      Port to bind server to  (default: 8008)
    -u, --user      Username for authentication
    -p, --password  Password for given user
    -n, --noauth    Pass parameter if server should not ask for authentication
                    This means that every user has access
    -m, --mysql     Pass this parameter if you want MySQL based authentication.
                    If you want to use MySQL then the usage of a configuration
                    file is mandatory.
    -J, --lockemu   Activate experimental LOCK and UNLOCK mode (WebDAV Version 2).
                    Currently know to work but needs more tests. Default is ON.
    -M, --nomime    Deactivate mimetype sniffing. Sniffing is based on magic numbers
                    detection but can be slow under heavy load. If you are experiencing
                    speed problems try to use this parameter.
    -i, --icounter  If you want to run multiple instances then you have to
                    give each instance it own number so that logfiles and such
                    can be identified. Default is 0
    -d, --daemon    Make server act like a daemon. That means that it is going
                    to background mode. All messages are redirected to
                    logfiles (default: /tmp/pydav.log and /tmp/pydav.err).
                    You need to pass one of the following values to this parameter
                        start   - Start daemon
                        stop    - Stop daemon
                        restart - Restart complete server
                        status  - Returns status of server

    -v, --verbose   Be verbose
    -l, --loglevel  Select the log level : DEBUG, INFO, WARNING, ERROR, CRITICAL
                    Default is WARNING
    -h, --help      Show this screen

Please send bug reports and feature requests to %s
""" % (__version__, __author__)

def setupDummyConfig(**kw):

    class DummyConfigDAV:
        def __init__(self, **kw):
            self.__dict__.update(**kw)

        def getboolean(self, name):
            return (str(getattr(self, name, 0)) in ('1', "yes", "true", "on", "True"))

    class DummyConfig:
        DAV = DummyConfigDAV(**kw)

    return DummyConfig()

def run():
    verbose = False   
    port = 8008
    host = 'localhost'
    noauth = False
    user = ''
    password = ''
    daemonize = False
    daemonaction = 'start'
    counter = 0
    mysql = False
    lockemulation = True
    configfile = ''
    mimecheck = True
    loglevel = 'warning'

    # parse commandline
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'P:D:H:d:u:p:nvhmJi:c:Ml:',
                ['host=', 'port=', 'user=', 'password=',
                 'daemon=', 'noauth', 'help', 'verbose', 'mysql',
                 'icounter=', 'config=', 'lockemu', 'nomime', 'loglevel'])
    except getopt.GetoptError, e:
        print usage
        print '>>>> ERROR: %s' % str(e)
        sys.exit(2)

    for o,a in opts:
        if o in ['-i', '--icounter']:
            counter = int(str(a).strip())

        if o in ['-m', '--mysql']:
            mysql = True

        if o in ['-M', '--nomime']:
            mimecheck = False

        if o in ['-J', '--lockemu']:
            lockemulation = True

        if o in ['-c', '--config']:
            configfile = a

        if o in ['-H', '--host']:
            host = a

        if o in ['-P', '--port']:
            port = a

        if o in ['-v', '--verbose']:
            verbose = True

        if o in ['-l', '--loglevel']:
            loglevel = a.lower()

        if o in ['-h', '--help']:
            print usage
            sys.exit(2)

        if o in ['-n', '--noauth']:
            noauth = True

        if o in ['-u', '--user']:
            user = a

        if o in ['-p', '--password']:
            password = a

        if o in ['-d', '--daemon']:
            daemonize = True
            daemonaction = a

    chunked_http_response = 1

    # This feature are disabled because they are unstable
    http_request_use_iterator = 0
    http_response_use_iterator = 0

    conf = None
    if configfile != '':
        log.info('Reading configuration from %s' % configfile)
        conf = Configuration(configfile)

        dv = conf.DAV
        verbose = bool(int(dv.verbose))
        loglevel = dv.get('loglevel', loglevel).lower()
        port = dv.port
        host = dv.host
        noauth = bool(int(dv.noauth))
        user = dv.user
        password = dv.password
        daemonize = bool(int(dv.daemonize))
        if daemonaction != 'stop':
            daemonaction = dv.daemonaction
        counter = int(dv.counter)
        lockemulation = dv.lockemulation
        mimecheck = dv.mimecheck

        if 'chunked_http_response' not in dv:
            dv.set('chunked_http_response', chunked_http_response)

        if 'http_request_use_iterator' not in dv:
            dv.set('http_request_use_iterator', http_request_use_iterator)

        if 'http_response_use_iterator' not in dv:
            dv.set('http_response_use_iterator', http_response_use_iterator)

    else:

        _dc = { 'verbose' : verbose,
                'port' : port,
                'host' : host,
                'noauth' : noauth,
                'user' : user,
                'password' : password,
                'daemonize' : daemonize,
                'daemonaction' : daemonaction,
                'counter' : counter,
                'lockemulation' : lockemulation,
                'mimecheck' : mimecheck,
                'chunked_http_response': chunked_http_response,
                'http_request_use_iterator': http_request_use_iterator,
                'http_response_use_iterator': http_response_use_iterator
                }

        conf = setupDummyConfig(**_dc)

    if verbose and (LEVELS[loglevel] > LEVELS['info']):
        loglevel = 'info'

    logging.getLogger().setLevel(LEVELS[loglevel])

    if daemonaction != 'stop':
        log.info('Starting up PyWebDAV server (version %s)' % __version__)
    else:
        log.info('Stopping PyWebDAV server (version %s)' % __version__)

    if daemonaction == 'status':
        log.info('Checking for state...')

    if type(port) == type(''):
        port = int(port.strip())

    log.info('chunked_http_response feature %s' % (conf.DAV.getboolean('chunked_http_response') and 'ON' or 'OFF' ))
    log.info('http_request_use_iterator feature %s' % (conf.DAV.getboolean('http_request_use_iterator') and 'ON' or 'OFF' ))
    log.info('http_response_use_iterator feature %s' % (conf.DAV.getboolean('http_response_use_iterator') and 'ON' or 'OFF' ))

#    if daemonize:
#
#        # check if pid file exists
#        if os.path.exists('/tmp/pydav%s.pid' % counter) and daemonaction not in ['status', 'stop']:
#            log.error(
#                  'Found another instance! Either use -i to specifiy another instance number or remove /tmp/pydav%s.pid!' % counter)
#            sys.exit(3)
#
#        startstop(stdout='/tmp/pydav%s.log' % counter,
#                    stderr='/tmp/pydav%s.err' % counter,
#                    pidfile='/tmp/pydav%s.pid' % counter,
#                    startmsg='>> Started PyWebDAV (PID: %s)',
#                    action=daemonaction)

    # start now
    handler = DbAuthHandler
    
    # injecting options
    handler._config = conf

    runserver(port, host, verbose, noauth, user, password,
              handler=handler)

if __name__ == '__main__':
    run()
