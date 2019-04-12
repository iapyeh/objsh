/*
 * 2018/12/23
 */
//required by react
//uncomment import $ from 'jquery'

function get_sdk_src(){
    //return the url of sdk.js or sdk_react.js
    var scripts = document.getElementsByTagName('script');
    var my_src = ''
    for(var i=0;i<scripts.length;i++){
        if (scripts[i].src.indexOf('/sdk') > 0){
            my_src = scripts[i].src
            break
        }
    }
    return my_src
}
if (!window.TextDecoder){
    //support MSIE
    var my_src = get_sdk_src()
    var script = document.createElement('script')
    var p = my_src.indexOf('/sdk.js')
    if (p==-1) p = my_src.indexOf('/sdk_react.js')
    script.src = my_src.substring(0,p)+'/encoding.js'
    document.head.appendChild(script)
}

function ArrayBufferToString(buffer) {
    return BinaryToString(String.fromCharCode.apply(null, Array.prototype.slice.apply(new Uint8Array(buffer))));
}

function StringToArrayBuffer(string) {
    return StringToUint8Array(string);
}

function BinaryToString(binary) {
    var error;

    try {
        return decodeURIComponent(escape(binary));
    } catch (_error) {
        error = _error;
        if (error instanceof URIError) {
            return binary;
        } else {
            throw error;
        }
    }
}

function StringToBinary(string) {
    var chars, code, i, isUCS2, len, _i;

    len = string.length;
    chars = [];
    isUCS2 = false;
    for (i = _i = 0; 0 <= len ? _i < len : _i > len; i = 0 <= len ? ++_i : --_i) {
        code = String.prototype.charCodeAt.call(string, i);
        if (code > 255) {
            isUCS2 = true;
            chars = null;
            break;
        } else {
            chars.push(code);
        }
    }
    if (isUCS2 === true) {
        return unescape(encodeURIComponent(string));
    } else {
        return String.fromCharCode.apply(null, Array.prototype.slice.apply(chars));
    }
}

function StringToUint8Array(string) {
    var binary, binLen, buffer, chars, i, _i;
    binary = StringToBinary(string);
    binLen = binary.length;
    buffer = new ArrayBuffer(binLen);
    chars  = new Uint8Array(buffer);
    for (i = _i = 0; 0 <= binLen ? _i < binLen : _i > binLen; i = 0 <= binLen ? ++_i : --_i) {
        chars[i] = String.prototype.charCodeAt.call(binary, i);
    }
    return chars;
}

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
            name:name,
            rawsize:0,
        }
    }
}
Command.prototype = {
    get_payload:function(){
        return JSON.stringify(this.content)
    },
    get_payload_header:function(type,num){
        var arr = new Uint8Array([
            (type & 0x000000ff),
            (num & 0xff000000) >> 24,
            (num & 0x00ff0000) >> 16,
            (num & 0x0000ff00) >> 8,
            (num & 0x000000ff)
       ]);
       //return ArrayBufferToString(arr)
       //return String.fromCharCode.apply(null, arr);
       return arr
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
     *    protocol:(string;optional) default "ws:" for http or "wss:" for https (Deprecicated since 20180927) 
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

    if (typeof(options)=='undefined') {
        //try to figure out connection options
        var port = window.location.port 
        if (!port) port = window.location.protocol=='https:' ? 443 : 80
        var hostname = window.location.hostname //let
        //figure out accesspath by url
        var paths = get_sdk_src().split('/') //let
        var p = paths.indexOf('websdk')
        // simple url is http://host:port/websdk/sdk.js, so p should > 3
        var access_path = '/'+(p>3 ? paths[p-1] : '') 
        options = {
            host:hostname,
            port:port,
            access_path:access_path,
            websocket:null //to be assigned after login
        }
    }
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
        //console.log('options=',options)
        //this should be called before login
        //caution: options of websocket could be overrided after login
        if (this.ws) return
        var is_secure = window.location.protocol=='https:' //let
        this.ws_protocol = is_secure ? 'wss:' : 'ws:' //let
        
        this.host = options.host || window.location.hostname //let
        var path = options.access_path || '/' //let
        if (path=='/'){
            //not behind proxy
            this.port = options.port
        }
        else{
            //behide proxy, use same port with loading page
            this.port = window.location.port
        }
        if (!this.port) this.port = is_secure ? '443' : '80'
        var current_host_port = window.location.host.split(':') 
        if (current_host_port.length==1) current_host_port.push((is_secure ? '443' : '80'))
        this.site_url = '//' + this.host + ':' +this.port
        
        //ensure access_path is ended by /
        this.access_path = path + (/\/$/.test(path) ? '' : '/')
        this.is_cross_site = (this.host != current_host_port[0] || this.port != current_host_port[1])
        
        // assing this.ws_url
        if (options.websocket){
            var ws_route = options.websocket ? options.websocket.route : null
            if (ws_route){
                this.ws_url = this.ws_protocol + '//' + this.host + ':' + this.port + ws_route
            }
            else{
                var ws_port = options.websocket ? options.websocket.port : 0
                this.ws_url = this.ws_protocol + '//' + this.host + ':' + ws_port
            }    
        }
        else{
            this.ws_url = null
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
        var self = this //let
        var url = this.site_url+this.access_path+'login' //let
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
                var x = window.open(cross_site_url,'objsh_login') //let
                setTimeout(function(){try{x.close()}catch(e){}},100)
            }
        }
        else{
            if (!username) username = self._credential ? self._credential.username : ''
            if (!password) password = self._credential ? self._credential.password : ''
            //console.log('login',username,password,promise)
            data = {username:username,password:password,ts:new Date()} //let
            if (this.is_cross_site) {
                var cross_site_url = url//let
                cross_site_url += '?username='+username+'&password='+password //let
                var x = window.open(cross_site_url,'objsh_login') //let
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
                if (!self.ws_url){
                    var options = {websocket:self.metadata.websocket_options}
                    var ws_route = options.websocket.route
                    if (ws_route){
                        self.ws_url = self.ws_protocol + '//' + self.host + ':' + self.port + ws_route
                    }
                    else{
                        var ws_port = options.websocket.port
                        self.ws_url = self.ws_protocol + '//' + self.host + ':' + ws_port
                    }
                }
                self.user.set_userdata(self.metadata.user)
                self.user.is_authenticated = true

                // Command will use this copy no matter what instance name of ObjshSDK is.
                ObjshSDK.metadata = {
                    username:self.metadata.user.username,
                    runner_name : self.metadata.statetree_runner_name, 
                    server_name:self.metadata.server_name, 
                    objsh_version:self.metadata.objsh_version,
                    resource_route_name:self.metadata.resource_route_name
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
        var self = this //let
        var url = this.site_url+this.access_path+'logout' //let
        if (this.is_cross_site) {
            var x = window.open(url,'objsh_login') //let
            setTimeout(function(){x.close()},100)
        }

        this.is_authenticated = false
        this.user.is_authenticated = false
        delete this._credential

        if (this.ws) this.ws.close()
        
        var promise = new $.Deferred()//let
        $.ajax({
          dataType: "json",
          url: url,
          data: null,
          success: function(response){
            if (response.retcode==0){
                // initialize with metadata
                self.metadata = null
                ObjshSDK.metadata = null
                promise.resolve(true)
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
        var self = this //let
        self.ws_array_buffer = null
        self.ws_boundary = '♞'
        self.ws_boundary_ab_length =  StringToArrayBuffer(self.ws_boundary).length
        self.ws = new WebSocket(this.ws_url)
        var promise = new $.Deferred()
        self.ws.onopen = function(evt){
            self.is_connected = true

            //initialize Preferences
            self.user.on_connected()
            
            self.promise_of_state.notify('onopen',evt)
            promise.notify('onopen',evt)
        }
        self.ws.onmessage = function(evt){
            //console.log('>>'+evt.data.length+',data=',evt.data)
            self._last_ping_ts = new Date().getTime()
            var fileReader = new FileReader();
            var package_overhead = 5 + self.ws_boundary_ab_length
            var packages = []   
            fileReader.onload = function(event){
                var data_buffer = new Uint8Array(event.target.result)
                var array_buffer
                if (self.ws_array_buffer){
                    array_buffer = new Uint8Array(self.ws_array_buffer.length + data_buffer.length)
                    array_buffer.set(self.ws_array_buffer)
                    array_buffer.set(self.ws_array_buffer.length,data_buffer)
                }
                else{
                    array_buffer = data_buffer
                }
                while (true){
                    var package_type = array_buffer[0]
                    var package_length = (array_buffer[1] << 24) + (array_buffer[2] << 16) + (array_buffer[3] << 8) + array_buffer[4] 
                    //console.log('==>',package_type, package_length, array_buffer)
                    if (array_buffer.length >= package_overhead+package_length){
                        var content_array = array_buffer.subarray(5,5+package_length)
                        var package = new TextDecoder("utf-8").decode(content_array);
                        packages.push(package)
                        array_buffer = array_buffer.subarray( package_overhead+package_length )
                        if (array_buffer.length < package_overhead) break
                    }
                    else{
                        break
                    }
                }
                self.ws_array_buffer = array_buffer.length ? array_buffer : null
                __.forEach(packages,function(package_content,idx){
                    try{
                        var response = JSON.parse(package_content)
                        Command.consume(response)
                    }
                    catch(e){
                        console.log('response=',package_content)
                        console.warn(e)
                    }
                })                
            }
            fileReader.readAsArrayBuffer(evt.data)
        }
        self.ws.onclose = function(evt){
            self.ws = null
            self.is_connected = false
            self.promise_of_state.notify('onclose',evt)
            //reconect
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
        if (!this.ws) {
            console.warn('not connected, command is aborted ',command_obj)
            var promise = new $.Deferred()//let
            setTimeout(function(){promise.reject('not connected, command is aborted')},0)
            return promise
        }
        else if (command_obj.file){
            //upload style command
            var formData = new FormData();//let
            formData.append('file',command_obj.file);
            formData.append('args',JSON.stringify(command_obj.content.args));
            var promise = new $.Deferred()//let
            var url = command_obj.content.cmd.replace(/\./g,'/')
            if (url.indexOf(ObjshSDK.metadata.resource_route_name) != 0){
                url = ObjshSDK.metadata.resource_route_name+'/'+url
            }
            $.ajax({
                url : this.access_path + url,
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
            var payload = StringToArrayBuffer(command_obj.get_payload()+this.ws_boundary)
            var payload_length = payload.length - this.ws_boundary_ab_length
            var payload_header = command_obj.get_payload_header(1,payload_length)
            var tmp = new Uint8Array(payload_header.byteLength + payload.byteLength);
            tmp.set(new Uint8Array(payload_header), 0);
            tmp.set(new Uint8Array(payload), payload_header.byteLength);
            this.ws.send(tmp)
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
    
    var self = this //let
    
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
        var promise = new $.Deferred() //let
        var self = this //let

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
        var watching_all = (args.length == 1 ? true : false);

        this.sdk.send_command(new Command('task',args,null,'list-task')).done(function(response){
            if (response.retcode==0){
                //console.log(response)
                var new_taskdata = response.stdout //let
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
    get_result:function(task_id){
        return this.list([task_id])
    },
    search:function(keyword,search_scope){
        /* 
         Returns:
                a promise, resolves with (true,taskdata_dict) or (false, err_message)
        */
        keyword = keyword.trim()
        
        if (keyword.length==0) return $.when({}) //do nothing
        
        var promise = new $.Deferred() //let
        var self = this //let
        var args = ['search',search_scope,keyword]
        
        this.sdk.send_command(new Command('task',args,null,'search-task')).done(function(response){
            if (response.retcode==0){
                //console.log(response)
                var new_taskdata = response.stdout //let
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
        var self = this //let
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
        var self = this //let
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
        var self = this //let
        var command = new Command('task',['cancel',task_id])
        this.sdk.send_command(command)
        var promise = new $.Deferred()
        command.done(function(response){
            var success = response.retcode==0 //let
            if (success) promise.resolve(response.stdout)
            else promise.reject(response.stderr) 
        })
        return promise
    },
    is_watching:function(task_id){
        return this.watching_ids[task_id] ? true : false
    },
    to_background:function(task_id){
        var self = this //let
        var command = new Command('task',['background',task_id])
        this.sdk.send_command(command)
        var promise = new $.Deferred()
        command.done(function(response){
            var success = response.retcode==0 //let
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

    var self = this //let
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
        var idx = this.listeners[channel_name].indexOf(callback) //let
        if (idx >= 0) this.listeners[channel_name].splice(idx,1)
        if (this.listeners.length==0){
            this.close_channel()
        }
    },
    open_channel:function(){
        var self = this //let
        self.openned = true
        
        var event_channel_command = this.sdk.run_command_line('root.pub.event.observe') //let
        event_channel_command.progress(function(response){
            if (response.retcode==null || response.retcode==0) {
                //self.listeners.event.forEach(function(func){
                __.forEach(self.listeners.event,function(func){
                    func(response.stdout)
                })
            }
            else console.warn('event observer error',response)
        })

        var log_channel_command = this.sdk.run_command_line('root.pub.log.observe') //let
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
        var self = this //let
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
        var a_line = JSON.stringify(content) //let
        var command = new Command(this.sdk.metadata.runner_name+'.root.pub.log.msg',[level, a_line]) //let
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
        var command = new Command(this.sdk.metadata.runner_name+'.root.pub.log.get',[options]) //let
        var self = this //let
        var promise = new $.Deferred() //let
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
                    var time = parseFloat(line.substr(0,13))//let
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
    this.room_id = null
}
Bus.prototype = {
    join:function(room_id){
        var self = this
        this.promise = new $.Deferred()
        var args = ['R'+room_id]
        //ensure room_id to be text (not number), prefix a 'R'
        this.room_id = room_id
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
    this.metadata = null //keep the origin data from server
}
User.prototype = {
    set_userdata:function(userdata){
        // metadat only contains "username"
        this.username = userdata.username
        this.metadata = userdata.metadata
    },
    on_connected:function(){
        var self = this
        this.preferences.sync_from_server().done(function(){
            self.ready = true
            self.ready_callbacks.forEach(function(callback){
                callback()
            })
            //keep self.ready_callbacks for reconnection
            //delete self.ready_callbacks
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
        var self = this //let
        var promise = new $.Deferred() //let
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
        var self = this //let
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
        var self = this //let
        var _version = this._version //let
        var command = new Command(self.sdk.metadata.runner_name+'.root.pub.user_preferences.set',[this.values])
        var promise = this.sdk.send_command(command)//let
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
console.log('Objsh SDK 20181223')
//uncomment export { Command, ObjshSDK };