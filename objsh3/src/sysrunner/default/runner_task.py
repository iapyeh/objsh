#! -*- coding:utf-8 -*-
from ..__init__ import *

import re
from twisted.internet import reactor

#try:
#    from UserDict import UserDict
#except ImportError:
#    from collections import UserDict

@runner.provider('task','*')
def run(task):
    cmd = task.command.cmd
    args = task.command.args

    # don't accept to run this command in background 
    if task.command.is_background:
        raise RunnerError('task command should be in foreground')
    
    subcmd = args[0]
    ObjshTask = task.__class__
    if subcmd == 'list':
        if len(args)>1:
            task_ids = []
            # task id might be comma seperated in a single argument
            for arg in args[1:]:
                task_ids.extend(filter(None,[x.strip() for x in arg.split(',')]))
            taskdata_dict = ObjshTask.list_tasks(task_ids)
        else:
            taskdata_dict = ObjshTask.list_tasks()
            # remove the task of myself
            del taskdata_dict[task.id]
        return taskdata_dict
    
    elif subcmd == 'search':
        # scope is one of ('cmd','name','*')
        if len(args) <= 2: return {}
        scope = args[1]
        keywords = []
        # task id might be comma seperated in a single argument
        for arg in args[2:]:
            keywords.extend(filter(None,[x.strip() for x in arg.split(',')]))
        taskdata_dict = ObjshTask.search_by_name(scope,keywords)
        return taskdata_dict
    
    elif subcmd == 'watch':
        # watch task is a foreground, progressive task
        # it hooks a progress deferred to the targeting task.
        # the hooked task only calls notify(has_more, result) of the hooked progress deferred
        # the watch task gets to call callback for its own task deferred.
        task_id = str(args[1])
        target_task = ObjshTask.get_running_task(task_id) if task_id else None

        # search cached task to see if task_id is not running
        if target_task is None:
            target_task = ObjshTask.get_task_from_cache(task_id)

            if target_task:
                return target_task
            else:
                raise RunnerError('task #%s is no more available' % task_id)

        # target_task is running, only background task is allowed to watch
        #elif not target_task.command.is_background:
        #    #print ('task #%s is in foreground, it is not watchable' % task_id)
        #    return target_task.get_result()
        
        # return an instance of ProgressDeferred to inform the client
        # that there are multiple responses 
        my_deferred = ProgressDeferred()
        watcher_deferred = ProgressDeferred()
        
        def progressBack(task_serialized_data,the_my_deferred):
            the_my_deferred.notify(task_serialized_data)
        
        def callbackBack(task_serialized_data,the_my_deferred):
            the_my_deferred.callback(task_serialized_data)

        watcher_id = task.get_peer_hash()
        watcher_deferred.addProgressBack(progressBack,my_deferred)
        watcher_deferred.addCallback(callbackBack,my_deferred)
        target_task.watch(watcher_id,watcher_deferred)
        
        #auto unwatch if connection lost
        canceller = lambda x=watcher_id:target_task.unwatch(x)
        task.enable_cancel_at_lost_connection(canceller)
        
        return my_deferred
    
    elif subcmd == 'unwatch':
        task_id = str(args[1])
        target_task = ObjshTask.get_running_task(task_id) if task_id else None
        if target_task is None:
            raise RunnerError('%s is not watching' % task_id)
        watcher_id = task.get_peer_hash()
        target_task.unwatch(watcher_id)
        return True

    elif subcmd == 'cancel':
        task_id = str(args[1])
        target_task = ObjshTask.get_running_task(task_id) if task_id else None
        if target_task is None:
            raise RunnerError('%s is not running or not existed' % task_id)

        return target_task.cancel()

    elif subcmd == 'background':
        task_id = str(args[1])
        target_task = ObjshTask.get_running_task(task_id) if task_id else None
        if target_task is None:
            raise RunnerError('%s is not running or not existed' % task_id)

        if target_task.command.is_background:
            return True

        ObjshTask.task_to_background(target_task)
        return True
