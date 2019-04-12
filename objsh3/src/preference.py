#! -*- coding:utf-8 -*-
#
# This is to implement a hierarchical preference system
# Similar project: Bunch @ https://github.com/dsc/bunch/tree/master/bunch
#
import os, datetime, json
from twisted.internet import reactor
from twisted.python import log

try:
    import cPickle as pickle
    #from UserDict import UserDict
except ImportError:
    import pickle
    #from collections import UserDict

class PreferenceItem(object):
    """
    Represents a object-like instance with presistence repository for primative values.
    
    Methods:
        set(name,value)
        get(name)
        items()
        to_dict()
        purge()
    """
    
    def __init__(self,parent,name,value=None):
        self._parent = parent
        self._name = name
        self._child = {}
        self._touch_callbacks = []
        self._value = value
        if type(value)==type({}):
            # "value" can not be the key 
            assert 'value' not in value,'"value" can not be preference name'
    
    @property
    def value(self):
        if len(self._child):
            a_dict = {}
            for name,item in self._child.items():
                a_dict[name] = item.value
            return a_dict
        else:
            return self._value
    
    @value.setter
    def value(self,v):
        assert not hasattr(v,'__dict__'), 'preference value can not be an instance of '+v.__class__.__name__
        if len(self._child):
            log.msg('Warning: preference '+self._name+' purged by value.setter')
            self.purge()
        if type(v)==type({}):
            # "value" can not be the key 
            assert 'value' not in v,'"value" can not be preference name'
        self._value = v        

    def to_dict(self,a_dict=None):
        """ almost synonym of .value """
        if a_dict is None: a_dict = {}
        if len(self._child):
            a_dict[self._name] = {}
            for key,value in self._child.items():
                a_dict[self._name].update(value.to_dict())
        else:
            a_dict[self._name] = self._value
        return a_dict
    
    def touch(self,changed_item=None):
        if changed_item is None: changed_item=self
        if self._parent:self._parent.touch(changed_item)
        for callback in self._touch_callbacks:
            try:
                callback(self)
            except:
                traceback.print_exc()
    
    def call_when_touch(self,callback):
        assert callable(callback) 
        assert callback not in self._ontouch_callbacks
        self._touch_callbacks.append(callback)
    
    def __contains__(self,name):
        return self._child.__contains__(name)
    
    def __iter__(self):
        return self._child.__iter__()
    
    def __eq__(self,other):
        # allow user to compare value by ==
        # ex. system.version == None
        return self._value is other
    
    def __nonzero__(self):
        # boolean test
        return  True if (len(self._child) or self._value) else False
    
    def __len__(self):
        # allow user to test true or false
        return len(self._child)
    
    def __delattr__(self,name):
        try:
            del self._child[name]
            self.touch()
        except KeyError:
            raise AttributeError(name)
    
    def __getattr__(self,name):
        try:
            item = self._child[name]
            if len(item._child) or item._value is None: return item
            value = item._value
        except KeyError:
            value = PreferenceItem(self,name)
            self._child[name] = value
        return value
    
    def __setattr__(self,name,value):
        if name.startswith('_') or name in ('value',):
            return super(PreferenceItem,self).__setattr__(name,value)
        try:
            self._child[name].value = value
            self.touch()
        except KeyError:
            self._child[name] = PreferenceItem(self,name,value)
            self.touch(self._child[name])

    def __getitem__(self,name):
        return self.__getattr__(name)

    def __setitem__(self,name,value):
        return self.__setattr__(name,value)
    
    def items(self):
        return self.to_dict()[self._name].items()
    
    def set(self,name,child_node):
        assert isinstance(child_node,PreferenceItem)
        self._child[name] = child_node
    
    def get(self,name):
        return self._child[name]
    
    def purge(self):
        self._value = None
        if len(self._child):
            for name,child in self._child.items():
                child.purge()
                del child
            self._child = {}
        self.touch()
    
    @staticmethod
    def from_ini_config(config):
        #
        # Converet the settings in state.ini to a dictionary
        #
        # see state_unittest.ini for details
        #
        sections = config.sections()
        ini_preferences = {}
        for section in sections:
            if not section.startswith('preference.'): continue
            names = section.split('.')
            section_dict = ini_preferences
            for name in names:
                if section_dict.get(name) is None:
                    next_section_dict = {}
                    section_dict[name] = next_section_dict
                else:
                    next_section_dict = section_dict[name]
                section_dict = next_section_dict
            
            for name,value in config.items(section):
                names = name.split('.')
                item_dict = section_dict
                for name in names[:-1]:
                    if item_dict.get(name) is None:
                        next_item_dict = {}
                        item_dict[name] = next_item_dict
                    else:
                        next_item_dict = item_dict[name]
                    item_dict = next_item_dict
                name = names[-1]
                if value.startswith('json:'):
                    value = json.loads(value[5:].strip())
                elif value.startswith('int:'):
                    value = int(value[4:].strip())
                elif value.startswith('date:'):
                    ymd = value[5:].strip().split('-')
                    value = datetime.datetime(int(ymd[0]),int(ymd[1]),int(ymd[2]))
                elif value.startswith('datetime:'):
                    ymd_s,hms_s = value[9:].strip().split(' ')
                    ymd = ymd_s.split('-')
                    hms = hms_s.split(':')
                    value = datetime.datetime(int(ymd[0]),int(ymd[1]),int(ymd[2]),int(hms[0]),int(hms[1]),int(hms[2]))
                item_dict[name] = value
        preference = ini_preferences.get('preference')
        #pp.pprint(preference)
        if preference is None: preference = {}
        return PreferenceItem.from_dict(preference)
    @staticmethod
    def from_dict(a_dict,parent=None,root_name='preference'):
        """
        convert a dictionary to a top preference item.
        """
        
        def gen(_dict,top):
            for name,value in _dict.items():
                #if type(top)==type(_dict):
                #    top[name] = PreferenceItem(top,name,value)
                #else:
                assert isinstance(top,PreferenceItem)
                if type(value)==type(_dict):
                    v = PreferenceItem(top,name)
                    top._child[name] = v
                    gen(value,v)
                elif isinstance(value,PreferenceItem):
                    top._child[name] = value
                else:
                    getattr(top,name).value = value
        
        root = PreferenceItem(parent,root_name)
        gen(a_dict,root)
        #data = root.to_dict()
        #pp.pprint(data[root_name])
        
        return root

class Preference(object):
    def __init__(self,preference_id,default_preferences=None,preference_config=None):
        """
        priority: stored > set in ini file > default_preferences

        Arguments:
            preference_id: (string) id to used for save/restore pickled dict
            default_preferences: (string) path to save/restore pickled dict
            preference_config: (dict) 
        
        Methods:
            set (name,value)
            get (name)
        """
        self._save_on_touch = False
        self._save_timer = 0
        self._save_interval = 3
        self._id = preference_id
        
        #default pickle folder
        self._pickle_folder = os.path.abspath(os.path.dirname(__file__))

        if type(default_preferences)==type({}):
            init_dict = default_preferences
        elif isinstance(default_preferences,PreferenceItem):
            init_dict = default_preferences.to_dict()
        else:
            init_dict = {}
        #
        # merge (A)restored data in pickle_folder and (B)default_preferences
        # (B) takes priority
        #
        if preference_config is not None:
            self._pickle_folder = os.path.abspath(os.path.normpath(os.path.join(preference_config['folder']['etc'],preference_config['save_to_folder'])))

            ini_preference = preference_config.get('default',{})
        else:
            ini_preference = {}

        init_dict.update(ini_preference)
        
        self._pickle_path = os.path.join(self._pickle_folder,'%s.pk' % self._id)
        if os.path.exists(self._pickle_path):
            try:
                serialized_dict = pickle.load(open(self._pickle_path,'rb')).get(self._id) or {}
            except UnicodeDecodeError:
                # python2 pickled data been loaded in python3
                serialized_dict = {}
            except ValueError:
                # python3 pickled data been loaded in python2
                serialized_dict = {}
        else:
            serialized_dict = {}
        init_dict.update(serialized_dict)
        
        if len(init_dict):
            self._preference_root = PreferenceItem.from_dict(init_dict,self,self._id)
        else:
            self._preference_root = PreferenceItem(self,self._id)
    
    def __getattr__(self,name):
        """
        Divert attribute getting to root item
        """
        try:
            return self.__dict__[name]
        except KeyError:
            try:
                return getattr(self._preference_root,name)
            except AttributeError:
                # dynamically create an item for missing attribute
                value = PreferenceItem(self._preference_root,name)
                self._preference_root._child[name] = value
                return value

    def __delattr__(self,name):
        delattr(self._preference_root,name)

    def __setattr__(self,name,value):
        """
        Divert attribute setting to root item
        """
        if name.startswith('_') or name in ('save_on_touch',):
            return super(Preference,self).__setattr__(name,value)
        setattr(self._preference_root,name,value)

    def __contains__(self,name):
        return name in self._preference_root

    def __iter__(self):
        return self._preference_root.__iter__()

    def call_when_touch(self,callback):
        return self._preference_root.call_when_touch(callback)

    def to_dict(self):
        return self._preference_root.to_dict()

    def set(self,name,value):
        return setattr(self,name,value)

    def get(self,name):
        return getattr(self,name)

    @property
    def save_on_touch(self):
        return self._save_on_touch

    @save_on_touch.setter
    def save_on_touch(self,yes):
        self._save_on_touch = True if yes else False

    def touch(self,changed_item):
        if (not self._save_on_touch) or self._save_timer: return
        self._save_timer = reactor.callLater(self._save_interval,self.save)

    def save(self):
        #log.msg('Warning preference not saved')
        #return 
        if not os.path.exists(self._pickle_folder):
            os.mkdir(self._pickle_folder)
        pickle.dump(self.to_dict(),open(self._pickle_path,'wb'))
        self._save_timer = 0

if __name__ == '__main__':
    import pprint,sys
    pp = pprint.PrettyPrinter()
    from twisted.python import log
    log.startLogging(sys.stdout.buffer)
    def unittest_preference():
        base_folder = os.path.abspath(os.path.dirname(__file__))
        preference_ini_path = os.path.join(base_folder,'state','preference_unittest.ini')

        if 1:
            # empty start
            pref = Preference('my_preference',{},None)
            assert 'version' not in pref
            assert pref.version == None
            assert 'version' in pref
            assert not pref.something
            pref.something = 0
            assert not pref.something
            pref.something = 1
            assert pref.something
            try:
                pref.something.next = 0
            except AttributeError:
                print ('failed to assign pref.something.next = 0')
                print ('because pref.something is 1')
                del pref.something
            pref.something.next = {} # {} is evaluated to False
            assert pref.something
            assert not pref.something.next
            assert pref.something.next == {}

            #print 'pref.version=',pref.version
            pref.general.deleteme = 1
            assert pref.general.deleteme ==1
            del pref.general.deleteme
            assert pref.general == None
            assert pref.general is not None
            del pref.general
            pref.version = '1.0'
            assert pref.version == '1.0'
            pref.system.name = 'my preference'
            assert pref.system.name == 'my preference'
            assert not 'release' in pref.system
            pref.system.release = '0.9beta'
            assert 'release' in pref.system
            assert len(pref.system)==2
            for name in pref:
                print ('pref has',name)
            for name in pref.system:
                print ('pref.system has',name)
            pp.pprint(pref.to_dict())
            reactor.callLater(0,reactor.stop)
            return
        elif 0:
            # honor ini config
            pref = Preference('my_preference',{'Owner':'Unit Testing'},preference_ini_path)
            # override existing value in ini config
            pref.hardware.cpu.vendor = 'AMD'
            pref.default.system.name = 'Preference Unit Test'
            # assign new value
            pref.system.name = 'my preference'
            assert pref.system.name == 'my preference'
            pp.pprint(pref.to_dict())
        elif 0:
            # save and restore
            pref = Preference('my_preference',{'Owner','Unit Testing'},preference_ini_path)
            if 1:
                pk_path = os.path.join(base_folder,'state','preference_unittest','my_preference.pk')
                if os.path.exists(pk_path): os.unlink(pk_path)
                def change1():
                    pref.hardware.cpu.vendor = 'AMD'
                def change2():
                    pref.default.system.name = 'Preference Unit Test'
                def change3():
                    pref.system.name = 'my preference'
                    #pp.pprint(pref.to_dict())
                    reactor.callLater(3,reactor.stop)
                pref.save_on_touch = True
                reactor.callLater(0,change1)
                reactor.callLater(1,change2)
                reactor.callLater(2,change3)
            elif 1:
                reactor.callLater(0,reactor.stop)
                pp.pprint(pref.to_dict())
                assert pref.hardware.cpu.vendor == 'AMD'
                assert pref.default.system.name == 'Preference Unit Test'
                assert pref.system.name == 'my preference'
                
            
    reactor.callWhenRunning(unittest_preference)
    reactor.run()