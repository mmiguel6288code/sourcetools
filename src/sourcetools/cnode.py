"""
Parse AST -> ast tree
Astoid tree built off of ast tree
Code tree built off of astoid tree

Specific types of astoid nodes correspond to code nodes.
There is also a special code node called a line block.
Code nodes have both lines and astoids as part of themselves.
They have successors, predecessors, parents and children, which are all code nodes.
Indentation in lines denotes the start of a new set of children nodes.

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


ast_type_map = {
        ast.Module:CnodeModule,
        ast.ClassDef:CnodeClass,
        ast.FunctionDef:CnodeFunction,
        ast.AsyncFunctionDef:CnodeAsyncFunction,
        }

class ParseState(Enum):
    NEWBLOCK=auto()
    BUILD=auto()
    ENDBLOCK=auto()
    DONE=auto()

def parse(source,parent_cnode=None):
    astoid_tree = astoid.parse(source)
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
                cnode = CnodeBlock(parent_cnode)
                next_state = cnode.add_astoid(astoid,state)
            else:
                #not block
                if ast_type in ast_type_map:
                    cnode_class = ast_type_map[ast_type]
                    cnode = cnode_class(parent_cnode)
                    next_state = cnode.add_astoid(astoid,state)
                else:
                    raise Exception('Unexpected type: %s' % repr(astoid.type))
        elif state == ParseState.BUILD:
            next_state = cnode.add_astoid(astoid,state)
        elif state == ParseState.DONE:
            next_state = ParseState.DONE

        else:
            raise Exception('Invalid state: %s' % repr(state))

        if next_state == ParseState.NEWBLOCK:
            stack.append(cnode)
            parent_cnode = cnode
            cnode = None
        elif next_state == ParseState.ENDBLOCK:
            if len(stack) > 0:
                get_next = False #astoid not consumed, send same astoid through loop again after popping stack and changing state
                cnode = stack.pop()
                parent_cnode = cnode.parent
                next_state = ParseState.BUILD
            else:
                next_state = ParseState.DONE
        elif next_state == ParseState.BUILD:
            pass
        elif next_state == ParseState.DONE:
            pass
        else:
            raise Exception('Invalid state transition: %s to %s' % (repr(state),repr(next_state)))
        state = next_state
    return cnode

class Cnode():
    def __init__(self,parent):
        self.parent = parent
        self.astoids = []

    def add_astoid(self,astoid,parse_state):
        initialization = (len(self.astoids) == 0)
        next_parse_state = self.process_astoid(astoid,parse_state)
        if initialization:
            self.init(self,astoid)

    def init(self,first_astoid):
        raise NotImplementedError('This method is intended to be overwritten by subclasses')
        self.indentation = ...
        self.line_index = ...
        self.predecessor = 
    def process_astoid(self,astoid,parse_state):
        raise NotImplementedError('This method is intended to be overwritten by subclasses')

class CnodePackage(Cnode):
    ...
class CnodeModule(Cnode):
    def process_astoid(self,astoid,parse_state):
        if len(self.astoids) == 0 and astoid.type == (ast.Module,CodeClause.BODY):
            self.astoids.append(astoid)
        else:
            raise Exception('Only a single module body astoid should be added a CnodeModule')
        return ParseState.NEWBLOCK

class CnodeClass(Cnode):
    ...

class CnodeFunction(Cnode):
    ...

class CnodeAsyncFunction(CnodeFunction):
    pass #identical to CnodeFunction for now

class CnodeBlock(Cnode):
    def add_astoid(self,astoid,parse_state):
        if len(self.astoids) == 0 and astoid.type == (ast.Module,CodeClause.BODY):
            self.astoids.append(astoid)
        else:
            raise Exception('Only a single module body astoid should be added a CnodeModule')
        return ParseState.BUILD



def code_tree(target):
    """
    Loads the code tree for the specified target
    target is an importable name or a path to a package or module
    """
    spec = find_spec(target)
    if spec is not None:
        #target is an importable name
        target_path = spec.origin
    else:
        if os.path.exists(target):
            #target is a path that exists
            target_path = target
        else:
            raise Exception('Target could not be identified as an importable name nor a path')
    if os.path.basename(target_path).lower() == '__init__.py':
        containing_folder = os.path.dirname(target_path)
        while '__init__.py' in [filename.lower() for filename in os.listdir(containing_folder)]:
            containing_folder = os.path.abspath(os.path.join(containing_folder,'..'))
        package_path = containing_folder
        return PackageNode(package_path)
    else:
        in_package = False
        containing_folder, = os.path.dirname(target_path)
        while '__init__.py' in [filename.lower() for filename in os.listdir(containing_folder)]:
            in_package = True
            containing_folder = os.path.abspath(os.path.join(containing_folder,'..'))
        if in_package:
            package_path = containing_folder
            return PackageNode(package_path)
        else:
            return ModuleNode(target_path)

class CodeNode():
    """
Every type of code node has the following attributes:
    code_type = One of CodeType enumeration values
    name = string name of item (None for anything other than packages, modules, classes, functions, async functions)

    lineage = List of ancestor nodes from self to parent, to parent's parent, etc
    parent = Parent code node (None for root node)
    context = Lowest level package, module, function, async function, or class containing the given code (None for packages or modules defined outside of packages)
    module = Module code node (None for packages, self for modules)
    package = Package code node (None if module is defined outside of package, self for packages)
    root = Root code node
    next_sibling = Next code node in parents children list (None if no next sibling exists)
    prev_sibling = Previous code node in parents children list (None if no previous sibling exists)
    children = List of children code nodes

    source_path = Path to package folder for packages or module .py file for other types of code nodes. 
    line_index = Zero-based line index for the first line (None for packages, modules)
    indentation = Leading whitespace string (None for packages, modules)
    lines = List of lines of code. Indentation and ending carriage returns/newlines are stripped.
    starts_block = True if the next sibling should indicate an increase in indentation (False for packages, modules, lineblocks)

    docstring = A DocstringInterface instance (None for anything besides modules, functions, classes, async functions)

    test = A TestInterface instance (None for anything besides packages, modules, functions, classes, async functions)
    loaded_as_test = True if tree was loaded as a test structure for some other tree, otherwise False

    ast = An AstInterface instance

Every type of code node has the following methods:
    get_lineage() = List of code nodes from the root to the current code node 
    walk() = Iterate recursively through children depth-first
    write() = For non-packages, dispatched to the module i.e. equivalent to .module.write(). Rewrites the file using the the def_indentation, block_indentation, def_lines, and block_lines of all elements within the module. The line indices are not used. For packages, dispatched to all child elements.
    reload() = Returns a fresh copy of the code tree from reading all the files. Does not incorporate local code tree changes or modify the local code tree in any way.
    get_end_line_index() = Returns the start line index of the next sibling or the number of lines in the source file if next sibling is None; Returns None if 
    get_module_raw_lines() = Returns a list of the raw lines (including indentation and carriage returns/newlines) of the module
    get_indentation(line_index)
    """
    def get_lineage(self):
        result = [self]
        parent = self.parent
        while parent is not None:
            result.append(parent)
            parent = parent.parent
        return result[::-1]
    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()
    def write(self):
        self.module.write()

    def reload(self):
        """
        Returns a fresh copy of the code tree from reading all the files. Does not incorporate local code tree changes or modify the local code tree in any way.
        """
        return code_tree(self.root.source_path)

    def order_siblings(self):
        for child in self.children:
            child.order_siblings()
        for prev_sibling,curr_sibling,next_sibling in iterate_with_siblings(self.children):
            curr_sibling.prev_sibling = prev_sibling
            curr_sibling.next_sibling = next_sibling
    def populate_line_info(self):
        for child in self.children:
            child.populate_line_info()
        next_sibling = self.next_sibling()
        if next_sibling is not None:

        else:

    def get_module_raw_lines(self):
        return self.module.source_raw_lines
    def get_indentation(self,line_index=None):
        if line_index is None:
            line_index = self.line_index
        raw_line = self.module.source_raw_lines[line_index]
        tokens = tokenize_raw_lines([raw_line])
        if len(tokens) > 0:
            first_token = tokens[0]
            if token.tok_name[first_token.type] == 'INDENT':
                return first_token.string
            else:
                return ''

        else:
            return ''
    def process_docstring(self,ast_body):
        """
        Detects a docstring if it exists
        Removes it from ast_body if it does exist
        """
        if len(ast_body) > 0:
            first_element = ast_body[0]
            if isinstance(first_element,ast.Expr) and isinstance(first_element.value,ast.Str):
                if len(ast_body) >= 2:
                    next_line_index = ast_body[1].lineno-1
                else:
                    next_sibling = self.next_sibling()
                    if next_sibling is not None:
                        next_sibling
                    else:
                self.docstring.set_ast(first_element,next_line_index)
                ast_body.pop(0)



class PackageNode(CodeNode):
    def __init__(self,source_path,parent_info=None,loaded_as_test=False):
        """
        source_path should be the path of the package directory
        """
        self.code_type = CodeType.PACKAGE
        self.source_path = source_path
        self.name = os.path.basename(source_path)
        self.line_index = None
        self.indentation = None
        self.lines = None
        self.starts_block = False
        self.docstring = None
        self.test = TestInterface(self)
        self.loaded_as_test = loaded_as_test
        self.ast = None

        if parent_info is None:
            self.parent = None
            self.lineage = []
            self.context = None
            self.module = None
            self.root = self
            self.prev_sibling = None
            self.next_sibling = None
        else:
            self.parent,self.lineage,self.context,self.module,self.package,self.root = parent_info
            self.prev_sibling = ... #to be filled when parent calls order_siblings()
            self.next_sibling = ... #to be filled when parent calls order_siblings()
        self.package = self

        self.children = []
        for item_name in sorted(os.listdir(source_path)):
            item_path = os.path.join(source_path,filename)
            if os.path.isdir(item_path):
                if os.path.exists(os.path.join(item_path,'__init__.py')):
                    #item is a sub-package
                    self.children.append(PackageNode(item_path,(self,[self]+self.lineage,self,None,None,self.root),loaded_as_test)
            elif os.path.splitext(item_name.lower())[1] in ['.py','.pyw']:
                #item is a module
                    self.children.append(ModuleNode(item_path,(self,[self]+self.lineage,self,None,self,self.root),loaded_as_test)
        self.order_siblings()

    def write(self):
        for child in self.children:
            child.write()
    def __repr__(self):
        return 'PackageNode(%s)' % (self.name)
    def __str__(self):
        return repr(self)
    def get_module_raw_lines(self):
        return None
    def get_indentation(self,line_index=None):
        return None
    def process_docstring(self,*args):
        return None

class ModuleNode(CodeNode):
    """
Every type of code node has the following attributes:
    code_type = One of CodeType enumeration values
    name = string name of item (None for anything other than packages, modules, classes, functions, async functions)

    lineage = List of ancestor nodes from self to parent, to parent's parent, etc
    parent = Parent code node (None for root node)
    context = Lowest level package, module, function, async function, or class containing the given code (None for packages or modules defined outside of packages)
    module = Module code node (None for packages, self for modules)
    package = Package code node (None if module is defined outside of package, self for packages)
    root = Root code node
    next_sibling = Next code node in parents children list (None if no next sibling exists)
    prev_sibling = Previous code node in parents children list (None if no previous sibling exists)
    children = List of children code nodes

    source_path = Path to package folder for packages or module .py file for other types of code nodes. 
    line_index = Zero-based line index for the line ending with a colon items that are followed by an indented block (None for packages, modules, and lineblocks)
    indentation = Leading whitespace string at the def_line (None for packages, modules, and lineblocks)
    lines = List of lines of code. Indentation and ending carriage returns/newlines are stripped.

    docstring = A DocstringInterface instance (None for anything besides modules, functions, classes, async functions)

    test = A TestInterface instance (None for anything besides packages, modules, functions, classes, async functions)
    loaded_as_test = True if tree was loaded as a test structure for some other tree, otherwise False

    ast = An AstInterface instance
    """
    def __init__(self,source_path,parent_info=None,loaded_as_test=False):
        self.code_type = CodeType.MODULE
        self.name = os.path.splitext(os.path.basename(origin))[0]
        self.source_path = source_path
        self.module = self
        self.line_index = None
        self.indentation = None
        self.lines = None
        self.starts_block = False
        self.test = TestInterface(self)
        self.loaded_as_test = loaded_as_test

        if parent_info is None:
            self.parent = None
            self.lineage = []
            self.context = None
            self.package = None
            self.root = self
            self.prev_sibling = None
            self.next_sibling = None
        else:
            self.parent,self.lineage,self.context,self.module,self.package,self.root = parent_info
            self.prev_sibling = ... #to be filled when parent calls order_siblings()
            self.next_sibling = ... #to be filled when parent calls order_siblings()
        self.module = self

        #self.docstring = DocstringInterface(self)
        #self.ast = AstInterface(self)
        self.children = []
        with open(source_path,'r') as f:
            self.source_content = f.read()
        self.source_raw_lines = source_content.splitlines(True)
        self.ast_node = ast.parse(source_content,source_path,'exec')
        self.astoids = [Astoid(self,self.ast_node)]
        ast_body = self.ast_structure[0][1]
        self.process_docstring(ast_body)
        last_child_lineblock = False
        for ast_child in ast_body:
            ast_type = type(ast_child)
            if ast_type in ast_type_map:
                child_code_type, child_class = ast_type_map[ast_type]
                self.children.append(child_class(self,ast_child,child_code_type))
                last_child_lineblock = False
            else:
                if not last_child_lineblock:
                    self.children.append(LineblockNode(self,ast_child,CodeType.LINEBLOCK))
                last_child_lineblock = True
        self.order_siblings() #introduce child nodes to their adjacent siblings
        self.populate_line_info()


    def write(self):
        ...
    def __repr__(self):
        return 'ModuleNode(%s)' % (self.name)
    def __str__(self):
        return repr(self)





class Astoid():
    """
    """
    def __init__(self,code_node,ast_node,parent=None,index_list=None):
        self.code_node = code_node
        self.ast_node = ast_node
        self.parent = parent
        if index_list is None:
            self.index_list = [0]
        else:
            self.index_list = index_list
        if isinstance(ast_node,ast.Module):
        elif isinstance(ast_node,ast.FunctionDef):
        elif isinstance(ast_node,ast.AsyncFunctionDef
        self.children = []
        if
        for child_index,child_ast_node in enumerate(ast.iter_child_nodes(ast_raw_node)):
            child_raw_node_type = type(child_raw_node)
            if child_raw_node_type in ast_raw_type_map:
                #code type of object
                child_code_type,child_code_class = ast_raw_type_map[child_raw_node_type]
                child_code_node = child_code_class(child_code_type,self.code_node)
                self.code_node.children.append(child_code_node)
            else:
                if lineblock_code_node is None:
                    lineblock_code_node = LineblockNode()
                child_code_node = lineblock_code_node

            child_ast_node = AstNode(child_code_node,child_raw_node,self,self.index_list+[child_index])

            self.children.append(AstNode(child_raw_node,self,self.index_list+[child_index]))
        if isinstance(ast_raw_node,ast.Module):
            self.introduce_siblings()
            self.determine_successor()

    def introduce_siblings(self):
        for child in self.children:
            child.introduce_siblings()
        for prev_sibling,curr_sibling,next_sibling in iterate_with_siblings(self.children):
            curr_sibling.prev_sibling = prev_sibling
            curr_sibling.next_sibling = next_sibling

    def determine_successor(self):
        for child in self.children:
            child.determine_successor()
        if len(self.children) > 0:
            self.successor = self.children[0]
        elif self.next_sibling is not None:
            self.successor = self.next_sibling
        else:
            ancestor = self.parent
            while ancestor is not None:
                if ancestor.next_sibling is not None:
                    self.successor = ancestor.next_sibling
                    break
                else:
                    ancestor = ancestor.parent
            else:
                self.successor = None
    def get_lineno(self):
        if hasattr(self.ast_raw_node,'lineno'):
            return self.ast_raw_node.lineno
        else:
            if len(self.children) > 0:
                return self.children[0].get_lineno()
            else:
                raise Exception('No lineno')



def tokenize_raw_lines(raw_lines):
    return list(tokenize.generate_tokens((raw_line for raw_line in raw_lines).__next__))


class DefNode(CodeNode):
    def __init__(self,code_type,parent):
        self.code_tree = code_tree
        self.name = name
        self.parent = parent 
        self.ast_node = ast_node
        self.ast_lineage = ast_lineage
        self.index = index
        self.code_type = ast_map[type(ast_node)]
        self.subtree = {}
    def walk(self):
        for child in self.subtree.values():
            yield child
            yield from child.walk()
    def __repr__(self):
        return 'DefNode(%s,%s)' % (self.name,self.code_type)
    def __str__(self):
        return repr(self)
    def prev_node(self):
        if self.index > 0:
            return self.code_tree.flat_ast[self.index-1]
        else:
            return None
    def next_node(self):
        if self.index < len(self.code_tree.flat_ast)-1:
            return self.code_tree.flat_ast[self.index+1]
        else:
            return None
class BlockNode(CodeNode):
    ...
class LineBlockNode(CodeNode):
    ...

class DocstringInterface():
    """
Docstring nodes represent docstrings and doctests of module, class, or function code nodes.

Docstring nodes have the following attributes:
    code_node
    exists = Whether docstring exists or not
    has_doctests = Whether doctests are present or not
    line_index = Zero-based line index for the first line (None for packages, modules)
    indentation = Leading whitespace string (None for packages, modules)
    lines = List of lines of code. Indentation and ending carriage returns/newlines are stripped.

Docstring nodes have the following methods:
    save()
    run_doctests()
    """
    def __init__(self,code_node):
        self.code_node = code_node
        self.exists = False
        self.start_lin

    def set_ast(self,ast_obj,next_line_index):
        self.exists = True
        self.line_index = ast_obj.lineno-1
        self.indentation = self.code_node.get_indentation(self.line_index)
        end_line_index = 
        self.lines = ast_obj.value.s.splitlines()
        self.st

class TestInterface():
    """
Test nodes represent test information for a given code node.

Assumes this project layout template structure:
    project_folder
        src
            package_1
                __init__.py
                __main__.py
                module_A.py
                module_B.py
                ...
            package_2
                __init__.py
                __main__.py
                module_C.py
                module_D.py
                ...
            ...
        tests
            test_package_1
                __init__.py
                __main__.py
                test_module_A.py
                test_module_B.py
                ...
            test_package_2
                __init__.py
                __main__.py
                test_module_C.py
                test_module_D.py
                ...
            ...

Each test package __init__ file is assumed to have the following lines at the top:
    import sys, os.path
    sys.insert(0,os.path.abspath(os.path.join(os.path.dirname(__file__),'../../src')))

These lines ensure that the packages in the src folder are importable and preferred (if there is ambiguity) when test packages are run

Tests are done at the following levels:
    Package-level tests:
        Tests some aspect of an entire integrated package
        May be multiple such tests for a single package
        Convention here is to defined as a "test_package" prefixed function or method in the __init__.py of the test package
        The name can be followed by additional descriptive text about what aspect is being tested.
            e.g. test_package_worst_case_scenario(), test_package_benign_environment()
        Also includes doctests defined in the src package __init__.py docstring
        Typically executed when __main__.py of the test package is executed

    Module-level tests:
        Tests some aspect of an entire integrated module
        May be multiple such tests for a single module
        Defined as a "test_module" prefixed function or method in the test module file
        The name can be followed by additional descriptive text about what aspect is being tested.
            e.g. test_module_off_nominal_inputs(), test_module_benign_environment()
        Also includes doctests defined in the src module docstring
        Typically executed when the test module is run directly (such that __name__ == '__main__')

    Unit tests:
        Tests a specific class or function
        May be multiple such tests for a single class or function
        Convention here is to define as a function or method prefixed by "test"+<class or function name> in the test module file.
        The name can be followed by additional descriptive text about what aspect is being tested.
            e.g. test_MyClass_connectivity() test_MyClass_data_clearing()
            e.g. test_myfunc_simple_request() test_myfunc_erroneous_inputs_1()
        Also includes doctests defined in the src class or function docstring
        Not typically executed when the test module is run directly

Test nodes have the following attributes:
    test_path
    test_prefix
    has_doctests
    has_test_funcs
    test_func_nodes

Test nodes have the following methods:
    run_doctests()
    run_test_funcs()
    run()
    create_func(suffix='') = Adds a test function. Reloads from root node

    """
    ...
ast_raw_type_map = {
        ast.Module:(CodeType.MODULE,ModuleNode),
        ast.ClassDef:(CodeType.CLASS,DefNode),
        ast.FunctionDef:(CodeType.FUNCTION,DefNode),
        ast.AsyncFunctionDef:(CodeType.ASYNCFUNCTION,DefNode),
        ast.For:(CodeType.FOR,BlockNode),
        ast.AsyncFor:(CodeType.ASYNCFOR,BlockNode),
        ast.While:(CodeType.WHILE,BlockNode),
        ast.If:(CodeType.IF,BlockNode),
        ast.With:(CodeType.WITH,BlockNode),
        ast.AsyncWith:(CodeType.ASYNCWITH,BlockNode),
        ast.Try:(CodeType.Try,BlockNode),
        }

if __name__ == '__main__':
    import os
    os.environ['PYTHONINSPECT'] = '1'
    os.chdir('/home/mtm/projects/ptkcmd/src')
    ct = code_tree('ptkcmd')
    for c in ct.walk():
        print('.'.join(item.name for item in c.lineage()) + ' (' + str(c.code_type) + ')')
