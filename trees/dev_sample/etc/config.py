#! -*- coding:utf-8 -*-
#version = '20180927-1'
developing_mode = True
import datetime, os, __main__, sys
PY3 = sys.version_info[0] == 3

def rel_to_user_path(path,subname=None):
    if subname is None: subname = '.objsh'
    user_home = os.path.expanduser('~')
    abspath = os.path.normpath(os.path.join(user_home,subname,path))
    assert os.path.exists(abspath),'%s not found' % abspath
    return abspath

# relative to this file
etc_folder = os.path.abspath(os.path.dirname(__file__))
def rel_to_etc_path(path):
    return os.path.abspath(os.path.normpath(os.path.join(etc_folder,path)))

# relative to src/objsh.py
if hasattr(__main__,'objsh'):
    #invoking by app.py
    src_folder = os.path.abspath(os.path.dirname(__main__.objsh.__file__))
else:
    src_folder = os.path.abspath(os.path.dirname(__main__.__file__))

def rel_to_src_path(path):
    return os.path.normpath(os.path.join(src_folder,path))
def rel_to_default_etc_path(path):
    return os.path.normpath(os.path.join(src_folder,'../etc',path))

folder = {
    'var':rel_to_etc_path('../var'),
    'etc' : rel_to_etc_path('./'),

    # point to system secret folder
    'secret': rel_to_src_path('../etc/secret'),

    # point to system sshclientkeys
    'opt' : rel_to_etc_path('../opt'),
}

def rel_to_opt_path(path):
    return os.path.normpath(os.path.join(folder['opt'],path))

def rel_to_secret_path(path):
    return os.path.normpath(os.path.join(folder['secret'],path))

def rel_to_var_path(path):
    return os.path.normpath(os.path.join(folder['var'],path))

# default is sysrunner/,  you can add extra folder
folder['runners'] = [rel_to_opt_path('runner')]

acl_options = {
    'pam':{
        'kind':'PAM',

        # prefix to username while doing authentication
        # ex. pam_username_prefix='nas', and client of username='admin' requests for login
        # pam will check credentials for "nas_admin" in the system account
        'username_prefix':'',

        # allow for all acccounts in system accounts
        #'username':('*',) 
        
        # username should include prefix if pam_username_prefix is not empty string
        'usernames':('me',),
    },
    'debuging':{
        'kind':'IN_MEMORY_ACCOUNTS',
        'accounts':{
            'playground':'1234',
            'admin':'' # account of empty password is ignored
        }
    },
    # folders to search client_publickeys
    'client_publickeys': (
        rel_to_src_path('../etc/sshclientkeys'), #in objsh's default src
        rel_to_etc_path('sshclientkeys'),        #in etc
    ),
    # LDAP
    # 
    'ldap':{
        'kind':'LDAP',
        'basedn':'dc=example,dc=com',
        'host':'192.168.56.100',
        'port':389,
        'dn':'uid=%(username)s,ou=People,dc=example,dc=com',
        'uid_attrname':'uid',#attribute to check username, search query will be (uid=%(name)s)
    }
}
# REF: to create crt and key: https://www.akadia.com/services/ssh_test_certificate.html
# ssl key pairs to use
ssl = {
    'default':{
        'key' : rel_to_secret_path('ssl.key'),
        'crt' : rel_to_secret_path('ssl.crt'),
    }
}

general = {
    'server_name':'Bstor NAS System',
    'developing_mode': developing_mode,
    'folder':folder,
    'log':{
        'filename' : 'objsh.log',
        # values: debug(log all,default), info, warn, error, fatal
        'min_log_level':'debug' if developing_mode else 'info',
    },
    'daemon':{
        'ssh':{
            'type':'ssh',
            'enable':True,
            'port':1722,
            'server_rsa_private': rel_to_default_etc_path('secret/ssh_host_rsa_key'),
            'server_rsa_public': rel_to_default_etc_path('secret/ssh_host_rsa_key.pub'),
            'server_rsa_private_passphrase':'1234',
            # change this in productive environment
            # REF: http://twistedmatrix.com/documents/16.1.0/_downloads/sshsimpleserver.py
            # REF: https://www.freebsd.org/cgi/man.cgi?query=ssh-keygen&sektion=1&manpath=OpenBSD+3.9
            'primes':{
                2048: [(2, 24265446577633846575813468889658944748236936003103970778683933705240497295505367703330163384138799145013634794444597785054574812547990300691956176233759905976222978197624337271745471021764463536913188381724789737057413943758936963945487690939921001501857793275011598975080236860899147312097967655185795176036941141834185923290769258512343298744828216530595090471970401506268976911907264143910697166165795972459622410274890288999065530463691697692913935201628660686422182978481412651196163930383232742547281180277809475129220288755541335335798837173315854931040199943445285443708240639743407396610839820418936574217939)],
                4096: [(2, 889633836007296066695655481732069270550615298858522362356462966213994239650370532015908457586090329628589149803446849742862797136176274424808060302038380613106889959709419621954145635974564549892775660764058259799708313210328185716628794220535928019146593583870799700485371067763221569331286080322409646297706526831155237865417316423347898948704639476720848300063714856669054591377356454148165856508207919637875509861384449885655015865507939009502778968273879766962650318328175030623861285062331536562421699321671967257712201155508206384317725827233614202768771922547552398179887571989441353862786163421248709273143039795776049771538894478454203924099450796009937772259125621285287516787494652132525370682385152735699722849980820612370907638783461523042813880757771177423192559299945620284730833939896871200164312605489165789501830061187517738930123242873304901483476323853308396428713114053429620808491032573674192385488925866607192870249619437027459456991431298313382204980988971292641217854130156830941801474940667736066881036980286520892090232096545650051755799297658390763820738295370567143697617670291263734710392873823956589171067167839738896249891955689437111486748587887718882564384870583135509339695096218451174112035938859)],
            },
            #
            # sshclient_pubkey_folders is a tuple of folders which contains clients' public key.
            # gen a key pair: $ ckeygen -t rsa -f <username>
            # then, copy <username>.pub to etc/sshclientkeys folder
            # key files in the given folders must ended with .pub
            #            
            'acls':['pam','debuging','client_publickeys']
        },
        # telnet localhost 1723
        'telnet':{
            'type':'telnet',
            'enable':True,
            'port':1723,
            'acls':['pam','debuging']
        },
        # telnet-ssl -z ssl localhost 1724
        'telnet-ssl':{
            'type':'telnet',
            'enable':True,
            'port':1724,
            'ssl':ssl['default'],
            'acls':['pam','debuging']
        },
        'http':{
            'type':'web',
            'enable':True,
            'port':1780,
            'max_failure':30,
            'websocket':{
                'enable':True,
                'port':0,
                'route':'/ws'
            },
            #'acls':['pam','debuging','ldap'],
            'acls':['pam','debuging','ldap'],

            #'allow_cross_origin': False,#True if developing_mode else False,
            'allow_cross_origin': True, #  developing_mode

            # root folder of static file if http daemon enabled
            # Attention:/login, /login, /run, /websdk is reserved
            'htdocs' :{
                '/': {
                    'path':rel_to_opt_path('htdocs'),#document root /,
                    'public':True,
                    },
                '/private':{
                    'path':rel_to_opt_path('htdocs_private'),
                    'public':False,
                    }
            }
        },
        'https':{
            'type':'web',
            'enable':True,
            'port':1443,
            'ssl':ssl['default'],
            'websocket':{
                'enable':True,
                'port':0,
                'route':'/ws'
            },
            'acls':['pam','debuging'],

            #'allow_cross_origin': False,#True if developing_mode else False,
            'allow_cross_origin': True, #  developing_mode
            
            # root folder of static file if http daemon enabled
            # Attention:/login, /login, /run, /websdk is reserved
            'htdocs' :{
                '/': {
                    'path':rel_to_opt_path('htdocs'),#document root /,
                    'public':True,
                    },
                '/private':{
                    'path':rel_to_opt_path('htdocs_private'),
                    'public':False,
                    }
            }           
        },
        'tcpclient':{
            'type':'tcpsocket',
            'enable':True,
            'port':1725,
            'acls':['pam','debuging']
        },
        'tlsclient':{
            'type':'tcpsocket',
            'enable':True,
            'port':1726,
            'ssl':ssl['default'],
            'acls':['pam','debuging']
        }
    }
}
#
# playground settings
#
playground = {
    'enable':'yes',
    'sidebar':[
        {'Documents':[
            {'title':'BStor GDrive','url':'https://drive.google.com/drive/u/0/folders/1M8sWoDBbogpr3mdmd7SfpF7g5Glgqqqs'},
            {'API':[
                {'title':'API 試行規則', 'url':'https://docs.google.com/spreadsheets/d/1ToYI_NyJQmxnqYSYe7-zXwyuW3TXPgRgFGNIRfmRYVw/edit#gid=678031444'},
                {'title':'API 設計參考原則', 'url':'http://iapyeh.readthedocs.io/en/latest/blogs/technical/API_Guide.html'}
                ]
            }]
        }
    ]
}

statetree = {
    # used to register runner command in runner_state.py
    'runner_name':'bstor',
    'factory':rel_to_opt_path('state/mystatetree.py'),
    # used in plugin script to refrence the statetree
    'global_name':'statetree',
    'plugin_folders' : [rel_to_opt_path('state/plugins')],
    'sidebar':{
        'menuitems':[
            {'title':'Documents',
             'items':[
                    {'title':'API 設計參考原則', 'url':'http://iapyeh.readthedocs.io/en/latest/blogs/technical/API_Guide.html'}
                    ]
            }
        ]
    },
    'preference': {
        'save_to_folder':rel_to_var_path('preference'),
        'default':{}
    },
    # url path to export node to web (starts with /)
    # To disable, please set 'route':None 
    'route':'/objsh'
}

runner = {
    'ttl': 3600, # background task ttl
    'maintenance_interval':30 # maintenance of cache result of background tasks
}

'''
# An example to monkey patch log format
from twisted.python import log
_msg = log.msg
def my_config_msg(*message,**kw):
    message = (':^_^:',)+message
    return _msg(*message,**kw)
log.msg = my_config_msg
'''
#
# **DONT_TOUCH_BELOW**
#
# Lines blow will be reserved even config file has reset to default
#