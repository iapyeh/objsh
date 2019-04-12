#! -*- coding:utf-8 -*-
"""
A message channel, accessed by root.pub.bus
"""
from .__init__ import *
import __main__
from twisted.python import log
from twisted.internet import reactor,error
import json, traceback
import base64
import sys
import copy
PY3 = sys.version_info[0] == 3
class MessageBus(SimpleStateValue):
    ws_listeners = None
    node_listeners = None
    def __init__(self):
        super(MessageBus,self).__init__()
        if MessageBus.ws_listeners is None:
            MessageBus.ws_listeners = {}
            MessageBus.node_listeners = []
   
    def add_listener(self,callable):
        # internal listener (server side, not from browser)
        MessageBus.node_listeners.append(callable)

    @exportable
    @cancellable
    def join(self,task,room_id):
        """
        Warning: there is a potentional risk, any user might create room
        """
        assert room_id[0] == 'R'
        
        name = id(task.protocol)
        
        try:
            pd,_ = MessageBus.ws_listeners[room_id][name]
        except KeyError:
            '''
            # 本來是存放real username，現改為存放task.user物件(2019/1/15)
            try:
                # 測試是否是binder，如果是則取本來的username
                username_real = task.user.internal_metadata['username']
            except KeyError:
                username_real = task.user.username
            pd = ProgressDeferred()
            try:
                MessageBus.ws_listeners[room_id][name] = (pd,username_real)
            except KeyError:
                MessageBus.ws_listeners[room_id] = {name:(pd,username_real)}
            '''
            pd = ProgressDeferred()
            try:
                MessageBus.ws_listeners[room_id][name] = (pd,task.user)
            except KeyError:
                MessageBus.ws_listeners[room_id] = {name:(pd,task.user)}

        reactor.callLater(0,pd.notify,{'topic':'welcome','name':name})

        # broadcast room's number of memebers to room 
        
        def announce(room_id):
            room_id_wo_R = room_id[1:]
            try:
                count = len(MessageBus.ws_listeners[room_id])
            except KeyError:
                log.warn('announce to unexisted room: %s' % room_id)
            else:
                self.broadcast_by_internal_node(room_id_wo_R,{'topic':'_ANNOUNCE_','data':{'type':'JOIN','members_count':count}}) 
        reactor.callLater(1,announce,room_id)

        return pd
    join.require_task = True
    # don't call the line below (to_background), it is wrong practice
    #join.to_background = True


    @join.disconnection_canceller
    def leave(self,task):
        name = id(task.protocol)
        empty_rooms = []
        for room_id,listeners in MessageBus.ws_listeners.items():
            # lookup user is in which room 
            # and maintain MessageBus.ws_listeners to remove room if it is empty
            try:
                pd, _ = listeners[name]
            except KeyError:
                continue
            else:
                pd.callback(True)
                del listeners[name]
                if len(listeners) == 0:
                    empty_rooms.append(room_id)
                # announce to other members in the same room
                # also annouce to internal listeners
                def announce(room_id):
                    try:
                        count = len(MessageBus.ws_listeners[room_id])
                    except KeyError:
                        # room been removed
                        count = 0
                    room_id_wo_R = room_id[1:]
                    self.broadcast_by_internal_node(room_id_wo_R,{'topic':'_ANNOUNCE_','data':{'type':'LEAVE','members_count':count}}) 
               
                # do a simple throttle for member count annoucement
                reactor.callLater(1,announce,room_id)
            # there should be only one room to leave for a connection
            break
        # remove empty rooms from bus
        for empty_room_id in empty_rooms:
            del MessageBus.ws_listeners[empty_room_id]


    def broadcast_by_internal_node(self,room_id,data):
        """
        內部物件廣播給所有外部連線的listerner及內部的node listener)

        Arguments:
            room_id: room_id not prefiexed by "R", 
                if room_id is '__ALL__', means all internal listerners and external clients of all presentation
            data: a dict 
            
        called by internal node to broadcast,
        
        """
        #print('bus message by internal>>>>',data)
        
        # broadcast to internal listeners
        if len(MessageBus.node_listeners):
            # internal listener's room id is not prefixed with "R"
            def internal(_room_id, _data):
                for _callable in MessageBus.node_listeners:
                    try:
                        _callable(None,_room_id,_data)
                    except:
                        log.debug(traceback.format_exc())
            self.callInThread(internal,room_id,data)
        
        """
        這一段的作法是每次都會檢查空的房間並且把該房間刪除，順便作資料維護，
        這個作法可能是不必要的。
        # broadcast to external clients
        # external listener's room id is prefixed with "R"
        if room_id == '__ALL__':
            # 這是對所有的使用的廣播
            ws_listeners = []
            empty_Rroom_ids = []
            for Rroom_id, room_listeners in MessageBus.ws_listeners.items():
                if len(room_listeners):
                    ws_listeners.append(list(room_listeners.values()))
                else:
                    empty_Rroom_ids.append(Rroom_id)
            if len(empty_Rroom_ids):
                # should not happen, but if it do happen, remove this room
                for Rroom_id in empty_Rroom_ids:
                    del MessageBus.ws_listeners[Rroom_id]
        else:
            Rroom_id = 'R'+room_id
            try:
                ws_listeners = [list(MessageBus.ws_listeners[Rroom_id].values())]
            except KeyError:
                #log.debug('broadcasting to non-existed room:',Rroom_id,'data:',data)
                # 這個房間不存在可能是因為所有人都離開了
                return
            if len(ws_listeners[0]) == 0 :
                # should not happen, but if it do happen, remove this room
                del MessageBus.ws_listeners[Rroom_id]
                return
        
        def external(ws_listeners,data_4_remote):
            for listeners in ws_listeners:
                for (pd,_) in listeners:
                    try:
                        pd.notify(data_4_remote)
                    except:
                        statetree.log.debug('one broadcasting failure')
                        traceback.print_exc()
        self.callInThread(external,ws_listeners,data)
        """
        if room_id == '__ALL__':
            # 這是對所有的使用的廣播
            Rroom_ids = MessageBus.ws_listeners.keys()
        else:
            Rroom_ids = ['R'+room_id]
        
        for Rroom_id in Rroom_ids:
            self.broadcast(None,Rroom_id, data)
    
    @exportable
    def broadcast(self,task,Rroom_id,data):
        """
        called from brower to broadcast to server-slide listeners and other browsers.

        Warning: there is a potentional risk, any user might broadcast to room

        inject data into bus's room

        if data['_binary_']  is in data,
        data['_binary_'] will be converted to data['_base64_'] for javascript client.
        but data['_binary_'] will not be converted for internal listeners

        Note: broadcaster will not receive message (no echo)
        """
        # remove prefixing 'R' when calling listeners
        # this "R" is added by sdk.js
        
        if task is not None:
            # 如果task is None，這是從內部廣播（broadcast_by_internal_node()）而來
            # 不要再重複呼叫內部的listener
            room_id = Rroom_id[1:]
            if len(MessageBus.node_listeners):
                def internal(_room_id, _data):
                    for _callable in MessageBus.node_listeners:
                        try:
                            _callable(task,_room_id,_data)
                        except:
                            log.debug(traceback.format_exc())
                self.callInThread(internal,room_id,data)

        try:
            listeners = MessageBus.ws_listeners[Rroom_id]
        except KeyError:
            return
        # because internal node might do broadcast.
        # so we do the conversion even there is one listener.
        if len(listeners):
            # convert data['_binary_'] to json-able format
            data_4_remote = {}
            iter = data.items if PY3 else data.iteritems
            for k,v in iter():
                if k == '_binary_':
                    data_4_remote['_base64_'] = base64.encodestring(data['_binary_'])
                else:
                    data_4_remote[k] = v

            def external(my_name,Rroom_id,data_4_remote):
                # do a shadow copy to avoid listeners changes
                # in case of heavy loading
                _listeners = copy.copy(listeners)
                for name,(pd,_) in _listeners.items():
                    if name == my_name:
                        # don't echo
                        continue
                    try:
                        pd.notify(data_4_remote)
                    except:
                        statetree.log.debug('exception on bus broadcasting to '+name)
                        traceback.print_exc()
            my_name = id(task.protocol) if task else None
            self.callInThread(external,my_name,Rroom_id,data_4_remote)
    broadcast.require_task = True

    ''' 效能不佳，最好是不要廣播大量的資料
    @exportable
    def broadcast_raw(self,task,room_id,data):
        """
        receive binary (blob) data and divert into bus's room
        """
        #deferred = defer.Deferred()
        #print [task,room_id,data],'<<<<'
        def job(task,room_id,data):
            length = [data['length']]
            chunk = []
            def raw_receiver(raw,data):
                try:
                    chunk.append(raw)
                    length[0] -= len(raw)
                    if length[0] == 0:
                        task.protocol.raw_receiver = None
                        data['_binary_'] = ''.join(chunk)
                        self.broadcast(task,room_id,data)
                    elif length[0] < 0:
                        statetree.log.error('too much data, expect',data['length'],'got',len(chunk[0]))
                        task.protocol.raw_receiver = None
                except:
                    traceback.print_exc()
            task.protocol.raw_receiver = lambda x,y=data:raw_receiver(x,y)
        self.callInThread(job,task,room_id,data)
        return True
    broadcast_raw.require_task = True
    # Since broadcast_raw has callInThread, don't need to_background
    #broadcast_raw.to_background = True
    '''

    def get_members(self,room_id):
        """
        回傳的是user物件
        """
        Rroom_id = 'R'+room_id
        try:
            listeners = MessageBus.ws_listeners[Rroom_id]
        except KeyError:
            return []

        members = []
        for _, (_,user) in listeners.items():
            members.append(user)
        return members

    def unicast(self,room_id,target,data):
        """
        called by internal nodes to send data to some member
        Args:
            target: some username
        """
        Rroom_id = 'R'+room_id

        try:
            listeners = MessageBus.ws_listeners[Rroom_id]
        except KeyError:
            return False
        else:
            # because internal node might do broadcast.
            # so we do the conversion even there is one listener.
            for _,(pd,user) in listeners.items():
                if not user.username == target: continue
                pd.notify(data)
                return True
        return False
statetree.nodes.pub.add_node('bus',MessageBus())
