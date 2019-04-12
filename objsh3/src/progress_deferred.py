#! -*- coding:utf-8 -*-
import traceback
from twisted.internet import defer,reactor
from twisted.python import log
class ProgressDeferred(defer.Deferred):
    """ A deferred can be called multiple times with progress """
    def __init__(self):#,percent=0.0):
        """
        @param percent: initial percent, 0.0 - 1.0
        """
        #assert percent <= 1.0
        defer.Deferred.__init__(self)
        #self.percent = percent

    def callback(self,result):
        """ wrap original callback to set percent = 1 """
        # so, progressBack will not been invoked
        #
        #reactor.callLater(0,defer.Deferred.callback,self,result)
        defer.Deferred.callback(self,result)
        
    def addProgressBack(self,_callable,*progressArgs):
       
        try:
            self._progress_back.append((_callable,progressArgs))
        except AttributeError:
            self._progress_back = [(_callable,progressArgs)]

    def removeProgressBack(self,_callable):
        idx_to_remove = -1
        for idx,item in enumerate(self._progress_back):
            if item[0] == _callable:
                idx_to_remove = idx
                break
        if idx_to_remove >= 0:
            del self._progress_back[idx_to_remove]

    def progressBack(self,*payload):#,percent=None):
        """
        When percent is 1.0, the self.callback() is not been called.
        Because they might have different callback arguments.
        
        Call this has no effect if self.percent >= 1.0
        """
        
        if self.called:
            log.err('ProgressDeferred %s already called' % self)
            return
        
        try:
            for _callback, progressArgs in self._progress_back:
                try:
                    _callback(*payload) if progressArgs is None else _callback(*(payload+progressArgs))
                except:
                    log.msg(traceback.format_exc())
        except AttributeError:
            # no progress callbacks
            pass
    
    # borrowed terminology from JQuery promise
    progress = addProgressBack
    notify   = progressBack