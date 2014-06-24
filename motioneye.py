#!/usr/bin/env python

# Copyright (c) 2013 Calin Crisan
# This file is part of motionEye.
#
# motionEye is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>. 

import datetime
import inspect
import logging
import multiprocessing
import os.path
import re
import signal
import sys

import settings

sys.path.append(os.path.join(getattr(settings, 'PROJECT_PATH', os.path.dirname(sys.argv[0])), 'src'))

import smbctl

VERSION = '0.12'


def _configure_settings():
    def set_default_setting(name, value):
        if not hasattr(settings, name):
            setattr(settings, name, value)
    
    set_default_setting('PROJECT_PATH', os.path.dirname(sys.argv[0]))
    set_default_setting('TEMPLATE_PATH', os.path.join(settings.PROJECT_PATH, 'templates'))  # @UndefinedVariable
    set_default_setting('STATIC_PATH', os.path.join(settings.PROJECT_PATH, 'static'))  # @UndefinedVariable
    set_default_setting('STATIC_URL', '/static/')
    set_default_setting('CONF_PATH', os.path.join(settings.PROJECT_PATH, 'conf'))  # @UndefinedVariable
    set_default_setting('RUN_PATH', os.path.join(settings.PROJECT_PATH, 'run'))  # @UndefinedVariable
    set_default_setting('REPO', ('ccrisan', 'motioneye'))
    set_default_setting('LOG_LEVEL', logging.INFO)
    set_default_setting('LISTEN', '0.0.0.0')
    set_default_setting('PORT', 8765)
    set_default_setting('SMB_SHARES', False)
    set_default_setting('MOUNT_CHECK_INTERVAL', 300)
    set_default_setting('MOTION_CHECK_INTERVAL', 10)
    set_default_setting('CLEANUP_INTERVAL', 43200)
    set_default_setting('THUMBNAILER_INTERVAL', 60)
    set_default_setting('REMOTE_REQUEST_TIMEOUT', 10)
    set_default_setting('MJPG_CLIENT_TIMEOUT', 10)
    set_default_setting('PICTURE_CACHE_SIZE', 8)
    set_default_setting('PICTURE_CACHE_LIFETIME', 60)
    
    length = len(sys.argv) - 1
    for i in xrange(length):
        arg = sys.argv[i + 1]
        
        if not arg.startswith('--'):
            continue
        
        next_arg = None
        if i < length - 1:
            next_arg = sys.argv[i + 2]
        
        name = arg[2:].upper().replace('-', '_')
        
        if name == 'HELP':
            _print_help()
            sys.exit(0)
        
        if hasattr(settings, name):
            curr_value = getattr(settings, name)
            
            if next_arg.lower() == 'debug':
                next_arg = logging.DEBUG
            
            elif next_arg.lower() == 'info':
                next_arg = logging.INFO
            
            elif next_arg.lower() == 'warn':
                next_arg = logging.WARN
            
            elif next_arg.lower() == 'error':
                next_arg = logging.ERROR
            
            elif next_arg.lower() == 'fatal':
                next_arg = logging.FATAL
            
            elif next_arg.lower() == 'true':
                next_arg = True
            
            elif next_arg.lower() == 'false':
                next_arg = False
            
            elif isinstance(curr_value, int):
                next_arg = int(next_arg)
            
            elif isinstance(curr_value, float):
                next_arg = float(next_arg)

            setattr(settings, name, next_arg)
        
        else:
            return arg[2:]
    
    try:
        os.makedirs(settings.CONF_PATH)
        
    except:
        pass
    
    try:
        os.makedirs(settings.RUN_PATH)

    except:
        pass


def _test_requirements():
    if os.geteuid() != 0:
        if settings.SMB_SHARES:
            print('SMB_SHARES require root privileges')
            return False

    try:
        import tornado  # @UnusedImport
        tornado = True
    
    except ImportError:
        tornado = False

    try:
        import jinja2  # @UnusedImport
        jinja2 = True
    
    except ImportError:
        jinja2 = False

    try:
        import PIL.Image  # @UnusedImport
        pil = True
    
    except ImportError:
        pil = False

    import mediafiles
    ffmpeg = mediafiles.find_ffmpeg() is not None
    
    import motionctl
    motion = motionctl.find_motion() is not None
    
    import v4l2ctl
    v4lutils = v4l2ctl.find_v4l2_ctl() is not None
    
    mount_cifs = smbctl.find_mount_cifs() is not None
    
    ok = True
    if not tornado:
        print('please install tornado (python-tornado)')
        ok = False
    
    if not jinja2:
        print('please install jinja2 (python-jinja2)')
        ok = False

    if not pil:
        print('please install PIL (python-imaging)')
        ok = False

    if not ffmpeg:
        print('please install ffmpeg')
        ok = False

    if not motion:
        print('please install motion')
        ok = False

    if not v4lutils:
        print('please install v4l-utils')
        ok = False

    if settings.SMB_SHARES and not mount_cifs:
        print('please install cifs-utils')
        ok = False

    return ok

        
def _configure_signals():
    def bye_handler(signal, frame):
        import tornado.ioloop
        
        logging.info('interrupt signal received, shutting down...')

        # shut down the IO loop if it has been started
        ioloop = tornado.ioloop.IOLoop.instance()
        ioloop.stop()
        
    def child_handler(signal, frame):
        # this is required for the multiprocessing mechanism to work
        multiprocessing.active_children()

    signal.signal(signal.SIGINT, bye_handler)
    signal.signal(signal.SIGTERM, bye_handler)
    signal.signal(signal.SIGCHLD, child_handler)


def _configure_logging():
    logging.basicConfig(filename=None, level=settings.LOG_LEVEL,
            format='%(asctime)s: %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


def _print_help():
    print('Usage: ' + sys.argv[0] + ' [option1 value1] ...')
    print('available options: ')
    
    options = list(inspect.getmembers(settings))
    
    for (name, value) in sorted(options):
        if name.upper() != name:
            continue
        
        if not re.match('^[A-Z0-9_]+$', name):
            continue
        
        name = '--' + name.lower().replace('_', '-')
        if value is not None:
            value = type(value).__name__
        
        line = '    ' + name
        if value:
            line += ' <' + value + '>'
        print(line)
    
    print('')


def _run_server():
    import cleanup
    import motionctl
    import thumbnailer
    import tornado.ioloop
    import server

    server.application.listen(settings.PORT, settings.LISTEN)
    logging.info('server started')
    
    tornado.ioloop.IOLoop.instance().start()

    logging.info('server stopped')
    
    if thumbnailer.running():
        thumbnailer.stop()
        logging.info('thumbnailer stopped')

    if cleanup.running():
        cleanup.stop()
        logging.info('cleanup stopped')

    if motionctl.running():
        motionctl.stop()
        logging.info('motion stopped')
    
    if settings.SMB_SHARES:
        smbctl.umount_all()
        logging.info('SMB shares unmounted')


def _start_motion():
    import tornado.ioloop
    import config
    import motionctl

    # add a motion running checker
    def checker():
        ioloop = tornado.ioloop.IOLoop.instance()
        if ioloop._stopped:
            return
            
        if not motionctl.running() and config.has_enabled_cameras():
            try:
                motionctl.start()
                logging.info('motion started')
            
            except Exception as e:
                logging.error('failed to start motion: %(msg)s' % {
                        'msg': unicode(e)}, exc_info=True)

        ioloop.add_timeout(datetime.timedelta(seconds=settings.MOTION_CHECK_INTERVAL), checker)
    
    checker()


def _start_cleanup():
    import cleanup

    cleanup.start()
    logging.info('cleanup started')


def _start_thumbnailer():
    import thumbnailer

    thumbnailer.start()
    logging.info('thumbnailer started')


if __name__ == '__main__':
    cmd = _configure_settings()
    
    if not _test_requirements():
        sys.exit(-1)
    
    _configure_signals()
    _configure_logging()
    
    if settings.SMB_SHARES:
        smbctl.update_mounts()

    _start_motion()
    _start_cleanup()
    
    if settings.THUMBNAILER_INTERVAL:
        _start_thumbnailer()
    
    _run_server()
