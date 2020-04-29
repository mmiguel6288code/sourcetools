"""
Targets a package or module and extracts information from the code inside.
The result is a tree of code nodes.
The root node represents a package or a module that is not within a package.
If a module inside of a package is targeted, then the top level package containing that module will be loaded as the root instead.
If the project is laid out as recommended (with src and tests folders), then the test package in the corresponding test folder will be loaded as well.

Types of code nodes are:
    Package
    Module
    Class
    Synchronous Function
    Asynchronous Function
    Lines
These are identified by the CodeType enumeration.

Lambda functions are not included.

"""
import ast, os.path, os.path
from importlib.util import find_spec
from enum import Enum

class CodeType(Enum):
    PACKAGE=1
    MODULE=2
    CLASS=3
    FUNCTION=4
    ASYNCFUNCTION=5
    FOR=6
    ASYNCFOR=7
    WHILE=8
    IF=9
    WITH=10
    ASYNCWITH=11
    TRY=12
    LINEBLOCK=13


def ast_ordered_walk(ast_node):
    """
    walk() method in ast standard module has no specified order
    """
    yield ast_node
    for child_node in ast.iter_child_nodes(ast_node):
        yield from ast_ordered_walk(child_node)
def iterate_with_siblings(iterable):
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
    line_index = Zero-based line index for the line ending with a colon items that are followed by an indented block (None for packages, modules, and lineblocks)
    indentation = Leading whitespace string at the def_line (None for packages, modules, and lineblocks)
    lines = List of lines of code. Indentation and ending carriage returns/newlines are stripped.

    docstring = A DocstringInterface instance (None for anything besides modules, functions, classes, async functions)

    test = A TestInterface instance (None for anything besides packages, modules, functions, classes, async functions)
    loaded_as_test = True if tree was loaded as a test structure for some other tree, otherwise False

    ast = An AstInterface instance

Every type of code node has the following methods:
    get_lineage() = List of code nodes from the root to the current code node 
    walk() = Iterate recursively through children depth-first
    write() = For non-packages, dispatched to the module i.e. equivalent to .module.write(). Rewrites the file using the the def_indentation, block_indentation, def_lines, and block_lines of all elements within the module. The line indices are not used. For packages, dispatched to all child elements.
    reload() = Returns a fresh copy of the code tree from reading all the files. Does not incorporate local code tree changes or modify the local code tree in any way.
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
        for prev_sibling,curr_sibling,next_sibling in iterate_with_siblings(self.children):
            curr_sibling.prev_sibling = prev_sibling
            curr_sibling.next_sibling = next_sibling

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

        self.docstring = DocstringInterface(self)
        self.ast = AstInterface(self)
        self.children = []
        with open(source_path,'r') as f:
            source_content = f.read()
        ast_module = ast.parse(source_content,source_path,'exec')
        ast_body = list(ast_module.body)
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
        self.order_siblings()
        self.populate_line_info()
    def process_docstring(self,ast_body):
        ...
    def populate_line_info(self):
        ...
    def write(self):
        ...
    def __repr__(self):
        return 'ModuleNode(%s)' % (self.name)
    def __str__(self):
        return repr(self)

class DefNode(CodeNode):
    def __init__(self,parent,ast_node,code_type):
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
    exists = Whether docstring exists or not
    has_doctests = Whether doctests are present or not
    start_line
    end_line
    quote_indentation
    lines

Docstring nodes have the following methods:
    save()
    run_doctests()
    """

    ...
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
class AstInterface():
    """
Ast nodes represent abstract syntax tree info (see python ast module documentation)

Test nodes have the following attributes:
    parent
    ast
    """
    ...

ast_type_map = {
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
