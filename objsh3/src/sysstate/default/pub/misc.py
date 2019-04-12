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

class Misc(SimpleStateValue):
    """
    Misc utilities
    """
    def __init__(self):
        #initial value is False
        super(Misc,self).__init__()

    @exportable
    def echo(self,args):
        return args
        
statetree.nodes.pub.add_node('misc',Misc())
