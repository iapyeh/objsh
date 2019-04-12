#!/usr/bin/env
#! -*- coding:utf-8 -*-
# A python2 and python3 version
# 2018/07/16 starts to rewrite 
# dependences
#   twisted >= 18.7.0
#   txws
#   pyOpenSSL
#   lepl
#   python-pam
#   pyasn1
#   sqlitedict
#   Pillow
# system imports
import sys
PY3 = sys.version_info[0]==3
import os,shutil,re,time
#import configparser
import traceback, datetime, json, signal,pprint
import logging
import __main__
__main__.__all__ = []

if PY3:
    raw_input = input

from twistedutil import get_tzoffset
# choose a good reactor for this platform
from twistedutil import install_reactor
reactor = install_reactor()

# twiwsted related imports
from twisted.internet            import defer, ssl
from twisted.internet.protocol   import Protocol, ServerFactory
from twisted.internet.address    import IPv4Address
from twisted.internet.endpoints  import TCP4ServerEndpoint

from twisted.protocols.basic     import LineReceiver
from twisted.python              import log
from twisted.python.logfile      import DailyLogFile
from twisted.web                 import static, server, resource
from txws_patched                import WebSocketFactory,WebSocketProtocol

# package imports, ulitilies first
from progress_deferred import ProgressDeferred
__main__.ProgressDeferred = ProgressDeferred
__main__.__all__.append('ProgressDeferred')


from cancellable import cancellable
__main__.cancellable = cancellable
__main__.__all__.append('cancellable')

import reloader
from objshobjects import ObjshTask, ObjshCommand
from shellrunner import ObjshRunner
from logformat import productive_logformat, apply_min_log_level
from objshssh import ObjshSshFactory,ObjshTelnetFactory, ObjshAvatar, getObjshPortal
from objshweb import *
from objshshell import *

def start_up(config):
    """
    starts up daemons
    """

    # put some config items to __main__, for safety not all are copied
    __main__.developing_mode = config.general['developing_mode']

    runner = ObjshRunner(config)
    ObjshTask.runner = runner
    ObjshTask.cache_folder = os.path.join(config.folder['var'],'task')
    if not os.path.exists(ObjshTask.cache_folder):
        os.mkdir(ObjshTask.cache_folder)

    # shorten this task maintenance interval in developing mode
    ObjshTask.maintenance_interval = config.runner['maintenance_interval']
    ObjshTask.ttl = config.runner['ttl']

    factories = []

    # cached portal
    portals = {}

    for name, daemon_options in config.general['daemon'].items():
        if not daemon_options.get('enable'):
            continue

        if daemon_options.get('ssl'):
            ssl_key = daemon_options['ssl']['key']
            ssl_crt = daemon_options['ssl']['crt']
        else:
            ssl_key = None
            ssl_crt = None

        acls = daemon_options['acls']
        acls_key = ','.join(sorted(acls))
        portal = portals.get(acls_key)
        if portal is None:
            enabled_acls = {}
            for acl_name in acls:
                enabled_acls[acl_name] = config.acl_options[acl_name]
            portal = getObjshPortal(ObjshProtocol,enabled_acls)
            portals[acls_key] = portal

        assert portal is not None
        # http, websocket or telnet
        daemon_type = daemon_options.get('type','').upper()

        if daemon_type == 'WEB':

            # for the site-root, a single is used (changed from 2018/5/10)
            #if ObjectiveShellSiteRoot.singleton is None:
            #    ObjectiveShellSiteRoot(None, portal=portal,daemon_options=daemon_options)
            root = ObjectiveShellSiteRoot.get_singleton(None, portal=portal,daemon_options=daemon_options)

            web_factories = []
            
            # suppress the web server to log
            factory_site = server.Site(root,logPath='/dev/null')
            #factory_site = server.Site(root)
            
            web_factories.append((daemon_options['port'], factory_site))
            log.info('Web in %s' % daemon_options['port'])

            if daemon_options['websocket']['enable']:
                factory = ObjshFactory()
                if daemon_options.get('ssl'):
                    AuthWebSocketProtocol.secure_site = factory_site
                else:
                    AuthWebSocketProtocol.site = factory_site
                WebSocketFactory.protocol = AuthWebSocketProtocol
                factory_websocket = WebSocketFactory(factory)

                if daemon_options['websocket']['route']:
                    route = daemon_options['websocket']['route']
                    # upgrade /ws to websocket connection
                    assert route[0] == '/'
                    root.putChild(route[1:].encode(),WebSocketResource(factory_websocket))
                    log.info('Websocket in route %s' % daemon_options['websocket']['route'])
                else:
                    assert daemon_options['websocket']['port'] > 0
                    web_factories.append((daemon_options['websocket']['port'],factory_websocket))
                    log.info('Websocket in port %s' % daemon_options['websocket']['port'])
                
            if daemon_options.get('ssl'):
                assert ssl_key and ssl_crt
                for _port, _factory in web_factories:
                    reactor.listenSSL(_port,
                                      _factory,
                                      ssl.DefaultOpenSSLContextFactory(ssl_key, ssl_crt))

                    # for tracking
                    factories.append(_factory)
            else:
                for _port, _factory in web_factories:
                    reactor.listenTCP(_port, _factory)
                    # for tracking
                    factories.append(_factory)

        elif daemon_type=='SSH':
            # for authentication and authorization
            factory = ObjshSshFactory(portal,daemon_options)
            reactor.listenTCP(daemon_options['port'], factory)
            # for tracking
            factories.append(factory)
            log.msg('SSH in %s' % daemon_options['port'])
        elif daemon_type=='TELNET':
            # telnet localhost 1723
            # telnet-ssl -z ssl localhost 1724
            factory = ObjshTelnetFactory(portal)
            if daemon_options.get('ssl'):
                assert ssl_key and ssl_crt
                reactor.listenSSL(daemon_options['port'],
                                  factory,
                                  ssl.DefaultOpenSSLContextFactory(ssl_key, ssl_crt))
            else:
                reactor.listenTCP(daemon_options['port'], factory)
            # for tracking
            factories.append(factory)
            log.msg('TELNET in %s %s secure' % (daemon_options['port'],'with' if daemon_options.get('secure') else 'without'))
        elif daemon_type=='TCPSOCKET':
            factory = ObjshFactory(portal)
            if daemon_options.get('ssl'):
                assert ssl_key and ssl_crt
                reactor.listenSSL(daemon_options['port'],
                                  factory,
                                  ssl.DefaultOpenSSLContextFactory(ssl_key, ssl_crt))
            else:
                reactor.listenTCP(daemon_options['port'], factory)
            # for tracking
            factories.append(factory)
            log.msg('TCPSOCKET in %s %s secure' % (daemon_options['port'],'with' if daemon_options.get('secure') else 'without'))
        else:
            raise Exception('unsupported daemon type "%s"' % daemon_type)



    """
    def beforeShutdown():
        for factory in factories:
            if not isinstance(factory,ObjectiveShellFactory): continue
            for protocol in factory.protocols:
                for task in protocol.running_tasks:
                    print 'disposing task',task.id
                    task.dispose()
    #reactor.addSystemEventTrigger('before', 'shutdown', beforeShutdown)
    """

    #
    # add signal handler to reload runner
    #
    def rescan_runner(number,frame):
        reloader.enable()
        reloader.reload(objshrunner)
        factories[0].runner.scan()

    signal.signal(signal.SIGUSR1, rescan_runner)

    return factories

def init(home_path=None):
    # load config.py
    pwd = os.path.abspath(os.path.dirname(__file__))

    def get_relpath(path):
        return os.path.relpath(path,pwd)

    # home_path is the specific "tree" folder where has "etc", "opt", "var"
    # home_path could be multiple. objsh.py will collect "etc,opt,var" from these path.
    # also, these paths will be inserted into sys.path
    home_paths = []
    home_path_default = os.path.abspath(os.path.normpath(os.path.join(pwd,'..')))
    
    # get home_path from second argument of command line
    if home_path is None:
        # run in style of "python objsh.py <tree>"
        if len(sys.argv)>=2:
            argv = sys.argv[1]
            if argv[0] == '~':
                home_path = os.path.expanduser(argv)
            else:
                home_path = os.path.abspath(os.path.normpath(argv))
            assert os.path.exists(home_path),'path "%s" not found' % home_path
            home_paths.append(home_path)
    else:
        # run in style of "python <tree>/app.py"
        assert os.path.exists(home_path),'path "%s" not found' % home_path
        home_paths.append(home_path)

    # use default folder
    if len(home_paths)==0:
        home_paths.append(home_path_default)

    def search_in_homepaths_for(name):
        for home_path in home_paths:
            _path = os.path.join(home_path,name)
            if os.path.exists(_path): return _path
        #raise ValueError('folder for "%s" not found in %s' % (name,home_paths))
    etc_folder = search_in_homepaths_for('etc')
    assert etc_folder, ValueError('folder "etc" not found in %s' % home_paths)
    config_py_path = os.path.join(etc_folder,'config.py')
    config_py_path_default = os.path.join(home_path_default,'etc','config.py')
    reset_config_py = True
    if config_py_path == config_py_path_default:
        reset_config_py = False
    elif os.path.exists(config_py_path):
        # check config version
        # if config version was obsoleted, upgrade it
        #
        def get_version(path):
            fd = open(path)
            version = None
            for line in fd.readlines():
                if line.startswith('#version'):
                    version = line.split('=')[1].strip()
                    break
            return version
        v0 = get_version(config_py_path_default)
        assert v0
        v1 = get_version(config_py_path)
        if v0 == v1:
            reset_config_py = False
        else:
            
            #Dont ask, just overwrite
            #answer = raw_input('Reset config.py from version "%s" to "%s" (Yes/No)? ' % (v1,v0))
            answer = 'yes'

            if answer.lower().strip()=='yes':
                pass
            else:
                if answer.lower().startswith('y'):
                    print ('Explicit "Yes" should be answered to ensure you agree to override existing config.py')
                print ('New version of config.py should be applied to continue.',)
                print ('Please update the config.py manually. Or run this again with "Yes"')
                reset_config_py = False
                reactor.stop()
                return

    if reset_config_py:
        log.msg('config.py has reset to version %s' % v0)

        # make a backup and lookup for "**DONT_TOUCH_BELOW**"
        reserved_lines = None
        if os.path.exists(config_py_path):

            reserved_lines = []
            fd = open(config_py_path,'r')
            reserve_found = False
            dont_touch_below = '**DONT_TOUCH_BELOW**'
            for line in fd:
                if reserve_found:
                    reserved_lines.append(line)
                elif line.find(dont_touch_below)>1:
                    reserve_found = True
                    reserved_lines.append(line)

            # append "**DONT_TOUCH_BELOW**" if it is not in config.py
            if not reserve_found:
                reserved_lines.append('#\n# '+dont_touch_below+'\n#\n')
                reserved_lines.append('# Lines blow will be reserved even config file has reset to default\n')
                reserved_lines.append('#\n')
            config_py_path_backup = config_py_path+('.%s' % int(time.time()))
            shutil.copy(config_py_path,config_py_path_backup)
            log.msg('existing config.py rename to %s' % os.path.basename(config_py_path_backup))

        # append reserved_lines to the end
        config_py_path_dafault = os.path.join(home_path_default,'etc','config.py')
        if reserved_lines is not None:
            content = open(config_py_path_dafault,'r').read()
            fd = open(config_py_path,'w')
            fd.write(content.rstrip())
            fd.write('\n#\n')
            fd.write(''.join(reserved_lines))
            fd.close()
        else:
            # simply override config.py with src/../etc/config.py
            shutil.copy(config_py_path_dafault,config_py_path)

    # load confin.py
    sys.path.insert(0,etc_folder)
    sys.stderr.write('use config.py in %s\n' % etc_folder)
    try:
        config = __import__('config',fromlist=[[]])
        __main__.config = config
    except:
        traceback.print_exc()
        reactor.stop()
    finally:
        sys.path.remove(etc_folder)

    # assign config.objsh (used by objshweb)
    import config_objsh
    config.objsh = config_objsh.info
    assert config.objsh['version']
    sys.stderr.write('config version is %s\n' % config.objsh['version'])

    config.general['folder']['pwd'] = pwd
    # setup conventional folders
    for name in ('var','etc','opt'):
        folder = config.general['folder'][name]
        sys.stderr.write('include %s\n' % folder)
        assert len(folder) , 'missing "%s" in "%s"' % (name,os.path.join(etc_folder,'config.py'))
        #config.general['folder'][name] = os.path.abspath(os.path.normpath(os.path.join(etc_folder,folder)))
        #assert os.path.exists(config.general['folder'][name]),'not found:'+config.general['folder'][name]
        
        if os.path.exists(folder): continue
        folder = search_in_homepaths_for(name)
        assert folder and os.path.exists(folder), 'folder "%s" is not existed' % name
        config.general['folder'][name] = folder
    
    sys.stdout.write('logging started(reactor=%s)\n' % reactor)
    # start logging
    log.FileLogObserver.emit=productive_logformat
    log_folder = os.path.join(config.general['folder']['var'],'logs')
    if not os.path.exists(log_folder): os.mkdir(log_folder)
    log.startLogging(DailyLogFile.fromFullPath(os.path.join(log_folder,config.general['log']['filename'])),setStdout=False)

    developing_mode = config.general['developing_mode']
    if developing_mode:
        tzoffset = get_tzoffset()
        def dump_log(eventDict):
            try:
                if PY3:
                    if eventDict['log_level'].name == 'warn':
                        try:
                            raw_msg = [str(eventDict['warning'])]
                        except KeyError:
                            raw_msg = [str(eventDict['message'])]
                    else:
                        raw_msg = eventDict.get('failure')
                        if raw_msg is None:
                            raw_msg = eventDict['message']
                        else:
                            raw_msg = [raw_msg.getErrorMessage(),raw_msg.getTraceback()]

                    chunks = [x if isinstance(x,str) else str(x) for x in raw_msg]
                    msg = ' '.join(chunks)
                else:
                    msg = eventDict.get('failure') or ' '.join([x.encode('utf-8') if isinstance(x,unicode) else str(x) for x in eventDict['message']])
                
                if msg == '' and eventDict['log_format'].startswith('Timing out client:'):
                    return
                ts = str(eventDict['time']+tzoffset)
                # append 0 for value likes "1526537871.8"
                ts += '0' if len(ts)==12 else ''
                sys.stdout.write('%s:%s:%s\n' % (ts,eventDict['log_level'].name,msg))
            except:
                traceback.print_exc()
        log.addObserver(dump_log)

    # output settings to log
    log.msg('use config.py file at %s ' % get_relpath(config_py_path))
    for name in ('var','etc','opt'):
        #log.msg('>>> set '+name+' folder to %s' % (os.path.relpath(config.general['folder'][name],config_py_path)))
        log.msg('set '+name+' folder to %s' % (config.general['folder'][name]))

    task_folder = os.path.join(config.general['folder']['var'],'task')
    if not os.path.exists(task_folder): os.mkdir(task_folder)
    config.general['folder']['task'] = task_folder


    #
    # load default and user runners
    #
    runner_folders = [os.path.join(config.general['folder']['pwd'],'sysrunner')]
    folders = config.general.get('runners',[])
    for folder in folders:
        folder = folder.strip()
        if not folder: continue
        runner_folder = os.path.abspath(os.path.normpath(os.path.join(etc_folder,folder)))
        assert os.path.exists(runner_folder), 'not found: '+runner_folder
        runner_folders.append(runner_folder)
        log.msg('runner folder',get_relpath(runner_folder))
    config.general['folder']['runners'] = runner_folders

    #
    # load default statetree
    #
    state_config = config.statetree
    statestree_py = os.path.abspath(os.path.normpath(os.path.join(etc_folder,state_config['factory'])))
    assert os.path.exists(statestree_py), 'not found:'+statestree_py
    log.msg('load statetree from ',get_relpath(statestree_py))

    # load statetree builder script
    statestree_py_dir = os.path.dirname(statestree_py)
    statestree_py_basename = os.path.splitext(os.path.basename(statestree_py))[0]
    if statestree_py_dir in sys.path:
        statestree_py_dir_remove = False
    else:
        statestree_py_dir_remove = True
        sys.path.insert(0,statestree_py_dir)
    try:
        factory = getattr(__import__(statestree_py_basename),'factory')
    except AttributeError:
        log.msg('factory() not found in ',statestree_py)
        sys.exit(1)
    except:
        log.msg(traceback.format_exc())
        sys.exit(1)
    else:
        log.msg(os.path.basename(statestree_py),'load completed')
        config.statetree['folder'] = config.folder
        statetree = factory(config.statetree)
        if config.general['developing_mode']:
            def dump():
                pp = pprint.PrettyPrinter()
                log.msg('\n'+statetree.dump())
                log.msg(pp.pformat(statetree.preference.value))
            statetree.call_when_ready(dump)

        # enable min_log_level    
        statetree.call_when_ready(apply_min_log_level)
    
    if statestree_py_dir_remove: sys.path.remove(statestree_py_dir)

    # bring up network services
    def do_start_up(config):
        try:
            start_up(config)
        except:
            traceback.print_exc()
            reactor.stop()
    reactor.callWhenRunning(do_start_up,config)

def app(homepath=None):
    try:
        init(homepath)
    except:
        traceback.print_exc()
        reactor.stop()

if __name__ == '__main__':
    reactor.callWhenRunning(app)
    reactor.run()