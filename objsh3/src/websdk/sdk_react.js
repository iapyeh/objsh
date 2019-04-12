/*
 * 2018/08/31
 */

//required by react
import $ from 'jquery'
/*
Some obsoleted mobile phone does not support EPS6.
So we borrow some utilit functions from _.js
*/
var __ = {}
var shallowProperty = function(key) {
    return function(obj) {
      return obj == null ? void 0 : obj[key];
    };
};
var getLength = shallowProperty('length');
var MAX_ARRAY_INDEX = Math.pow(2, 53) - 1;
var isArrayLike = function(collection) {
    var length = getLength(collection);
    return typeof length == 'number' && length >= 0 && length <= MAX_ARRAY_INDEX;
};
__.forEach = function(obj,iteratee) {
    var i, length;
    for (i = 0, length = obj.length; i < length; i++) {
        iteratee(obj[i], i, obj);
    }
    return obj;
}; 

function Command(cmd,args,line_or_file,name){
    /*
     * cmd:(string; optional)
     * args: (array; optional)
     * line_or_file: (string; optional) or (instanceof File)
     * name: (string; optional) #name to retrieve, watch the task later
     *
     * If this is used for uploading file, only one file is supported.
     * The file can be one of the args item,
     * or the 3rd argument. If both, the 3rd argument take priority. 
     */
    this.promise = new $.Deferred()
    this.ts_sent = 0 //will be assigned if this command has been sent
    this.file = false //a File instance
    var escaped_args = []    
    var str_type = typeof('')
    if (args){
        var self = this
        //args.forEach(function(item){
        __.forEach(args,function(item){
            if ((item instanceof File)) self.file = item
            else if (typeof(item)==str_type) escaped_args.push(item.replace('\r','\\r').replace('\n','\\n'))
            else escaped_args.push(item)
        })
    }
    var escaped_line = null;
    if ((line_or_file instanceof File)){
        escaped_line = ''
        this.file = line_or_file
    }
    else if (line_or_file){
        escaped_line = line_or_file.trim().replace('\r','\\r').replace('\n','\\n')
    }
    //_id is internal use only
    this.content = {
        id:''+(new Date().getTime())+''+Math.floor(Math.random()*1000),
        cmd:cmd,
        args:escaped_args,
        line:escaped_line,
        options:{
            name:name
        }
    }
}
Command.prototype = {
    get_payload:function(){
        return JSON.stringify(this.content)
    },
    done:function(callback,args){
        //wrap to this.promise
        return this.promise.done.apply(this.promise,arguments)
    },
    notify:function(callback){
        //wrap to this.promise
        return this.promise.notify.apply(this.promise,arguments)
    },
    progress:function(callback,args){
        //wrap to this.promise
        return this.promise.progress.apply(this.promise,arguments)
    },
    then:function(callback,args){
        //wrap to this.promise
        return this.promise.then.apply(this.promise,arguments)
    },
    is_background:function(){
        return this.content.line ? this.content.line.substring(this.content.line.length-1) == '&' : false
    },
    cancel_command:function(){
        return new Command('task',['cancel',this.content.id])
    }
}
/* class methods and properties */
Command.waiting_queue = {}
Command.handlers = {}
Command.from_line = function(line,name){
    return new Command(null,null,line,name)
}
Command.consume = function(response){
    //console.log('responsed-command',response.command.cmd)
    //console.log('command response>>',response.id)
    if (response.id){
        var command_obj = Command.waiting_queue[response.id]
        if (command_obj){
            //console.log('<<--',command_obj.content.line)
            var has_more = false
            if (typeof(response._progress_) != 'undefined'){
                has_more = response._progress_
                delete response._progress_
            };
            if (has_more){
                command_obj.promise.notify(response.command) 
            }
            else {
                //console.log('resolve',response.command)
                command_obj.promise.resolve(response.command);
                delete Command.waiting_queue[response.id]
            }
        }
        else{
            console.warn('orphan response',response.command.cmd, response.command.args)
        }
    }
    else {
        //unsolicited messages
        //such as multitasks progress updating
        Command.handlers[response.kind](response)
    }
}


function ObjshSDK(options){
    /*
     * @param options: 
     *    host: (string;optional) host to login and connnect
     *    port: (int;optional) default 1433 for https or 1780 for ws
     *    ws_port: (int;optional) default 1434 for wss or 1781 for ws
     *    protocol:(string;optional) default "ws:" for http or "wss:" for https
     *
     *    When ws was disconnected,
     *    self.login will be called if auto_relogin_connect is true, otherwise
     *    self.connect will be called if auto_reconnect is true, otherwise, nothing will do.
     *
     *    When login success,
     *    self.connect will be called if auto_relogin_connect is true, otherwise, nothing will do.

     */

    this.ws = null //assigned later    
    // will be assigned after login success
    this.metadata = {}
    
    // a promise to listen on state changes
    this.promise_of_state = new $.Deferred()

    this.is_authenticated = false
    this.is_connected = false

    if (typeof(options)=='undefined') options = {}
    this.set_options(options)
    this.task = new TaskUtility(this)
    this.channel = new SDKChannel(this)
    this.log = new Logger(this)
    this.user = new User(this)
    this.bus = new Bus(this)
    
    var self = this
    window.onbeforeunload = function(){
        if (!self.is_connected) return
        self.ws.close()
    }
}
// will be assigned after login success
ObjshSDK.metadata = null
ObjshSDK.prototype = {
    set_options:function(options){
        //this should be called before login
        if (this.ws) return

        let is_secure = window.location.protocol=='https:' 
        var ws_protocol =  options.protocol
        if (!ws_protocol) ws_protocol = is_secure ? 'wss:' : 'ws:'
        this.ws_protocol = ws_protocol
        /*
        if (true){
            console.warn('enforce websocket to /ws')
            //server is behide nginx by proxying path
            this.ws_url = 'ws://'+window.location.host+'/ws'
            this.site_url = '//' + window.location.host
            this.route_prefix = ''
            this.is_cross_site = false
        }
        else 
        */
        if (options.path){
            //server is behide nginx by proxying path
            this.ws_url = ws_protocol+'//'+window.location.host+options.ws_path
            this.site_url = '//' + window.location.host +options.path
            //append / to this.route_prefix if it is not ended with /
            this.route_prefix = options.path + (/\/$/.test(options.path) ? '' : '/')
            this.is_cross_site = false
        }
        else{
            //server is direct accessed
            let host = options.host || window.location.hostname 
            var port = options.port 
            if (!port) port = is_secure ? '1443' : '1780'
    
            var current_host_port = window.location.host.split(':') 
            if (current_host_port.length==1) current_host_port.push('80')
            this.is_cross_site = (host != current_host_port[0] || port != current_host_port[1])
    
            var ws_port = ws_protocol.ws_port 
            if (!ws_port) ws_port = is_secure ? '1444' : '1781'
    
            this.ws_url = ws_protocol+'//'+host+':'+ws_port
            this.site_url = '//' + host +':'+port
            this.route_prefix = ''
        }
    },
    login:function(username,password){
        /* style 1:
         *  @param username:(string)
         *  @param password:(string)
         * style 2:
         *  @param username:(object),{
         *         type:(string),
         *         data:(any JSON-able value)
         *      }
         */
        let self = this 
        let url = this.site_url+'/login' 
        var promise = new $.Deferred()
        var data;
        if (typeof(username)=='object' && username.type){
            data = {
                type:username.type,
                data:JSON.stringify(username.data)
            }
            if (this.is_cross_site) {
                var cross_site_url = url
                cross_site_url += '?type='+data.type+'&data='+ encodeURIComponent(data.data)
                let x = window.open(cross_site_url,'objsh_login') 
                setTimeout(function(){try{x.close()}catch(e){}},100)
            }
        }
        else{
            if (!username) username = self._credential ? self._credential.username : ''
            if (!password) password = self._credential ? self._credential.password : ''
            //console.log('login',username,password,promise)
            data = {username:username,password:password,ts:new Date()} //let
            if (this.is_cross_site) {
                let cross_site_url = url
                cross_site_url += '?username='+username+'&password='+password //let
                let x = window.open(cross_site_url,'objsh_login') 
                setTimeout(function(){try{x.close()}catch(e){}},100)
            }
        }
        $.ajax({
          dataType: "json",
          url: url,
          method:'POST',
          cache:false,
          data: data
        }).done(function(response){
            if (response.retcode==0){
                self.is_authenticated = true

                // initialize with metadata
                self.metadata = response.stdout
                //make an alias to runner_name
                self.metadata.runner_name = self.metadata.statetree_runner_name

                self.user.set_metadata(self.metadata.user)
                self.user.is_authenticated = true

                // Command will use this copy no matter what instance name of ObjshSDK is.
                ObjshSDK.metadata = {
                    username:self.metadata.user.username,
                    runner_name : self.metadata.statetree_runner_name, 
                    server_name:self.metadata.server_name, 
                    objsh_version:self.metadata.objsh_version,
                    resource_route_name:self.route_prefix+self.metadata.resource_route_name
                }
                
                // update websocket's settings
                if (self.metadata.websocket_options){
                    if (self.metadata.websocket_options.route){
                        self.ws_url = self.ws_protocol+self.site_url+self.metadata.websocket_options.route
                    }
                    else if (self.metadata.websocket_options.port){
                        self.ws_url = self.ws_url.replace(/\:\d+$/,':'+self.metadata.websocket_options.port)
                    }
                }

                // keep credential if self.auto_reconnect is true
                self._credential = {username: username, password: password}
                promise.resolve(true)
            }
            else{
                promise.reject(200,response.stderr)
            }
          }).fail(function(jqXHR, textStatus, errorThrown){
            console.log('login failure:',[jqXHR, textStatus, errorThrown])
            if (jqXHR.status == 0){
                // network problem
                promise.reject(jqXHR.status,jqXHR.statusText)
            }
            else{
                // 403 mostly
                self.is_authenticated = false
                ObjshSDK.metadata = {}
                delete self._credential
                promise.reject(jqXHR.status,jqXHR.responseText)
            }
          }
        )
        return promise
    },
    logout:function(){
        /*
         * if logout is called, auto_relogin and auto_reconnect will be set to false
         *
         */
        let self = this 
        let url = this.site_url+'/logout' 
        if (this.is_cross_site) {
            let x = window.open(url,'objsh_login') 
            setTimeout(function(){x.close()},100)
        }

        this.is_authenticated = false
        this.user.is_authenticated = false
        delete this._credential

        //this.auto_reconnect = false
        //this.auto_relogin = false

        if (this.ws) this.ws.close()
        
        let promise = new $.Deferred()
        $.ajax({
          dataType: "json",
          url: url,
          data: null,
          success: function(response){
            if (response.retcode==0){
                promise.resolve(true)
                // initialize with metadata
                self.metadata = null
                ObjshSDK.metadata = null
            }
            else{
                promise.reject(response.stderr)
            }
          },
          error:function(err){
            console.log('logut error',err)
            if (err.status == 0){
                promise.reject(err.status,err.statusText)
            }
            else{
                promise.reject(err.status,err.responseText)
            }
          }
        });
        return promise
    },    
    connect:function(){
        let self = this 
        self.ws_buffer = []
        //self.ws_boundary = '\r\n'
        self.ws_boundary = '♞'
        self.ws = new WebSocket(this.ws_url)
        var promise = new $.Deferred()
        self.ws.onopen = function(evt){
            console.log('connected')
            self.is_connected = true

            //initialize Preferences
            self.user.on_connected()
            
            self.promise_of_state.notify('onopen',evt)
            promise.notify('onopen',evt)
        }
        self.ws.onmessage = function(evt){
            //console.log('>>'+evt.data.length+'data=',[evt.data])
            self._last_ping_ts = new Date().getTime()
            var responses = [] 
            let p = evt.data.indexOf(self.ws_boundary) 
            if (p==-1){
                self.ws_buffer.push(evt.data)
                return
            }
            var chunks = (self.ws_buffer.join('')+evt.data).split(self.ws_boundary)
            if (p==evt.data.length-1){
                chunks.pop()
                self.ws_buffer = []
            }
            else{
                self.ws_buffer = [chunks.pop()]
            }
            __.forEach(chunks,function(chunk,idx){                
                try{
                    var response = JSON.parse(chunk)
                    //console.log('resonse=>',response)
                    Command.consume(response)
                }
                catch(e){
                    console.warn(e)
                    console.log(chunk)
                }
            })
        }
        self.ws.onclose = function(evt){
            self.ws = null
            self.is_connected = false
            self.promise_of_state.notify('onclose',evt)
            promise.notify('onclose',evt)
        }
        self.ws.onerror = function(evt){
            console.warn('websocket onerror:',evt)
            self.promise_of_state.notify('onerror',evt)
            promise.notify('onerror',evt)
        }
        return promise
    },
    send_command:function(command_obj){
        /*
         * @param command: Command instance or "command line"
         */
        //console.log('send command',command_obj)
        //console.log('-->>',command_obj.content.line)
        if (!this.ws) {
            console.warn('not connected, command is aborted ',command_obj)
            let promise = new $.Deferred()
            setTimeout(function(){promise.reject('not connected, command is aborted')},0)
            return promise
        }
        else if (command_obj.file){
            //upload style command
            let formData = new FormData();
            //console.log('uploading file')
            formData.append('file',command_obj.file);
            formData.append('args',JSON.stringify(command_obj.content.args));
            let promise = new $.Deferred()
            var url = command_obj.content.cmd.replace(/\./g,'/')
            if (url.indexOf(ObjshSDK.metadata.resource_route_name) != 0){
                url = ObjshSDK.metadata.resource_route_name+'/'+url
            }
            $.ajax({
                    url : (/^\//.test(url) ? '' : '/')+url, //enforce to start with root("/") 
                    type : 'POST',
                    data : formData,
                    dataType:'json',
                    processData: false,  // tell jQuery not to process the data
                    contentType: false,  // tell jQuery not to set contentType
                    success : function(response) {
                        promise.resolve(response);
                    },
                    error:function(xhr,err){
                        promise.reject(err)
                    }
            });
            return promise
        }
        else{
            command_obj.ts_sent = new Date().getTime()
            Command.waiting_queue[command_obj.content.id]=command_obj
            //console.log('send==>',command_obj.get_payload())
            this.ws.send(command_obj.get_payload()+this.ws_boundary)        
            return command_obj
        }
    },
    upload:function(command_obj){
        //this is just alias of send_command
        return this.send_command(command_obj)
    },
    get_command_url:function(line){
        return '/run/'+ObjshSDK.metadata.runner_name+'.'+line
    },
    run_command_line:function(line){
        // submit command by websocket, and 
        // auto append ObjshSDK.metadata.runner_name
        return this.send_command(Command.from_line(ObjshSDK.metadata.runner_name+'.'+line))
    },
    get_command_line:function(line){
        /* submit the command by http request */
        var promise = new $.Deferred()
        $.ajax({
            method:'GET',
            url:this.get_command_url(line),
            dataType:'json',
            success:function(response){
                promise.resolve(response.command)
            },
            error:function(xhr,err){
                promise.reject(err)
            }
        })
        return promise
    }
}

/* sdk.task */
function TaskUtility(sdk){
    this.sdk = sdk
    // a collection of task_id been watching
    this.watching_ids = {}
    this.watching_ids_list = []
    this.defaults = {
        refresh_interval: 5,
        watch_interval: 5
    }
    // a local cache of the taskdata in server
    this.taskdata_dict = {}
    
    let self = this 
    
    //response to connection state changes
    this.sdk.promise_of_state.progress(function(state){self._onsdk_state(state)})
}
TaskUtility.prototype = {
    list:function(task_ids){
        /* 
         Get the task list from server once.
         
         Returns:
                a promise, resolves with (true,taskdata_dict) or (false, err_message)
        */
        let promise = new $.Deferred() 
        let self = this 

        var args = ['list']
        
        // decise what to list
        if (typeof(task_ids) != 'undefined'){
            //if (task_ids.forEach){
            if (isArrayLike(task_ids)){
                //suppose task_ids is a list
                //task_ids.forEach(function(task_id){
                __.forEach(task_ids,function(task_id){
                    args.push(task_id)
                })
            }
            else{
                //suppose task_ids is string
                args.push(task_ids)
            }
        }
        var watching_all = args.length == 1

        this.sdk.send_command(new Command('task',args,null,'list-task')).done(function(response){
            if (response.retcode==0){
                //console.log(response)
                let new_taskdata = response.stdout 
                var task_updated = {}
                var taskdata_dict = {} // for responses when not listing all
                for (var task_id in new_taskdata){
                    if (new_taskdata[task_id]){
                        self.taskdata_dict[task_id] = new TaskData(new_taskdata[task_id])
                        taskdata_dict[task_id] = self.taskdata_dict[task_id]
                        task_updated[task_id] = 1
                    }
                    else{
                        self.taskdata_dict[task_id] = null
                        taskdata_dict[task_id] = null
                    }
                }
                if (watching_all){
                    // maintain self.taskdata_dict
                    // check and cleanup non-existing self.taskdata_dict
                    var task_to_remove = {}
                    for (var task_id in self.taskdata_dict){
                        if (task_updated[task_id]) continue
                        task_to_remove[task_id] = true

                        // send null to inform watcher, there is no more value
                        if (self.watching_ids[task_id]){
                            self.watching_ids[task_id].notify(null)
                            self.unwatch(task_id)
                        }
                    }
                    for (var task_id in task_to_remove){
                        delete self.taskdata_dict[task_id]
                    }
                    promise.resolve(self.taskdata_dict)
                }
                else{
                    promise.resolve(taskdata_dict)
                }
                
            }
            else{
                promise.reject(response.stderr)
            }
        })
        return promise
    },
    get_result(task_id){
        return this.list([task_id])
    },
    search:function(keyword,search_scope){
        /* 
         Returns:
                a promise, resolves with (true,taskdata_dict) or (false, err_message)
        */
        keyword = keyword.trim()
        
        if (keyword.length==0) return $.when({}) //do nothing
        
        let promise = new $.Deferred() 
        let self = this 
        var args = ['search',search_scope,keyword]
        
        this.sdk.send_command(new Command('task',args,null,'search-task')).done(function(response){
            if (response.retcode==0){
                //console.log(response)
                let new_taskdata = response.stdout 
                var task_updated = {}
                var taskdata_dict = {} // for responses when not listing all
                for (var task_id in new_taskdata){
                    if (new_taskdata[task_id]){
                        self.taskdata_dict[task_id] = new TaskData(new_taskdata[task_id])
                        taskdata_dict[task_id] = self.taskdata_dict[task_id]
                        task_updated[task_id] = 1
                    }
                    else{
                        self.taskdata_dict[task_id] = null
                        taskdata_dict[task_id] = null
                    }
                }
                promise.resolve(taskdata_dict)
            }
            else{
                promise.reject(response.stderr)
            }
        })
        return promise
    },
    watch:function(task_id){
        /*
         * Returns a resolved promise or a command object.
         * If a command object is returned, it will call notify to response running data.
         * So, caller has to use "then" for receiving all kinds of response.
         *
         * ex. 
         * var handler = function(response){..your stuffs..}
         * sdk.task.watch(task_id).progress(handler).fail(handler)
         * 
         */
        let self = this 
        var command = new Command('task',['watch',task_id])
        this.sdk.send_command(command)
        this.watching_ids[task_id] = command 
        var promise = new $.Deferred()
        var watch_handler = function(command_data){
            if (command_data.retcode == 0||(command_data.retcode===null)) {
                //if (command_data.stdout){
                promise.notify(command_data.stdout.command)
            }
            else {
                promise.reject(command_data.stderr)
            }
        }
        command.then(watch_handler,watch_handler,watch_handler)
        return promise
    },
    unwatch:function(task_id){
        if (this.watching_ids[task_id]){
            this.watching_ids[task_id].cancel_command()
            delete this.watching_ids[task_id]
        }
        let self = this 
        var promise = new $.Deferred()
        var command = new Command('task',['unwatch',task_id])
        this.sdk.send_command(command)
        command.done(function(response){
            if (response.retcode==0) promise.resolve(true)
            else promise.reject(response.stderr)
        })
        return promise
    },
    cancel:function(task_id){
        let self = this 
        var command = new Command('task',['cancel',task_id])
        this.sdk.send_command(command)
        var promise = new $.Deferred()
        command.done(function(response){
            let success = response.retcode==0 
            if (success) promise.resolve(response.stdout)
            else promise.reject(response.stderr) 
        })
        return promise
    },
    is_watching:function(task_id){
        return this.watching_ids[task_id] ? true : false
    },
    to_background:function(task_id){
        let self = this 
        var command = new Command('task',['background',task_id])
        this.sdk.send_command(command)
        var promise = new $.Deferred()
        command.done(function(response){
            let success = response.retcode==0 
            promise.resolve(success, (success ? response.stdout : response.stderr))
        })
        return promise
    },
    _onsdk_state:function(state){
        /*
         * save the state of refresh, and restore it when connection is back.
         * internal only
         */
        switch(state){
            case 'onclose':
                if (typeof(this._refresh_timer) != 'undefined'){
                    this._refresh_pause = this._refresh_interval
                }
                break
            case 'onopen':
                if (this._refresh_pause){
                    this.refresh(this._refresh_pause)
                    delete this._refresh_pause
                }
                break
            case 'onerror':
                break
        }
    }
}

function TaskData(metadata){
    /* represents a structure of serialzied task data */
    this.id = metadata.id
    this.name = metadata.name
    this.owner = metadata.owner
    this.state = metadata.state
    this.state_name = ['Cancelled','Ready','Running','Completed','Error'][this.state+1]
    this.command = metadata.command
    this.command_line = (this.command.cmd.split('.').pop())+(this.command.args ? ' '+this.command.args.join(' ') : '')
    this.alive = metadata.alive
    this.background = metadata.command.background
    if (this.background) this.command_line += '&'
}
TaskData.STATE_CANCELLED = -1
TaskData.STATE_READY = 0
TaskData.STATE_RUNNING = 1
TaskData.STATE_COMPLETED = 2
TaskData.STATE_ERROR = 3
TaskData.prototype = {
}

function SDKChannel(sdk){
    /* 
     * convinent object to listen on server-side logs and events
     */
    this.sdk = sdk
    this.disabled = true
    this.listeners = {log:[],event:[]}
    this.openned = false //true if channel is openned

    let self = this 
    this.event = {
        add_listener:function(callback){return self.add_listener('event',callback)},
        remove_listener:function(callback){return self.remove_listener('event',callback)}
    }
    this.log = {
        add_listener:function(callback){return self.add_listener('log',callback)},
        remove_listener:function(callback){return self.remove_listener('log',callback)}
    }
    //response to connection state changes
    this.sdk.promise_of_state.progress(function(state){self._onsdk_state(state)})
}
SDKChannel.prototype = {
    enable:function(yes){
        //should be called before sdk is connected
        if (typeof(yes)=='undefined') yes = true
        this.disabled = yes ? false : true
    },
    add_listener:function(channel_name, callback){
        /*
         * @param channel_name:(string) event or log
         */
        this.listeners[channel_name].push(callback)
    },
    remove_listener:function(channel_name,callback){
        /*
         * @param channel_name:(string) event or log
         */
        let idx = this.listeners[channel_name].indexOf(callback) 
        if (idx >= 0) this.listeners[channel_name].splice(idx,1)
        if (this.listeners.length==0){
            this.close_channel()
        }
    },
    open_channel:function(){
        let self = this 
        self.openned = true
        
        let event_channel_command = this.sdk.run_command_line('root.pub.event.observe') 
        event_channel_command.progress(function(response){
            if (response.retcode==null || response.retcode==0) {
                //self.listeners.event.forEach(function(func){
                __.forEach(self.listeners.event,function(func){
                    func(response.stdout)
                })
            }
            else console.warn('event observer error',response)
        })

        let log_channel_command = this.sdk.run_command_line('root.pub.log.observe') 
        log_channel_command.progress(function(response){
            if (response.retcode==null || response.retcode==0) {
                //self.listeners.log.forEach(function(func){
                __.forEach(self.listeners.log,function(func){
                    func(response.stdout)
                })
            }
            else console.warn('log observer error',response)
        })
        this._openned_channels = [event_channel_command, log_channel_command]
        
    },
    close_channel:function(){
        let self = this 
        self.openned = false
        //this._openned_channels.forEach(function(channel_command){
        __.forEach(this._openned_channels,function(channel_command){
            self.sdk.send_command(channel_command.cancel_command()).done(function(){
                //console.log('event channel closed')
            })
        })
    },    
    _onsdk_state:function(state){
        if (this.disabled) return
        switch(state){
            case 'onopen':
                this.open_channel()
                break
            case 'onclose':
                this.openned = false
                break
        }
    }
}

function Logger(sdk){
    /*
     * wrapper to write log to server log
     */
    this.sdk = sdk
    this.level_names = {
        '10':'debug',
        '20':'info',
        '30':'warn',
        '40':'error',
        '50':'critical'
    }
    this.received_min_timestamp = Infinity
}
Logger.prototype = {
    _msg:function(level, content){
        let a_line = JSON.stringify(content) 
        let command = new Command(this.sdk.metadata.runner_name+'.root.pub.log.msg',[level, a_line]) 
        return this.sdk.send_command(command)
    },
    info:function(content){
        return this._msg('info',content)
    },
    warn:function(content){
        return this._msg('warn',content)
    },
    error:function(content){
        return this._msg('error',content)
    },
    debug:function(content){
        return this._msg('debug',content)
    },
    critical:function(content){
        return this._msg('critical',content)
    },
    get:function(options){
        /*
         * Arguments:
         *      options:{
         *          start:
         *          end:
         *      }, or
         *      options:{
         *          last_hours: (int) hours before
         *      },
         * Returns:
         *      [{
         *          time:
         *          level:
         *          name:
         *          text:    
         *      }*],
         */
        //if (typeof(options.end_ts)=='undefined') end_ts = null
        let command = new Command(this.sdk.metadata.runner_name+'.root.pub.log.get',[options]) 
        let self = this 
        let promise = new $.Deferred() 
        var allrows = []
        var chunks = []
        this.sdk.send_command(command).progress(function(response){
            if (response.retcode>0)return promise.reject(response.stderr)
            var rows = []
            chunks.push(response.stdout)
        }).done(function(response){
            self.received_min_timestamp  = response.stdout.start_ts
            var rows = []
            var t0 = new Date().getTime()
            for (var i=0;i<chunks.length;i++){
                var chunk = chunks[i]
                for (var j=0;j<chunk.length;j++){
                    var line = chunk[j]
                    let time = parseFloat(line.substr(0,13))
                    rows.push({
                        time : time,
                        level : parseInt(line.substr(14,2)),
                        name : self.level_names[line.substr(14,2)],
                        text:line.substr(17).replace(/\\n/g,'\n')
                    })
                }                   
            }
            var t1 = new Date().getTime()
            promise.notify(rows)
            promise.resolve(response.stdout)
        })
        return promise
    },
    reset_received_min_timestamp:function(){
        this.received_min_timestamp = Infinity
    },

}
function Bus(sdk){
    /*
     * wrapper to write message to other web clients
     */
    this.sdk = sdk
}
Bus.prototype = {
    join:function(room_id){
        var self = this
        this.promise = new $.Deferred()
        var args = ['R'+room_id]
        //ensure room_id to be text (not number), prefix a 'R'
        var cmd = new Command(ObjshSDK.metadata.runner_name+'.root.pub.bus.join',args)
        this.sdk.send_command(cmd).progress(function(response){
            self.promise.notify(response.stdout)
        })
        //this.progress = this.promise.progress
        return this.promise
    },
    broadcast:function(room_id,payload){
        var cmd = new Command(ObjshSDK.metadata.runner_name+'.root.pub.bus.broadcast',['R'+room_id,payload])
        return this.sdk.send_command(cmd)
    },
    broadcast_raw:function(room_id,payload,blob_obj){
        payload.length = blob_obj.size
        var self = this
        var cmd = new Command(ObjshSDK.metadata.runner_name+'.root.pub.bus.broadcast',['R'+room_id,payload])
        var promise = new $.Deferred()
        this.sdk.send_command(cmd).done(function(response){
            if (response.retcode==0){
                try{
                    self.sdk.ws.send(blob_obj)
                    promise.resolve(true)
                }
                catch(e){
                    console.warn(e)
                    promise.reject(e)
                }
            }
            else promise.reject(response.stderr)
        })
        return promise       
    }
}

function User(sdk){
    this.sdk = sdk
    this.username = null
    this.is_authenticated = false
    this.preferences = new Preferences(sdk)
    this.ready_callbacks = []
    this.ready = false
}
User.prototype = {
    set_metadata:function(metadata){
        // metadat only contains "username"
        this.username = metadata.username
    },
    on_connected:function(){
        var self = this
        this.preferences.sync_from_server().done(function(){
            self.ready = true
            self.ready_callbacks.forEach(function(callback){
                callback()
            })
            delete self.ready_callbacks
        })
    },
    call_when_ready:function(callback){
        if (this.ready) setTimeout(function(){callback()},0)
        else this.ready_callbacks.push(callback)
    }
}
function PreferenceItem(preferences,name){
    this.name = name
    this.preferences = preferences
    this._value = this.preferences.get(name)
    var self = this
    this.preferences.__defineGetter__(name,function(){return self._value})
    this.preferences.__defineSetter__(name,function(v){
        self._value = v
        self.preferences.set(name,self._value)
    })
}
function Preferences(sdk){
    this.sdk = sdk
    this.values = null
    this._version = 0
    this._sync_timer = 0
}
Preferences.prototype = {
    sync_from_server:function(){
        //called soon after login
        let self = this 
        let promise = new $.Deferred() 
        this.sdk.run_command_line('root.pub.user_preferences.get').done(function(response){
            if (response.retcode != 0) {
                console.warn(response.stderr)
                promise.reject(response.retcode,response.stderr)
                return            
            }
            self.values = response.stdout
            promise.resolve()
        })
        return promise
    },/*
    get_item:function(name){
        var item = new PreferenceItem(this,name)
        return item
    },*/
    get:function(name){
        if (this.name===null) throw "Preferences is not ready to access"
        return this.values[name]
    },
    set:function(key,value){
        this.values[key] = value
        this._version += 1
        this.touch()
    },
    touch:function(){
        //call this to invoke sync to server
        let self = this 
        if (this._sync_timer==0){
            this._sync_timer = setTimeout(function(){ self.sync_to_server()},3000)
        }
    },
    remove:function(name){
        delete this.values[name]
        this._version += 1
        this.touch()
    },
    clear:function(){
        this.values = {}
        this._version += 1
        this.touch()
    },
    sync_to_server:function(){
        //store to server
        let self = this 
        let _version = this._version 
        var command = new Command(self.sdk.metadata.runner_name+'.root.pub.user_preferences.set',[this.values])
        let promise = this.sdk.send_command(command)
        promise.done(function(response){
            //console.log(response)
            //console.log('Preferences stored',self._version, _version,self.value)
            if (self._version == _version) {
                self._sync_timer = 0
            }else{
                self._sync_timer = setTimeout(function(){ self.sync_to_server()},3000)
            }
        })
        return promise
    },    
}
console.log('Objsh SDK 20180831')
export { Command, ObjshSDK };

/*Auth generated by js2es6.py at 2018-09-16 17:14:46.922803*/
