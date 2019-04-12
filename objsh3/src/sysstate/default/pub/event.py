#! -*- coding:utf-8 -*-
"""
State node of root.pub.
The aggregator for public stuffs. Such as utilities.
"""
from .__init__ import *
import __main__
from twisted.python import log
from twisted.internet import reactor
import time

class Event(SimpleStateValue):
    """
    Observe event
    """
    def __init__(self):
        super(Event,self).__init__()
        self.running = False

    def is_ready(self):
        return True


    @exportable
    @cancellable
    def observe(self):
        """
        output is string
        """
        pd = ProgressDeferred()

        def job(_pd):
            def observer(evt):
                if self.running: _pd.notify(evt.serialized_data)
        
            def stopObserver(_pd,_observer):
                self.running = False
                statetree.root.remove_event_listener(observer)
                _pd.callback('event observing cancelled')

            self._observer = lambda x=_pd,y=observer: stopObserver(x,y)
            statetree.root.add_event_listener(observer)
            _pd.notify({'time':time.time(),'name':'EventObserver','source':'event','payload':'Event observing starts'})
        self.running = True
        #reactor.callInThread(job)
        self.callInThread(job,pd)
        return pd

    @observe.canceller(True)
    def stop_observe(self):
        if self.running:
            self._observer()
            del self._observer

statetree.nodes.pub.add_node('event',Event())
