#! -*- coding:utf-8 -*-

from twisted.protocols import basic

class StatefulTelnetProtocol(basic.LineReceiver, TelnetProtocol):
    delimiter = b'\n'

    state = 'Discard'

    def connectionLost(self, reason):
        basic.LineReceiver.connectionLost(self, reason)
        TelnetProtocol.connectionLost(self, reason)


    def lineReceived(self, line):
        oldState = self.state
        newState = getattr(self, "telnet_" + oldState)(line)
        if newState is not None:
            if self.state == oldState:
                self.state = newState
            else:
                log.msg("Warning: state changed and new state returned")


    def telnet_Discard(self, line):
        pass


from twisted.cred import credentials

class AuthenticatingTelnetProtocol(StatefulTelnetProtocol):
    """
    A protocol which prompts for credentials and attempts to authenticate them.
    Username and password prompts are given (the password is obscured).  When the
    information is collected, it is passed to a portal and an avatar implementing
    L{ITelnetProtocol} is requested.  If an avatar is returned, it connected to this
    protocol's transport, and this protocol's transport is connected to it.
    Otherwise, the user is re-prompted for credentials.
    """

    state = "User"
    protocol = None

    def __init__(self, portal):
        self.portal = portal
        print("~"*30,protocol)
        self.transport.protocol.set_delimiter_to_newline()
    
    def connectionMade(self):
        self.transport.write(b"Username: ")


    def connectionLost(self, reason):
        StatefulTelnetProtocol.connectionLost(self, reason)
        if self.protocol is not None:
            try:
                self.protocol.connectionLost(reason)
                self.logout()
            finally:
                del self.protocol, self.logout


    def telnet_User(self, line):
        self.username = line
        self.transport.will(ECHO)
        self.transport.write(b"Password: ")
        return 'Password'


    def telnet_Password(self, line):
        username, password = self.username, line
        del self.username
        def login(ignored):
            creds = credentials.UsernamePassword(username, password)
            d = self.portal.login(creds, None, ITelnetProtocol)
            d.addCallback(self._cbLogin)
            d.addErrback(self._ebLogin)
        self.transport.wont(ECHO).addCallback(login)
        return 'Discard'


    def _cbLogin(self, ial):
        interface, protocol, logout = ial
        assert interface is ITelnetProtocol
        self.protocol = protocol
        self.logout = logout
        self.state = 'Command'

        protocol.makeConnection(self.transport)
        self.transport.protocol = protocol


    def _ebLogin(self, failure):
        self.transport.write(b"\nAuthentication failed\n")
        self.transport.write(b"Username: ")
        self.state = "User"
