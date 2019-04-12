#! -*- coding:utf-8 -*-
# magic line to be auto imported by objstate.py
from __init__ import *


class Hello(SimpleStateValue):
    def __init__(self):
        #initial value is False
        return super(Hello,self).__init__(False)

# add node under an existing node
@statetree.root.plug_node('hello')
def value_provider(node):
    return Hello()

# add method to an existing node
@statetree.nodes.hello.plug_method()
def say_hi(self):
    assert self.__class__.__name__ == 'Hello'
    #statetree.log.msg('say hi to ',name)
    return 'Hi  how are you'

# add method to an existing node
@statetree.nodes.hello.plug_method()
def goodbye(self):
    assert self.__class__.__name__ == 'Hello'
    #statetree.log.msg('say hi to ',name)
    return 'good bye!'
