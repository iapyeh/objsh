#! -*- coding:utf-8 -*-
#
# This is to implement a hierarchical state machine with event features.
#

import time,random,traceback,functools
import sys,os,time,re, json, datetime
PY3 = sys.version_info[0] == 3
import __main__
import importlib
try:
    import cPickle as pickle
except ImportError:
    import pickle

from zope.interface import Interface, Attribute, implementer
import zope.interface.interface as interface
from zope.interface              import implements
from twisted.internet            import task,reactor,defer
from twisted.python              import log,failure
from twisted.web.resource        import Resource, IResource
from twisted.web                 import static
from twisted.web.server          import NOT_DONE_YET
from twisted.logger              import LogLevel
from descriptor import exportable
from preference import Preference,PreferenceItem

from objshweb import ObjectiveShellSiteRoot, ObjshWebUser

class IStateEvent(Interface):
    name = Attribute('string: unique name of a class of event')
    src_nodename  = Attribute('string: node name of the event originated')
    ts = Attribute('int: timestamp in seconds since 1970')
    def cancel():
        """
        cancel the event, propagation would be stopped.
        """

class IStateValue(Interface):
    state = Attribute("""dict: return a dict""")
    value = Attribute("""any type: content""")
    def is_ready():
        """
        return a boolean to indicate if value is available
        
        """

class StateError(Exception):
    def __init__(self,name=None,message=None,data=None,retcode=1):
        assert message or name
        super(StateError,self).__init__(message or name)
        # descriptive name
        self.name = name
        # data is a dict to be used when doing i18n.
        # for example: data might be {'name':'some_node'}, then the value could be:
        # '%(name)s is not found' % {'name':'some_node'}
        # '%(name)s 不存在' % {'name':'some_node'}
        self.data = data or {}
        # customized retcode
        self.retcode = retcode
        self.message = message
    
    @property
    def serialized_data(self):
        return {
            #'type':'StateError',
            'name':self.name,
            'message':self.message,
            'data':self.data,
            'retcode':self.retcode
        }
'''
class exportable(Descriptor):
    def __get__(self,inst,type=None):
        """
        inst is the instance which owns the caller
        this is only been called when caller is referenced by <instance>.<method>
        """
        if self.inst is None:
            assert isinstance(inst,SimpleStateValue)
            self.inst = inst
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
'''
# decorator @resource
class resource:
    def __init__(self,public=False):
        self.public = public
    def __call__(self,func):
        """
        This is called in the following style of code block:
            @resource(public=True)
            def func(self,request)
                ...
        """
        func = func
        def f(self,request):
            if f.auth:
                u_id = 's:'+(request.getSession().uid.decode() if PY3 else request.getSession().uid)
                request.user = ObjshWebUser.users[u_id]
            else:
                request.user = None
            
            # follow site to set headers:allow_cross_origin
            if ObjectiveShellSiteRoot.singleton.allow_cross_origin:
                request.setHeader('Access-Control-Allow-Origin','*')

            return func(self,request)

        f.auth = not self.public
        return f


# decorator @resource
class resource_of_upload(resource):
    def __call__(self,func):
        """
        This is called in the following style of code block:
            @upload_resource(public=True)
            def func(self,request,args,content)
                ...
        """
        func = func
        def f(self,request):
            if f.auth:
                request.user = ObjshWebUser.users['s:'+(request.getSession().uid.decode() if PY3 else request.getSession().uid) ]
            else:
                request.user = None
                
            _args = request.args.get(b'args',[None])[0]
            try:
                args = [] if _args is None else json.loads(_args.decode() if PY3 else _args)
            except ValueError:
                args = []

            # follow site to set headers:allow_cross_origin
            if ObjectiveShellSiteRoot.singleton.allow_cross_origin:
                request.setHeader('Access-Control-Allow-Origin','*')

            try:
                len(request.args[b'file'])#test "file" keys
                result = func(self,request,args,request.args[b'file'][0])
            except KeyError:
                result = func(self,request,args,None)
            except:
                log.debug(traceback.format_exc())
                result = {'retcode':500, 'stderr':traceback.format_exc()}
            
            if isinstance(result,defer.Deferred):
                def okback(ret,req):
                    req.setResponseCode(200)
                    response = json.dumps(ret).encode() if PY3 else json.dumps(ret)
                    #log.debug(response,'<<<')
                    req.write(response)
                    req.finish()
                '''
                def errback(failure,req):
                    req.setResponseCode(200)
                    ret = {'retcode':500,'stderr':failure.getErrorMessage()}
                    response = json.dumps(ret).encode() if PY3 else json.dumps(ret)
                    log.debug(response,'<<err')
                    req.write(response)
                    req.finis()
                result.addCallbacks(okback,errback,callbackArgs=[request],errbackArgs=[request])
                '''
                # please call okback always and response something like:
                # {stderr:'error message', retcode:500} for reporting error
                result.addCallback(okback,request)
                return NOT_DONE_YET
            else:
                ret = json.dumps(result)
                return ret.encode() if PY3 else ret
        f.auth = not self.public
        return f
        
@implementer(IResource)
class StateNode(object):
    """
    A brick to build a state tree. Representing a generic node or leaf.
    """
    # default to allow all methods to be pluged
    plugable_methods = None
    # method names to be exported to GUI
    # exports will expanded to include exports from value-providers(SimpleStateValue instance)
    exports = ('state',)
    # event names this class might fired
    # events will expanded to include events from value-providers(SimpleStateValue instance)
    #_events = None # {'event_name':'description',...}
    # exceptions unique names this class might raise
    # exceptions will expanded to include exceptions from value-providers(SimpleStateValue instance)
    exceptions = None

    #implement IResource
    isLeaf = False 
    def __init__(self,parent,name,value=None,hidden=False):
        self._events = {
            'stateDidChange':'fired when value changed',
            'stateError':'fired when StateError was thrown'
        }
        self._exceptions = None
        self._name = name
        self._value = value
        self._ctime = time.time()
        self._mtime = self._ctime
        self._listeners = []
        self._node_children = {}
        self._attr_children = {}
        self.ready = None
        self._readycallbacks = []
        self._event_listeners = {}
        
        self._parent = parent
        #sssert isinstance(parent,StateNode) or isinstance(parent,StateTree), '%s is not StateNode' % parent._name
        
        if IStateValue.providedBy(value):
            value._set_owner(self)

        self._parent.register_node(self)

        # if True, this node would be invisible to GUI
        self._hidden = hidden

    def register_node(self,node):
        #
        # cascading up to top statetree, or any node which implements its own register_node
        # 
        if self._parent: return self._parent.register_node(node)
    def __repr__(self):
        return '(StateNode:'+self._name+')'
    
    @property
    def state(self):
        """
        If this node is a leaf, it returns the value-provider's .state 
        otherwise it recursively call .state of all child nodes.
        """
        if IStateValue.providedBy(self._value):
            return self._value.state
        
        elif len(self._node_children):
            _state = {}
            for name,child in self._node_children.items():
                _state[name] = child.state
            return _state
        
        elif callable(self._value):
            return self._value()
        
        else:
            return self._value
    
    @property
    def value(self):
        if IStateValue.providedBy(self._value):
            return self._value.value
        elif callable(self._value):
            return self._value()
        else:
            return self._value

    @value.setter
    def value(self,value):
        if IStateValue.providedBy(self._value):
            assert not IStateValue.providedBy(value)
            #
            # wrapped to _value (value provider)
            #
            self._value.value = value
        else:
            assert IStateValue.providedBy(value)
            self._value = value

    def call_when_ready(self,callback):
        if self.ready:
            # schedule to call in next loop
            # this is important to run in next loop
            # otherwise the caller in is_ready() will go crazy
            #
            return reactor.callLater(0,callback)
        self._readycallbacks.append(callback)
    
    def is_ready(self):
        if self.ready is not None:
            # alreay initialized
            return self.ready

        def trigger_readycallbacks():
            for callback in self._readycallbacks:
                self.call_when_ready(callback)
            del self._readycallbacks[:]
        
        def okback(args):
            list_type,boolean_type,tuple_type, int_type = type([]),type(True),type((1,)),type(1)
            if type(args) in (list_type, tuple_type):
                def resolve_list(a_list):
                    #
                    # resolve the final readines in nested lists 
                    # which is returned by a deferred list
                    #
                    list_ready = 1
                    for item in a_list:
                        if isinstance(item,failure.Failure):
                            list_ready = 0
                        elif type(item) in (list_type,tuple_type):
                            item_ready = resolve_list(item)
                            list_ready = list_ready * item_ready
                        else:
                            assert type(item) in (boolean_type,int_type)
                            list_ready = list_ready * (1 if item else 0)
                    return list_ready
                ready = resolve_list(args)
            else:
                assert type(args) in (boolean_type,int_type)
                ready = args
            #
            # If a deferred was returned by some class's is_ready()
            # it must be called when it is ready,
            # so, it is not expected to get False
            #
            assert ready in (1,True)
            self.ready = True
            trigger_readycallbacks()
            return ready

        if len(self._node_children):
            deferred_list = []
            ready = 1
            for child in self._node_children.values():
                ret = child.is_ready()
                if ret is None: ret = True 
                if isinstance(ret,defer.Deferred):
                    deferred_list.append(ret)
                else:
                    ready = ready * ret
            if len(deferred_list):
                deferred = defer.DeferredList(deferred_list)
                deferred.addCallback(okback)
                return deferred
            else:
                assert ready
                self.ready = True
                trigger_readycallbacks()
                return ready
        
        elif IStateValue.providedBy(self._value):
            ret = self._value.is_ready()
            if isinstance(ret,defer.Deferred):
                ret.addCallbacks(okback)
                return ret
            else:
                # if is_ready() returns None,
                # it is the same as returns True
                self.ready = True if ret is None else ret
                assert self.ready
                trigger_readycallbacks()
                return ret
        else:
            self.ready = True
            trigger_readycallbacks()
            return True
    
    def add_node(self,name,value=None,*args,**kw):
        """
        handly subroutine of self.add_node and self.add_attr
        """
        assert type(name) in (type(''),type(u' '))
        assert self._node_children.get(name) is None, 'alreay has %s (%s)' % (name,self._node_children.get(name).__class__)
        assert self._attr_children.get(name) is None
        if isinstance(value,StateNode):
            assert self._value is None, '"%s" has value provider <%s>, it cann\'t add "%s"' % (self._name,self._value.__class__.__name__,name)
            self._node_children[name] = value
            return value
        elif (value is None) or (IStateValue.providedBy(value)):
            assert self._value is None, '"%s" has value provider <%s>, it cann\'t add "%s"' % (self._name,self._value.__class__.__name__,name)
            child = StateNode(self,name,value,*args,**kw)
            self._node_children[name] = child
            return child
        else:
            return self.add_attr(name, value)
        
    def add_attr(self,name,value):
        assert type(name) in (type(''),type(u' '))
        assert self._attr_children.get(name) is None
        assert self._node_children.get(name) is None
        self._attr_children[name] = value
        return value

    def __getattr__(self,name):
        try:
            return super(StateNode,self).__getattr__(name)
        except AttributeError:
            try:
                return self._attr_children[name]
            except KeyError:
                if len(self._node_children):
                    try:
                        return self._node_children[name]
                    except KeyError:
                        raise AttributeError(name+' is not child of '+self._name)
                elif IStateValue.providedBy(self._value):
                    return getattr(self._value,name)
                raise AttributeError(name+' is not attribute of '+self._name)


    '''
    def old__getattr__(self,name):
        try:
            return self._attr_children[name]
        except KeyError:
            if len(self._node_children):
                child = self._node_children.get(name)
                if child is not None: return child
            elif IStateValue.providedBy(self._value):
                return getattr(self._value,name)
            raise AttributeError(name+' not found in '+self._name)
    '''
    
    def __getitem__(self,path):
        if type(path)==type([]):
            paths = path
        else:
            paths = list(filter(None,path.split('.')))
        
        if len(paths)==0:
            raise AttributeError('path is empty string')
 
        node = self
        for path in paths:
            node = getattr(node,path)
        return node

    def dump(self,rows=None,indent=None,with_value=False):
        if rows is None: rows = []
        if indent is None: indent = ''
        rows.append(indent+self._name)
        if self._value is not None: rows.append(' <%s>' % self._value.__class__.__name__)
        if len(self._attr_children):
            #writer('\n    '+indent+'--attributes--\n')
            rows.append('\n')
            keys = self._attr_children.keys()
            #keys.sort()
            for key in sorted(keys):
                rows.append(indent+key+':'+str(self._attr_children[key]).replace('\n','\\n')+'\n')
        if len(self._node_children):
            #writer('\n    '+indent+'--children----\n')
            rows.append('\n')
            names = self._node_children.keys()
            #names.sort()
            for name in sorted(names):
                child = self._node_children[name]
                child.dump(rows,indent+'    ')
        elif with_value and IStateValue.providedBy(self._value):
            rows.append(':'+str(self._value.state)+'\n')
        elif with_value and self._value is not None:
            rows.append(':'+str(self._value)+'\n')
        else:
            rows.append('\n')
        return ''.join(rows)
    
    def plug_method(self,export=False):
        assert self._value is not None and IStateValue.providedBy(self._value)
        def gen(func):
            method_name = func.__name__
            if (self._value.plugable_methods is None) or (method_name in self._value.plugable_methods):
                #log.msg('%s plugs=> %s' % (method_name,self._value.__class__.__name__))
                setattr(self._value,method_name,func.__get__(self._value))
                if export:
                    self.exports +=tuple([method_name])
                    self._value.exports += tuple([method_name])
            else:
                raise RuntimeError('%s is not allowed to plugin to %s(%s)' % (method_name,self._name,self._value.__class__.__name__))
        return gen

    def plug_node(self,node_name,*args,**kw):
        """
        a decorator style (@plug_node) for add_node
        """
        def gen(value_factory):
            node_value = value_factory(self)
            assert IStateValue.providedBy(node_value)
            self.add_node(node_name,node_value,*args,**kw)
        return gen
    #
    # Event related implementation starts
    #
    def fire_event(self,event_name,payload=None):
        """
        Fire an event by name. event will bubble up.
        The event_name should be registered in class attribute "events". (a tuple of string)
        But, if event_name provides IStateEvent, the name checking is ignored.

        Arguments:
            @param event_name: (string or IStateEvent)
            @param payload: (any json-able objects)
        """
        if IStateEvent.providedBy(event_name):
            event = event_name
            event_name = event.name
            # ignore silently a cancelled event
            if event.cancelled: return
        else:
            assert event_name in self._events,'Failed to fire '+event_name+', it is not in envet_names of '+self._name
            event = StateEvent(event_name,self,payload)
        
        if len(self._event_listeners):
            #
            # listener added with specified event name got called in advance.
            #
            listeners = self._event_listeners.get(event_name,[]) + self._event_listeners.get('_ALL_',[])
            if len(listeners):
                def fire(event,listener,current_target):
                    
                    # ignore silently a cancelled event
                    if event.cancelled: return
                    
                    event.current_target = current_target
                    try:
                        listener(event)
                    except:
                        log.msg(traceback.format_exc())

                for listener in listeners:
                    reactor.callLater(0,lambda e=event,x=listener,n=self:fire(e,x,n))
                
                # bubble up to root (not to statetree)
                if self._parent and isinstance(self._parent,StateNode):
                    reactor.callLater(0,self._parent.fire_event,event)

                return

        # bubble up to root (not to statetree)
        if self._parent and isinstance(self._parent,StateNode):
            reactor.callLater(0,self._parent.fire_event,event)

    #alias
    emit = fire_event

    def add_event_listener(self,listener, event_name=None):
        """
            Arguments:
                listner: (callable); callable will be called with callable(StateEvent_instance)
                event_name: (string, optional), if missing, listen to all

            listener added with specified event name got called in advance.
        """
        assert callable(listener)
        if event_name is None:
            event_name = '_ALL_'
        else:
            # suppose event of event_name might be fired by child nodes
            #assert event_name in self.events,'Failed to listen '+event_name+', it is not fired by '+(self.__class__.__name__)+', events are '+','.join(self.events)
            pass
        try:
            self._event_listeners[event_name].append(listener)
        except KeyError:
            self._event_listeners[event_name] = [listener]
    
    def remove_event_listener(self,listener,event_name=None):
        if event_name is None:
            event_name = '_ALL_'
        else:
            assert event_name in self._events,'Failed to remove '+event_name+', it is not fired by '+self.__class__.__name__

        try:
            self._event_listeners[event_name].remove(listener)
            log.msg('event listener %s removed' % listener)
        except (KeyError, ValueError) as e:
            pass

    # Event related implementation end
    
    #
    # implementation IResource starts
    #
    def getChildWithDefault(self,name,request):
        if self._value is not None:
            return self._value
        else:
            try:
                return self._node_children[name]
            except KeyError:
                # return a self to do dummy render 
                # this would avoid an error page was dumped to user
                return self
    def putChild(self,name,child):
        raise NotImplementedError('donot put child to StateNode')
    def render(self,request):
        #dummy render if request a node 
        return self._name
    # implementation IResource end

@implementer(IStateEvent)
class StateEvent(object):
    #implements(IStateEvent)
    def __init__(self,name,source_node,payload=None,current_source_node=None):
        """
        @param name: name of this event
        @type name: string
        
        @param target_node: StateNode which is the origin (first) owners this event
        @param current_source_node: StateNode which emits this event
        """
        assert isinstance(source_node,StateNode)
        assert current_source_node is None or isinstance(current_source_node,StateNode)
        self.name = name
        self.source = source_node
        self.current_source = current_source_node or source_node
        self.payload = payload
        self.ts = int(time.time())
        self.cancelled = False
    
    def cancel(self):
        self.cancelled = True
    
    def __repr__(self):
        return '{Event:%s, source:%s by:%s}' % (self.name,self.source._name,self.current_source._name)

    @property
    def serialized_data(self):
        return {'name':self.name,'payload':self.payload,'ts':self.ts,'source':self.source._name}

@implementer(IResource,IStateValue)
class SimpleStateValue(object):
    """
    Provide "value" to a node.
    """
    #implements(IStateValue)
    exports = ('state','unittest',)
    exceptions = None
    # default to allow all methods to be pluggable
    plugable_methods = None
    
    # implment IResource
    isLeaf = True

    def __init__(self,value=None):
        """
        Arguments:
            value: any type or a callable
        """
        self._ctime = time.time()
        self._mtime = self._ctime
        self._value = value
        self.owner_node = None
        self.name = None #will be assigned to owner_node._name
        self._preference = None
        self._events = None
        self._exceptions = None
        self.register_exception('unknow.error','an unexpected error')

    def _set_owner(self,node):
        assert isinstance(node,StateNode)
        assert len(node._node_children)==0, 'node "%s" is not a leaf node for %s' % (node._name,self.name)


        self.owner_node = node
        self.name = node._name

        # kick off __get__ of @exportable,@cancellable if there is any
        # this will enforce func_name to be added into "exports"
        def kick_exports(this):
            exports = []
            for k in dir(this):
                attr = getattr(this,k) 

                # pick up method which claims exportable by style:
                # def X(self): pass
                # X.exportable  True
                if callable(attr) and hasattr(attr,'__dict__') and \
                   attr.__dict__.get('exportable') and \
                   not (attr.func_name in this.exports):
                   exports.append(attr.func_name) 
            if len(exports):
                this.exports += tuple(exports)
            this.owner_node.exports += this.exports
        reactor.callLater(0,lambda x=self:kick_exports(x))
        #kick_exports(self)

        # this is a good chance to retrieve node's preference
        # because every node instance should have a unique name
        self._preference = __main__.statetree.preference.get(node._name)
        # merge events
        if self._events is not None:
            #self.owner_node.events = self.events
            if self.owner_node._events is not None:
                self.owner_node._events.update(self._events)
            else:
                self.owner_node._events = self._events.copy()
            del self._events

        if hasattr(self,'events') and self.events is not None:
            log.msg('*'*10,'Warning! self.events is deprecated, please use self.register_event(name,description)')
            #self.owner_node.events = self.events
            if self.owner_node._events is not None:
                self.owner_node._events.update(self.events)
            else:
                self.owner_node._events = self.events.copy()
            del self.events


        # merge exceptions
        if hasattr(self,'exceptions') and self.exceptions is not None:
            log.msg('*'*10,'Warning! self.exceptions is deprecated, please use self.register_exception(name,description)')
            if self.owner_node._exceptions is not None:
                self.owner_node._exceptions.update(self.exceptions)
            else:
                self.owner_node._exceptions = self.exceptions.copy()
            #del self.exceptions
        
        if self._exceptions is not None:
            if self.owner_node._exceptions is not None:
                self.owner_node._exceptions.update(self._exceptions)
            else:
                self.owner_node._exceptions = self._exceptions.copy()
            del self._exceptions

    def register_event(self,name,description=None):
        """
        @param name: string, or a dictionary
        """
        if self._events is None: self._events = {}
        if isinstance(name,dict):
            self._events.update(name)
        else:
            self._events[name] = description or ''
    
    def register_exception(self,name,message=None,retcode=1):
        """
        @param name: string, or a dictionary, 
            if it is a dict, it should of format:
            {'$name':{
                'message':$message,
                'retcode':$retcode
                }
            }
        """
        if self._exceptions is None: self._exceptions = {}
        if isinstance(name,dict):
            self._exceptions.update(name)
        else:
            self._exceptions[name] = {
                'message': message or '',
                'retcode':retcode
            }

    @property
    def preference(self):
        return self._preference
    
    @preference.setter
    def preference(self,pref):
        if pref is None:
            self._preference = None
        else:
            if isinstance(pref,PreferenceItem):
                self._preference = pref
            else:
                # pref should be primative type, not instance of object
                assert (self.owner_node is not None) and not hasattr(pref,'__dict__')
                self._preference = __main__.statetree.preference.get(self.owner_node._name)
                self._preference.value = pref
    @property
    def state(self):
        """ an json-able object represents its current state """
        return self.value

    @property
    def value(self):
        return self._value() if callable(self._value) else self._value
    
    @value.setter
    def value(self,value):
        self._value = value
        self.fire_event('stateDidChange')
        self.touch()

    def touch(self):
        self._mtime = time.time()
    
    def is_ready(self):
        return True
    
    def unittest(self):
        """
        A routine for auto-testing.

        Returns:
            discard.
            
        Raises:
            Any kind of Exception, if something goes wrong.
        """
        pass
    
    def repeat(self,attr_or_method,callback,interval=1.0,callback_args=None):
        """
        repeatly calls the method_name of this instance.
        
        Arguments:
            attr_or_method:(string) callable method or attribute.
            callback:(callable) repeatly to call with value or result of given method_name.
            interval:(float) repeat once per interval
            callback_args:(list) extra arguments follows the value for callback
        
        Note:
            If the callback returns a True value, the repeating would be stopped.
        """
        assert callable(callback)
        loop = None
        if callable(attr_or_method):
            def callable_job(func):
                try:
                    result = attr_or_method()
                    stop = callback(result) if callback_args is None else callback(result,*callback_args)
                    if stop: loop.stop()
                except:
                    traceback.print_exc()
                    loop.stop()
            loop = task.LoopingCall(lambda x=attr_or_method:callable_job(x))
        else:
            def job():
                try:
                    result = getattr(self,attr_or_method)
                    stop = callback(result) if callback_args is None else callback(result,*callback_args)
                    if stop: loop.stop()
                except:
                    traceback.print_exc()
                    loop.stop()
            loop = task.LoopingCall(job)
        deferred = loop.start(interval)
            
    def __getattr__(self,name):
        try:
            # shoulde not use the line below, this would confused the AttributeError 
            # by getting value from @property-style attribute
            #return super(SimpleStateValue,self).__getattr__(name)
            return object.__getattribute__(self,name)
        except AttributeError:
            if not IStateValue.providedBy(self._value):
                raise
            else:
                try:
                    return self._value[name]
                except KeyError as e2:
                    raise AttributeError('%s does not have attribute %s (%s)' % (self,name,e2.message))
    
    def plugin(self,method_name):
        #
        # decorator factory to hook up plugins
        #
        def gen(func):
            if self.plugable_methods is None or method_name in self.plugable_methods:
                log.msg('(%s plugs>> %s)' % (method_name,self.__class__.__name__))
                setattr(self,method_name,func.__get__(self))
            else:
                raise RuntimeError('%s is not allowed to plugin to %s(%s)' % (method_name,self._name,self.__class__))
        return gen
    #
    # Event related
    #
    def fire_event(self,event_name,payload=None):
        return self.owner_node.fire_event(event_name,payload)
    def add_event_listener(self,listener,event_name=None):
        return self.owner_node.add_event_listener(listener,event_name)
    def remove_event_listener(self,listener,event_name=None):
        return self.owner_node.remove_event_listener(listener,event_name)
     #alias
    emit = fire_event
   
    def callInThread(self,callable,*args,**kw):
        def run(callable,args,kw):
            try:
                callable(*args,**kw)
            except Exception as e:
                log.msg('Error:%s' % e)
                log.msg('callInTrhead Error:%s' % traceback.format_exc())
                reactor.callFromThread(self.throw,'unknow.error',{'message':e.message})
                return
        reactor.callInThread(run,callable,args,kw)

    # Raising Error (will be converted to RunnerError in runner_state.py)
    def throw(self,unique_name,data=None):
        if isinstance(unique_name,StateError):
            # unregisterd exception
            stateError = unique_name
        else:
            # payload is error's data
            registered_data = self.owner_node._exceptions[unique_name]
            
            stateError = StateError('%s.%s' % (self.owner_node._name,unique_name),registered_data['message'],data,retcode=registered_data['retcode'])
        # emit an internal stateError event
        reactor.callLater(0,self.emit,'stateError',stateError.serialized_data)
        raise stateError

    #
    # implementation IResource starts
    #
    def getChildWithDefault(self,name,request):
        raise NotImplementedError('donot get child from SimpleNodeValue')
    
    def putChild(self,name,child):
        raise NotImplementedError('donot put child to SimpleNodeValue')
    
    def render(self,request):
        # allow extra path component, for example
        # "/studio/root/studio/project/98342332" to be handled by "project" 
        # not by "98342332"
        my_path = self.owner_node._name
        request_path = request.path.decode() if PY3 else request.path
        paths = request_path[request_path.rfind(my_path):].split('/')
        prop_name = paths[1]

        try:
            prop = getattr(self,prop_name)
            prop.auth
        except AttributeError:
            request.setResponseCode(404)
            return b'not found'
        
        if prop.auth:
            user = __main__.statetree.get_web_user(request)
            if not (user and user.authenticated):
                request.setResponseCode(403)
                return b'forbidden'
        try:
            ret = prop(request)
        except:
            request.setResponseCode(500)
            err = traceback.format_exc()
            __main__.statetree.log.error(err)
            return err.encode()
        else:
            try:
                if isinstance(ret,defer.Deferred):
                    def done(content,req):
                        req.setResponseCode(200)
                        req.write(content)
                        req.finish()
                    def err(failure,req):
                        req.setResponseCode(500)
                        req.write(failure.getErrorMessage().encode())
                        req.finish()
                    ret.addCallbacks(done,err,callbackArgs=[request],errbackArgs=[request])
                    return NOT_DONE_YET
                return ret
            except:
                request.setResponseCode(500)
                return traceback.format_exc().encode()

    # implementation IResource end

class PesudoNode(object):
    """
    When a node was referenced somewhere before it is really created.
    An instance of PesudoNode is created to be the placeholder.
    """
    def __init__(self,node_registry,name):
        self._name = name
        self.node_registry = node_registry
        self._attr_children = {}
        self._node_children = {}
        self._event_listeners = {}
        self._readycallbacks = []
        self.ready = False
        # the real node after assigened when it is registerd
        #self._realNode = None

    def is_ready(self):
        raise NotImplementedError('%s is still pesudo node yet' % self._name)
        
    def register_node(self,child):
        self.node_registry.regiter(child)
    
    def add_attr(self,name,value):
        assert self._attr_children.get(name) is None
        assert self._node_children.get(name) is None
        self._attr_children[name] = value
        return value
    
    def add_node(self,name,value=None,*args,**kw):
        assert self._attr_children.get(name) is None
        assert self._node_children.get(name) is None
        if (value is None) or (IStateValue.providedBy(value)):
            child = StateNode(self,name,value,*args,**kw)
            self._node_children[name] = child
            return child
        else:
            return self.add_attr(name, value)
    
    def plug_node(self,node_name,*args,**kw):
        """
        a decorator style (@plug_node) for add_node
        """
        def gen(value_factory):
            node_value = value_factory(self)
            assert IStateValue.providedBy(node_value)
            self.add_node(node_name,node_value,*args,**kw)
        return gen

    def add_event_listener(self,listener,event_name=None):
        assert callable(listener)
        
        if event_name is None:
            event_name = '_ALL_'
        else:
            pass
        
        try:
            self._event_listeners[event_name].append(listener)
        except KeyError:
            self._event_listeners[event_name] = [listener]

    def call_when_ready(self,callback):
        if self.ready:
            # schedule to call in next loop
            # this is important to run in next loop
            # otherwise the caller in is_ready() will go crazy
            #
            return reactor.callLater(0,callback)
        self._readycallbacks.append(callback)
    """
    def __getattr__(self,name):
        if self._realNode is None:
            return self.__dict__[name]
        return getattr(self._realNode, name)
    """    
        
class NodeRegistry(object):
    """
        A registry database to map name to node.
    """
    def __init__(self,statetree):
        self.statetree = statetree
        self.db = {}
    
    def regiter(self,node):
        """
            node._name must be unique
        """
        assert isinstance(node,StateNode)
        name = node._name

        try:
            pesudo = self.db[name]

            if isinstance(pesudo,PesudoNode):
                # take over attribute children
                for name,child_node in pesudo._node_children.items():
                    assert isinstance(child_node,StateNode)
                    node.add_node(name,child_node)
                    child_node._parent = node

                # take over child nodes
                for name,value in pesudo._attr_children.items():
                    node.add_attr(name,value)
                
                # take over listeners
                for name,listeners in pesudo._event_listeners.items():
                    for listener in listeners:
                        assert callable(listener)
                        node.add_event_listener(name,listener)
                
                # take over _readycallbacks
                node._readycallbacks.extend(pesudo._readycallbacks)

                #log.msg('replace pesudo node ',name, 'with <',obj.__class__.__name__,'>')
                
                #pesudo._realNode = self
                del pesudo
            else:
                raise ValueError(name+' already registered by '+ str(pesudo))

        except KeyError:
            pass

        self.db[name] = node
        
    def __getattr__(self,name):
        try:
            return self.__dict__[name]
        except KeyError:
            obj = self.db.get(name)
            if obj is not None: return obj
            try:
                return super(NodeRegistry,self).__getattr__(name)
            except AttributeError:
                obj = PesudoNode(self,name)
                self.db[name] = obj
                return obj
    
    def __getitem__(self,path):
        if type(path)==type([]):
            paths = path
        else:
            paths = filter(None,path.split('.'))
        
        if len(paths)==0:
            raise AttributeError('path is empty string')
        
        node = self
        for path in paths:
            node = getattr(node,path)

        return node
    
    def get(self,name):
        """
        Get the node of name and it should not be PesudoNode
        """
        try:
            node = self.db[name]
        except KeyError:
            node = None
        return node if (node and not isinstance(node,PesudoNode)) else None

class Gluer(object):
    pass

class StateTreeLogger(object):
    def debug(self,*args):
        #log.msg(*args,log_level=LogLevel.debug)
        log.debug(*args)
    def info(self,*args):
        #log.msg(*args,log_level=LogLevel.info)
        log.info(*args)
    def warn(self,*args):
        #log.msg(*args,log_level=LogLevel.warn)
        log.warn(*args)
    warning = warn
    def error(self,*args):
        #log.msg(*args,log_level=LogLevel.error)
        log.error(*args)
    def critical(self,*args):
        #log.msg(*args,log_level=LogLevel.critical)
        log.critical(*args)
    def __call__(self,*args):
        return log.info(*args)

class StateTree(object):
    def __init__(self,config):
        """
        Argumenst:
            config: (dict) config.statetree (loaded by config.py)
            
        """
        #  used to register runner command in runner_state.py
        self.runner_name = config['runner_name']
        
        # Expose this instance to __main__
        global_name = config.get('global_name','statetree')
        try:
            getattr(__main__,global_name)
            raise RuntimeError('Only one instance of StateTree is allowed')
        except AttributeError:
            __main__.__all__.append(global_name)
            setattr(__main__,global_name,self)
        # Read default configurations from config.statetree
        self._plugin_folders = [os.path.join(config['folder']['pwd'],'sysstate')]
        for folder in config['plugin_folders']:
            folder = folder.strip()
            if not folder: continue
            abs_folder = os.path.abspath(os.path.join(config['folder']['etc'],folder))
            assert os.path.exists(abs_folder), 'plugin folder not found:'+abs_folder
            self._plugin_folders.append(abs_folder)
        
        #
        # Preference, auto save
        #
        config_preference = config['preference']
        config_preference['folder'] = config['folder']
        self.preference = Preference('preference',{},config_preference)
        self.preference.save_on_touch = True
        
        #
        # create preference for playground
        #
        playground_preference = self.preference.playground
        
        links = []
        for item in config['sidebar']['menuitems'][0]['items']:
            links.append((item['title'],item['url']))
        #
        # Preset the preferece.playground
        #
        playground_preference.documents = {
            'links': links
        }
        #
        # log 
        # 
        self.log = StateTreeLogger()
        #
        # nodes
        #
        self.nodes = NodeRegistry(self)

        # build root
        self.root = StateNode(self,'root')
        
        '''
        # test event listener
        def event_to_log(evt):
            log.msg('Event:%s' % evt)
        
        self.root.add_event_listener(event_to_log)
        '''
        
        # schedule to load plugins
        reactor.callLater(0,self.scan)
        
        # schedule to check if all node are ready to work
        self.ready = False
        self._readycallbacks = []
        reactor.callLater(0,self.polling_readiness)
        
        # add to web requests
        route = (config.get('route') or '').lstrip('/')
        if route:
            # should not have "/" in middle
            assert route.find('/') == -1
            self.route_name = route #send to sdk
            def add_route(site_root):
                # need this to do authentication for routed resouce
                self.get_web_user = lambda request:site_root.login_resource.get_user(request)
                try:
                    site_root.putChild(route.encode('utf-8'),ResourceOfStateTree(self))
                except:
                    traceback.print_exc()
                    reactor.stop()
            ObjectiveShellSiteRoot.call_when_singleton_created(add_route)
        else:
            self.route_name = 'statetree-hasnot-route'
        # build initial nodes
        self.build()

    def build(self):
        raise NotImplementedError('%s should override bulid()' % self.__class__.__name__)

    def register_node(self,node):
        assert isinstance(node,StateNode)
        self.nodes.regiter(node)

    def polling_readiness(self):
        log.msg('polling state tree readiness')
        ready = 1
        def call_when_ready():
            for callback in self._readycallbacks:
                try:
                    self.call_when_ready(callback)
                except:
                    #traceback.print_exc()
                    log.err('error on polling readiness')
                    log.msg('callback has error',callback)
            del self._readycallbacks[:]
        try:
            ret = self.root.is_ready()
        except:
            log.msg('polling error:%s' % traceback.format_exc())
            reactor.callLater(0,reactor.stop)
            return
        else:
            list_type,boolean_type,tuple_type,int_type = type([]),type(True),type((1,)),type(1)
            if isinstance(ret,defer.Deferred):
                def okback(args):
                    #
                    # Nodes' is_ready() is expected to return True or a deferred.
                    # If it returns deferred, the deferred's callback is expected
                    # to be called with True.
                    #
                    ready = args
                    assert ready in (1,True)
                    self.ready = True
                    log.msg('state tree ready')
                    call_when_ready()
                    #else:
                    #    reactor.callLater(0.5,self.polling_readiness)
                def errback(failure):
                    log.err()
                ret.addCallbacks(okback,errback)
            elif ret==1:
                self.ready = 1
                call_when_ready()
                log.msg('state tree ready')
            else:
                reactor.callLater(0.5,self.polling_readiness)
    
    def is_ready(self):
        return self.ready

    def call_when_ready(self,callback):
        assert callable(callback)
        if self.ready: return reactor.callLater(0,callback)
        self._readycallbacks.append(callback)

    def dump(self):
        return self.root.dump()

    def scan(self):
        for path in self._plugin_folders:
            try:
                self.scan_folder(path)
            except:
                log.msg('scan error:%s' % traceback.format_exc())
                reactor.callLater(0,reactor.stop)

    def scan_folder(self,plugin_folder):
        base_dir = os.path.abspath(os.path.dirname(__file__))

        #(obsoleted implementaion, seems useless, temporary disable)
        #loaded_module_names = sys.modules.keys()
        #module_to_reload = []

        # pat to recognize a runner script
        if PY3:
            has_plugin_pat = re.compile('^\s*from\s+\.__init__\s+import\s+')
        else:
            has_plugin_pat = re.compile('^\s*from\s+\.?__init__\s+import\s+')

        #plugin_folder_root = os.path.normpath(os.path.join(plugin_folder,root))
        assert plugin_folder.startswith('/')
        syspath_to_remote = False
        relpath = os.path.relpath(plugin_folder,base_dir)
        
        if relpath.startswith('..'):
            base_dir = os.path.dirname(plugin_folder)

        if not base_dir in sys.path:
            syspath_to_remote = base_dir
            sys.path.insert(0,base_dir)
        log.msg('scanning state plugin in %s' % relpath)
        for root,folders,files in os.walk(plugin_folder):
            foldername = os.path.basename(root)
            if foldername.startswith('_') or foldername.startswith('.'): continue           
            relpath_root = os.path.relpath(root,base_dir)
            package_name = '' if relpath_root == '.' else relpath_root.replace('/','.')
            for file in files:
                if file.startswith('.') or file.startswith('_'): continue
                elif file[-3:]=='.py':
                    # avoid to load twice if execution is from the runner subfolder for unit testing
                    file_path = os.path.join(root,file)
                    # only load file which wants to register runner
                    is_plugin_script = False
                    fd = open(file_path,'r')
                    for _ in range(20):
                        line = fd.readline()
                        if has_plugin_pat.search(line) is not None:
                            #if has_old_plugin_pat.search(line) is not None:
                            #    log.msg('in %s "from __init__ import *" should be "from .__init__ import *"' % file)
                            #    break
                            is_plugin_script = True
                            break
                    fd.close()
                    if not is_plugin_script:
                        log.msg('skip %s' % file)
                        continue
                    
                    name = os.path.splitext(file)[0]
                    module_name = package_name+('' if package_name == '' else '.')+name
                    #if module_name in loaded_module_names:
                    #    log.msg('reload plugin %s' % (module_name))
                    #    module_to_reload.append(module_name)                    
                    #else:
                    log.msg('found plugin %s' % (module_name,))
                    try:
                        importlib.import_module(module_name)
                    except Exception as e:
                        log.err('load failure, because %s' % e)
                        traceback.print_exc()
                        reactor.stop()

        #if len(module_to_reload):
        #    reloader.enable()
        #    for module_name in module_to_reload:        
        #        reloader.reload(sys.modules[module_name])
        #    reloader.disable()
        
        #cleanup 
        if syspath_to_remote:
            sys.path.remove(syspath_to_remote)
    
    def __getitem__(self,path):
        return self.nodes[path]
        '''
        if type(path)==type([]):
            paths = path
        else:
            paths = path.split('.')
        node = self
        for path in paths:
            node = getattr(node,path)
        return node
        '''
    
    def get_node(self,name):
        return self.nodes.get(name)

    def fire_event(self,event_name,payload=None):
        """
        This should be called from outside of this statetree to inject event into the event-bus
        For example, when user loging by __main__.statetree.fire_event
        """
        evt = StateEvent(event_name,self.root,payload)
        self.root.emit(evt)
    emit = fire_event

# Expose state node and method by URL
# this is different from /run/, 
# purpose of this is for handling upload and download 
class ResourceOfStateTree(Resource):
    def __init__(self,statetree):
        Resource.__init__(self)
        self.statetree = statetree

    def getChild(self,path,request):
        # root in the url is optional
        if PY3:
            path = path.decode()
        
        if path=='root': return self
        try:
            return self.statetree.root[path]
        except AttributeError:
            # return a dummy resource to avoid page of error dumps
            class Dummy(object):
                isLeaf = True
                def render(self,request):
                    request.setResponseCode(404)
                    return (path + ' not found').encode()
            return Dummy()
            

def get_options():
    #
    # Lookup plugins folder from command arguments
    # Used for unit testing or developing
    #
    
    # temporary disabled in python3
    log.startLogging(sys.stdout.buffer)
    
    default_plugins_folder = os.path.abspath(os.path.join(os.path.dirname(__file__),'state','plugins'))
    assert os.path.isdir(default_plugins_folder)
    if '--plugins' in sys.argv:
        plugins_folder = os.path.abspath(os.path.normpath(sys.argv[sys.argv.index('--plugins')+1]))
        assert os.path.isdir(plugins_folder)
        options = {'plugin':{'folder':[default_plugins_folder,plugins_folder]}}
    else:
        options = {'plugin':{'folder':[default_plugins_folder]}}
    return options

__main__.SimpleStateValue = SimpleStateValue

__all__ = ['IStateValue','SimpleStateValue','StateNode',
           'StateTree','StateError','__main__',
           'resource','resource_of_upload']

if __name__ == '__main__':

    import pprint,sys
    pp = pprint.PrettyPrinter()
    from twisted.python import log
    log.startLogging(sys.stdout.buffer)
    def unittest():
        class MyStateTree(StateTree):
            def build(self):
                pass
        options = {}
        base_folder = os.path.abspath(os.path.dirname(__file__))
        options['state_ini_path'] = os.path.join(base_folder,'state','state_unittest.ini')
        options['preference_ini_path'] = os.path.join(base_folder,'state','preference_unittest.ini')
        my_statetree = MyStateTree(options)
        
    reactor.callWhenRunning(unittest)
    reactor.run()