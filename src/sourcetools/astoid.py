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

def parse(source):
    source_lines = source.splitlines(keepends=True)
    ast_node = ast.parse(source)
    predecessor_astoid = _parse(source_lines,ast_node)
    predecessor_astoid.successor = None
    introduce_siblings(ast_node)
    return ast_node
def _parse(source_lines,ast_node,parent_astoid=None,homeroom=None,predecessor_astoid=None):
    if homeroom is None:
        homeroom = []
        root=True
    else:
        root = False
    if isinstance(ast_node,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.With,ast.AsyncWith)):
        #body only
        if len(ast_node.body) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom,predecessor_astoid)
            homeroom.append(astoid)
            predecessor_astoid = astoid
            for child_ast_node in ast_node.body:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
    elif isinstance(ast_node,(ast.For,ast.AsyncFor,ast.While)):
        #body and orelse
        if len(ast_node.body) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom)
            homeroom.append(astoid)
            predecessor_astoid = astoid
            for child_ast_node in ast_node.body:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
        if len(ast_node.orelse) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELSE,homeroom,predecessor_astoid)
            homeroom.append(astoid)
            predecessor_astoid = astoid
            for child_ast_node in ast_node.orelse:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
    elif isinstance(ast_node,ast.If):
        #body and orelse - special handling for elif
        if len(ast_node.body) > 0:
            if source_lines[ast_node.lineno-1].lstrip().startswith('elif'):
                #elevate self at same level as the parent, which is an (ast.If,CodeClause.ELSE) astoid and "cut in front of it"
                astoid_parent_else = parent_astoid #save parent 
                assert(astoid_parent_else.type == (ast.If,CodeClause.ELSE)) #check assumptions

                homeroom = astoid_parent_else.homeroom #change home room to be one level up (promotion)
                parent_astoid = astoid_parent_else.parent #parent update

                #cut in front by changing linked list
                predecessor_astoid = astoid_parent_else.predecessor
                astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELIF,homeroom,predecessor_astoid) #overwrites successor of predecessor to be self
                astoid_parent_else.predecessor = ... #needs to be set after all done
                predecessor_astoid = astoid
            else:
                astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom,predecessor_astoid)
                predecessor_astoid = astoid
            homeroom.append(astoid)
            for child_ast_node in ast_node.body:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
        if len(ast_node.orelse) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELSE,homeroom,predecessor_astoid)
            predecessor_astoid = astoid
            for child_ast_node in ast_node.orelse:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)

                
            #check if there was actually an else, not just elifs
            if len(astoid.children) > 0:
                #check if unset by an elif
                if astoid.predecessor == ...:
                    astoid.predecessor = predecessor_astoid #set to the most recent thing processed
                    predecessor_astoid.successor = astoid #both sides of link list
                homeroom.append(astoid)
    elif isinstance(ast_node,ast.Try):
        #body, excepthandlers, orelse, finalbody
        if len(ast_node.body) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.BODY,homeroom,predecessor_astoid)
            homeroom.append(astoid)
            predecessor_astoid = astoid
            for child_ast_node in ast_node.body:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
        if len(ast_node.handlers) > 0:
            for handler_ast_node in ast_node.handlers:
                if len(handler_ast_node.body) > 0:
                    astoid = Astoid(source_lines,handler_ast_node,parent_astoid,CodeClause.EXCEPT,homeroom)
                    homeroom.append(astoid)
                    predecessor_astoid = astoid
                    for child_ast_node in handler_ast_node.body:
                        predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
        if len(ast_node.orelse) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.ELSE,homeroom)
            predecessor_astoid = astoid
            homeroom.append(astoid)
            for child_ast_node in ast_node.orelse:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
        if len(ast_node.finalbody) > 0:
            astoid = Astoid(source_lines,ast_node,parent_astoid,CodeClause.FINALLY,homeroom)
            homeroom.append(astoid)
            predecessor_astoid = astoid
            for child_ast_node in ast_node.finalbody:
                predecessor_astoid = _parse(source_lines=source_lines,ast_node=child_ast_node,parent_astoid=astoid,homeroom=astoid.children,predecessor_astoid=predecessor_astoid)
    else:
        astoid = Astoid(source_lines,ast_node,parent_astoid,None,homeroom)
        homeroom.append(astoid)
        predecessor_astoid = astoid

    return predecessor_astoid

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
    def __init__(self,source_lines,ast_node,parent_astoid,clause,homeroom,predecessor):
        self.source_lines = source_lines
        self.ast_node = ast_node
        self.clause = clause
        self.type = (type(ast_node,clause))
        self.parent = parent_astoid
        self.homeroom = homeroom
        self.children = []
        self.prev_sibling = ...
        self.next_sibling = ...
        self.successor = ...
        self.predecessor = predecessor

        if predecessor is not None:
            if predecessor.successor == ...:
                predecessor.successor = self
            else:
                raise Exception('Multiple successors')
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

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

if __name__ == '__main__':
    import os
    os.environ['PYTHONINSPECT'] = '1'
    with open('astoid.py','r') as f:
        source = f.read()
    result = parse(source)

