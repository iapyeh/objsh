import sys
import time, datetime
import __main__
def current_reactor_klass():
    """
    Return class name of currently installed Twisted reactor or None.
    """
    #from twisted.python import reflect
    from twisted.internet.error import ReactorAlreadyInstalledError
    if 'twisted.internet.reactor' in sys.modules:
        #raise ReactorAlreadyInstalledError()
        #current_reactor = reflect.qual(sys.modules['twisted.internet.reactor'].__class__).split('.')[-1]
        current_reactor = sys.modules['twisted.internet.reactor']
    else:
        current_reactor = None
    return current_reactor

def install_reactor(use_asyncio=False):
    """
    Borrowed from https://github.com/crossbario/autobahn-python/blob/master/autobahn/twisted/choosereactor.py
    """
    current_reactor = current_reactor_klass()    
    if current_reactor:
        return current_reactor

    if use_asyncio:
        #files=132, cost=186.99198293685913 seconds, speed=2007542.4309862417
        import asyncio
        import uvloop
        #asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        asyncio.set_event_loop(uvloop.new_event_loop())
        from twisted.internet import asyncioreactor
        asyncioreactor.install()
    elif 'bsd' in sys.platform or sys.platform.startswith('darwin'):
        # This reactor is faster in MacOS
        # files=132, cost=61.64284586906433 seconds, speed=6089828.182127992
        # files=132, cost=58.344452142715454 seconds, speed=6434105.149907892
        # *BSD and MacOSX
        #
        from twisted.internet import kqreactor
        kqreactor.install()
    elif sys.platform in ['win32']:
        from twisted.internet.iocpreactor import reactor as iocpreactor
        iocpreactor.install()
    elif sys.platform.startswith('linux'):
        from twisted.internet import epollreactor
        epollreactor.install()
    else:
        from twisted.internet import selectreactor
        selectreactor.install()
    from twisted.internet import reactor
    return reactor

def get_tzoffset():
    """
    returns the tzoffset in seconds, time.time()+tzoffset would convert local timestamp to utc timestamp    
    """
    try:
        return __main__.tzoffset
    except AttributeError:
        _n = time.time()
        offset = datetime.datetime.utcfromtimestamp(_n) - datetime.datetime.fromtimestamp(_n)
        __main__.tzoffset = offset.days * (60 * 60 * 24) + offset.seconds
        return __main__.tzoffset