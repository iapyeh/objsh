/*
 * Encapsulate communications between client and server
 *
 * 2017-12-30
 *      Fix: rename from sdk.js to objsh.js
 * 2017-12-27
 *      Fix: set default hostname to localhost (for compatible in React)
 */
function Command(cmd,args){
    this.promise = new $.Deferred()
    this.ts_sent = 0 //will be assigned if this command has been sent
    this.content = {
        id:''+(new Date().getTime())+''+Math.floor(Math.random()*1000),
        cmd:cmd,
        args:args
    }
}
Command.prototype = {
    get_payload:function(){
        return JSON.stringify(this.content)
    },
    done:function(callback,args){
        this.promise.done(function(response){callback(response,args)})
    }
}
/* class methods and properties */
Command.waiting_queue = {}
Command.handlers = {}
Command.from_line = function(line){
    line = line.trim()
    var p = line.indexOf(' ')
    var cmd, args
    if (p==-1){
        cmd = line
        args = null
    }
    else{
        cmd = line.substring(0,p)
        var args_raw = line.substring(p+1).trim().split(/\s+/)
        args = []
        for (var i=0,len=args_raw.length;i<len;i++){
            if ( (i+1) && ((args_raw[i].substr(0,1)=='"' && args_raw[i+1].substr(0,1)=='"')||(args_raw[i].substr(0,1)=='\'' && args_raw[i+1].substr(0,1)=='\''))){
                var arg = args_raw[i]+args_raw[i+1]
                args.push(arg.substr(1,arg.length-2))
                i += 1
            }
            else{
                args.push(args_raw[i])
            }
        }
    }
    if (cmd) return new Command(cmd,args)
    else return null
}
Command.consume = function(response){
    if (response.id){
        var command_obj = Command.waiting_queue[response.id]
        if (command_obj){
            command_obj.promise.resolve(response)
            delete Command.waiting_queue[response.id]
        }
        else{
            console.warn('orphan response',response)
        }
    }
    else {
        //unsolicited messages
        //such as multitasks progress updating
        Command.handlers[response.kind](response)
    }
}


function StructuredShell(ws_url){
    this.ws_url = ws_url
}
StructuredShell.prototype = {
    connect:function(){
        var promise = $.Deferred(); 
        var self = this
        self.ws_buffer = []
        self.ws_boundary = '\r\n'
        self.ws = null
        var url = this.ws_url || (location ? 'ws://'+location.hostname+':1788' : 'ws://localhost:1788')
        var ws = new WebSocket(url)
        ws.onopen = function(evt){
            self.ws = ws
            promise.resolve(ws)
        }
        ws.onmessage = function(evt){
            //console.log('>>'+evt.data.length+'::'+evt.data)
            self._last_ping_ts = new Date().getTime()
            var data = self.ws_buffer.join('')+evt.data
            self.ws_buffer = []
            var responses = []
            var p = data.indexOf(self.ws_boundary)
            if (p==-1){
                self.ws_buffer.push(data)
                return
            }
            var pos = 0
            while (p>0){
                if (pos==0) {
                    var chunk = self.ws_buffer.join('')+data.substring(0,p)
                    //console.log('('+chunk+')')
                    var response = JSON.parse(chunk)
                    responses.push(response)
                    self.ws_buffer = []
                }
                else{
                    var chunk = data.substring(pos,p)
                    console.log(chunk)
                    var response = JSON.parse(chunk)
                    responses.push(response)
                }
                pos = p+(self.ws_boundary.length-1)+1
                if (pos>=data.length) break
                p = data.indexOf(self.ws_boundary,pos)
            }
            if (pos < data.length){
                self.ws_buffer.push(data.substring(pos))
            }
            responses.forEach(function(response){
                Command.consume(response)
            })
        }
        ws.onclose = function(evt){
            console.log('ws closed')
        }
        return promise
    },
    send_command:function(command_obj){
        command_obj.ts_sent = new Date().getTime()
        Command.waiting_queue[command_obj.content.id]=command_obj
        this.ws.send(command_obj.get_payload()+this.ws_boundary)
        return command_obj
    }
}