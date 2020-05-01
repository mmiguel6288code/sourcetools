from enum import Enum,auto
import ast, sys
def iterate_with_siblings(iterable):
    """
    Yields triplets of an item with its adjacent siblings
    First item's previous sibling is None
    Last item's next sibling is None
    """
    prev_sibling = None
    curr_sibling = None
    items = list(iterable)
    for next_sibling in items:
        if curr_sibling is not None:
            yield (prev_sibling,curr_sibling,next_sibling)
        prev_sibling = curr_sibling
        curr_sibling = next_sibling
    if curr_sibling is not None:
        next_sibling = None
        yield (prev_sibling,curr_sibling,next_sibling)

class CodeClause(Enum):
    BODY=auto()
    ELIF=auto()
    ELSE=auto()
    EXCEPT=auto()
    FINALLY=auto()

def astoid_parse(source):
    source_lines = source.splitlines(keepends=True)
    ast_node = ast.parse(source)
    return _astoid_parse(source_lines,ast_node)
def _astoid_parse(source_lines,ast_node,parent_astoid=None,homeroom=None):
    if homeroom is None:
        homeroom = []
        root=True
    else:
        root = False
    if isinstance(ast_node,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.With,ast.AsyncWith)):
        #body only
        if len(ast_node.body) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom)
            homeroom.append(astoid)
            for child_ast_node in ast_node.body:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
    elif isinstance(ast_node,(ast.For,ast.AsyncFor,ast.While)):
        #body and orelse
        if len(ast_node.body) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom)
            homeroom.append(astoid)
            for child_ast_node in ast_node.body:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
        if len(ast_node.orelse) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELSE,homeroom)
            homeroom.append(astoid)
            for child_ast_node in ast_node.orelse:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
    elif isinstance(ast_node,ast.If):
        #clause might be elif
        #body and orelse
        if len(ast_node.body) > 0:
            if source_lines[ast_node.lineno-1].lstrip().startswith('elif'):
                #elevate self at same level as else
                homeroom = parent_astoid.homeroom
                astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELIF,homeroom)
            else:
                astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom)
            homeroom.append(astoid)
            for child_ast_node in ast_node.body:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
        if len(ast_node.orelse) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELSE,homeroom)
            for child_ast_node in ast_node.orelse:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
            #check if there was actually an else, not just elifs
            if len(astoid.children) > 0:
                homeroom.append(astoid)
    elif isinstance(ast_node,ast.Try):
        #body, excepthandlers, orelse, finalbody
        if len(ast_node.body) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom)
            homeroom.append(astoid)
            for child_ast_node in ast_node.body:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
        if len(ast_node.handlers) > 0:
            for handler_ast_node in ast_node.handlers:
                if len(handler_ast_node.body) > 0:
                    astoid = Astoid(source_lines,handler_ast_node,parent_astoid,CodeClause.EXCEPT,homeroom)
                    homeroom.append(astoid)
                    for child_ast_node in handler_ast_node.body:
                        astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
        if len(ast_node.orelse) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELSE,homeroom)
            homeroom.append(astoid)
            for child_ast_node in ast_node.orelse:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
        if len(ast_node.finalbody) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.FINALLY,homeroom)
            homeroom.append(astoid)
            for child_ast_node in ast_node.finalbody:
                astoid_parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children)
    else:
        astoid = Astoid(source_lines,ast_node,parent_astoid,None,homeroom)
        homeroom.append(astoid)

    if root:
        introduce_siblings(homeroom[0])
        determine_successor(homeroom[0])
        determine_predecessor(homeroom[0])
        return homeroom[0]

def introduce_siblings(astoid):
    for prev_sibling,curr_sibling,next_sibling in iterate_with_siblings(astoid.children):
        introduce_siblings(curr_sibling)
        curr_sibling.prev_sibling = prev_sibling
        curr_sibling.next_sibling = next_sibling

def determine_successor(astoid):
    for child in astoid.children:
        determine_successor(child)
    if len(astoid.children) > 0:
        astoid.successor = astoid.children[0]
    else:
        if astoid.next_sibling is not None:
            astoid.successor = astoid.next_sibling
        else:
            ancestor = astoid.parent
            while ancestor is not None:
                if ancestor.next_sibling is not None:
                    astoid.successor = ancestor.next_sibling
                    break
                else:
                    ancestor = ancestor.parent
            else:
                astoid.successor = None
def determine_predecessor(astoid):
    for child in astoid.children:
        determine_predecessor(child)
    if astoid.prev_sibling is not None:
        target = astoid.prev_sibling
        while len(target.children) > 0:
            target = target.children[-1]
        astoid.predecessor = target
    else:
        if astoid.parent is not None:
            astoid.predecessor = astoid.parent
        else:
            astoid.predecessor = None


class Astoid():
    def __init__(self,source_lines,ast_node,parent_astoid,clause,homeroom):
        self.source_lines = source_lines
        self.ast_node = ast_node
        self.clause = clause
        self.parent = parent_astoid
        self.homeroom = homeroom
        self.children = []
        self.prev_sibling = ...
        self.next_sibling = ...
        self.successor = ...
        self.predecessor = ...
        self.line_index = ast_node.lineno-1
        self.col_offset = ast_node.col_offset
        if sys.version_info[:2] < (3,8) and isinstance(ast_node,ast.Expr) and isinstance(ast_node.value,ast.Str) and ast_node.col_offset == -1:
            #issue 16806 lineno wrong for multiline string - fixed in python 3.8
            self.line_index -= ast_node.value.s.count('\n') #adjust to point to beginning of multiline string instead of end
            line = source_lines[self.line_index] #grab first line of source code where multiline string starts
            line_str = ast_node.value.s.splitlines(keepends=True)[0] #grab string content after triple quote start of string in that line
            self.col_offset = len(line)-len(line_str)-3 #calculate start of triple quote in first line
                
    def __str__(self):
        return 'Astoid(%s,%s)' % (type(self.ast_node).__name__,repr(self.clause))
    def __repr__(self):
        return '<' + str(self) + '>'

if __name__ == '__main__':
    import os
    os.environ['PYTHONINSPECT'] = '1'
    with open('astoid.py','r') as f:
        source = f.read()
    result = astoid_parse(source)

