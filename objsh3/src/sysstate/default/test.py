#! -*- coding:utf-8 -*-
# magic line to be auto imported by objstate.py
from .__init__ import *
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