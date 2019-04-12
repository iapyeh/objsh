#! -*- coding:utf-8 -*-

"""
SSH server implementation.

For ssh you can use:

$ ckeygen -t rsa -f ssh-keys/ssh_host_rsa_key
$ ckeygen -t rsa -f ssh-keys/client_rsa

Re-using DH primes and having such a short primes list is dangerous, generate
your own primes.

In this example the implemented SSH server identifies itself using an RSA host
key and authenticates clients using username "user" and password "password" or
using a SSH RSA key.

# Clean the previous server key as we should now have a new one
$ ssh-keygen -f ~/.ssh/known_hosts -R [localhost]:5022
# Connect with password
$ ssh -p 5022 -i ssh-keys/client_rsa user@localhost
# Connect with the SSH client key.
$ ssh -p 5022 -i ssh-keys/client_rsa user@localhost
"""

import pam,os,traceback,sys
PY3 = sys.version_info[0] == 3
from collections import deque
from twisted.conch.ssh.factory import SSHFactory
from twisted.conch.ssh.transport import SSHServerTransport
from twisted.conch.ssh import keys as ssh_keys
from twisted.conch.ssh import userauth, connection, session
from twisted.conch.interfaces import IConchUser
from twisted.cred import portal as cred_portal
from twisted.cred.error import UnauthorizedLogin
from twisted.cred import checkers, credentials
from twisted.cred.checkers import (
                ICredentialsChecker,
                InMemoryUsernamePasswordDatabaseDontUse,
                AllowAnonymousAccess)
from twisted.conch.telnet import (
                ITelnetProtocol,
                AlreadyNegotiating,
                AuthenticatingTelnetProtocol,
                TelnetTransport)                                  
from twisted.cred.credentials import IUsernamePassword
from twisted.cred.credentials import UsernamePassword
from twisted.conch.checkers import SSHPublicKeyChecker, InMemorySSHKeyDB
from twisted.conch import avatar
from twisted.python import components, log, failure
from twisted.internet import reactor, defer
from twisted.internet.protocol import ServerFactory
from twisted.web.resource import IResource
from zope.interface import implementer,implements

# monkey patch to set a flag on SSHSessionProcessProtocol
# users can set SSHSessionProcessProtocol.use_objshcommand_delimiter to True
# to use ObjshCommand.boundary as delimiter to send json string (maybe for auto testing)
from twisted.conch.ssh.session import SSHSessionProcessProtocol
SSHSessionProcessProtocol.use_objshcommand_delimiter = False

# Pre-computed big prime numbers used in Diffie-Hellman Group Exchange as
# described in RFC4419.
# This is a short list with a single prime member and only for keys of size
# 1024 and 2048.
# You would need a list for each SSH key size that you plan to support in your
# server implementation.
# You can use OpenSSH ssh-keygen to generate these numbers.
# See the MODULI GENERATION section from the ssh-keygen man pages.
# See moduli man pages to find out more about the format used by the file
# generated using ssh-keygen.
# For Conch SSH server we only need the last 3 values:
# * size
# * generator
# * modulus
#
# The format required by the Conch SSH server is:
#
# {
#   size1: [(generator1, modulus1), (generator1, modulus2)],
#   size2: [(generator4, modulus3), (generator1, modulus4)],
# }
#
# twisted.conch.openssh_compat.primes.parseModuliFile provides a parser for
# reading OpenSSH moduli file.
#
# Warning! Don't use these numbers in production.
# Generate your own data.
# Avoid 1024 bit primes https://weakdh.org
#


class ObjectiveShellSshFactory(SSHFactory):
    """
    This is the entry point of our SSH server implementation.

    The SSH transport layer is implemented by L{SSHTransport} and is the
    protocol of this factory.

    Here we configure the server's identity (host keys) and handlers for the
    SSH services:
    * L{connection.SSHConnection} handles requests for the channel multiplexing
      service.
    * L{userauth.SSHUserAuthServer} handlers requests for the user
      authentication service.
    """
    #protocol = SSHServerTransport
    # Server's host keys.
    # To simplify the example this server is defined only with a host key of
    # type RSA.
    # Service handlers.
    #services = {
    #    b'ssh-userauth': userauth.SSHUserAuthServer,
    #    b'ssh-connection': connection.SSHConnection
    #}
    
    # a list for currently connected protocols (aka clients)
    # for management purpose
    protocols = []

    runner = None
    
    def __init__(self,options):
        self.publicKeys = {
            b'ssh-rsa': ssh_keys.Key.fromFile(options['server_rsa_public'])
        }
        self.privateKeys = {
            b'ssh-rsa': ssh_keys.Key.fromFile(options['server_rsa_private'],passphrase=options['server_rsa_private_passphrase'])
        }
        self.primes = options['primes']
    
    def buildProtocol(self, addr):
        """
         Pending: Do IP based authentication here
         for example: assert addr.host=='127.0.0.1'
        """

        # protocol is wisted.conch.ssh.transport.SSHServerTransport instance
        protocol = SSHFactory.buildProtocol(self,addr)

        return protocol

    def getPrimes(self):
        """
        See: L{factory.SSHFactory}
        """
        self.primes

class ObjshAvatar(avatar.ConchUser):
    def __init__(self, protocol_class, username):
        avatar.ConchUser.__init__(self)
        self.protocol_class = protocol_class
        self.username = username
        
        # will be assigned later
        self.addr = None
        self.session = None
        
        self.channelLookup.update({b'session':session.SSHSession})
        
        # adapt to objsh system
        self.authenticated = True

        # a cache-like object to store custom data
        self.metadata = {}

    # adapt to objsh system
    def logout(self):
        #log.msg('------ avatar %s logout----' % self.username)
        pass
    
    def add_connected_protocol(self,prop):
        """
        because every ssh connection create only one user instance,
        we don't need to bother protocols management like websocket.
        """
        pass

    def remove_connected_protocol(self,prop):
        """
        because every ssh connection create only one user instance,
        we don't need to bother protocols management like websocket.
        """
        pass

@implementer(cred_portal.IRealm)
class ObjshRealm(object):
    """
    When using Twisted Cred, the pluggable authentication framework, the
    C{requestAvatar} method should return a L{avatar.ConchUser} instance
    as required by the Conch SSH server.
    """
    
    def __init__(self,protocol_class):
        self.protocol_class = protocol_class
        
    def requestAvatar(self, avatarId, mind, *interfaces):
        """
        See: L{portal.IRealm.requestAvatar}
        """
        try:
            #telnet
            if ITelnetProtocol in interfaces:
                user = ObjshAvatar(self.protocol_class,avatarId)
                av = self.protocol_class(user)
                #av.state = 'Command'
                return (ITelnetProtocol,
                       av,
                       lambda: None)

            # twisted.conch.interfaces.IConchUser
            # ssh
            elif IConchUser in interfaces:
                return (interfaces[0],
                       ObjshAvatar(self.protocol_class,avatarId),
                       lambda: None)
            # web
            elif IResource in interfaces:
                return (IResource, 
                    ObjshAvatar(self.protocol_class,avatarId),
                    lambda: None)
            else:
                raise NotImplementedError('%s is not implemented' % interfaces)
        except:
            log.msg(traceback.print_exc())

class SSHSession(object):
    """
    This selects what to do for each type of session which is requested by the
    client via the SSH channel of type I{session}.
    """
    
    def __init__(self, avatar):
        """
        In this example the avatar argument is not used for session selection,
        but for example you can use it to limit I{shell} or I{exec} access
        only to specific accounts.
        """
        self.avatar = avatar
        self.avatar.session = self
        self.protocol_class = self.avatar.protocol_class  # ObjectiveShellProtocol
        self.is_pty = False

    def getPty(self, term, windowSize, attrs):
        """
        This will be called before openShell() when user runs
        $ ssh user@localhost -p 22
        """
        self.is_pty = True
        #log.msg('ssh get pty requeset with term=%s, windowSize=%s, attrs=%s' % (term, windowSize,attrs))

    def openShell(self, proto):
        """
        Use our protocol as shell session.
        
        Arguments:
            proto: is a twisted.conch.ssh.session.SSHSessionProcessProtocol object

        * SSHAutoTester in autotest.py goes this way.
        * self.protocol is a objshshell.ObjshProtocol object
        """
        if self.is_pty:
            log.msg('shell opened by pty')
        else:
            log.msg('shell not opened by pty')
        self.avatar.addr = proto.getPeer().address
        self.remote_ip = self.avatar.addr.host
        self.protocol = self.protocol_class(self.avatar)
                
        # Connect the new protocol to the transport and the transport
        # to the new protocol so they can communicate in both directions.        
        self.protocol.makeConnection(proto)
        proto.makeConnection(session.wrapProtocol(self.protocol))
    def execCommand(self, proto, cmd):
        """
        Support command execution sessions.

        Arguments:
            proto: is an instance of SSHSessionProcessProtocol
        """
        self.avatar.addr = proto.getPeer().address
        self.remote_ip = self.avatar.addr.host
        self.protocol = self.protocol_class(self.avatar)

        # Connect the new protocol to the transport and the transport
        # to the new protocol so they can communicate in both directions.
        self.protocol.makeConnection(proto)
        proto.makeConnection(session.wrapProtocol(self.protocol))
        # execute command might also requires get_pty
        #assert not self.is_pty

        # in case, there is no new line at the file end
        end = '' if cmd[-1] in ('\r','\n') else '\n'
        self.protocol.rawDataReceived(cmd+end+'EOF\n')
    
    def eofReceived(self):
        """
        Called when reach file end when user run "$ ssh -t server:port < file"
        """
        #log.msg('~~~~~~ssh eofReceived~~~~~~~')
        
        # in case, there is no new line at the file end
        self.protocol.rawDataReceived(b'\n')
        
        # enforce to disconnect
        self.protocol.rawDataReceived(b'EOF\n')

    def closed(self):
        """
            "Exit" was called
        """
        #log.msg('~~~~~~ssh session from %s closed~~~~~~~' % self.avatar.addr)
        self.protocol.connectionLost('ssh section closed')

#SSHSession enables ObjshAvatar to provide session.ISession
components.registerAdapter(SSHSession, ObjshAvatar, session.ISession)

@implementer(ICredentialsChecker)
class CascadingChecker:
    """
    Check multiple checkers untill one succeeds.
    Else raise UnauthorizedLogin.
    
    Credit: http://pepijndevos.nl/check-multiple-twistedcred-checkers-for-a-val/index.html
    """

    #implements(ICredentialsChecker)
    credentialInterfaces = set() #ISSHPrivateKey
    
    def __init__(self):
        self.checkers = []
        self.checked = []
    
    def registerChecker(self, checker):
        self.checkers.append(checker)
        self.credentialInterfaces.update(checker.credentialInterfaces)
    
    def _requestAvatarId(self, err, queue, credentials):
        # disallow empty password to be authenticated
        if IUsernamePassword.providedBy(credentials) and \
            ((not credentials.password) or (credentials.username=='root')):
            raise UnauthorizedLogin()
        try:
            ch = queue.popleft()
        except IndexError:
            raise UnauthorizedLogin()
        d = ch.requestAvatarId(credentials)
        return d.addErrback(self._requestAvatarId, queue, credentials)
    
    #requestAvatarId = lambda self, credentials: self._requestAvatarId(None, deque(self.checkers), credentials)
    def requestAvatarId(self,credentials):
        if PY3 and isinstance(credentials.username, bytes):
                credentials.username = credentials.username.decode()
                credentials.password = credentials.password.decode()
        return self._requestAvatarId(None, deque(self.checkers), credentials)

@implementer(ICredentialsChecker)
class PamPasswordDatabase(object):
    """Authentication/authorization backend using the 'login' PAM service"""
    
    credentialInterfaces = IUsernamePassword,
    #implements(ICredentialsChecker)
 
    def __init__(self,allow_pam_usernames,pam_username_prefix):
        assert isinstance(allow_pam_usernames,tuple)
        self.allow_pam_usernames = allow_pam_usernames
        self.pam_username_prefix = pam_username_prefix
        self.allow_all = '*' in self.allow_pam_usernames 
        self.authenticate = pam.pam().authenticate
        
    def requestAvatarId(self, credentials):
        #log.msg('ssh handling login of ',self.pam_username_prefix+('+' if self.pam_username_prefix else '')+credentials.username)
        #print("@@@@@",[self.pam_username_prefix , credentials.username, credentials])
        username = self.pam_username_prefix + credentials.username
        # check the given username is allow to access or not
        if (not self.allow_all) and (username not in self.allow_pam_usernames):
            #log.msg('ssh reject login of ',self.pam_username_prefix+('+' if self.pam_username_prefix else '')+credentials.username)
            return defer.fail(UnauthorizedLogin("invalid username"))

        if self.authenticate(username, credentials.password):
            #log.msg('login success by pam')
            return defer.succeed(username)
        #log.msg('login rejected by pam')
        return defer.fail(UnauthorizedLogin("invalid password"))

try:
    from ldaptor import config as ldaptor_config
    from ldaptor import ldapfilter
    from ldaptor.protocols.ldap import ldapsyntax, ldapclient, ldapconnector, ldaperrors
except ImportError:
    LDAPBindingChecker = None
else:
    @implementer(checkers.ICredentialsChecker)
    class LDAPBindingChecker(object):
        """

        The avatarID returned is an LDAPEntry.

        """
        credentialInterfaces = (credentials.IUsernamePassword,)

        def __init__(self,uid_attrname,cfg):
            self.config = cfg
            self.uid_attrname = uid_attrname
        
        def _found(self, results, _credentials, deferred):
            if not (results and len(results)==1):
                deferred.errback(failure.Failure(UnauthorizedLogin('LDAP login failure')))
            entry = results[0]
            #ensure uid is what we are looking for
            uid_attributeset = entry.get(self.uid_attrname)
            if not (len(uid_attributeset)==1 and _credentials.username in uid_attributeset):
                deferred.errback(failure.Failure(UnauthorizedLogin('LDAP login failure')))
                return

            def _valid(result, entry, _credentials, deferred):
                #matchedDN, serverSaslCreds = result
                deferred.callback(_credentials.username)
            
            def _invalid(err,_credentials,deferred):
                deferred.errback(err)

            d = entry.client.bind(str(entry.dn), _credentials.password)
            d.addCallback(_valid,entry,_credentials,deferred)
            d.addErrback(_invalid,_credentials,deferred)

        def _connected(self, client, filt, _credentials, deferred):
            base = ldapsyntax.LDAPEntry(client, self.config.getIdentityBaseDN())
            d = base.search(filterObject=filt,
                            sizeLimit=1,
                            attributes=[self.uid_attrname]
                            )
            def err(_failure,_deferred):
                log.msg(_failure.getErrorMessage())
                _deferred.errback(failure.Failure(UnauthorizedLogin('Object not found')))
            d.addCallback(self._found, _credentials,deferred)
            d.addErrback(err,deferred)

        def requestAvatarId(self, _credentials):
            try:
                baseDN = self.config.getIdentityBaseDN()
            except ldaptor_config.MissingBaseDNError as e:
                raise UnauthorizedLogin("Disabled due configuration error: %s." % e)
            if not _credentials.username:
                raise UnauthorizedLogin('I dont support anonymous')
            filtText = self.config.getIdentitySearch(_credentials.username)
            try:
                filt = ldapfilter.parseFilter(filtText)
            except ldapfilter.InvalidLDAPFilter:
                raise UnauthorizedLogin("Couldn't create filter")
            deferred = defer.Deferred()
            client = ldapconnector.LDAPClientCreator(reactor, ldapclient.LDAPClient)
            d = client.connect(baseDN, self.config.getServiceLocationOverrides())
            d.addCallback(self._connected, filt, _credentials, deferred)
            
            def timeout(_deferred,_client):
                if _deferred.called: return
                log.msg('Warning! LDAP connection timeout')
                _deferred.errback(UnauthorizedLogin('LDAP connection timeout'))
                # ClientCreator has no disconnect()
                #_client.disconnect()
            reactor.callLater(3,timeout,deferred,client)
            
            def _err(reason,_deferred):
                if _deferred.called: return ##maybe has timeout
                log.msg('Warning! LDAP connection problem %s' % reason)  
                reason.trap(ldaperrors.LDAPInvalidCredentials,
                            # this happens with slapd 2.1.30 when binding
                            # with DN but no password
                            ldaperrors.LDAPUnwillingToPerform)
                _deferred.errback(UnauthorizedLogin('LDAP connection problem'))
            d.addErrback(_err,deferred)
            return deferred
    
def getObjshPortal(protocol_class,acl_options):
    
    realm = ObjshRealm(protocol_class)
    portal = cred_portal.Portal(realm)

    # ssh client's public key
    sshclient_pubkey_folders = acl_options.get('client_publickeys')
    if sshclient_pubkey_folders:
        del acl_options['client_publickeys']
        client_keydb = {}
        loaded_folders = []
        for sshclient_pubkey_folder in sshclient_pubkey_folders:
            if sshclient_pubkey_folder in loaded_folders: continue
            if not os.path.exists(sshclient_pubkey_folder): continue
            loaded_folders.append(sshclient_pubkey_folder)
            for file in os.listdir(sshclient_pubkey_folder):
                username,ext = os.path.splitext(file)
                if username.startswith('.') or ext != '.pub': continue
                try:
                    client_keydb[username].append(ssh_keys.Key.fromFile(os.path.join(sshclient_pubkey_folder,file)))
                    log.msg('load key-based ssh user '+username)
                except KeyError:
                    try:
                        client_keydb[username] =  [ssh_keys.Key.fromFile(os.path.join(sshclient_pubkey_folder,file))]
                        log.msg('load key-based ssh user '+username)
                    except ssh_keys.BadKeyError:
                        log.msg('Warning! failed to load sshkey of '+username)
        sshDB = SSHPublicKeyChecker(InMemorySSHKeyDB(client_keydb))

        # this should register to portal to make it work
        portal.registerChecker(sshDB)

    # username, password based authentication
    cascading_checker = CascadingChecker()
    for acl_name, acl_settings  in acl_options.items():
        if acl_settings['kind'] == 'LDAP':
            if LDAPBindingChecker is None:
                log.msg('Warning: package ldaptor is not installed, LDAP authentication ignored')
                continue
            #basedn = 'dc=example,dc=com'
            basedn = acl_settings['basedn']
            query = '(%s=%%(name)s)' % acl_settings['uid_attrname']
            cfg = ldaptor_config.LDAPConfig(basedn,{basedn: (acl_settings['host'], acl_settings.get('port',389))},None,query)
            checker = LDAPBindingChecker(acl_settings['uid_attrname'],cfg)
            cascading_checker.registerChecker(checker)        
        elif acl_settings['kind'] == 'PAM':
            # system accounts
            cascading_checker.registerChecker(PamPasswordDatabase(acl_settings['usernames'],acl_settings['username_prefix']))
        elif acl_settings['kind'] == 'IN_MEMORY_ACCOUNTS':
            # in memory accounts
            passwdDB = InMemoryUsernamePasswordDatabaseDontUse()
            for username, password in acl_settings.get('accounts',{}).items():
                username = username.strip() # do not allow empty username
                password = password.strip() # do not allow empty password
                if password and username:
                    passwdDB.addUser(username,password)
                    log.msg('Warning! in memory account: %s' % (username))
            cascading_checker.registerChecker(passwdDB)
        else:
            raise ValueError('Acl kind of %s is unknown' % acl_name)

    portal.registerChecker(cascading_checker)
    return portal

def ObjshSshFactory(portal,ssh_options):

    # assign portal to ssh factory
    ObjectiveShellSshFactory.portal = portal
    factory = ObjectiveShellSshFactory(ssh_options)

    return factory


def ObjshTelnetFactory(portal):
    # ref: https://github.com/skyepn/telechat-py/blob/master/examples/telnet_cred.py
    factory = ServerFactory()
    factory.protocol = lambda: TelnetTransport(AuthenticatingTelnetProtocol, portal)
    return factory