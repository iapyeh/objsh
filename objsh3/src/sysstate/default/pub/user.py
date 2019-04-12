#! -*- coding:utf-8 -*-
"""
State node of root.pub.
The aggregator for public stuffs. Such as utilities.
"""
from .__init__ import *
import __main__
from twisted.python import log
from twisted.internet import reactor, threads, defer
import os, sys
import json, logging, datetime, time, traceback
from twisted.logger import LogLevel
import sqlitedict
class UserPreferences(SimpleStateValue):
    """
    Preference repository for every single account
    """
    #exports = (
    #    'get',
    #)    
    def __init__(self):
        super(UserPreferences,self).__init__()
        var_folder = __main__.config.general['folder']['var']
        self.path = os.path.join(var_folder,'user_preferences.sqlitedict')            
        self.dict = None
    
    def is_ready(self):
        self.dict =  sqlitedict.SqliteDict(self.path,autocommit=True)
    
    @exportable
    def get(self,task):
        """
        get previously stored preferences object by set() of current login user
        """
        try:
            return self.dict[task.user.username]
        except KeyError:
            return {}
    get.require_task = True

    @exportable
    def set(self,task,value):
        """
        set an object of preferences to current login user
        """
        self.dict[task.user.username] = value
        #statetree.log.debug('set preference of %s to %s' % (task.user.username,value))
        return True
    set.require_task = True

statetree.nodes.pub.add_node('user_preferences',UserPreferences())
