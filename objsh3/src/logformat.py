from twisted.python import log,util
from twisted.logger import LogLevel
import sys, traceback, __main__
from twisted.internet import reactor
PY3 = sys.version_info[0]==3
import time, datetime
# maps log-level name to nubmer
#CRITICAL	50
#ERROR	40
#WARNING	30
#INFO	20
#DEBUG	10
#NOTSET	0
level_code  = {
    'debug':'10',
    'info':'20',
    'warn':'30',
    'warning':'30',  #alias of warn
    'error':'40',
    'critical':'50'
}

_n = time.time()
offset = datetime.datetime.utcfromtimestamp(_n) - datetime.datetime.fromtimestamp(_n)
tzoffset = offset.days * (60 * 60 * 24) + offset.seconds
def productive_logformat(self,eventDict):
    text = log.textFromEventDict(eventDict)
    if text is None: return
    code = level_code[eventDict['log_level'].name]
    timeStr = str(eventDict['time'] + tzoffset) # use UTC timestamp
    
    # append 0 for value likes "1526537871.8" (disabled to reduce overhead)
    # timeStr += '0' if len(timeStr)==12 else ''

    # python2 len is 13, python3 len is 17
    #assert len(timeStr)==13,'expect len(timeStr)==13, got %s(%s)' % (len(timeStr), timeStr)
    
    fmtDict = {
      'text': text.replace('\n','\\n'), # flat into one line only
      'code':code,
    }
    
    msgStr = log._safeFormat(":%(code)s:%(text)s\n", fmtDict)
    util.untilConcludes(self.write, timeStr[:13] + msgStr)
    util.untilConcludes(self.flush)

def patch_log():
    _msg = log.msg
    def my_msg(*message,**kw):
        try:
            kw['log_level']
        except KeyError:
            kw['log_level'] = LogLevel.debug
        return _msg(*message,**kw)  

    # default level of log.msg is debug
    log.msg = my_msg

    #
    # add convenient functions to log
    # log.info, log.warn, log.error, log.debug
    #

    def my_debug(*message,**kw):
        kw['log_level'] = LogLevel.debug
        _msg(*message,**kw)
    log.debug = my_debug

    def my_info(*message,**kw):
        kw['log_level'] = LogLevel.info
        _msg(*message,**kw)
    log.info = my_info

    def my_warn(*message,**kw):
        kw['log_level'] = LogLevel.warn
        _msg(*message,**kw)
    log.warn = my_warn
    log.warning = log.warn

    def my_error(*message,**kw):
        kw['log_level'] = LogLevel.error
        _msg(*message,**kw)
    log.error = my_error

    def my_critical(*message,**kw):
        kw['log_level'] = LogLevel.critical
        _msg(*message,**kw)
    log.critical = my_critical
patch_log()

# implement general['log']['min_log_level'] of config.py
# this will be called after statetrees is ready.
# before it, all level of log are dumped.
def apply_min_log_level():    
    #
    # Monkey patch to set default log level to be debug
    # 

    def ignore_log(*message,**kw):
        pass

    min_log_level = __main__.config.general['log'].get('min_log_level','debug').lower() or 'debug'
    sys.stdout.write('set min log level to %s\n' % min_log_level)
    if min_log_level == 'crtical':
        log.msg = log.error = log.warn = log.info = log.debug = ignore_log
    elif min_log_level == 'error':
        log.msg = log.warn = log.info = log.debug = ignore_log
    elif min_log_level == 'warn':
        log.msg = log.info = log.debug = ignore_log
    elif min_log_level == 'info':
        log.msg = log.debug = ignore_log
