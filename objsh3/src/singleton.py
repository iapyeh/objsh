#
# REF from https://stackoverflow.com/questions/6760685/creating-a-singleton-in-python
#
_singleton_classs = []
import sys
class Singleton(object):
    _instance = None
    def __new__(class_, *args, **kwargs):
        if not isinstance(class_._instance, class_):
            for inst in _singleton_classs:
                if inst.__class__.__name__ == class_.__name__:
                    raise Exception('Duplicated singleton of %s created by %s and %s' % (class_.__name__,inst.__class__,class_))
            #print 'creating singleton for ',class_.__name__
            if sys.version_info[0]==2:
                class_._instance = object.__new__(class_, *args, **kwargs)
            else:
                class_._instance = object.__new__(class_)
            _singleton_classs.append(class_._instance)
        return class_._instance
