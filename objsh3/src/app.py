"""
This script is intented to run from "tree".

case 1: when objsh is a site-package
    (not implemented yet)

    $python3 app.py

    For example:
        cd ~/Dropbox/workspace/ObjectiveShell/trees/iap_sidebyside3
        python3 app.py

case 2: when objsh is not a site-package (in source code)
    
    $python3 app.py <src path of objsh>
    
    For example:
        cd ~/Dropbox/workspace/ObjectiveShell/trees/iap_sidebyside3
        python3 app.py "~/Dropbox/workspace/ObjectiveShell/objsh3/src"

這個app.py的用法：
1. 複製一份本程式（app.py）到app的tree去，例如
    cp app.py ~/Dropbox/workspace/sidebyside白板系統/sidebyside
2. 在 ~/ 放一個whiteboard.sh，內容是（兩行）：
        cd ~/Dropbox/workspace/sidebyside白板系統/sidebyside
        python3 app.py "~/Dropbox/workspace/ObjectiveShell/objsh3/src"
    把objsh的src路徑當參數傳給app.py
"""

import sys, os, __main__, traceback
try:
    import objsh
except ImportError:
    #development environment
    objsh_path = sys.argv[1]
    if objsh_path[0] == '~':
        objsh_path = os.path.expanduser(objsh_path)
    assert os.path.exists(objsh_path)
    if not objsh_path in sys.path:
        sys.path.insert(0,objsh_path)
    import objsh

reactor = objsh.reactor
def main():
    __main__.objsh = objsh
    
    tree_path = os.path.abspath(os.path.dirname(__file__))
    sys.stderr.write('use tree at %s\n' % tree_path)
    try:
        objsh.init(tree_path)
    except:
        traceback.print_exc()
        reactor.stop()
if __name__ == '__main__':
    from twisted.internet import reactor
    reactor.callWhenRunning(main)
    reactor.run()
