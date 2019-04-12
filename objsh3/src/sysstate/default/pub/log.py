#! -*- coding:utf-8 -*-
"""
State node of root.pub.
The aggregator for public stuffs. Such as utilities.
"""
from .__init__ import *
import __main__
from twisted.python import log
from twisted.internet import reactor, threads, defer
import os, sys
import json, logging, datetime, time, traceback
from twisted.logger import LogLevel

class Log(SimpleStateValue):
    """
    Observe log
    """
    exports = (
        'observe',
    )
    def __init__(self):
        #initial value is False
        super(Log,self).__init__()
        self.level_names ={
            'info':logging.INFO,
            'error':logging.ERROR,
            'debug':logging.DEBUG,
            'warn':logging.WARNING,
            'critical':logging.CRITICAL
        }
        self._log_observers = {}
        
        _n = time.time()
        offset = datetime.datetime.utcfromtimestamp(_n) - datetime.datetime.fromtimestamp(_n)
        self.tzoffset = offset.days * (60 * 60 * 24) + offset.seconds
    
    @cancellable
    def observe(self,task):
        """
        output is string
        """
        pd = ProgressDeferred()
        name = id(task.protocol)
        def job(name,pd):
            def observer(a_dict):
                ts = str(a_dict['time']+self.tzoffset)
                # append 0 for value likes "1526537871.8"
                ts += '0' if len(ts)==12 else ''                 
                pd.notify({
                    'time':ts,
                    'level':self.level_names[a_dict['log_level'].name],
                    'name':a_dict['log_level'].name,
                    'text':' '.join([str(x) for x in a_dict['message']])
                })
            self._log_observers[name] = (pd,observer)
            log.addObserver(observer)
            ts = str(time.time())
            ts += '0' if len(ts)==12 else ''
            pd.notify({
                    'time':ts,
                    'level':self.level_names['info'],
                    'name':'info',
                    'text':'start to listen on logs'
                })
            
        self.callInThread(job,name,pd)
        return pd
    observe.require_task = True

    @observe.disconnection_canceller
    def stop_observe(self,task):
        name = id(task.protocol)
        try:
            pd, observer = self._log_observers[name]
            log.removeObserver(observer)
            pd.callback(True)
            del self._log_observers[name]
        except KeyError:
            pass
        
        except:
            traceback.print_exc()
        #if hasattr(self,'_log_observer'):
        #    self._log_observer()
        #    del self._log_observer

    @exportable
    def msg(self,level,line):
        """
        A wrapper to twisted.python.log

        Args:
            line: (string) \r,\n should be escaped to \\r, \\n
        """
        if level == 'info':
            log.msg(json.loads(line),log_level=LogLevel.info)
        elif level == 'warn':
            log.msg(json.loads(line),log_level=LogLevel.warn)
        elif level == 'error':
            log.msg(json.loads(line),log_level=LogLevel.error)
        elif level == 'critical':
            log.msg(json.loads(line),log_level=LogLevel.critical)
        elif level == 'debug':
            log.msg(json.loads(line),log_level=LogLevel.debug)
        return 'ok'
    
    @exportable
    def get(self,options):
        pd = ProgressDeferred()
        def back(options,pd):
            start_ts,end_ts,rows = self._get_worker(options)
            # default to 200, max is 500
            chunksize = min(options.get('chunk_size',200),500)
            def send(pos,pd,rows,start_ts,end_ts):
                pd.notify(rows[pos:pos+chunksize])
                pos += chunksize
                if pos < len(rows):
                    reactor.callLater(0.1,send,pos,pd,rows,start_ts,end_ts)
                else:
                    del rows[:]
                    reactor.callLater(0.1,pd.callback,{'start_ts':start_ts,'end_ts':end_ts})
            send(0,pd,rows,start_ts,end_ts)
        self.callInThread(back,options,pd) 
        return pd
    # below statement would cause alreadyCallError, don't do it
    # because "to_background" will cause returned pd to be called
    #get.to_background = True

    def _get_worker(self,options):
        """
        Arguments:
            options:
                last_hours:(int)
                max_rows:(int) if presented, do not return over this number of rows. 0 means unlimited
                min_level:(int), default to 20 (inclusive)
                order:(string)  'ASC' or 'DESC', default to 'ASC',
                start_ts(inclusive) is in seconds, not in micro-seconds like javascript
                end_ts(exclusive)
        """
        today = datetime.datetime.utcnow()
        last_hours = options.get('last_hours')
        max_rows = 0 # temporary disabled # options.get('max_rows',0)
        reverse = options.get('order','ASC').upper() == 'DESC'
        min_level = str(options.get('min_level',20))

        if last_hours:
            start_ts = float((today - datetime.timedelta(seconds=last_hours*3600)).strftime('%s'))
            end_ts = None
            start_dt = datetime.datetime.fromtimestamp(start_ts)
            end_dt = today
        else:
            start_ts = options['start_ts']
            end_ts = options.get('end_ts')
            start_dt = datetime.datetime.fromtimestamp(start_ts)#.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_dt = datetime.datetime.fromtimestamp(end_ts) if end_ts else today

        assert start_dt < end_dt
        #log file
        var_folder = __main__.config.general['folder']['var']
        log_folder = os.path.join(var_folder,'logs')
        log_filename = __main__.config.general['log']['filename']
        
        start_ts_str = str(int(start_ts))+'.00'
        assert len(start_ts_str) == 13
        if end_ts:
            end_ts_str = str(int(end_ts))+'.00'
        else:
            end_ts_str = end_dt.strftime('%s')+'.00'
        
        assert len(start_ts_str) == 13 and len(end_ts_str) == 13
        #print '===log==',start_dt,'to',end_dt
        rows = []
        curr_dt = start_dt
        
        def collect_row(line):
            if min_level > line[14:16]:
                return True #skip but continue to collect
            rows.append(line)
            return False if (max_rows and len(rows)>=max_rows) else True

        while curr_dt <= end_dt:
            try:
                if curr_dt.date()==today.date():
                    log_file = os.path.join(log_folder,log_filename)
                else:
                    log_file = os.path.join(log_folder,log_filename+'{d.year}_{d.month}_{d.day}'.format(d=curr_dt))
                log_path = os.path.join(log_folder,log_file)

                if not os.path.exists(log_path):
                    curr_dt += datetime.timedelta(days=1)
                    continue
                
                fd = open(log_path,'r')
                if end_ts is None:
                    # collect all rows until now
                    if curr_dt==start_dt:
                        # only collect rows after start_dt
                        collect_start = False
                        #print '@1' * 40
                        for line in fd:
                            if collect_start:
                                assert line[:13] >= start_ts_str
                                if not collect_row(line): break
                            elif line[:13] >= start_ts_str:                            
                                if not collect_row(line): break
                                collect_start = True
                    else:
                        #print '@2' * 40
                        # start_dt must be days ago, 
                        # we collect all rows in between days
                        for line in fd:
                            if not collect_row(line): break
                        
                else:
                    if curr_dt==start_dt:
                        # only collect rows after start_dt
                        if curr_dt == end_dt:
                            collect_start = False
                            for line in fd:
                                if collect_start:
                                    if end_ts_str > line[:13]:
                                        if not collect_row(line): break
                                    else:#end_ts_str <= line[:13]:
                                        break
                                elif end_ts_str > line[:13] >= start_ts_str:
                                    if not collect_row(line): break
                                    collect_start = True
                        else:
                            # must be curr_dt < end_dt
                            assert curr_dt < end_dt
                            collect_start = False
                            #print '@4' * 40,(start_ts_str,end_ts_str)
                            for line in fd:
                                if collect_start:
                                    if line[:13] < end_ts_str:
                                        if not collect_row(line): break
                                    else:
                                        # exceeds end_ts_str
                                        break
                                elif line[:13] < start_ts_str:
                                    # skip rows before start_ts
                                    continue
                                elif line[:13] < end_ts_str:
                                    # start to collect rows
                                    collect_start = True
                                    if not collect_row(line): break
                    elif curr_dt < end_dt:
                        # we collect all rows in between days
                        for line in fd:
                            if not collect_row(line): break
                    else:
                        # only collect rows before end_ts
                        for line in fd:
                            if line[:13] < end_ts_str:
                                if not collect_row(line): break
                            else:
                                break
                fd.close()
                if max_rows and len(rows)>=max_rows: break
                curr_dt += datetime.timedelta(days=1)
            except:
                traceback.print_exc()
                break
        if reverse: rows.reverse()
        #print 'log total', len(rows),'reverse is',reverse, 'size',sys.getsizeof(rows),'rows',len(rows)
        return (float(start_dt.strftime('%s')),float(end_dt.strftime('%s')),rows)
        
statetree.nodes.pub.add_node('log',Log())
