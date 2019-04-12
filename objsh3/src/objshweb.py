#!/usr/bin/env python
#! -*- coding:utf-8 -*-

import os, sys, traceback, __main__, time
PY3 = sys.version_info[0] >= 3
import json
from twisted.internet            import reactor, defer
from twisted.web                 import static, server, resource
from twisted.web.resource        import IResource
from twisted.web.server          import NOT_DONE_YET, Request, Site
from txws_patched                import WebSocketFactory,WebSocketProtocol
from twisted.cred.credentials    import UsernamePassword
from twisted.cred.error          import UnauthorizedLogin
from twisted.python              import log
from objshssh import ObjshAvatar
from objshobjects import ObjshTask, ObjshCommand
from twisted.logger import LogLevel

server.Session.sessionTimeout = 9000

try:
    from urllib import unquote
except ImportError:
    from urllib.parse import unquote

#
# Monkey-patch Request.getSession to add "httpOnly" to session cookie
#
def makeSession(self,uid=None):
        """
        Generate a new Session instance, and store it for future reference.
        """
        if uid is None: uid = self._mkuid()
        session = self.sessions[uid] = self.sessionFactory(self, uid)
        session.startCheckingExpiration()
        return session
Site.makeSession = makeSession

def getSession(self, sessionInterface=None, forceNotSecure=False):
    """
    Check if there is a session cookie, and if not, create it.
    By default, the cookie with be secure for HTTPS requests and not secure
    for HTTP requests.  If for some reason you need access to the insecure
    cookie from a secure request you can set C{forceNotSecure = True}.
    @param forceNotSecure: Should we retrieve a session that will be
        transmitted over HTTP, even if this L{Request} was delivered over
        HTTPS?
    @type forceNotSecure: L{bool}
    """
    # Make sure we aren't creating a secure session on a non-secure page
    secure = self.isSecure() and not forceNotSecure

    if not secure:
        cookieString = b"TWISTED_SESSION"
        sessionAttribute = "_insecureSession"
    else:
        cookieString = b"TWISTED_SECURE_SESSION"
        sessionAttribute = "_secureSession"

    session = getattr(self, sessionAttribute)

    # Session management
    if not session:
        cookiename = b"_".join([cookieString] + self.sitepath)
        sessionCookie = self.getCookie(cookiename)
        if sessionCookie:
            try:
                session = self.site.getSession(sessionCookie)
            except KeyError:
                pass
        # if it still hasn't been set, fix it up.
        if not session:
            session = self.site.makeSession(sessionCookie)
            self.addCookie(cookiename, session.uid, path=b"/",
                           secure=secure, httpOnly=True) ## patched

    session.touch()
    setattr(self, sessionAttribute, session)

    if sessionInterface:
        return session.getComponent(sessionInterface)

    return session
Request.getSession = getSession

#
# let static.File be aware of allow_cross_origin
#
class StaticFile(static.File):
    def __init__(self,*args,**kw):
        super(StaticFile,self).__init__(*args,**kw)
        self.allow_cross_origin = True
    def render(self,request):
        if self.allow_cross_origin:
            request.setHeader('Access-Control-Allow-Origin','*')
            request.setHeader('Access-Control-Allow-Credentials','*')
            
        return super(StaticFile,self).render(request)

class ObjshWebUser(object):
    max_authentication_failure_count = 3
    authentication_failure_count_interval = 60
    users = {}
    
    @classmethod
    def get_by_session(cls,session,portal):
        user_id = 's:%s' % session.uid.decode('utf-8') # to unicode
        user = cls.users.get(user_id)
        if user is None:
            user = cls(user_id,session=session)
            user.portal = portal
            cls.users[user_id] = user
        return user

    @classmethod
    def get_by_tcp(cls,addr):        
        user_id = 'tcp:%s:%s' % (addr.host,addr.port)
        user = cls.users.get(user_id)
        if user is None:
            user = cls(user_id,addr=addr)
            cls.users[user_id] = user
        return user
        
    @classmethod
    def get_by_username(cls,username):
        for user in cls.users.values():
            if user.username == username:
                return user

    def __init__(self,user_id,session=None,addr=None):

        # Caution:
        # user's preferences is implemented in 
        # src/sysstate/default/pub/users, don't double implement it here

        # user_id is created from session_id, 
        # this is not persistent id, for internal use only.
        self.user_id = user_id
        self.session = session # from web
        self.addr = addr       # from socket
        self.authentication_failure_count = 0
        self.last_authentication_failure_ts = 0
        
        self.username = None
        self.authenticated = False
        self.home_path = None
        self.title = ''
        
        #extra data to pass to browser
        self.metadata = {} 
        #extra data not to pass to browser, internally used 
        self.internal_metadata = {}  
        # login type (like sbs) if any
        self.type = None
        
        self.connected_protocols = []
        
        if self.session is not None:
            def expired():
                #print '@' * 200,self.addr,'expired'
                pass
            self.session.notifyOnExpire(expired)
    
    def login(self,username,password):
        try:
            credentials = UsernamePassword(username,password)
            deferred = defer.Deferred()
            def okback(ret,_deferred):
                _interface,objshAvatar,_lambda = ret
                #print '>>>>',_a,objshAvatar,_b
                assert objshAvatar is not None
                self.username = username
                self.authenticated = True
                self.title = username.upper()
                self.avatar = objshAvatar
                # reset login history
                self.authentication_failure_count = 0
                self.last_authentication_failure_ts = 0
                _deferred.callback(True)
            
            def errback(_failure,_deferred):
                errmsg  = _failure.getErrorMessage()
                if errmsg: log.msg('login failure:%s' % errmsg)
                _deferred.callback(False)
            d = self.portal.login(credentials, None, IResource)
            d.addCallback(okback,deferred)
            d.addErrback(errback,deferred)
            return deferred
        except UnauthorizedLogin:
            self.authenticated = False
            self.did_login_failure()
        except:
            traceback.print_exc()

    def did_login_failure(self):
        self.authenticated = False
        now = time.time()
        if self.last_authentication_failure_ts and (now - self.last_authentication_failure_ts) < self.authentication_failure_count_interval:
            self.authentication_failure_count += 1
        else:
            self.last_authentication_failure_ts = now
            self.authentication_failure_count = 1
    
    def logout(self):
        # make no sense if not been authenticated
        if not self.authenticated: return

        self.authenticated = False
        # remove from tracking
        try:
            del self.users[self.user_id]
            if self.session:
                self.session.expire()
                self.session = None
            
        except (ValueError,AttributeError):
            traceback.print_exc()
            pass 
        
        #log.debug('user '+self.username+' logout, connection count #%s' % len(self.connected_protocols))
        
        for protocol in self.connected_protocols:
            #print ['protocol',protocol,'will disconnected from',self]
            reactor.callLater(0,protocol.cutoff_connection)
        self.connected_protocols = []
        
    def add_connected_protocol(self,protocol):
        """
        called when a protocol was connected by websocket
        """
        #assert isinstance(protocol,ObjectiveShellProtocol)
        #print ['protocol',protocol,'added to protocol of',self]
        self.connected_protocols.append(protocol)

    def remove_connected_protocol(self,protocol):
        """
        called when a protocol was lose connection  by websocket
        """
        try:
            self.connected_protocols.remove(protocol)
            #print ['protocol',protocol,'removed to protocol of',self]
        except ValueError:
            # in case of logout
            #print ['protocol',protocol,'is not in protocol of',self]
            pass
    @property
    def serialized_data(self):
        return {'username':self.username,'metadata':self.metadata}  
        
class ObjshWebResource(resource.Resource):
    isLeaf = True
    def __init__(self,*args,**kw):
        self.allow_cross_origin = False
        if PY3:
            super(ObjshWebResource,self).__init__(*args,**kw)
        else:
            resource.Resource.__init__(self,*args,**kw)
    def make_response(self,obj):
        """
        Utility function to convert any object to string befor sending out.(for instant response)
        
        Args:
            obj (:obj:): any json-able objects. Such as dictionary.
            
        Returns:
            string: string in json format.
        """
        try:
            raw = json.dumps(obj)
        except UnicodeDecodeError:
            raw = json.dumps(obj,ensure_ascii=False)
        return raw.encode('utf-8')
    
    def send_object(self,request,obj):
        """
        Utility function to send any object via request. (for delaied response)
        
        Args:
            request (:obj:): the http request.
            obj (:obj:`any`): any json-able objects. Such as dictionary.
            
        """    
        
        request.write(self.make_response(obj))

class ObjshWebLogin(ObjshWebResource):
    """Twisted web resources for login"""
    def __init__(self,portal,max_failure,websocket_options):
        ObjshWebResource.__init__(self)
        self.portal = portal
        self.max_failure = max_failure or 10
        self.websocket_options = websocket_options
        
        # login request can pass a "type" parameter to select
        # which handler to do authentication.
        #
        # type(string):handler(callable)
        # should return True if passed
        #
        self.type_handler = {}

    def get_user(self,request):
        return ObjshWebUser.get_by_session(request.getSession(),self.portal)

    def render_POST(self,request):
        return self.render_GET(request)
    
    def render_GET(self,request):
        """
        handle requests like
        /login/username<space>password
        /login/username/password
        /login?username=&password=

        /logout
        /logout?next=URL
        """
        paths = unquote(request.path.decode('utf-8')).split('/')

        command = paths[1]
        
        # only /login, /logout allowed
        assert command in ('login','logout')

        user = self.get_user(request)
        client_ip = request.transport.getPeer().host
        
        if self.allow_cross_origin:
            request.setHeader('Access-Control-Allow-Origin','*')
            request.setHeader('Access-Control-Allow-Credentials','*')

        #print 'command = ',command,'user.authenticated',user.authenticated
        __main__.statetree.emit('UserRequestLogin',user.username)
        
        session = request.getSession()
        
        if command == 'login' and user.authenticated:
            session.touch()
            log.info('User '+user.username+' login from '+client_ip)
            return self.make_response({'retcode':0,'stdout':self.success_login_metadata(user)})
        
        elif command == 'logout':
            if user.authenticated:
                log.debug('user '+user.username+' logout from '+client_ip)
                user.logout()
            next_url = request.args.get(b'next',[None])[0]
            if next_url:
                #http://127.0.0.1:2880/logo?next=http://127.0.0.1:2880/app/whiteboard.html
                assert not next_url.startswith(b'/logout')
                request.setResponseCode(302)
                request.setHeader('Location',next_url.decode())
                return b'bye'
            else:
                return self.make_response({'retcode':0,'stdout':'Good-bye'})
        

        def login_failed(request):
            request.setResponseCode(403)
            user.did_login_failure()
            if user.authentication_failure_count < self.max_failure:
                # diffrent message to hind the failure point (developing)
                log.warn('login failured from '+client_ip)
                request.write(b'Login failure, try again')
                request.finish()
            else:
                log.warn('login failures over '+str(self.max_failure)+' times from '+client_ip)
                request.write(b'Too many failure, good bye')
                request.finish()

        # do login starts
        login_type = request.args.get(b'type',[None])[0]
        if login_type:
            # A customized mechanism to do login
            # 1. Register a type-handler in server side
            try:
                ok = self.type_handler[login_type.decode()](user,request)
            except Exception as e:
                log.warn('login failure, type=%s, e=%s' % (login_type,e))
                login_failed(request)
                return NOT_DONE_YET
        else:
            # re-compose command line, accepts following formats
            # /login/username<space>password
            # /login/username/password
            # /login?username=&password=
            message = ''
            username = ''
            password = ''
            if len(paths[2:]):
                line = 'login '+(' '.join(paths[2:]))
                commands = ObjshCommand.decodeChunks([line])
                # only 1 command supported per request
                command = commands[0]
            
                #log.msg('line = '+line+'; args=',command.args)
                username = str(command.args[0]) if len(command.args) > 0 else ''
                password = str(command.args[1]) if len(command.args) > 1 else ''

            elif request.args.get(b'username'):
                username = request.args[b'username'][0].decode('utf-8').strip()
                password = request.args.get(b'password',[b''])[0].decode('utf-8').strip()

            else:
                message = 'access denied!'
            
            message = 'unauthorized %s' % time.time()

            if not (username and password):
                login_failed(request)
                return NOT_DONE_YET
            
            # user.login is an inline callback, so the following line is blocking code
            try:
                log.debug('login with',[username, password])
                ok = user.login(username, password)
            except:
                traceback.print_exc()
        
        if isinstance(ok,defer.Deferred):
            def next(ret,request):
                if user.authenticated:
                    # succeed to login
                    log.info('A user '+user.username+' login from '+client_ip)

                    # enforce to su to another user
                    #if os.environ['USER']=='root':  raise NotImplementedError()
                    self.send_object(request,{'retcode':0,'stdout':self.success_login_metadata(user)})
                    request.finish()
                else:
                    login_failed(request)
            def err(failure,request):
                errmsg = failure.getErrorMessage()
                if errmsg: log.msg('auth error:%s' % errmsg)
                login_failed(request)
            ok.addCallback(next,request)
            ok.addErrback(err,request)
            return NOT_DONE_YET
        elif user.authenticated:
            log.info('USER '+user.username+' login from '+client_ip)
            return self.make_response({'retcode':0,'stdout':self.success_login_metadata(user)})
        else:
            login_failed(request)
            return NOT_DONE_YET

    def success_login_metadata(self,user):
        return {
            'statetree_runner_name': __main__.statetree.runner_name,
            'server_name':__main__.config.general['server_name'],
            'objsh_version':__main__.config.objsh['version'],
            'user':user.serialized_data,
            'resource_route_name':__main__.statetree.route_name,
            #playground需要這個用來校正websocket資料
            'websocket_options': self.websocket_options
        }

class PrivateFile(StaticFile):
    def __init__(self,portal,path):
        #static.File.__init__(self,path)
        super(PrivateFile,self).__init__(path)
    def render_GET(self,request):
        user = ObjectiveShellSiteRoot.singleton.login_resource.get_user(request)
        if not user.authenticated:
            request.setResponseCode(403)
            return 'Forbidden'
        return super(PrivateFile,self).render_GET(request)

class ObjshWebRun(ObjshWebResource):
    """Twisted web resources for executing runners.
    Attributes:
        running_tasks (list): tasks in running.
        factory (:obj:): instance of Factory
        runner (:obj:): instance of ObjectiveShellRunner
    """
    
    def __init__(self,portal):
        self.portal = portal
        resource.Resource.__init__(self)
    
    def render_GET(self,request):

        session = request.getSession()
        user = ObjshWebUser.get_by_session(session,self.portal)
        
        # do authentication first
        if not user.authenticated:
            #return self.authenticate(request,command,user)
            request.setResponseCode(403)
            return 'access denied'

        paths = unquote(request.path.decode('utf-8')).split('/')
        # only /run allowed
        assert (paths[0]=='' and paths[1]=='run')
    
        if self.allow_cross_origin:
            request.setHeader('Access-Control-Allow-Origin','*')
            request.setHeader('Access-Control-Allow-Credentials','*')
            
        # compose command line
        line = '/'.join(paths[2:])
        commands = ObjshCommand.decodeChunks([line])
        if not len(commands): return 'please see help'
        # only 1 command supported per request
        command = commands[0]

        # handle login, logout again
        if command.cmd=='logout':
            # session.expire() will be called by user.logout()
            user.logout() 
            command.set_result(0,'good bye')
            return self.make_response(command.get_result())
            
        # maybe user reloads webpage
        #elif command.cmd=='login':
        #    session.touch()
        #    command.set_result(0,'already login')
        #    return self.make_response(command.get_result())
        
        # handle other command
        else:
            session.touch()
            def response(the_task):
                self.send_object(request,the_task.get_result())
                request.finish()
        
            def err_callback(failure,the_task):
                the_task.set_result(1,failure.getMessage())
                self.send_object(request,the_task.get_result())
                request.finish()

            try:
                task = ObjshTask(self,user,command)
                #print ['task',task]
                task.deferred.addCallbacks(response,err_callback,errbackArgs=[task])
                task.start()
                return NOT_DONE_YET
            except:
                log.msg('Error',traceback.format_exc())
                command.set_result(False,traceback.format_exc())
                return self.make_response(command.get_result())
    
    '''
    #Not implemented yet
    def render_POST(self,request):
        print 'post ' * 20,request
        with open(request.args['filename'][0], 'wb') as fd:
            fd.write(request.content.read())
        request.setHeader('Content-Length', os.stat(request.args['filename'][0]).st_size)
        with open(request.args['filename'][0], 'rb') as fd:
            request.write(fd.read())
        request.finish()
        return server.NOT_DONE_YET
    '''

class ObjectiveShellSiteRoot(StaticFile):
    """
        An instance of ObjectiveShellSiteRoot will be created
        every time the web root url is requested.
    """
    isLeaf = False
    websdk_folder = os.path.join(os.path.abspath(os.path.dirname(__file__)),'websdk')
    
    singleton = None
    _callbacks = None
    @classmethod
    def get_singleton(cls,*args,**kw):
        if cls.singleton: return cls.singleton
        cls.singleton = cls(*args,**kw)
        if cls._callbacks:
            def callback_singleton_listeners():
                for callback in cls._callbacks:
                    callback(cls.singleton)
            reactor.callLater(0,callback_singleton_listeners)
        return cls.singleton
    @classmethod
    def call_when_singleton_created(cls,callable):
        if cls._callbacks is None:
            cls._callbacks = [callable]
        else:
            cls._callbacks.append(callable)

    def __init__(self, path, defaultType="text/html", ignoredExts=(), registry=None, allowExt=0,portal=None,daemon_options=None):
        self.portal = portal

        #debuging only
        # preparing initial arguments for static.File
        assert isinstance(daemon_options,dict),'daemon_options should be dict instance not %s' % daemon_options
        htdocs_settings = daemon_options['htdocs']
        setting = htdocs_settings['/']
        assert os.path.exists(setting['path'])
        root = htdocs_settings['/']
        #static.File.__init__(self,root['path'] if path is None else path)
        super(ObjectiveShellSiteRoot,self).__init__(root['path'] if path is None else path)

        allow_cross_origin = daemon_options.get('allow_cross_origin',False)
        self.allow_cross_origin = allow_cross_origin
        
        self.login_resource = ObjshWebLogin(portal,daemon_options.get('max_failure'),daemon_options.get('websocket'))
        self.login_resource.allow_cross_origin = allow_cross_origin

        self.run_resource = ObjshWebRun(portal)
        self.run_resource.allow_cross_origin = allow_cross_origin

        # special file: index.html, use this to decide where is root_folder
        if os.path.exists(os.path.join(root['path'],'index.html')):
            root_folder = root['path']
            sf = StaticFile(os.path.join(root_folder,'index.html'))
            sf.allow_cross_origin = allow_cross_origin
            self.putChild(b'',sf)
        else:
            root_folder = self.websdk_folder
            sf = StaticFile(os.path.join(self.websdk_folder,'default_index.html'))
            sf.allow_cross_origin = allow_cross_origin
            self.putChild(b'',sf)
        
        # files, folders in root folder should be added one-by-one
        for file in os.listdir(root_folder):
            # ignore .*, _*.* files
            if file[0] in ('.','_') : continue
            path = os.path.join(root_folder,file)
            if isinstance(file,str):
                file = file.encode('utf-8')
            sf = StaticFile(path)
            sf.allow_cross_origin = allow_cross_origin
            self.putChild(file,sf)

        for file in ('favicon.ico','robots.txt'):
            if os.path.exists(os.path.join(root['path'],file)):
                sf = StaticFile(os.path.join(root['path'],file))
                sf.allow_cross_origin = allow_cross_origin
                self.putChild(file.encode('utf-8'),sf)
            else:
                sf = StaticFile(os.path.join(self.websdk_folder,file))
                sf.allow_cross_origin = allow_cross_origin
                self.putChild(file.encode('utf-8'),sf)
        
        for webpath,setting in htdocs_settings.items():
            if webpath=='/': continue
            assert os.path.exists(setting['path']),'path not found:%s' % setting['path']
            _webpath = webpath.replace('/','')
            assert _webpath not in ('websdk','login','logout','run') , '/%s is reserved' % _webpath
            if setting['public']:
                sf = StaticFile(setting['path'])
                sf.allow_cross_origin = allow_cross_origin
                self.putChild(_webpath.encode('utf-8'),sf)
            else:
                pf = PrivateFile(portal,setting['path'])
                pf.allow_cross_origin = allow_cross_origin
                self.putChild(_webpath.encode('utf-8'),pf)
        
        #
        # /websdk, /login, /logout, /run are resererved route
        #
        self.putChild(b'websdk',StaticFile(self.websdk_folder))
        self.putChild(b'login',self.login_resource)
        self.putChild(b'logout',self.login_resource)
        self.putChild(b'run',self.run_resource)

class AuthWebSocketProtocol(WebSocketProtocol):
    site = None
    secure_site = None
    do_binary_frames = True
    def validateHeaders(self):
        
        if not WebSocketProtocol.validateHeaders(self): return False
        
        cookie = str(self.headers.get('Cookie'))
        # no cookie, if user has been login success, this should not happen
        # unless the cookie is disabled
        if not cookie: return False
        
        # REF: https://github.com/twisted/twisted/blob/twisted-17.9.0/src/twisted/web/server.py#L431
        # REF: https://github.com/BITalinoWorld/python-serverbit/blob/master/txws.py
        session_cookie = None
        if self.isSecure():
            q = cookie.find('TWISTED_SECURE_SESSION=') # length=23
            if q >= 0:
                e = cookie.find(';',q)
                session_cookie = cookie[q+23:] if e==-1 else cookie[q+23:e]
        else:
            p = cookie.find('TWISTED_SESSION=') # length=16
            if p >= 0: 
                e = cookie.find(';',p)
                session_cookie = cookie[p+16:] if e==-1 else cookie[p+16:e]
        
        # before calling websocket, we suppose user has been login
        if session_cookie is None:
            # but for autotesting (not from browser), it has not cookie
            return False

        try:
            if self.isSecure():
                session = self.secure_site.getSession(session_cookie.encode('utf-8'))
            else:
                session = self.site.getSession(session_cookie.encode('utf-8'))
            user = ObjshWebUser.users['s:'+session.uid.decode('utf-8')]
        except KeyError:
            return False
        except Exception as e:
            #print ('AuthWebSocketProtocol Error',[e])
            traceback.print_exc()
            return False
        else:            
            #if not session: return False
            # self.wrappedProtocol is an instance of ObjectiveShellProtocol
            # self.wrappedProtocol.user is not authenticated yet.
            # we replace it with the authenticated user instance which is created by the web daemon
            if not user.authenticated:
                return False
            user.addr = self.wrappedProtocol.user.addr
            user.add_connected_protocol(self.wrappedProtocol)
            self.wrappedProtocol.set_user(user)
            #log.debug('set websocket user to',user.username)
            return True

#
# Borrowed from 
# https://github.com/crossbario/autobahn-python/blob/master/autobahn/twisted/resource.py
#
try:
    # noinspection PyUnresolvedReferences
    from twisted.web.error import NoResource
except ImportError:
    # starting from Twisted 12.2, NoResource has moved
    from twisted.web.resource import NoResource
from twisted.protocols.policies import ProtocolWrapper
class WebSocketResource(object):
    """
    A Twisted Web resource for WebSocket.
    """
    isLeaf = True

    def __init__(self, factory):
        """
        :param factory: An instance of :class:`autobahn.twisted.websocket.WebSocketServerFactory`.
        :type factory: obj
        """
        self._factory = factory

    # noinspection PyUnusedLocal
    def getChildWithDefault(self, name, request):
        """
        This resource cannot have children, hence this will always fail.
        """
        return NoResource("No such child resource.")

    def putChild(self, path, child):
        """
        This resource cannot have children, hence this is always ignored.
        """

    def render(self, request):
        """
        Render the resource. This will takeover the transport underlying
        the request, create a :class:`autobahn.twisted.websocket.WebSocketServerProtocol`
        and let that do any subsequent communication.
        """
        # Create Autobahn WebSocket protocol.
        #
        protocol = self._factory.buildProtocol(request.transport.getPeer())
        if not protocol:
            # If protocol creation fails, we signal "internal server error"
            request.setResponseCode(500)
            return b""

        # Take over the transport from Twisted Web
        #
        transport, request.channel.transport = request.channel.transport, None

        # Connect the transport to our protocol. Once #3204 is fixed, there
        # may be a cleaner way of doing this.
        # http://twistedmatrix.com/trac/ticket/3204
        #
        if isinstance(transport, ProtocolWrapper):
            # i.e. TLS is a wrapping protocol
            transport.wrappedProtocol = protocol
        else:
            transport.protocol = protocol
        
        #protocol is AuthWebSocketProtocol
        protocol.makeConnection(transport)

        # On Twisted 16+, the transport is paused whilst the existing
        # request is served; there won't be any requests after us so
        # we can just resume this ourselves.
        # 17.1 version
        if hasattr(transport, "_networkProducer"):
            transport._networkProducer.resumeProducing()
        # 16.x version
        elif hasattr(transport, "resumeProducing"):
            transport.resumeProducing()

        # We recreate the request and forward the raw data. This is somewhat
        # silly (since Twisted Web already did the HTTP request parsing
        # which we will do a 2nd time), but it's totally non-invasive to our
        # code. Maybe improve this.
        #
        if PY3:

            data = request.method + b' ' + request.uri + b' HTTP/1.1\x0d\x0a'
            for h in request.requestHeaders.getAllRawHeaders():
                data += h[0] + b': ' + b",".join(h[1]) + b'\x0d\x0a'
            data += b"\x0d\x0a"
            data += request.content.read()

        else:
            data = "%s %s HTTP/1.1\x0d\x0a" % (request.method, request.uri)
            for h in request.requestHeaders.getAllRawHeaders():
                data += "%s: %s\x0d\x0a" % (h[0], ",".join(h[1]))
            data += "\x0d\x0a"
        protocol.dataReceived(data)
        return NOT_DONE_YET
# end of WebSocketResource
__all__ = ['ObjshWebUser','ObjshWebResource','ObjshWebLogin','ObjectiveShellSiteRoot','AuthWebSocketProtocol','WebSocketResource']