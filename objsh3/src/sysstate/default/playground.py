#! -*- coding:utf-8 -*-
# magic line to be auto imported by objstate.py
from .__init__ import *
import sys,os
import inspect
import traceback
import __main__
from twisted.python import log
from twisted.internet import reactor

class Playground(SimpleStateValue):
    """
    Provides inspection feature to web GUI.
    """
    def __init__(self):
        #initial value is False
        super(Playground,self).__init__()

        # got content in self.get_hierarchy() 
        self.event_exception_list = None

    def is_ready(self):
        if not self.preference.gui_settings:
            self.preference.gui_settings = {
                'saved_command_lines':[],
                'relative_path':False
            }
            self.preference.touch()
        return True
    
    @exportable
    def get_hierarchy(self):
        try:
            return self._get_hierarchy()
        except:
            log.msg(traceback.format_exc())
            return {
                'name':statetree.root._name,
                'doc':'',
                'exports':{},
                'exceptions':[],
                'events':[],
                'file':None,
                'classname': 'StateNode'
            }

    def _get_hierarchy(self): 
        if self.event_exception_list is None:
            self.event_exception_list = {}
    
        def get_exports(obj):
            if isinstance(obj,SimpleStateValue):
                exports = obj.owner_node.exports
            else:
                exports = obj.exports

            exports_data = {}
            for method_name in exports:
                if method_name in ('state',):
                    # these two is inherited, their signature is already known
                    exports_data[method_name] = {
                        'doc':inspect.getdoc(getattr(obj,method_name)),
                        'argspec':None, 
                    }
                    continue
                exports_data[method_name] = None
                trial_count = 0
                method = getattr(obj,method_name)
                while trial_count < 3:
                    if inspect.isfunction(method) or inspect.ismethod(method):
                        try:
                            exports_data[method_name] = {
                                'doc':inspect.getdoc(method),
                                'argspec': inspect.getargspec(method)
                            }
                        except AssertionError:
                            # if an @exported function has no docstring,
                            # it will throw an AssertionError by descripter.py(__get__)
                            # (this is a work-around implementation)
                            exports_data[method_name] = {
                                'doc':'(no docstring)',
                                'argspec': inspect.getargspec(method)
                            }
                        break
                    elif isinstance(method,property):
                        # ignore @property, like this. Because @property's signature is known
                        break
                    elif inspect.ismethoddescriptor(method):
                        break
                    elif inspect.isgetsetdescriptor(method):
                        break
                    elif hasattr(method,'fget'):
                        # @exportable, @cancellable
                        method = method.fget
                        trial_count += 1
                    elif method is None:
                        break
                    else:
                        # ignore @property, like this. Because @property's signature is known
                        #@property
                        #@exportable
                        #def property1(self):
                        #    return '87'
                        break
                if exports_data[method_name] is None and method is not None:
                    exports_data[method_name] = {
                        'doc':inspect.getdoc(method),
                        'argspec':None, 
                    }
            return exports_data
        def get_resouces(obj):
            data = {}
            for k,v in obj.__class__.__dict__.items():
                if callable(v) and hasattr(v,'auth'):
                    data[k] = {
                        'doc': inspect.getdoc(v)
                    }
            return data
        def get_events(obj):
            if isinstance(obj,StateNode):
                #
                # Because IStateValue append its events to owner node,
                # So we take the events from StateNode instead of IStateValue instance.
                #
                return obj._events
            elif IStateValue.providedBy(obj):
                return obj._events
        
        def get_exceptions(obj):
            if isinstance(obj,StateNode):
                #
                # Because IStateValue append its events to owner node,
                # So we take the events from StateNode instead of IStateValue instance.
                #
                return obj._exceptions
            elif IStateValue.providedBy(obj):
                return obj._exceptions
        
        def get_classname(obj):
            if isinstance(obj,StateNode):
                if IStateValue.providedBy(obj._value):
                    return obj._value.__class__.__name__
                else:
                    return obj.__class__.__name__
            else:
                return obj.__class__.__name__    
        
        def gen(root):

            assert isinstance(root,StateNode),'expect StateNode, got %s' % root.__class__
            
            ret = {
                'name':root._name,
                'doc':'',
                'exports':{},
                'resources':{},
                'exceptions':[],
                'events':[],
                'file':None,
                'classname': get_classname(root)
            }

            if IStateValue.providedBy(root._value):
                #log.msg('inspect.getmodule',root._value.__class__.__name__,inspect.getmodule(root._value))
                ret['file'] = os.path.relpath(__main__.config.folder['opt'],inspect.getmodule(root._value).__file__)
            else:
                ret['file'] = os.path.relpath(__main__.config.folder['opt'],inspect.getmodule(root).__file__)

           
            if len(root._node_children):
                ret['children'] = []
                # don't take StateNode's doc
                ret['doc'] = ''
                for node in root._node_children.values():
                    if node._hidden: continue
                    ret['children'].append(gen(node))
            
            elif IStateValue.providedBy(root._value):
                if root._value.__doc__:
                    ret['doc'] = inspect.getdoc(root._value)
                
                ret['exports'] = get_exports(root._value)
                ret['resources'] = get_resouces(root._value)               

            else:
                pass
            # append events at the end of document
            ret['events']  = get_events(root) or  {}
            ret['exceptions'] = get_exceptions(root) or {}

            # prepare data for leafnode.html
            self.event_exception_list[ret['name']] = {
                'doc':ret['doc'],
                'classname':ret['classname'],
                'events':{},
                'exceptions':{},
                'exports':{},
                'resources':{}
            }
            for key,value in ret['events'].items():
                self.event_exception_list[ret['name']]['events'][key] = value
            for key,value in ret['exceptions'].items():
                self.event_exception_list[ret['name']]['exceptions'][key] = value
            self.event_exception_list[ret['name']]['exports'] = ret['exports']
            if ret.get('resources'):
                self.event_exception_list[ret['name']]['resources'] = ret['resources']
                        
            return ret
        return gen(statetree.root)

    @exportable
    def gui_initdata(self):
        """
        Returns a dict, with keys:
            hierarchy: a dict,
            saved_command_lines: a list
        """
        return {
            'hierarchy':self.get_hierarchy(),
            'gui_settings':self.preference.value['gui_settings'],
            'documents':self.preference.documents
        }

    @exportable
    def gui_settings_change(self,change_name,*args):
        """
        Change the preference.gui_settings 
        """
        if change_name == 'add_command_line':
            line = ' '.join(args)
            self.preference.value['gui_settings']['saved_command_lines'].append(line)
            self.preference.touch()
        elif change_name == 'del_command_line':
            line = ' '.join(args)
            if line in self.preference.value['gui_settings']['saved_command_lines']:
                self.preference.value['gui_settings']['saved_command_lines'].remove(line)        
            self.preference.touch()
        return

    @exportable
    def gui_get_source(self,node_path):
        assert node_path.startswith('root.')
        node = statetree.root[node_path[5:]]
        if IStateValue.providedBy(node._value):
            return inspect.getsource(node._value.__class__) 
        else:
            return inspect.getsource(node.__class__) 

    @exportable
    def get_event_exception_list(self):
        return self.event_exception_list

    @exportable
    def get_daemons(self):
        fields = ('type','port','enable','acls')
        values = {}
        for name, settings in __main__.config.general['daemon'].items():
            values[name] = {}
            for field in fields:
                values[name][field] = settings[field]
        return values

if __main__.developing_mode:
    # add node under an existing node
    log.msg('Playground enabled')
    @statetree.root.plug_node('playground',hidden=True)
    def value_provider(node):
        return Playground()
