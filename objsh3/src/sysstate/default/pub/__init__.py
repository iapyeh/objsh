#! -*- coding:utf8 -*-
"""
root.pub is a group of utility nodes.
"""
import objshstate
from objshstate import *
from __main__ import *
import __main__

# Add root.pub if it is not existed
if statetree.nodes.get('pub') is None:
    pub = statetree.root.add_node('pub')

__all__ = objshstate.__all__ + __main__.__all__
