import __main__
import sys
PY3 = sys.version_info[0] == 3

class Descriptor(object):
    def __init__(self,caller):
        """
        caller is the func below @cancellable
        
        @cancellable
        def the_caller(self):
            ...
        """
        super(Descriptor,self).__init__()
        if isinstance(caller,Descriptor):
            self._prev_caller = caller
            self.caller = caller.caller

            # get decorated func's __dict__
            if PY3:
                self.__dict__.update(self.caller.__dict__)
            else:
                self.func_dict = self.caller.func_dict
        elif isinstance(caller,property):
            # in style of :
            # @exportable
            # @property
            # def xxxx:
            #     ....
            #
            self._prev_caller = caller
            self.caller = caller
            if PY3:
                self.__dict__ = {}
            else:
                self.func_dict = None
            
        else:
            self._prev_caller = None
            self.caller = caller
            # get decorated func's __dict__
            if PY3:
                self.__dict__.update(self.caller.__dict__)
            else:
                self.func_dict = self.caller.func_dict


        # get decorated func's __doc__
        self.__doc__ = self.caller.__doc__
        self.inst = None
        self.type = None
        self._fget = self.caller

    def __get__(self,inst,type=None):
        """
        inst is the instance which owns the caller
        this is called when caller is referenced by <instance>.<method>
        
        usually type is the class, inst is an instance of that class,
        but type is None in two styles below:
        @property
        @exportable
        def prop(self):
            ...
            
        @exportable 
        @cancellable
        def prop(self):
            ...
        """
        assert isinstance(inst,__main__.SimpleStateValue),'Expect instance of SimpleStateValue got %s' % inst
        if inst and self.inst is None:
            self.inst = inst
        if type and self.type is None:
            self.type = type
        
        if isinstance(self.caller,property):
            return self.caller
        elif self._prev_caller and self._prev_caller.inst is None:
            self._prev_caller.__get__(inst,type)
        
        return self

    def __set__(self,inst,value):

        assert isinstance(inst,__main__.SimpleStateValue)

        if self.inst is None:
            self.inst = inst
        
        if self._prev_caller and self._prev_caller.inst is None:
            self._prev_caller.__set__(inst,value)

        self.caller = value
    
    '''
    def fget(self):
        if isinstance(self.caller,property):
            return self.caller.fget
        elif self._prev_caller:
            return self._prev_caller.fget
        else:
            return self.caller.fget
    '''
    @property
    def fget(self):
        return self._fget
    def __call__(self,*args,**kw):
        """
        when the caller is called
        """
        if isinstance(self.caller,property):
            return self.caller.fget(self.inst)
        elif self.inst is None:
            # in style of
            # @property
            # @exportable
            # def prot(self):
            #     ....
            inst = args[0]
            # this will set self.inst, so next time, this would not be called,
            # instead, next statement will be called (self.type is None)
            self.__get__(inst)
            return self.caller(*args,**kw)
        elif self.type is None:
            return self.caller(self.inst)
        else:
            return self.caller(self.inst,*args,**kw)
        
    def __delete__(self,inst):
        raise NotImplementedError('__delete__ is not implemented')
    
    def __getattr__(self,name):
        """
        This is required for the following code to work:
            @exportable
            @cancellable
            def observe(self):
                pass
            
            # observe is an instace of exportable, it has no "canceller"
            # the .canceller is an attribute of its _prev_caller
            # so, we should lookup into _prev_caller
            @observe.canceller(True)
            def stop_observe(self):
                pass
        """
        '''
        try:
            #return self.__dict__[name]
            return object.__getattribute__(self,name)
        except AttributeError as e:
            print name,' not found<<<<<<<<<<<<<<<'
            if self._prev_caller is not None:
                return getattr(self._prev_caller,name)
            else:
                raise AttributeError(name+' is not attribute of '+self.__class__.__name__)
        '''
        try:
            return self.__dict__[name]
        except KeyError as e:
            if self._prev_caller is not None:
                return getattr(self._prev_caller,name)
            else:
                raise AttributeError(name+' is not attribute of '+self.__class__.__name__)

import __main__
class exportable(Descriptor):
    def __get__(self,inst,type=None):
        """
        inst is the instance which owns the caller
        this is only been called when caller is referenced by <instance>.<method>
        """
        if self.inst is None:
            assert isinstance(inst,__main__.SimpleStateValue)
            self.inst = inst
            if PY3:
                if isinstance(self.caller,property):
                    func_name = self.caller.fget.__name__
                else:
                    func_name = self.caller.__name__
            else:
                if isinstance(self.caller,property):
                    func_name = self.caller.fget.func_name
                else:
                    func_name = self.caller.func_name #self._prev_caller.func_name if  self._prev_caller else self.caller.func_name
            if inst.owner_node is None and func_name not in inst.exports:
                inst.exports += (func_name,)
            elif inst.owner_node is not None and (func_name not in inst.owner_node.exports):
                inst.owner_node.exports += (func_name,)

        super(exportable,self).__get__(inst,type)

        return self
__main__.exportable = exportable
__main__.__all__.append('exportable')