#! -*- coding:utf-8 -*-
#
# This is a script of unit tests
#  - reginal readiness feature of statetree
# 
#

import time,sys,datetime,os,re
import __main__
from __init__ import *
from nodes_dev import *
class MyStateTree(StateTree):
    def build(self):
        system = self.root.add_node('system')
        storage = system.add_node('storage')
        general = system.add_node('general')
        general.add_node('uptime',Uptime())
        network = system.add_node('network')
        network.add_node('ethernet',Ethernet())
        
        storage.add_node('samba_service',SambaService())
        storage.add_node('raid_system',RAIDSystem())

def factory(options):
    return MyStateTree(options)
