#! -*- coding:utf-8 -*-
"""
A descriptor for @cancellable and @xxx.canceller

"""
from descriptor import Descriptor
class cancellable(Descriptor):
    def __init__(self,caller):
        super(cancellable,self).__init__(caller)
        self.auto_cancel = False
        
    def canceller(self,call_at_connection_lost):
        """
        func is the func below @...canceller
        """
        # style 1: @xxx.canceller
        if callable(call_at_connection_lost):
            self.cancel = lambda: call_at_connection_lost(self.inst)#_cancel
            return
        
        # style 2: @xxx.canceller(True)
        def gen(func):
            """
            def _cancel(*args):
                return func(self.inst,*args)
            # when self.cancel is called, the func is called (_cancel)
            self.cancel = _cancel
            """
            self.cancel = lambda *args: func(self.inst,*args)
            assert isinstance(call_at_connection_lost, bool)
            self.auto_cancel = call_at_connection_lost
            
        return gen
    
    def disconnection_canceller(self,func):
        """
        func is the func below @observe.disconnection_canceller
        this func will be called when connection lost
        """
        def _cancel(*args):
            return func(self.inst,*args)
        # when self.cancel is called, the func is called (_cancel)
        self.cancel = _cancel
        self.auto_cancel = True
        return func


if __name__ == '__main__':
    pass