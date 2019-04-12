#! -*- coding:utf-8 -*-
#
# REF for interfaces:
#   https://zopeinterface.readthedocs.io/en/latest/adapter.html#multi-adapters
#
global options
from singleton import Singleton
from zope.interface import Interface, Attribute, implements, implementer
from twisted.python.components import registerAdapter
from twisted.internet.protocol import Factory
from twisted.web.server import Session
import time

class IAccountProvider(Interface):
    factory = Attribute('the factory which this provider service for ')
    def get_user(ip,session=None):
        """
        Args:
            ip: ip address
            session:optional, instance of twisted session
        return:
            an IUser instance, or None to reject login
        """
        

class IAdminAccountProvider(Interface):
    factory = Attribute('the factory which this provider service for ')

class IUser(Interface):
    ip = Attribute("the IP address coming from")
    authentication_failure_count = Attribute('login failure count')
    max_authentication_failure_count = Attribute('max number of login failure during a given interval')
    
    name = Attribute("username, unique value of a user")
    authenticated = Attribute("where this user has successfully authenticated")
    home_path = Attribute("absolute path of user's home folder")
    title = Attribute("user's display name")
    def login(username,password):
        """
        if success, self.authenticated would be True, and self.name would be username
        
        return boolean for success or failuser.
        """
    def did_login_failure():
        """
        when this user failed to login, this is called to do some counting.
        
        return None
        """
    def logout():
        """
        clean up
        
        return None
        """

@implementer(IAccountProvider)
class LocalAccountProvider(Singleton):
    #implements(IAccountProvider)
    def __init__(self,factory):
        self.factory = factory
    
    def get_user(self,ip,session=None):
        if session:
            user = ObjshLocalUser.users.get(session)
            if user is None:
                user = ObjshLocalUser(ip)
                ObjshLocalUser.users[session] = user
                #
                # trigger session cleanup
                #
                def cleanup_session(_session):
                    del ObjshLocalUser.users[_session]
                session.notifyOnExpire(lambda : cleanup_session(session))
                session.startCheckingExpiration()
            return user
        else:
            allowed = False
            users = ObjshLocalUser.users.get(ip)
            if users is None or len(users)==0:
                allowed = True
            else:
                user = users[-1]
                now = time.time()
                if user.authentication_failure_count < ObjshLocalUser.max_authentication_failure_count\
                   or (now - user.last_authentication_failure_ts) >  ObjshLocalUser.authentication_failure_count_interval:
                   allowed = True
            if allowed:
                return ObjshLocalUser(ip)
            else:
                return None

class LocalAdminAccountProvider(LocalAccountProvider):
    implements(IAdminAccountProvider)

registerAdapter(LocalAccountProvider,Factory,IAccountProvider)
registerAdapter(LocalAdminAccountProvider,Factory,IAdminAccountProvider)

class ObjshLocalUser(object):
    implements(IUser)
    max_authentication_failure_count = 3
    authentication_failure_count_interval = 60
    users = {}
    def __init__(self,ip):
        self.ip = ip
        users = self.users.get(ip)
        if users:
            if len(users):
                #
                # recover failure count from previous object
                #
                self.authentication_failure_count = users[-1].authentication_failure_count
                self.last_authentication_failure_ts = users[-1].last_authentication_failure_ts
            else:
                self.authentication_failure_count = 0
                self.last_authentication_failure_ts = 0
            users.append(self)
        else:
            self.users[ip] = [self]
            self.authentication_failure_count = 0
            self.last_authentication_failure_ts = 0
        
        self.name = None
        self.authenticated = False
        self.home_path = None
        self.title = ''
    
    def login(self,username,password):
        
        #passed = username=='iap' and password=='1234'
        passed = True
        if passed:
            self.name = username
            self.authenticated = True
            self.title = username.upper()
            self.authentication_failure_count = 0
        else:
            self.did_login_failure()
        return passed
    
    def did_login_failure(self):
        self.authenticated = False
        now = time.time()
        if self.last_authentication_failure_ts and (now - self.last_authentication_failure_ts) < self.authentication_failure_count_interval:
            self.authentication_failure_count += 1
        else:
            self.last_authentication_failure_ts = now
            self.authentication_failure_count = 1
    
    def logout(self):
        #
        # make no sense if not been authenticated
        #
        if not self.authenticated: return
        #
        # reset
        #
        self.last_authentication_failure_ts = 0
        self.authentication_failure_count = 0
        self.authenticated = False
        #
        # remove from tracking
        #
        try:
            self.users.get(self.ip).remove(self)
        except (ValueError,AttributeError):
            #self.users has not key of self.ip, or self is not in self.users[self.ip]
            pass 
        
import pam
class ObjshSystemUser(object):
    implements(IUser)
    auth = pam.pam()
    #
    # keep a mapping from ip to <user> for telnet channel
    #
    users = {}
    #
    # keep a mapping from session to <user> for http channel
    #
    sessions = {}
    # count authentication_failure_count within allowed_interval
    # aks recount authentication_failure_count after allowed_interval
    allowed_interval = 360 # 6min
    max_failure_count = 3
    #
    # keep a cached failure login of ip to protect from try-password attack
    #
    failure_login_ip = {}
    def __init__(self,ip):
        self.ip = ip
        try:
            ObjectiveShellUser.users[ip].append(self)
        except KeyError:
            ObjectiveShellUser.users[ip] = []
        
        
        self.name = None
        self.authenticated = False

        self.authentication_failure_count = 0
        self.authentication_failure_ts = 0
    
    @property
    def home_path(self):
        if not self.authenticated: return None
        return '/Users/'+self.name
    
    def login(self,username,password):
        self.authenticated = ObjectiveShellUser.auth.authenticate(username,password)
        if self.authenticated:
            self.name = username
            if ObjectiveShellUser.failure_login_ip.get(self.ip) is not None:
                del ObjectiveShellUser.failure_login_ip[self.ip]
        else:
            self.did_login_failure()
    
    def did_login_failure(self):
        now = time.time()
        if self.authentication_failure_ts and (now - self.authentication_failure_ts) < ObjectiveShellUser.allowed_interval:
            self.authentication_failure_count += 1
        else:
            self.authentication_failure_count = 1
        self.authentication_failure_ts = now

        ObjectiveShellUser.failure_login_ip[self.ip] = (self.authentication_failure_count,now)
    
    @classmethod
    def login_allowed(cls,ip):
        #
        # check if we should unlock this ip
        # 
        record = ObjectiveShellUser.failure_login_ip.get(ip)
        if record is None: return True
        elif (time.time()-record[1] > ObjectiveShellUser.allowed_interval):
            del ObjectiveShellUser.failure_login_ip[ip]
            return True
        elif record[0]<ObjectiveShellUser.max_failure_count:
            return True
        else:
            return False
    
    @classmethod
    def remove_user(cls,user):
        users = cls.users.get(user.ip)
        if not users: return
        cls.users[user.ip].remove(user)
    
    #
    # delegations for http daemon
    #
    @classmethod
    def get_user_of_session(cls,request):
        session = request.getSession()
        user = cls.sessions.get(session)
        if not user:
            user = cls(request.getClientIP())
            cls.sessions[session] = user
            print ('create user:%s for session:%s' % (id(user),id(session)))
        return user
    
    @classmethod
    def del_user_of_session(cls,request):
        session = request.getSession()
        user = cls.sessions.get(session)
        if user:
            del cls.sessions[session]
            cls.remove_user(user)
            print ('delete user:%s for session:%s' % (id(user),id(session)))
