#! -*- coding:utf-8 -*-
import __main__
import sys,re

try:
    from types import TupleType,ListType,StringTypes
except ImportError:
    StringTypes = (str,)
    ListType = list
    TupleType = tuple
from typing.re import Pattern
import traceback,json,importlib,os,random
from twisted.internet import defer,reactor
from twisted.python import log

from progress_deferred import ProgressDeferred
from singleton import Singleton
# https://github.com/jparise/python-reloader
import reloader
   
def get_args_str(args):
    #
    # effective arguments for getting formatters are arguments starts with -
    # if formatter does not fit this rule, it might only registered the command part
    # and check the metatata['args'] for what it wants
    #
    if args is None: return False,''
    elif type(args) in StringTypes: args = [args]
    assert type(args) in (TupleType,ListType), 'Type %s is not allowed for args' % type(args)

    #
    # allow args to be -la
    #
    has_star = False
    chunks = []
    for arg in args:
        if not (arg in StringTypes and arg.startswith('-')): continue
        #
        # resort the alphatic order of character behind '-'.
        # ex. re-sort -cba to -abc (normalize this order for matching registered runner)
        #
        for c in arg[1:]:
            if c=='*':
                has_star = True
            else:
                chunks.append('-'+c)
    
    #chunks.sort()
    return has_star, ':'.join(sorted(chunks)) if len(chunks) else ''
    
class GenericRunner(object):
    def get_chained(self,registered_dict,cmd,args):
        #
        # matching command part
        #
        objs = registered_dict['str_cmd'].get(cmd)
        if objs is None:
            objs = []
        for pat,obj in registered_dict['re_cmd']:
            if pat.search(cmd):
                objs.append(obj)
        if len(objs)==0: return None
        #
        # matching args part
        # weighting: 1 - 10
        #
        _,args_str = get_args_str(args)
        funcs = []
        for obj in objs:
            if obj['args'] is None:
                if args_str=='': funcs.append((10,obj['def']))
            else:
                #
                # check registered arg items
                #
                for obj_arg in obj['args']:
                    if obj_arg=='*':
                        #
                        # weight same as regular expression
                        #
                        funcs.append((1,obj['def']))
                        break
                    elif obj_arg is None or obj_arg=='':
                        #
                        # if None or '' in the args list
                        # it is the same as "obj['args'] is None"
                        # no more checking other arg in the args
                        if args_str=='': funcs.append((10,obj['def']))
                        break
                    elif isinstance(obj_arg,re._pattern_type):
                        if obj_arg.search(args_str):
                            #
                            # regular expression matching has lowest priority
                            #
                            funcs.append((1,obj['def']))
                            break
                    elif type(obj_arg) in StringTypes:
                        _, obj_arg_str = get_args_str(obj_arg)
                        if obj_arg_str==args_str:
                            #
                            # let the longer weights more , 
                            # but higher than regula expression,
                            # lower than no-argument
                            #
                            funcs.append((min(9,1+len(obj_arg_str)/2),obj['def']))
                            break
                    else:
                        raise Exception('should not be %s here' % type(obj_arg))
        return funcs if len(funcs) else None

class BeforeRunner(GenericRunner):
    def __init__(self):
        self.guarders = {
            'str_cmd':{},
            're_cmd':[]
        }
        self.guarder_all = None
        
    def guarder(self,target_cmd,target_args=None):
        if isinstance(target_cmd,Pattern):
            target_cmd_str = '/'+target_cmd.pattern+'/'
        else:
            target_cmd_str = target_cmd
        if isinstance(target_args,Pattern):
            target_args_str = '/'+target_args.pattern+'/'
        else:
            target_args_str = target_args
        log.msg('guarder (%s, %s)' % (target_cmd_str,target_args_str))

        def gen(func):
            if target_cmd=='*':
                self.guarder_all = func
            else:
                if target_args is None:
                    args = None
                elif type(target_args) in (TupleType,ListType):
                    args = target_args
                else:
                    args = [target_args]
                obj = {
                    'def':func,
                    'args':args
                }
                if isinstance(target_cmd,re._pattern_type):
                    self.guarders['re_cmd'].append((target_cmd,obj))
                else:
                    try:
                        self.guarders['str_cmd'][target_cmd].append(obj)
                    except KeyError:
                        self.guarders['str_cmd'][target_cmd]= [obj]
        return gen
        
    def get_guarder(self,task):
        funcs = self.get_chained(self.guarders,task.command.cmd,task.command.args)
        if funcs is None or len(funcs)==0:
            return self.guarder_all

        def chained_func(task):
            passed = self.guarder_all(task) if self.guarder_all else True
            if not passed: return False
            for weight, func in funcs:
                if not func(task):
                    passed = False
                    break
            return passed
        
        return chained_func

class Runner(GenericRunner):
    def __init__(self):
        self.providers = {
            'str_cmd':{},
            're_cmd':[]
        }
        self.default_provider = None
               
    def provider(self,target_cmd,target_args=None):
        """
        decorate function of @runner.provider
        """
        if isinstance(target_cmd,Pattern):
            target_cmd_str = '/'+target_cmd.pattern+'/'
        else:
            target_cmd_str = target_cmd
        if isinstance(target_args,Pattern):
            target_args_str = '/'+target_args.pattern+'/'
        else:
            target_args_str = target_args

        log.msg('runner (%s, %s)' % (target_cmd_str,target_args_str))
        
        def gen(func):
            if target_cmd=='*':
                self.default_provider = func
            else:
                if target_args is None:
                    args = None
                elif type(target_args) in (TupleType,ListType):
                    args = target_args
                else:
                    args = [target_args]
                obj = {
                    'def':func,
                    'args':args
                }            
                #if isinstance(target_cmd,re._pattern_type):
                if isinstance(target_cmd,Pattern):
                    self.providers['re_cmd'].append((target_cmd,obj))
                else:
                    try:
                        self.providers['str_cmd'][target_cmd].append(obj)
                    except KeyError:
                        self.providers['str_cmd'][target_cmd]= [obj]
        
        return gen

    def get_provider(self,cmd,args):
        #
        # only one provider is allowed
        # the default provider (registered as "*") has lowest priority
        #
        funcs = self.get_chained(self.providers,cmd,args)
        if (funcs is None or len(funcs)==0):
            return self.default_provider
        else:
            max_weight = 0
            effective_func = None
            for weight,func in funcs:
                if weight > max_weight:
                    max_weight = weight
                    effective_func = func
            return effective_func

class AfterRunner(GenericRunner):
    def __init__(self):
        self.formatters = {
            'str_cmd':{},
            're_cmd':[]
        }
    def formatter(self,target_cmd,target_args=None):
        if isinstance(target_cmd,Pattern):
            target_cmd_str = '/'+target_cmd.pattern+'/'
        else:
            target_cmd_str = target_cmd
        if isinstance(target_args,Pattern):
            target_args_str = '/'+target_args.pattern+'/'
        else:
            target_args_str = target_args
        log.msg('formatter (%s, %s)' % (target_cmd_str,target_args_str))

        def gen(func):
            if target_args is None:
                args = None
            elif type(target_args) in (TupleType,ListType):
                args = target_args
            else:
                args = [target_args]
            obj = {
                'def':func,
                'args':args
            }            
            #if isinstance(target_cmd,re._pattern_type):
            if isinstance(target_cmd,Pattern):
                self.formatters['re_cmd'].append((target_cmd,obj))
            else:
                try:
                    self.formatters['str_cmd'][target_cmd].append(obj)
                except KeyError:
                    self.formatters['str_cmd'][target_cmd]= [obj]
        return gen
    
    def get_formatter(self,cmd,args):        
        funcs = self.get_chained(self.formatters,cmd,args)
        if funcs is None or len(funcs)==0: return None
        def chained_func(task,raw):
            for _, func in funcs:
                try:
                    #
                    # weight is ignored in formatters
                    #
                    raw = func(task,raw)
                except Exception as e:
                    task.command.set_stderr('formatter "%s" error: %s\ntraceback:\n%s' % (func.__name__,e,traceback.format_exc()))
                    break
            return raw
        return chained_func

#
# for py3, use class ObjshRunner(metaclass=Singleton):
# for details, see https://stackoverflow.com/questions/6760685/creating-a-singleton-in-python
#
class RunnerError(Exception):
    def __init__(self,value,retcode=1):
        self.retcode = retcode
        Exception.__init__(self,value)

__main__.RunnerError = RunnerError
__main__.__all__.append('RunnerError')

class ObjshRunner(Singleton):
    #__metaclass__ = Singleton
    before_runner = BeforeRunner()
    runner = Runner()
    after_runner = AfterRunner()
    counter = 0

    def __init__(self,config):
        __main__.objshrunner = self
        __main__.__all__.append('objshrunner')
        reactor.callLater(0,self.init,config)

    def init(self,config):
        if ObjshRunner.counter : return
        self.config = config
        ObjshRunner.counter += 1
        for runner_folder in config.folder['runners']:
            try:
                self.scan(runner_folder)
            except:
                log.err('error on scanning '+runner_folder)
                #log.err()
                traceback.print_exc()
                if __main__.developing_mode: reactor.stop()
    
    def run(self,task,result_deferred):
        """
        @param result_deferred: a deferred to callback(task) when completed
        """
        #user = task.user
        
        assert task.command.cmd is not None

        # apply security control
        try:
            guarder_callable = self.before_runner.get_guarder(task)
        except Exception as e:
            result_deferred.errback(e)
            return

        else:
            cmd = task.command.cmd
            args = task.command.args
        
            if (guarder_callable is not None) and not guarder_callable(task):
                #task.command.set_result()
                result_deferred.callback((1,None,u'Forbidden \'%s\'' % cmd))
                return
            
            if task.command.is_function_call:
                runner = self.runner.get_provider(cmd,None)
            else:
                runner = self.runner.get_provider(cmd,args)
            
            if not runner:
                #task.command.set_result()
                result_deferred.callback((1,None,'unknown \'%s\'' % (cmd if len(cmd)<30 else cmd[:30])))
                return 
            
            def okback(raw,the_task,the_result_deferred):
                try:
                    task_command = the_task.command
                    # `command` skip formatter
                    if the_task.command.is_raw_result:
                        payload = raw
                    else:
                        formatter_callable = self.after_runner.get_formatter(task_command.cmd,task_command.args)
                        if formatter_callable:
                            payload = formatter_callable(task,raw)
                        else:
                            payload = raw

                    #task_command.set_result(0,payload)
                    #task.set_result()

                    #if not task_command.is_background:
                    the_result_deferred.callback((0,payload,None))

                except Exception as e:
                    log.msg(traceback.format_exc())
                    the_result_deferred.callback((1,None,traceback.format_exc()))
            
            def errback(failure,the_task,the_result_deferred):
                task_command = the_task.command
                if isinstance(failure.value,RunnerError):
                    log.msg(failure.value.args[0])
                    the_result_deferred.callback((failure.value.retcode,None,failure.value.args[0]))
                else:
                    log.msg(failure.getErrorMessage())
                    log.msg(failure.getTraceback())
                    the_result_deferred.callback((1,None,failure.getErrorMessage()))

            
            def run_task(runner,task):
                # run in thread-pool
                runner_deferred = defer.maybeDeferred(runner,task)
                runner_deferred.addCallbacks(okback,errback,callbackArgs=[task,result_deferred],errbackArgs=[task,result_deferred])
                if isinstance(runner_deferred,ProgressDeferred):
                    # enforce to background
                    #if not the_task.command.is_background:
                    #    the_task.__class__.task_to_background(the_task)
                    
                    def progressBack(progress_response,the_task,the_runner_deferred):
                        data = the_task.set_progress(progress_response)
                        if not the_task.command.is_background: the_task.output(data)

                    runner_deferred.addProgressBack(progressBack,task,runner_deferred)
            '''
            def run_task(runner,task):
                # run in thread-pool
                print '<<<<<<',task.command.cmd
                ret = runner(task)
                print '>>>>>>',[type(ret)]
                if isinstance(ret,defer.Deferred):
                    ret.addCallbacks(okback,errback,callbackArgs=[task,result_deferred],errbackArgs=[task,result_deferred])
                    if isinstance(ret,ProgressDeferred):
                        def progressBack(progress_response,the_task,the_runner_deferred):
                            data = the_task.set_progress(progress_response)
                            if not the_task.command.is_background: the_task.output(data)
                        ret.addProgressBack(progressBack,task,ret)
                else:
                    okback(ret,task,result_deferred)
            '''
            # current, we runs in main-thread, so we ask the task to run in another thread
            #reactor.callInThread(run_task, runner,task)
            run_task(runner,task)

    def scan(self,runner_folder):
        base_dir = os.path.abspath(os.path.dirname(__file__))
        loaded_module_names = sys.modules.keys()
        module_to_reload = []
        # pat to recognize a runner script
        has_runner_pat = re.compile('^@(after_|before_)?runner')
        
        for root,folders,files in os.walk(runner_folder):
            runner_folder_root = os.path.normpath(os.path.join(runner_folder,root))
            relpath = os.path.relpath(runner_folder_root,base_dir)
            paths = runner_folder_root.split('/')
            if (not relpath.startswith('..')) and len(relpath.split('/'))<2:
                sub_foldername = None
                if relpath=='.':
                    foldername = None
                    lib_folder = base_dir
                else:
                    foldername = paths[-1]
                    lib_folder = os.path.join(base_dir,paths[-1])
            else:
                foldername = paths[-2]
                sub_foldername = paths[-1]
                lib_folder = '/'+os.path.join(*paths[:-2])
            lib_folder_inserted = False
            if not lib_folder in sys.path:
                lib_folder_inserted = True
                sys.path.insert(0,lib_folder)
            for file in files:
                if file.startswith('.') or file.startswith('_'): continue
                elif file[-3:]=='.py':
                    # avoid to load twice if execution is from the runner subfolder for unit testing
                    file_path = os.path.join(runner_folder_root,file)
                    # only load file which wants to register runner
                    is_runner_script = False
                    fd = open(file_path,'r')
                    for line in fd:
                        if not has_runner_pat.search(line): continue
                        is_runner_script = True
                        break
                    fd.close()
                    if not is_runner_script: continue
                    
                    name = os.path.splitext(file)[0]
                    if sub_foldername is None:
                        module_name = '%s.%s' % (foldername,name)
                    else:
                        module_name = '%s.%s.%s' % (foldername,sub_foldername, name)
                    if module_name in loaded_module_names:
                        log.msg('reload runner %s' % (module_name))
                        module_to_reload.append(module_name)
                    else:
                        log.msg('load runner %s' % (module_name))
                        log.msg('lib ',lib_folder)
                        __import__(module_name, globals(), locals(), [], 0)
            # remove added path
            if lib_folder_inserted:
                sys.path.remove(lib_folder)
        if len(module_to_reload):
            reloader.enable()
            for module_name in module_to_reload:        
                reloader.reload(sys.modules[module_name])
            reloader.disable()
    
    def throw(self,value,retcode=1):
        raise RunnerError(value,retcode)