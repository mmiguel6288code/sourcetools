""" cnodes are based on astoids but focused on blocks of code
A block of python code is a set of lines at the same indentation


The line of a code node is the line of its first self astoid.
The self lines go from this to the line of its successor.

The module code node has no self lines but has an astoid and has children.
If an astoid increases indentation, it denotes the end of self and start of children.
    State = new code node

When state = new code, if the astoid is a code type, then that code node gets constructed.
If it is not a code type, a line block gets constructed.
Astoids get placed into the code node being constructed.
Decrease in indentation means code node is done.
Pop the stack til it matches the new indentation and set state = new code node.
Increase in indentation should only happen after specific code nodes.

Walk through astoids:
    get line no
    process lines up to that point and do stuff with them

"""

from enum import Enum, auto
import ast, re
from astoid import parse as astoid_parse, CodeClause
import tokenize, token, sys, os, os.path
from importlib.util import find_spec

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

    astoid_tree_walk = astoid_tree.walk()

    state = ParseState.NEWBLOCK
    astoid = None
    get_next = True
    while state != ParseState.DONE:
        if get_next:
            try:
                astoid = next(astoid_tree_walk)
            except StopIteration:
                state == ParseState.DONE
                astoid = None
        get_next = True #default for next iteration will be to get next unless explicitly told otherwise below in this iteration
        if state == ParseState.NEWBLOCK:
            ast_type,clause = astoid.type
            if clause is None:
                #block
                cnode = CnodeBlock(parent_cnode,prev_sibling_cnode,predecessor_cnode)
                next_state = cnode.add_astoid(astoid,state)
            else:
                #not block
                if ast_type in ast_type_map:
                    cnode_class = ast_type_map[ast_type]
                    if isinstance(cnode_class,CnodeModule):
                        cnode = cnode_class(path,parent_cnode,prev_sibling_cnode,predecessor_cnode)
                    else:
                        cnode = cnode_class(parent_cnode,prev_sibling_cnode,predecessor_cnode)
                    next_state = cnode.add_astoid(astoid,state)
                else:
                    raise Exception('Unexpected type: %s' % repr(astoid.type))
        elif state == ParseState.BUILD:
            next_state = cnode.add_astoid(astoid,state)
        elif state == ParseState.DONE:
            next_state = ParseState.DONE
        else:
            raise Exception('Invalid state: %s' % repr(state))

        predecessor_cnode = cnode
        if next_state == ParseState.NEWBLOCK:
            stack.append(cnode)
            parent_cnode = cnode
            cnode = None
            prev_sibling_cnode = None
        elif next_state == ParseState.ENDBLOCK:
            if len(stack) > 0:
                get_next = False #astoid not consumed, send same astoid through loop again after popping stack and changing state
                cnode = stack.pop()
                parent_cnode = cnode.parent
                next_state = ParseState.BUILD
                prev_sibling_cnode = cnode
            else:
                next_state = ParseState.DONE
        elif next_state == ParseState.BUILD:
            prev_sibling_cnode = cnode
        elif next_state == ParseState.DONE:
            pass
        else:
            raise Exception('Invalid state transition: %s to %s' % (repr(state),repr(next_state)))
        state = next_state
    return cnode

class Cnode():
    def __init__(self,parent,prev_sibling=None,predecessor=None):
        self.parent = parent
        self.astoids = []
        self.children = []
        self.line_index = ...
        self.indentation = ...
        if prev_sibling is not None:
            if prev_sibling.next_sibling == ...:
                prev_sibling.next_sibling = self
            else:
                raise Exception('Multiple next siblings')
        self.prev_sibling = prev_sibling
        self.next_sibling = None #may be overwritten by next sibling
        if predecessor is not None:
            if predecessor.successor == ...:
                predecessor.successor = self
            else:
                raise Exception('Multiple successors')
        self.predecessor = predecessor
        self.successor = None #may be overwritten by successor
    def final(self):
        target = self
        while len(target.children) > 0:
            target = target.children[-1]
        return target


    def add_astoid(self,astoid,parse_state):
        if astoid.cnode is not None:
            raise Exception('Multiple cnodes for one astoid')
        astoid.cnode = self
        initialization = (len(self.astoids) == 0)
        next_parse_state = self.process_astoid(astoid,parse_state)
        if initialization:
            self.init(self,astoid)
        return next_parse_state

    def init(self,first_astoid):
        #run immediately after the first astoid is added
        first_astoid = self.astoids[0]
        line_index = first_astoid.line_index
        self.line_index = line_index
        first_line = first_astoid.source_lines[line_index]
        self.indentation = wspace_re.search(first_line).group(0)

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
                    self.children.append(child)
                    child_prev_sibling = child
                    child_predecessor = child.final()
            else:
                if os.path.splitext(filename)[1].lower() in ['.py','.pyw']:
                    child = parse(os.path.join(path,filename),self,child_prev_sibling,child_predecessor)
                    self.children.append(child)
                    child_prev_sibling = child
                    child_predecessor = child.final()
        self.indentation = None
        self.line_index = None
        self.astoids = None
    def init(self,first_astoid):
        raise Exception('Package should have no astoids')
    def process_astoid(self,astoid,parse_state):
        raise Exception('Package should have no astoids')
    def add_astoid(self,astoid,parse_state):
        raise Exception('Package should have no astoids')


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

class CnodeDef(Cnode):
    def process_astoid(self,astoid,parse_state):
        self.astoids.append(astoid)
        return ParseState.NEWBLOCK

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
    ctree = cnode_import('cnode')
    os.environ['PYTHONINSPECT'] = '1'
