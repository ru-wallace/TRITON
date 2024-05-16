import sys
import traceback

def eprint(*args, **kwargs):
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)
    
def eprint_exception(e:Exception, **kwargs):
    kwargs['file'] = sys.stderr
    traceback.print_exception(e)
    
def eprint_exc(e, **kwargs):
    eprint_exception(e, **kwargs)