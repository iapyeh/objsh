#! -*- coding:utf-8 -*-
#
# This build a tree structure for representing this system
# 
#
from twisted.python import log
from twisted.internet import defer,reactor

from objshstate import SimpleStateValue,StateNode,StateTree
import time,sys,datetime,os,re,random

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
    plugable_methods = ['mystate','example']
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

class NTP(SimpleStateValue):
    def __init__(self):
        self.enabled = False
        super(NTP,self).__init__(self.enabled)
    
    def enable(self,yes):
        def done(ret_value,y):
            # 
            # ret_value = self._ntp_service_start(), or
            # ret_value = self._ntp_service_stop()
            #
            # if self._ntp_service_start() returns a deferred, ret_value
            # is the callback value of that deferred
            #
            # so, in this example class, ret_value is 'Enabled' or 'Disabled'
            #
            self._value = y
        def err(failure):
            log.err(failure)
        
        if yes:
            deferred = defer.maybeDeferred(self._ntp_service_start)
        else:
            deferred = defer.maybeDeferred(self._ntp_service_stop)
        deferred.addCallbacks(lambda x,y=yes:done(x,y),err)
        return deferred
    
    @property
    def state(self):
        return {
            'enabled':self._value
        }
    def is_ready(self):
        deferred = defer.Deferred()
        reactor.callLater(1,deferred.callback,True)
        return deferred
    def _ntp_service_start(self):
        deferred = defer.Deferred()
        reactor.callLater(0.5,deferred.callback,'Enabled')
        return deferred
    def _ntp_service_stop(self):
        return 'Disabled'

class MyStateTree(StateTree):
    def build(self):
        #print ('<<<',self.root,'>>>')
        # root
        system = self.root.add_node('system')
        # system
        general = system.add_node('general')
        preference = system.add_node('preference')
        network = system.add_node('network')
        storage = system.add_node('storage')
        #
        general.add_node('cpu',CPU())
        general.add_node('uptime',Uptime())
        general.add_node('memory',Memory())
        #
        preference.add_node('datetime',SystemDatetime())
        preference.add_node('timezone',SystemTimezone())
        preference.timezone.value = 'Asia/Taipei'
        #print preference.timezone.options
        preference.add_node('ntp',NTP())
        preference.ntp.enable(True)

def factory(config):
    """
    config = config.statetree (in config.py)
    """
    return MyStateTree(config)

if __name__ == '__main__':
    import __main__
    from objshstate import get_options
    statetree = MyStateTree(get_options())
    __main__.statetree = statetree
    def dd():
        print ('Uptime.mystate=',statetree.root.system.general.uptime.mystate())
        print ('Uptime.exampl=',statetree.root.system.general.uptime.example())
    #statetree.call_when_ready(statetree.dump)
    statetree.root.call_when_ready(dd)
    reactor.run()