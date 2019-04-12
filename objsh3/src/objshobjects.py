#! -*- coding:utf-8 -*-
import json,time,random,os,sys,traceback,re, copy, stat
from math import ceil
PY3 = sys.version_info[0]==3

if PY3:
    # python3
    import pickle
    #StringTypes = (unicode, str)
    #from collections import UserDict
else:
    # python2
    import cPickle as pickle
    #from types import StringTypes
    #from UserDict import UserDict

import __main__
from twisted.internet.threads import deferToThread
from twisted.internet import defer,reactor
from twisted.python import log
from twisted.protocols.basic import FileSender

from parse_line import parse_line as command_line_parser

class ObjshFileSender(FileSender):
    def __init__(self,abspath,options=None):
        """
        @param options:(dict) to be the stdout when sending to client
        """
        super(ObjshFileSender,self).__init__()
        assert os.path.exists(abspath)
        # test if this file is readable
        with open(abspath,'rb') as fd:
            fd.read(1024)
        self.abspath = abspath
        self.options = options or {}
        self.size = os.stat(abspath)[stat.ST_SIZE]
    def start(self,consumer,transform=None):
        fd = open(self.abspath,'rb')
        return self.beginFileTransfer(fd, consumer, transform)

class ObjshCommand(object):
    #boundary = '\x0d\x0a' #'\r\n' does not work in python3's websocket with Chrome
    boundary = u'♞'.encode('utf-8')
    def __init__(self,id, cmd, args,options=None):
        """
        @param options:
                    is_function_call:(boolean)
                    background:(boolean)
                    name:(string)
        @type options: dict
        """
        self.id = id 
        self.cmd = cmd
        self.args = args
        
        #self.next_command = None

        # calculated properties
        if self.args and self.args[-1]=='&':
            self.args.pop()
            self.is_background = True
        else:
            self.is_background = options.get('background',False) if options else False
        
        # this is a temporary property,
        # self.name will be taken over by running task
        self.rawdata = None
        if options is not None:
            self._name = options.get('name',None)
            self.rawsize = options.get('rawsize',0)
            self.rawdata = options.get('rawdata',None)
        else:
            self._name = None
            self.rawsize = 0
            self.rawdata = None

        # `command` would skip formatter to response raw result
        if self.args and self.cmd[0]=='`' and self.args[-1][-1]=='`':
            self.is_raw_result = True
            self.cmd = self.cmd[1:].strip()
            self.args[-1] = self.args[-1][:-1].strip()
            self.args = filter(None,self.args)
        else:
            self.is_raw_result = False
        
        self.stdin = None
        
        self.data = {
            'id':self.id,
            'cmd':self.cmd,
            'args':self.args,
            #'background',   # will be assigned later
            #'retcode':None, # will be assigned when completed
            #'stdout':None,  # will be assigned when completed
            #'stderr':None,  # will be assigned when completed
        }
        if self.is_background:
            self.data['background'] = True
        
        # if True, save state (call task.serialize()) when task complete
        self.background_w_state = False
        #
        # If the command is parsed from a line like: system.timezone.set('Asia/Taipei')
        # this command's is_function_call = True
        # for command of is_function_call==True,
        # the "args" part is regardless when matching its handling runner
        #
        self.is_function_call = options.get('is_function_call',False) if options else False

    #def encode(self):
    #    return json.dumps({'id':self.id, 'cmd':self.cmd, 'args':self.args})+Command.boundary
    
    #def set_name(self,name):
    #    self.data['name'] = name
    #    self.name = name

    def set_result(self, retcode, stdout=None, stderr=None):
        """
        called when command is completed.
        Args:
            retcode:(int) 0 for success, or other for error occured
            stdout:(any jsonable) or instance of ObjshFileSender
            stderr:(any jsonable)
        """
        self.data['retcode'] = retcode
        if retcode is None:
            ## progress back
            self.data['stdout'] = stdout
        else:
            if retcode == 0:
                self.data['stdout'] = stdout
            else:
                self.data['stderr'] = stderr

    def attach(self,abspath):
        """
        make the data['stdout'] to be an instance of ObjshFileSender
        """
        self.data['stdout'] = ObjshFileSender(abspath)

    def get_result(self):
        """
        為了一致性，回應與task.get_result相同格式的結構
        """
        simple_command_data = copy.copy(self.data)
        #del simple_command_data['cmd']
        del simple_command_data['args']
        response = {
            'id':self.id,
            'state':ObjshTask.STATE_COMPLETED,
            'command': simple_command_data
        }
        if self._name: response['name'] = self._name
        return response

    def set_stderr(self,errmsg):
        self.data['stderr'] = errmsg
    
    def get_stdout(self):
        return self.data['stdout']
    
    #def set_next_command(self,command):
    #    assert isinstance(command,ObjshCommand)
    #    self.next_command = command

    def to_background(self,w_state=None):
        if w_state is not None:
            self.background_w_state = w_state
        self.is_background = True
        self.data['background'] = True

    @classmethod
    def parse_command_line(cls,line,command_id=None):
        #command_line_parser
        """
        Currently, (pipe)| not supported yet
        """
        assert len(line) < 1024, 'command line too long'
        segment = line
        segment = segment.strip()
        cmd = None
        args = []
        #
        # seperate & (background)
        # drop the tailing &, unless it is in the last segment
        #
        is_background = False
        is_function_call = False
        if segment[-1]=='&':
            segment = segment[:-1].rstrip()
            is_background = True
        if segment[-1]==')' and segment.find('(')!=-1:
            #
            # parse in function-style arguments, such as call(1,2)
            #
            p = segment.find('(')
            args_part = segment[p+1:-1].strip()
            cmd_part = segment[:p].rstrip()
            is_function_call = True
            args = command_line_parser(args_part,',')
        else:
            first_space_at = segment.find(' ')
            if first_space_at == -1:
                cmd_part = segment
                args_part = ''
            else:
                cmd_part = segment[:first_space_at]
                args_part =  segment[first_space_at+1:].lstrip()
            #
            # parse in shell-style command line
            #
            try:
                args = command_line_parser(args_part,' ')
            except:
                traceback.print_exc()
        
        # convert escaped \\r and \\n to \r and \n respectively
        if PY3:
            for i in range(len(args)):
                if isinstance(args[i],str):
                    args[i] = args[i].replace('\\r','\r').replace('\\n','\n')
        else:
            for i in range(len(args)):
                if isinstance(args[i],unicode) or isinstance(args[i],str):
                    args[i] = args[i].replace('\\r','\r').replace('\\n','\n')

        if is_background:
            args.append('&')
        
        # auto generate command.id
        if command_id is None:
            command_id = '%s.%s' % (time.time(),random.randint(0,100000))
        command = cls(command_id,cmd_part,args,{'is_function_call':is_function_call})
        return [command]
    
    @classmethod
    def decode(cls,content,boundary):
        if isinstance(boundary,tuple):
            chunks = None
            for b in boundary:
                if content.find(b)==-1: continue
                chunks = content.split(b)
                break
            residue = conent if chunks is None else ('' if chunks[-1]=='' else chunks.pop())
        else:
            if content.find(boundary)==-1: return None, content
            chunks = content.split(boundary)
            residue = '' if chunks[-1]=='' else chunks.pop()
        return None if chunks is None else cls.decodeChunks(chunks), residue
    
    @classmethod
    def decodeChunks(cls,chunks):
        """
        Arguments:
            chunks:(list) currently it is lines
        """
        commands = []
        #consumed_length = 0
        idx = 0
        while idx < len(chunks):
            chunk = chunks[idx]
            try:
                # chunk is a json string, such as from sdk.js
                obj = json.loads(chunk)
                # chunk might be something like 123, 1.0
                # enforece to be handled by parse_command_line
                if not isinstance(obj,dict):raise ValueError()
            except ValueError:
                ## from telnet, ssh, web-request(command in url path)
                commands.extend(ObjshCommand.parse_command_line(chunk))

            else:            
                command_id = obj.get('id')
                if command_id is not None:
                    line = obj.get('line')
                    try:
                        if line:
                            command = ObjshCommand.parse_command_line(line,command_id)[0]
                            #command.set_id(obj.get('id'))
                            commands.append(command)
                        elif obj.get('cmd'):
                            commands.append(ObjshCommand(command_id, obj.get('cmd'),obj.get('args',[]),obj.get('options',None)))
                        else:
                            raise Exception('no command found')
                    except Exception as e:
                        command = ObjshCommand(command_id,line,None)
                        command.set_result(1,None,'%s:%s' % (line,e))
                        commands.append(command)
                        if command.rawsize and idx < len(chunks) - 1:
                            print('@'*20,'recover rawdata')
                            command.rawdata = chunks[idx+1]
                            idx += 1
                else:
                    #malform-ed json objects
                    pass
            idx += 1       
        return commands

    @classmethod
    def decodePackages(cls,packages):
        """
        Arguments:
            packages:(list)
        """
        commands = []
        #consumed_length = 0
        idx = 0
        while idx < len(packages):
            package = packages[idx]
            command_id = package.get('id')
            line = package.get('line')
            try:
                if line:
                    command = ObjshCommand.parse_command_line(line,command_id)[0]
                    commands.append(command)
                elif package.get('cmd'):
                    commands.append(ObjshCommand(command_id, package.get('cmd'),package.get('args',[]),package.get('options',None)))
                else:
                    raise Exception('no command found')
            except Exception as e:
                command = ObjshCommand(command_id,line,None)
                command.set_result(1,None,'%s:%s' % (line,e))
                commands.append(command)
            idx += 1        
        return commands


class ObjshTask(object):
    # constants
    STATE_CANCELLED = -1
    STATE_READY = 0
    STATE_RUNNING = 1
    STATE_COMPLETED = 2
    STATE_ERROR = 3
    
    # task management (use config.py to customize)
    maintenance_interval = 30
    ttl = 180
    
    running_tasks = []
    maintain_cache_timer = None
    watching_task_ids = {}
    # assigned at initialization stage
    cache_folder = None
    runner = None

    @classmethod
    def add_task(cls,task):
        cls.running_tasks.append(task)
        if task.command.is_background: ObjshTask.kick_maintain_cache()

    @classmethod
    def remove_task(cls,task):
        cls.running_tasks.remove(task)
        if task.command.is_background: ObjshTask.kick_maintain_cache()

    @classmethod
    def task_to_background(cls,task,background_w_state=None):
        task.command.to_background(background_w_state)
        if not task.deferred.called:task.deferred.callback(task)
        ObjshTask.kick_maintain_cache()
    
    @classmethod
    def get_running_task(cls,task_id):
        for task in cls.running_tasks:
            if task.id == task_id: return task
        return None

    @classmethod
    def get_task_from_cache(cls,task_id):
        filename = task_id
        path = os.path.join(cls.cache_folder,filename)
        if os.path.exists(path):
            try:
                with open(path,'rb') as fd:
                    return pickle.load(fd)
            except:
                log.msg(traceback.format_exc())
        return None

    @classmethod
    def maintain_cache(cls):
        """
        periodicall check serialized task data in taskcache folder.
        delete those expired data.
        """
        paths_to_remove = []
        now = time.time()
        for filename in os.listdir(cls.cache_folder):
            path = os.path.join(cls.cache_folder,filename)

            try:
                fd = open(path,'rb')
                data = pickle.load(fd)
                fd.close()
            except:
                log.msg(traceback.format_exc())
                paths_to_remove.append(path)

            else:
                
                #task_is_running
                if ObjshTask.get_running_task(data['id']): continue
                
                if data.get('start_ts') is not None and data.get('spend') is not None:
                    end_ts = data['start_ts']+ data['spend']
                    timeout = (data['state'] in (cls.STATE_CANCELLED, cls.STATE_COMPLETED, cls.STATE_ERROR)) and \
                              (data['ttl'] < (now - end_ts))
                else:
                    # if task is not running and it hasn't end_ts, 
                    # which means that this task might raise exception before completed
                    # and that exception has not been catched
                    timeout = True

                # state is cls.STATE_RUNNING but task is not running.
                if timeout or (data['state']  in (cls.STATE_READY, cls.STATE_RUNNING)):
                    # Maybe it was executed in previous server session,
                    # At this stage, we don't support re-run those tasks
                    log.msg('expired task data~' *20,data['id'],timeout,data['state'],'in', (cls.STATE_READY, cls.STATE_RUNNING))
                    paths_to_remove.append(path)

        for path in paths_to_remove:
            log.msg('remove task file',path)
            os.unlink(path)
        
        if len(os.listdir(cls.cache_folder)):
            cls.maintain_cache_timer = reactor.callLater(cls.maintenance_interval,cls.maintain_cache)
        else:
            cls.maintain_cache_timer = None
    
    @classmethod
    def kick_maintain_cache(cls):
        """ kick the maintenance routine to start if necessary """
        if cls.maintain_cache_timer: return
        cls.maintain_cache_timer = reactor.callLater(cls.maintenance_interval,reactor.callFromThread,cls.maintain_cache)

    @classmethod
    def list_tasks(cls,task_ids=None):
        """ 
        Retrieve data of foreground and background(includes running and serialized) tasks

        @param task_ids: a list task ids to get only

        Returns:
            A dictionary task_id => task_serialized_data.
            Taskdata of Running tasks has an extra 'alive':True item.
        """

        taskdata = {}

        # default return value to None if task_ids is presented
        if task_ids is not None:
            for task_id in task_ids: taskdata[task_id] = None
            
        for task in cls.running_tasks:

            # test if this is what we want
            if task_ids is not None and not task.id in task_ids: continue
            taskdata[task.id] = task.serialized_data
            # running state in task.command is un-trustable for the real running state
            taskdata[task.id]['alive'] = True

        # plus those on file system
        # suppose the filename is the task_id
        for task_id in os.listdir(cls.cache_folder):

            # test if this is what we want
            if (task_ids is not None) and (not task_id in task_ids):
                continue

            path = os.path.join(cls.cache_folder,task_id)

            try:
                fd = open(path,'rb')
                data = pickle.load(fd)
                fd.close()

            except:
                log.msg(traceback.format_exc())
                continue

            else:
                try:
                    # skip alive one
                    if taskdata[data['id']] is None:
                        taskdata[data['id']] = data
                except KeyError:
                    taskdata[data['id']] = data
        return taskdata
    
    @classmethod
    def search_by_name(cls,scope,keywords):
        """ 
        Retrieve data of foreground and background(includes running and serialized) tasks

        @param keywords: a list task ids to get only

        Returns:
            A dictionary task_id => task_serialized_data.
            Taskdata of Running tasks has an extra 'alive':True item.
        """
        assert scope in ('cmd','name','*')

        taskdata = {}

        for task in cls.running_tasks:
            hit = False
            for keyword in keywords:
                if scope == '*':
                    hit = (task.command.cmd.find(keyword) >= 0) or (task.name and task.name.find(keyword) >= 0)
                elif scope == 'cmd':
                    hit = task.command.cmd.find(keyword) >= 0
                elif task.name: # also scope == 'name':
                    hit = task.name.find(keyword) >= 0
                if hit:
                    taskdata[task.id] = task.serialized_data
                    # running state in task.command is un-trustable for the real running state
                    taskdata[task.id]['alive'] = True
                    break

        for task_id in os.listdir(cls.cache_folder):
            path = os.path.join(cls.cache_folder,task_id)
            try:
                fd = open(path,'rb')
                data = pickle.load(fd)
                fd.close()
            except:
                log.msg(traceback.format_exc())
                continue

            hit = False
            for keyword in keywords:
                if scope == '*':
                    hit = (data['command']['cmd'].find(keyword) >= 0) or (data['name'] and data['name'].find(keyword) >= 0)
                elif scope == 'cmd':
                    hit = data['command']['cmd'].find(keyword) >= 0
                elif data.get('name'):
                    hit = data['name'].find(keyword) >= 0
                if hit:
                    taskdata[data['id']] = data
                    break
        return taskdata

    def __init__(self,protocol,user,command,ttl=None):
        self.protocol = protocol
        self.user = user
        self.command = command
        self.id = command.id
        self.deferred = __main__.ProgressDeferred()
        self.state = ObjshTask.STATE_READY

        # take over the name from command
        self._name = self.command._name
        del self.command._name
        
        # assigned by registerred runner instance to stop this task
        # see runner_state.py for reference implementation
        self.canceller = None

        # result of a background task should be retrieved in ttl default to 180 seconds
        # count down started from task is completed
        self.ttl = ttl or ObjshTask.ttl

        self.watching_ids = {}

        self._connection_lost_registered = False

        # timestamp of start execution
        self.start_ts = 0
        # time spend of execution
        self.spend = 0

    @property
    def name(self): return self._name
    @name.setter
    def name(self,name):self._name = name
    
    @property
    def serialized_data(self):
        return {
            'id':self.id,
            'state':self.state,
            'owner':self.user.username,
            'ttl':self.ttl,
            'start_ts':self.start_ts,
            'spend':self.spend,
            'name': self._name,
            'command': self.command.data
        }

    def serialize(self):
        reactor.callFromThread(self._serialize)

    def _serialize(self):
        """
        called if the commaind is a background command
        """
        path = os.path.join(self.cache_folder,str(self.id))
        fd = open(path,'wb')
        pickle.dump(self.serialized_data,fd)
        fd.close()

    @property
    def is_running(self):
        return self.state==ObjshTask.STATE_RUNNING

    @property
    def is_cancelled(self):
        return self.state==ObjshTask.STATE_CANCELLED

    def output(self,content):
        """ 
        Encode a primitive data with json and send it to client.
        
        @param content: any primitive data
        
        @type content: dictionary
        """
        if content['command']['retcode'] == 0:
            assert content['command'].has_key('stdout')
        # since transport.lock been introduced, callFromThread will cause dead lock
        # when two routines are sending data at the same time
        #reactor.callFromThread(self.protocol.send_result,content)
        self.protocol.send_result(content)
    
    def get_peer_hash(self):
        """
        Returned value can be used as task's id
        """
        peer = self.protocol.transport.getPeer()
        return '%s:%s' % (peer.host,peer.port)
       
    def watch(self,watcher_id,progress_deferred,watchArgs=None):
        """
        Register a callable to be called when task.command's set_progress() or set_result() been called.
        The callable_id is a key of this callable, usually created by register's task.get_peer_hash().
        See runner_task.py for reference implementation.

        @param watcher_id: key to unwatch

        @param progress_deferred: an instance of ProgressDeferred

        @param watchArgs: extra argements list
        @type watchArgs: a list
        """

        if self.watching_ids is None: raise __main__.RunnerError('task %s is unable to watch' % self.id)

        try:
            self.watching_ids[watcher_id].append((progress_deferred, watchArgs))
        except KeyError:
            self.watching_ids[watcher_id] = [(progress_deferred, watchArgs)]

        #if not self._connection_lost_registered:
        #    self.protocol.connection_lost_deferred.addCallback(self.on_connection_lost)
        #    self._connection_lost_registered = True
        self.enable_cancel_at_lost_connection()

    def unwatch(self,watcher_id):
        callable_watchArgs_list = self.watching_ids.get(watcher_id)
        if callable_watchArgs_list is not None:
            del self.watching_ids[watcher_id]

            for progress_deferred, watchArgs in callable_watchArgs_list:
                # send None to watching listener to hint that the watching is over
                # the watching listener got the chance to end its job.
                # ex. runner_task.py use this signal to end a watching-task
                try:
                    if watchArgs is None:
                        progress_deferred.callback(None)
                    else:
                        progress_deferred.callback(None,*watchArgs)
                except:
                    log.msg(traceback.format_exc())

    def enable_cancel_at_lost_connection(self,canceller=None):
        """
        Call this to make this.cancel is called when lost connection
        Args:
            require_task:(bool) if true, task(self) will be the 1st argument when calls canceller
        """
        if canceller is not None:
            assert self.canceller is None
            self.canceller = canceller

        assert self.canceller, 'self.canceller is None, enable_cancel_at_lost_connection is useless'
        if not self._connection_lost_registered:
            self.protocol.connection_lost_deferred.addCallback(self.on_connection_lost)
            self._connection_lost_registered = True

    def on_connection_lost(self,protocol):
        """
        This is called when the connection which creates this task's has lost.
        
        Maybe at this moment, there are some active tasks is watching on this task.
        But those tasks will be closed when this task completed.
        So we do nothing here. 
        """ 
        try:
            self.canceller()
        except:
            traceback.print_exc()

    def propagate_to_watcher(self,final=False):

        data = self.get_result()
        if not final: data['_progress_'] = True
        
        def propagate(data):
            for watcher_id, callable_watchArgs_list in self.watching_ids.items():
                for progress_deferred, watchArgs in callable_watchArgs_list:
                    try:
                        if watchArgs is None:
                            if final:
                                progress_deferred.callback(data)
                            else:
                                progress_deferred.notify(data)
                        elif final:
                            progress_deferred.callback(data,*watchArgs)
                        else:
                            progress_deferred.notify(data,*watchArgs)
                    except:
                        log.msg(traceback.format_exc())
            
            # this task is no more to accept watching
            if final:
                self.watching_ids = None

        reactor.callLater(0,propagate,data)  
        return data

    def start(self):
        """
        Start to execute this task
        """

        if self.command.cmd in ('exit','quit','EOF'):
            self.state = ObjshTask.STATE_COMPLETED
            self.set_result(0,'Good-bye',None)
            self.deferred.callback(self)
            reactor.callLater(0,self.protocol.cutoff_connection)
            return

        self.state = ObjshTask.STATE_RUNNING
        self.start_ts = int(time.time())

        # tracking all tasks
        ObjshTask.add_task(self)

        deferred = defer.Deferred()
        if self.command.is_background:
            # response to caller immediately
            #self.deferred.callback(self)
            ObjshTask.task_to_background(self)

        def completed(result_tuple,the_task):
            #retcode,stdout,stderr = result_tuple
            the_task.set_result(*result_tuple)

            if self.command.is_background and self.command.background_w_state:
                # save the task state for caller to request later
                the_task.serialize()
            else:
                the_task.deferred.callback(the_task)
            
            ObjshTask.remove_task(the_task)

            return the_task

        def errback(failure,the_task):

            if the_task.command.is_background and the_task.command.background_w_state:
                the_task.serialize()

            ObjshTask.remove_task(the_task)
            the_task.propagate_to_watcher(final=True)

            return failure

        deferred.addCallbacks(completed,errback,callbackArgs=[self],errbackArgs=[self])
        self.runner.run(self,deferred)
        
    def get_result(self):
        # simplify the returned data to client
        # so no more return self.serialized_data
        simple_command_data = copy.copy(self.command.data)
        #del simple_command_data['cmd']
        del simple_command_data['args']
        response = {
            'id':self.id,
            'state':self.state,
            'name': self._name,
            'command': simple_command_data
        }
        if self._name: response['name'] = self._name
        return response
    
    
    def set_result(self,retcode,stdout=None,stderr=None):
        if retcode == 0:
            self.state = ObjshTask.STATE_COMPLETED
        else:
            self.state = ObjshTask.STATE_ERROR
        
        self.spend = int(time.time()) - self.start_ts
        
        self.command.set_result(retcode,stdout,stderr)
        
        return self.propagate_to_watcher(final=True)
    
    def set_progress(self,progress_result):
        
        self.command.set_result(None,progress_result)

        if self.command.is_background and self.command.background_w_state:
            try:
                if progress_result.savable: self.serialize()
            except AttributeError:
                pass
        
        return self.propagate_to_watcher(final=False)
    
    def cancel(self):
        # stop the execution only if this task is running 
        if not self.is_running:
            raise __main__.RunnerError('task #%s is not running' % self.id)

        self.state = ObjshTask.STATE_CANCELLED

        if self.canceller is None:
            raise __main__.RunnerError('task #%s is not cancellable' % self.id)
        else:
            return defer.maybeDeferred(self.canceller)

        
        
if __name__ == '__main__':
    lines = [ 
        'ls -l /',
        'ls -l "apple "&',
        'ls -l "apple \\"  news"',
        'ls -l "apple - news" "google - news" &',
        "ls -l 'in single quote'",
        "set(1,'2 3')",
        "set('a')",
        "set('a','b')",
        "set('a','b',\"c\")",
        "set('a','b',\"c\")",
        ]
    for line in lines:
        print (line)
        for cmd in ObjshCommand.parse_command_line(line):
            print ('cmd="%s"' % cmd.cmd, 'args=',cmd.args, 'is_background=',cmd.is_background)
        print ()