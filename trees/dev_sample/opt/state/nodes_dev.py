#! -*- coding:utf-8 -*-
from __init__ import *
from twisted.python import log
from twisted.internet import defer,reactor
import time, sys
PY3 = sys.version_info[0] == 3

class CPU(SimpleStateValue):    
    def __init__(self):
        #
        # inital value is a static dictionary
        #
        super(CPU,self).__init__(self.get_cpu_value())
    def get_cpu_value(self):
        return {
            'name':'Intel® Core™ i7-7500U',
            'clock_rate':'3.5GHz',
            'cores':4
            }
    @property
    def utilization(self):
        #
        # accessible by CPU().utilization
        #
        return round(random.random(),2)

class Uptime(SimpleStateValue):
    def __init__(self):
        #
        # value is a callable
        # Uptime().value == Uptime().seconds
        #
        super(Uptime,self).__init__(self.get_seconds)
    def get_seconds(self):
        #
        # also accessible by Uptime().value
        #
        return int(time.time()-self._ctime)
    @property
    def seconds(self):
        return self.value
    @property
    def state(self):
        value = self.value
        days,remain = divmod(value,86400)
        hours,remain = divmod(remain,60)
        minutes,seconds = divmod(remain,60)
        return {'days':days,'hours':hours,'minutes':minutes,'seconds':seconds}

class Memory(SimpleStateValue):
    def __init__(self):
        super(Memory,self).__init__({'size':'16GB'})

class SystemDatetime(SimpleStateValue):
    def __init__(self):
        super(SystemDatetime,self).__init__()
    @property
    def state(self):
        now = datetime.datetime.now()
        return {
            'datetime':now.strftime('%Y-%m-%d %H:%M:%S'),
            'date':now.strftime('%Y-%m-%d'),
            'time':now.strftime('%H:%M:%S')
        }

class SystemTimezone(SimpleStateValue):
    def __init__(self):
        self.options = []
        fd = open(os.path.join(os.path.dirname(__file__),'timezones.txt'))
        for line in fd:
            item = line.strip()
            if not item: continue
            self.options.append(item)
        super(SystemTimezone,self).__init__()

    #
    # Override the value setter of SimpleValueState
    #
    def set_value(self,value):
        assert value in self.options
        self._value = value
    value = property(SimpleStateValue.value.fget,set_value)
    
    @property
    def state(self):
        return {
            'options':self.options,
            'value':self._value
        }



class Ethernet(SimpleStateValue):
    def __init__(self):
        self.enabled = False
        super(Ethernet,self).__init__(self.enabled)
    def is_ready(self):
        deferred = defer.Deferred()
        def be_ready():
            self.ready = True
            log.msg('ethernet ready')
            deferred.callback(True)
        reactor.callLater(2,be_ready)
        return deferred

class RAIDSystem(SimpleStateValue):
    def __init__(self):
        self.enabled = False
        super(RAIDSystem,self).__init__(self.enabled)
    def is_ready(self):
        deferred = defer.Deferred()
        def be_ready():
            self.ready = True
            log.msg('RAID system ready')
            deferred.callback(True)
        reactor.callLater(3,be_ready)
        return deferred

class SambaService(SimpleStateValue):
    def __init__(self):
        self.enabled = False
        super(SambaService,self).__init__(self.enabled)

    def is_ready(self):
        self.preference = __main__.statetree.preference.samba
        if not self.preference.share_folders:
            self.preference.share_folders = ['share1','share2','public']
            self.preference.enabled = True
        else:
            del self.preference.enabled
            del self.preference.share_folders
        deferred = defer.Deferred()
        ready_count = [0]
        def check_readiness():
            if ready_count[0] < 2: return
            __main__.statetree.log('samba service ready')
            self.ready = True
            deferred.callback(True)
        def ethernet_ready():
            ready_count[0] += 1
            check_readiness()
        def raidsystem_ready():
            ready_count[0] += 1
            check_readiness()
        __main__.statetree.root.system.network.ethernet.call_when_ready(ethernet_ready)
        __main__.statetree.root.system.storage.raid_system.call_when_ready(raidsystem_ready)
        return deferred
