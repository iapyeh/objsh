#! -*- coding:utf-8 -*-
from ..__init__ import * #runner,after_runner,objshrunner
import re
from twisted.python import log
@runner.provider('echo','*')
def run(task):
    cmd = task.command.cmd
    args = task.command.args
    return ' '.join([str(x) for x in args])

'''
class LogReader(object):
    singleton = None
    def __init__(self):
        print '&' * 100

@runner.provider('log')
def run(task):
    cmd = task.command.cmd
    args = task.command.args
    if LogReader.singleton is None:
        LogReader.singleton = LogReader()
    return LogReader.singleton.read()
'''