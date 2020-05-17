""" cnodes are based on astoids but focused on named blocks of code
"""

from enum import Enum, auto
import ast, re
from astoid import parse as astoid_parse, CodeClause
import tokenize, token, sys, os, os.path, traceback, pdb
from importlib.util import find_spec
import logarhythm

logger = logarhythm.getLogger()
logger.level = logarhythm.DEBUG

wspace_re = re.compile('^\\s*')


class ParseState(Enum):
    NEWBLOCK=auto()
    BUILD=auto()
    ENDBLOCK=auto()
    DONE=auto()


def parse_module(path,parent_cnode=None,prev_sibling_cnode=None,predecessor_cnode=None):
    if os.path.splitext(path)[1].lower() not in ['.py','.pyw']:
        raise Exception('parse() must be called against a python script file')
    with open(path,'r') as f:
        source = f.read()
    astoid_tree = astoid_parse(source)
    source_lines = astoid_tree.source_lines
    stack = []
    cnode = None
    module_cnode = None

    astoid_tree_walk = astoid_tree.walk()

    state = ParseState.NEWBLOCK
    astoid = None
    get_next = True
    while state != ParseState.DONE:
        if get_next:
            try:
                astoid = next(astoid_tree_walk)
            except StopIteration:
                logger.debug('Walk stop iteration')
                state = ParseState.DONE
                astoid = None
        get_next = True #default for next iteration will be to get next unless explicitly told otherwise below in this iteration
        logger.debug('Astoid: %s' % astoid)
        logger.debug('State: %s' % state)
        logger.debug('Starting Cnode: %s' % cnode)
        logger.debug('Parent: %s' % parent_cnode)
        logger.debug('Prev sibling: %s' % prev_sibling_cnode)
        logger.debug('Predecessor: %s' % predecessor_cnode)
        logger.debug('Stack: %s' % stack)
        if state == ParseState.NEWBLOCK:
            if astoid.line_index is not None:
                first_line = astoid.source_lines[astoid.line_index]
                indentation = wspace_re.search(first_line).group(0)
            else:
                indentation = None
            logger.debug('Indentation: %s' % repr(indentation))
            if indentation is not None and prev_sibling_cnode is not None and prev_sibling_cnode.indentation is not None and prev_sibling_cnode.indentation != indentation and prev_sibling_cnode.indentation.startswith(indentation):
                next_state = ParseState.ENDBLOCK
            else:
                ast_type,clause = astoid.type
                if clause is None or ast_type not in ast_type_map:
                    cnode = CnodeBlock(parent_cnode,prev_sibling_cnode,predecessor_cnode,module_cnode)
                    next_state = cnode.add_astoid(astoid,state)
                else:
                    cnode_class = ast_type_map[ast_type]
                    if cnode_class is CnodeModule:
                        cnode = cnode_class(path,parent_cnode,prev_sibling_cnode,predecessor_cnode)
                        module_cnode = cnode
                        next_state = cnode.add_astoid(astoid,state)
                    else:
                        cnode = cnode_class(parent_cnode,prev_sibling_cnode,predecessor_cnode,module_cnode)
                        next_state = cnode.add_astoid(astoid,state)
        elif state == ParseState.BUILD:
            if astoid.line_index is not None:
                first_line = astoid.source_lines[astoid.line_index]
                indentation = wspace_re.search(first_line).group(0)
            else:
                indentation = None
            logger.debug('Indentation: %s' % repr(indentation))
            if indentation is not None and prev_sibling_cnode is not None and prev_sibling_cnode.indentation is not None and prev_sibling_cnode.indentation != indentation and prev_sibling_cnode.indentation.startswith(indentation):
                next_state = ParseState.ENDBLOCK
            else:
                ast_type,clause = astoid.type
                if clause is None or ast_type not in ast_type_map:
                    next_state = cnode.add_astoid(astoid,state)
                else:
                    cnode_class = ast_type_map[ast_type]
                    prev_sibling_cnode = cnode
                    cnode = cnode_class(parent_cnode,prev_sibling_cnode,predecessor_cnode,module_cnode)
                    next_state = cnode.add_astoid(astoid,state)
        elif state == ParseState.DONE:
            next_state = ParseState.DONE
        else:
            raise Exception('Invalid state: %s' % repr(state))

        logger.debug('Ending Cnode: %s' % cnode)
        logger.debug('-------> %s\n' % (next_state))

        predecessor_cnode = cnode
        if next_state == ParseState.NEWBLOCK:
            stack.append(cnode)
            parent_cnode = cnode
            cnode = None
            prev_sibling_cnode = None
        elif next_state == ParseState.ENDBLOCK:
            #clear prev_sibling.next_sibling
            if len(stack) > 0:
                get_next = False #astoid not consumed, send same astoid through loop again after popping stack and changing state
                prev_sibling_cnode = stack.pop()
                parent_cnode = prev_sibling_cnode.parent
                cnode = None
                next_state = ParseState.NEWBLOCK
            else:
                next_state = ParseState.DONE
        elif next_state == ParseState.BUILD:
            prev_sibling_cnode = cnode
        elif next_state == ParseState.DONE:
            pass
        else:
            raise Exception('Invalid state transition: %s to %s' % (repr(state),repr(next_state)))
        state = next_state
    return module_cnode

class Cnode():
    def __init__(self,parent,prev_sibling=None,predecessor=None,module=None):
        self.parent = parent
        if parent is not None:
            parent.children.append(self)
        self.astoids = []
        self.children = []
        self.line_index = ...
        self.indentation = ...
        if prev_sibling is not None:
            if prev_sibling.next_sibling is None:
                prev_sibling.next_sibling = self
            else:
                raise Exception('Multiple next siblings')
        self.prev_sibling = prev_sibling
        self.next_sibling = None #may be overwritten by next sibling
        if predecessor is not None:
            if predecessor.successor is None:
                predecessor.successor = self
            else:
                raise Exception('Multiple successors')
        self.predecessor = predecessor
        self.successor = None #may be overwritten by successor
        self.module=module
    def init(self,first_astoid,next_parse_state):
        #run immediately after the first astoid is added
        first_astoid = self.astoids[0]
        line_index = first_astoid.line_index
        self.line_index = line_index
        if line_index is not None:
            first_line = first_astoid.source_lines[line_index]
            self.indentation = wspace_re.search(first_line).group(0)
        else:
            self.indentation = None
        return next_parse_state

    def final(self):
        target = self
        while len(target.children) > 0:
            target = target.children[-1]
        return target

    def add_astoid(self,astoid,parse_state):
        if astoid.cnode is not None and astoid.cnode is not self:
            raise Exception('Multiple cnodes for one astoid')
        astoid.cnode = self
        initialization = (len(self.astoids) == 0)
        next_parse_state = self.process_astoid(astoid,parse_state)
        if initialization:
            next_parse_state = self.init(astoid,next_parse_state)
        return next_parse_state


    def process_astoid(self,astoid,parse_state):
        raise NotImplementedError('This method is intended to be overwritten by subclasses')
        self.astoids.append(astoid)
        next_parse_state = ...
        return next_parse_state


class CnodePackage(Cnode):
    def __init__(self,path,parent=None,prev_sibling=None,predecessor=None):
        if not os.path.isdir(path) or not os.path.exists(os.path.join(path,'__init__.py')):
            raise Exception('Path is not a valid package path: %s' % path)
        self.path = path
        super().__init__(parent,prev_sibling,predecessor)

        child_prev_sibling = None
        child_predecessor = self
        for item_name in sorted(os.listdir(path)):
            item_path = os.path.join(path,item_name)
            if os.path.isdir(item_path):
                if os.path.exists(os.path.join(item_path,'__init__.py')):
                    child = CnodePackage(item_path,self,child_prev_sibling,child_predecessor)
                    child_prev_sibling = child
                    child_predecessor = child.final()
            else:
                if os.path.splitext(filename)[1].lower() in ['.py','.pyw']:
                    child = parse(os.path.join(path,filename),self,child_prev_sibling,child_predecessor)
                    child_prev_sibling = child
                    child_predecessor = child.final()
        self.indentation = None
        self.line_index = None
        self.astoids = None
    def init(self,first_astoid,next_parse_state):
        raise Exception('Package should have no astoids')
    def process_astoid(self,astoid,parse_state):
        raise Exception('Package should have no astoids')
    def add_astoid(self,astoid,parse_state):
        raise Exception('Package should have no astoids')
    def __str__(self):
        return 'CnodePackage(%s)' % repr(os.path.basename(self.path))


class CnodeModule(Cnode):
    def __init__(self,path,parent=None,prev_sibling=None,predecessor=None):
        if os.path.isdir(path) or os.path.splitext(path)[1].lower() not in ['.py','.pyw']:
            raise Exception('Path is not a valid module path: %s' % path)
        self.path = path
        super().__init__(parent,prev_sibling,predecessor)

    def process_astoid(self,astoid,parse_state):
        if len(self.astoids) == 0 and astoid.type == (ast.Module,CodeClause.BODY):
            self.astoids.append(astoid)
        else:
            raise Exception('Only a single module body astoid should be added a CnodeModule')
        return ParseState.NEWBLOCK
    def __str__(self):
        return 'CnodeModule(%s)' % repr(os.path.basename(self.path))

class CnodeDef(Cnode):
    def process_astoid(self,astoid,parse_state):
        self.astoids.append(astoid)
        return ParseState.NEWBLOCK
    def init(self,first_astoid,next_parse_state):
        self.name = first_astoid.ast_node.name
        return super().init(first_astoid,next_parse_state)

    def __str__(self):
        return '%s(%s)' % (self.__class__.__name__,repr(self.name))

class CnodeClass(CnodeDef):
    pass
class CnodeFunction(CnodeDef):
    pass
class CnodeAsyncFunction(CnodeDef):
    pass
class CnodeBlock(Cnode):
    def process_astoid(self,astoid,parse_state):
        self.astoids.append(astoid)
        return ParseState.BUILD
    def __str__(self):
        return 'CnodeBlock(%s,%d)' % (os.path.basename(self.module.path),self.line_index)

def cnode_import(name):
    spec = find_spec(name)
    if spec is not None:
        path = spec.origin
        if os.path.basename(path).lower() == '__init__.py':
            #package
            path = os.path.dirname(path)
        else:
            #module
            pass
        return cnode_load(path)

    else:
        raise Exception('Not an importable name: %s' % name)

def cnode_load(path):
    if os.path.isdir(path):
        #package
        return CnodePackage(path)
    else:
        #module
        return parse_module(path)

ast_type_map = {
        ast.Module:CnodeModule,
        ast.ClassDef:CnodeClass,
        ast.FunctionDef:CnodeFunction,
        ast.AsyncFunctionDef:CnodeAsyncFunction,
        }
if __name__ == '__main__':
    os.environ['PYTHONINSPECT'] = '1'
    def _eh(exc_type,exc_value,exc_tb):
        traceback.print_exception(exc_type,exc_value,exc_tb)
        pdb.post_mortem(exc_tb)
    sys.excepthook = _eh
    ctree = cnode_import('simpler_test')
