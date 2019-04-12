#!/usr/bin/env python
#! -*- coding:utf-8 -*-

import json, traceback, re, sys, time, struct
from math import ceil

from twisted.conch.telnet        import StatefulTelnetProtocol
from twisted.internet.protocol   import Protocol, ServerFactory
from twisted.conch.telnet        import TelnetTransport
from twisted.conch.ssh.session   import SSHSessionProcessProtocol
from twisted.protocols.tls       import TLSMemoryBIOProtocol
from twisted.internet.tcp        import Server
from twisted.internet            import defer, reactor
from twisted.python              import log
from threading import Lock
PY3 = sys.version_info[0] == 3
if PY3:
    from collections import deque
else:
    pass
from objshobjects import ObjshTask, ObjshCommand, ObjshFileSender
from objshweb import AuthWebSocketProtocol, ObjshWebUser

import threading

# StatefulTelnetProtocol is for telnet, it is based on lineReceiver
class ObjshProtocol(StatefulTelnetProtocol):
    max_login_interval = 360
    def __init__(self, user):
        # set user
        assert user is not None
        self.set_user(user)
        self.buf_data = b''
        self.buf_packages = []
        self.reset_delimiter()
        self.queue = deque() if PY3 else []
        self._consume_timer = None
        
        # list of ShellTask
        #self.running_tasks = []
        #self.last_bg_task = None
        #print 'protocol(%s) user(%s %s) ' % (id(self),self.user.addr,self.user.session)
        
        self._connection_lost_deferred = None
            
    def reset_delimiter(self):
        if PY3:
            if isinstance(ObjshCommand.boundary,str):
                self.boundary = ObjshCommand.boundary.encode()
            else:
                self.boundary = ObjshCommand.boundary
        else:
            self.boundary = ObjshCommand.boundary #bytes
        self.boundary_len = len(self.boundary)
        #self.delimiter_pat = re.compile(b'(.*?)('+ObjshCommand.boundary+b')',re.S)

    def set_delimiter_to_newline(self):
        """
        called by ssh, telnet,... to use new line as command boundary
        """
        # match line ended by '\r','\n' or '\r\n'
        #self.delimiter_pat = re.compile(b'(.*?)(\r\n|\r|\n)',re.S)
        if PY3:
            self.boundary = b'\r\n'
        else:
            self.boundary = '\r\n'
        self.boundary_len = len(self.boundary)
        
    def set_user(self,user):
        self.user = user
        if user.addr is not None:
            self.remote_ip = user.addr.host
        else:
            self.remote_ip  = None
    
    @property
    def connection_lost_deferred(self):
        if self._connection_lost_deferred  is None:
            self._connection_lost_deferred = defer.Deferred()
        return self._connection_lost_deferred 
    
    def connectionMade(self):
        # self.transport is an instance of tcp.Server for ssh, but
        # self.transport is an instance of AuthWebSocketProtocol for ws://
        # self.transport is an instance of TLSMemoryBIOProtocol for wss://
        if isinstance(self.transport,TelnetTransport):
            self.set_delimiter_to_newline()
            # for telnet, getPeer() returns an IPV4Address instance
            self.user.addr = self.transport.getPeer()
            # at the moment, we can response a message for login succeed
            #login_ok_response = '{"cmd": "login", "retcode": 0, "id": "0", "args": ["telent"], "stdout": "welcome"}'
            self.transport.write(b'\r\n')
        elif isinstance(self.transport,SSHSessionProcessProtocol):
            #login_ok_response = '{"cmd": "login", "retcode": 0, "id": "0", "args": ["ssh"], "stdout": "welcome"}'
            #self.transport.write(login_ok_response+'\r\n')
            if not self.transport.use_objshcommand_delimiter:
                # traditional ssh delimiter is \r\n
                self.set_delimiter_to_newline()
        elif isinstance(self.transport,AuthWebSocketProtocol):
            # do nothing for websocket
            pass
        elif isinstance(self.transport,TLSMemoryBIOProtocol):
            # do nothing for secure websocket
            pass
        elif isinstance(self.transport,Server):
            # raw socket
            #self.transport.write(b'Welcome\r\n')
            addr = self.transport.getPeer()
            log.debug('connected by tcp socket from %s' % addr)

        self.setRawMode()
        self.transport.lock = Lock()
        # allow to succeed login in a period of time if self.max_login_interval is not zero.
        if self.max_login_interval:
            def login_checker():
                if not self.user.authenticated: self.cutoff_connection()
            reactor.callLater(self.max_login_interval,login_checker)
        
    def connectionLost(self, reason):
        # ssh would call this twice, so let's just it once
        #log.debug('connection lost from',self,'because',reason,',user=',self.user,'authenticated=',self.user.authenticated,self.transport.getPeer())
        
        # do not call user.logout, this is to allow login in multiple web pages
        #self.user.logout()
        
        # but remove self from the registered protocol
        self.user.remove_connected_protocol(self)
       
        if self._connection_lost_deferred  is not None:
            self._connection_lost_deferred.callback(self)

    def send_result(self,obj):
        """
        obj is got by task.get_result or command.get_result
        """
        # txws in python3 has a bug
        # which cause each frame should be shorter than 126 bytes
        #print('>>>>',obj)
        if obj['command']['retcode'] == 0 and isinstance(obj['command']['stdout'],ObjshFileSender):
            producer = obj['command']['stdout']
            obj['command']['stdout'] = producer.options
            obj['rawsize'] = producer.size
        else:
            producer = None

        if PY3:
            raw = json.dumps(obj,ensure_ascii=False).encode()
        else:
            try:
                raw = json.dumps(obj)
            except UnicodeDecodeError:
                raw = json.dumps(obj,ensure_ascii=False)           
        #should pack txws.py (used txws_patched.py instead)
        package_type = struct.pack('>B',1)
        length = struct.pack('>I',len(raw))
        content = package_type+length+raw+self.boundary #bytes
        self.transport.lock.acquire()
        self.transport.write(content)
        if producer:
            package_type = struct.pack('>B',2)
            length = struct.pack('>I',producer.size)
            self.transport.write(package_type+length)
            def sent_completed(last_sent):
                self.transport.write(self.boundary)
                self.transport.lock.release()
                log.debug('file sending completed')
            def sent_err(failure):
                self.transport.lock.release()
                log.warn('send file error:%s' % failure.getErrorMessage())
            producer.start(self.transport).addCallbacks(sent_completed,sent_err)
        else:
            self.transport.lock.release()
       
    def rawDataReceived(self, data):
        """
        received data might be of length 1 or as many as possible.
        """

        #log.msg('<<%s<<%s' % (time.time(),len(data)),'types',type(self.buf_data),type(data))
        # chunk is "bytes" type in py3
        self.buf_data += data
        packages = []
        package_overhead_len = 5 + self.boundary_len
        while len(self.buf_data) > 5:
            package_type = self.buf_data[0]
            assert package_type in (1,2)
            package_len = struct.unpack('>I',self.buf_data[1:5])[0]
            #log.debug('parsing got, type=',package_type,'length=',package_len,'now has',len(self.buf_data))
            if len(self.buf_data) >= package_overhead_len+package_len:
                # caution: this would almost double memory usage
                package_content = self.buf_data[5:5+package_len]
                rawsize = 0
                if package_type == 1:
                    package = json.loads(package_content.decode('utf-8'))
                    if package['options']['rawsize']:
                        self.buf_packages.append(package)
                    else:
                        packages.append(package)
                elif package_type == 2:
                    # lookup for content's owner,
                    # if none found, drop it
                    rawsize = package_len
                    # lookup package got at current chunk
                    for p in packages:
                        if p['options']['rawsize'] == rawsize:
                            p['options']['rawdata'] = package_content
                            rawsize = 0
                            break
                    # lookup at previous chunks
                    if rawsize:
                        for i in range(len(self.buf_packages)):
                            if self.buf_packages[i]['options']['rawsize'] == rawsize:
                                self.buf_packages[i]['options']['rawdata'] = package_content
                                packages.insert(0,self.buf_packages.pop(i))
                                rawsize = 0
                                break
                    #del package_content
                    assert rawsize == 0
                self.buf_data = self.buf_data[package_overhead_len+package_len:]
            else:
                break
        if len(packages):
            commands = ObjshCommand.decodePackages(packages)
            self.handleCommands(commands)
  
    def handleCommands(self,commands):

        def response(the_task):
            try:
                self.send_result(the_task.get_result())
            except Exception as e:
                the_task.command.set_result(1,None,'internal error:%s' % e)
                log.msg('handleCommand Error',traceback.format_exc())
                self.send_result(the_task.get_result())
            self.touch_queue()

        def err_callback(failure,the_task):
            #logger(traceback.format_exc())
            log.msg('handleCommand failure',failure.getErrorMessage())
            the_task.set_result(1,None,'error:%s' % failure.getErrorMessage())
            self.send_result(the_task.get_result())
            self.touch_queue()
        
        #for command in commands:
        #    # specical commands 
        #    if command.cmd in ('quit','exit'):
        #        self.cutoff_connection()
        #        return

        valid_commands = []
        for command in commands:
            # this command already has been set result, most likely it failed to parse
            if command.data.get('retcode') is not None:
                self.send_result(command.get_result())
            else:
                valid_commands.append(command)

        if len(valid_commands)==0: return
        
        # forbidden access (maybe user is from blocked ip)
        #if self.user is None:
        #    command.set_result(1,None,'access denied for none user')
        #    self.send_result(command.get_result())
        #    self.cutoff_connection()
        #    return

        # Run command
        if self.user.authenticated:
            
            # if login or logout appears, just handle it
            for command in valid_commands:
                if command.cmd=='logout':
                    command.set_result(0,'good bye')
                    self.send_result(command.get_result())
                    self.cutoff_connection()
                    return
                # this should not happen actually
                elif command.cmd=='login':
                    command.set_result(0,'already login')
                    self.send_result(command.get_result())
                    return

            # handle all commands other than login, logout
            def create_task(command):            
                try:
                    task = ObjshTask(self,self.user,command)
                    task.deferred.addCallbacks(response,err_callback,errbackArgs=[task])
                    self.queue_tasks([task])
                except:
                    log.msg('command Error',traceback.format_exc())
                    command.set_result(1,None,traceback.format_exc())
                    self.send_result(command.get_result())
            
            def hand_command():
                command = valid_commands.pop(0)
                assert hasattr(command,'_name'), 'not _name %s' % command
                create_task(command)
                if len(valid_commands): reactor.callLater(0,hand_command)
            if len(valid_commands): hand_command()
            #log.msg('queue len:',len(self.queue),'threads:',threading.active_count(),'by',id(threading.currentThread()))
        else:
            # only "login" is allowed
            # drop all other commands but the first
            command = valid_commands[0] 
            
            if command.cmd=='login' and command.args and len(command.args)==2:
                self.user.login(str(command.args[0]),str(command.args[1]))
                if self.user.authenticated:
                    #
                    # enforce to su to another user
                    #
                    #if os.environ['USER']=='root':
                    #    raise NotImplementedError()
                    command.set_result(0,'login succeed')
            
                elif self.user.authentication_failure_count < self.user.max_authentication_failure_count:
                    command.set_result(1,None,'try again')
            
                else:
                    command.set_result(1,None,'good bye')
                    self.cutoff_connection()
            
                self.send_result(command.get_result())
        
            # count as a credit of failure
            else:
                self.user.did_login_failure()
                if self.user.authentication_failure_count < self.user.max_authentication_failure_count:
                    command.set_result(1,'login [username] [password]','Login required, failure count:#%s' % (self.user.authentication_failure_count))
                else:
                    command.set_result(1,None,'good bye')
                    self.cutoff_connection()
                self.send_result(command.get_result())
    
    def cutoff_connection(self):
        log.msg('cutoff_connection is called by ',self)
        reactor.callLater(1,self.transport.loseConnection)

    
    def queue_tasks(self,tasks):
        self.queue.extend(tasks)
        self.touch_queue()
    
    def touch_queue(self):
        """ call this to inform queue to start consum """
        if self._consume_timer is None :
            self._consume_timer = reactor.callLater(0.001,self.consume_queue)
        elif not self._consume_timer.active():            
            self._consume_timer = reactor.callLater(0.001,self.consume_queue)
        elif len(self.queue) > 10:
            # In busy situation,
            # twisted might have some never been called reactor.callLater.
            # no idea if it is an implementation error of me
            # or it is a bug of twisted. (2018/7/14)
            self._consume_timer.cancel()
            self._consume_timer = reactor.callLater(0.001,self.consume_queue)    
    def consume_queue(self):

        if self._consume_timer.active():
            self._consume_timer.cancel()
        self._consume_timer = None
        
        if len(self.queue) == 0:
            return
        
        # max number of co-current handling task
        max_thread = 20

        # extract from queue as soon as possible
        i = 0
        tasks_to_handle = []
        while i < max_thread: 
            try:
                if PY3:
                    task = self.queue.popleft()
                else:
                    task = self.queue.pop(0)
                tasks_to_handle.append(task)
            except IndexError:
                break
            else:
                i += 1
        
        if len(self.queue):
            self._consume_timer = reactor.callLater(0.001,self.consume_queue)

        # run tasks
        for task in tasks_to_handle:
            reactor.callInThread(task.start)
        

class ObjshFactory(ServerFactory):
    #account_provider = None
    protocols = []
    def __init__(self,portal=None):
        self.portal = portal
    def buildProtocol(self, addr):
        try:
            remote_ip = addr.host
            user = ObjshWebUser.get_by_tcp(addr)
            if self.portal: user.portal = self.portal
            # user is not authenticatd at this stage
            proto = ObjshProtocol(user)
            self.protocols.append(proto)
            return proto
        except:
            traceback.print_exc()

__all__ = ['ObjshFactory','ObjshProtocol']