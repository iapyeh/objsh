#! -*- coding:utf-8 -*-
from ..__init__ import *
from twisted.internet import reactor,defer
from __main__ import statetree, RunnerError
from objshstate import *
import re,json

@runner.provider(re.compile('^'+statetree.runner_name+'\..+'),'*')
def run(task):
    cmd = task.command.cmd
    args = task.command.args
    user = task.user
    
    # allow cmd to be like set(arg1,arg2,...)
    #statetree.log.debug('%s@%s(%s)' % (user.username,cmd,args))

    paths = cmd.split('.')
    node = None
    leaf_name = None
    try:
        if len(paths)<3:
            pass
        elif paths[1]=='nodes':
            try:
                node = statetree.nodes[paths[2:-1]] 
                leaf_name = paths[-1] or 'state'
            except AttributeError:
                node = statetree.nodes[paths[2:]]
                leaf_name = 'state'
        elif paths[1]=='root':
            try:
                node = statetree.root[paths[2:-1]]
                leaf_name = paths[-1] or 'state'
            except AttributeError:
                node =  statetree.root[paths[2:]]
                leaf_name = 'state'

        if node is None:
            raise AttributeError
           
    except AttributeError:
        # node not found
        statetree.log('command "%s" not found' % cmd)
        raise RunnerError('command "%s" not found' % cmd)
    else:
        try:
            leaf = getattr(node,leaf_name)
            #statetree.log('web accessing',node,leaf)
            if isinstance(leaf,StateNode):
                return leaf.state
            else:
                #
                # Because SimpleStateValue instance will append its exports and events
                # to its owner_node, so, we just need to check exports of the StateNode
                #
                if not leaf_name in node.exports:
                    name = node._value.__class__.__name__ if IStateValue.providedBy(node._value) else node.__class__.__name__
                    raise StateError('run_state.1',leaf_name+' not exported by %s(node:%s)' % (name,node.__class__.__name__),{'leaf_name':leaf_name,'name':name,'exports':node.exports})
                
                if not callable(leaf): return leaf
                
                # handle callable starts
                
                require_task = leaf.__dict__.get('require_task',False)
                
                # by @canceller, style
                if hasattr(leaf,'cancel'):
                    if leaf.auto_cancel:
                        # by @X.canceller(True) or @X.disconnection_canceller
                        if require_task:
                            task.canceller = lambda _task=task:leaf.cancel(_task)
                        else:
                            task.canceller = leaf.cancel                            
                        task.enable_cancel_at_lost_connection()
                    else:
                        # by @X.canceller
                        task.canceller = leaf.cancel

                # by style of def X; X.canceller = Y
                elif leaf.__dict__.get('canceller'):
                    task.canceller = lambda _self=node._value:leaf.__dict__['canceller'](_self)
                
                # by style of def X; X.disconnection_canceller = Y
                elif leaf.__dict__.get('disconnection_canceller'):
                    if require_task:
                        task.canceller = lambda _self=node._value,_task=task:leaf.__dict__['disconnection_canceller'](_self,_task)
                    else:
                        task.canceller = lambda _self=node._value:leaf.__dict__['disconnection_canceller'](_self)
                    task.enable_cancel_at_lost_connection()
                    

                # check the command name
                task_name = leaf.__dict__.get('task_name')
                if task_name:
                    task.name = task_name

                # check if enforce this command to background
                if not task.command.is_background:
                    to_background = leaf.__dict__.get('to_background',False) 
                    to_background_w_state = leaf.__dict__.get('to_background_w_state',False) 
                    if to_background_w_state:
                        reactor.callLater(0,task.__class__.task_to_background,task,True)
                    elif to_background:
                        reactor.callLater(0,task.__class__.task_to_background,task)
                
                if require_task:
                    ret = leaf(task,*args)
                else:
                    ret = leaf(*args)

                if isinstance(ret,StateError):
                    objshrunner.throw(ret.serialized_data, ret.retcode)
                else:
                    return ret
        except StateError as e:
            #ret = {'name':e.name,'message':e.message,'type':'exception'}
            print('state error: %s' % e,'<'*30)
            objshrunner.throw(e.serialized_data, e.retcode)
