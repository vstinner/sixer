#!/usr/bin/env python3
import os
import re
import sys
import tokenize

# TODO: UserDict

# Maximum range which creates a list on Python 2. For example, xrange(10) can
# be replaced with range(10) without "from six.moves import range".
MAX_RANGE = 1024

OPERATIONS = set((
    "all", "iteritems", "itervalues", "iterkeys", "next", "long", "unicode",
    "raise", "xrange", "basestring", "six_moves", "stringio", "urllib"))

# Modules of the Python standard library
STDLIB_MODULES = ("copy", "re", "sys", "unittest", "heapq", "glob", "os")

# Name prefix of third-party modules (ex: "oslo" matches "osloconfig"
# and "oslo.db")
THIRD_PARTY_MODULES = ("oslo", "webob", "subunit", "testtools", "eventlet", "mock")

# Modules of the application
APPLICATION_MODULES = ("nova", "ceilometer", "glance", "neutron", "cinder")

SIX_MOVES = {
    # Python 2 import => six.moves import
    'BaseHTTPServer': 'BaseHTTPServer',
    'ConfigParser': 'configparser',
    'Cookie': 'http_cookies',
    'HTMLParser': 'html_parser',
    'Queue': 'queue',
    'SimpleHTTPServer': 'SimpleHTTPServer',
    'SimpleXMLRPCServer': 'xmlrpc_server',
    '__builtin__': 'builtins',
    'cookielib': 'http_cookiejar',
    'htmlentitydefs': 'html_entities',
    'httplib': 'http_client',
    'repr': 'reprlib',
#    'thread': '_thread',
    'xmlrpclib': 'xmlrpc_client',
}

SIX_MOVES_URLLIB = {
    # six.moves.urllib submodule => Python 2 urllib/urllib2 symbols
    'error': (
        'HTTPError',
        'URLError',
    ),

    'request': (
        'HTTPBasicAuthHandler',
        'HTTPCookieProcessor',
        'HTTPPasswordMgrWithDefaultRealm',
        'HTTPSHandler',
        'ProxyHandler',
        'Request',
        'build_opener',
        'install_opener',
        'urlopen',
    ),

    'parse': (
        'quote',
        'unquote',
        'urlencode',
    ),
}
URLLIB = {}
for submodule, symbols in SIX_MOVES_URLLIB.items():
    for symbol in symbols:
        URLLIB[symbol] = submodule
URLLIB_UNCHANGED = set('urllib.%s' % submodule
                       for submodule in SIX_MOVES_URLLIB)

# Ugly regular expressions because I'm too lazy to write a real parser,
# and Match Object are convinient to modify code in-place

def import_regex(name):
    return re.compile(r"^import %s\n" % name, re.MULTILINE)


# 'inst'
IDENTIFIER_REGEX = r'[a-zA-Z_][a-zA-Z0-9_]*'
# '[0]'
GETITEM_REGEX = r'\[[^]]+\]'
# '()' or '(obj, {})', don't support nested calls: 'f(g())'
CALL_REGEX = r'\([^()]*\)'
# '[0]' or '(obj, {})' or '()[key]'
SUFFIX_REGEX = r'(?:%s|%s)' % (GETITEM_REGEX, CALL_REGEX)
# 'var' or 'var[0]' or 'func()' or 'func()[0]'
SUBEXPR_REGEX = r'%s(?:%s)*' % (IDENTIFIER_REGEX, SUFFIX_REGEX)
# 'inst' or 'self.attr' or 'self.attr[0]'
EXPR_REGEX = r'%s(?:\.%s)*' % (SUBEXPR_REGEX, SUBEXPR_REGEX)
# '(...)'
SUBPARENT_REGEX= r'\([^()]+\)'
# '(...)' or '(...(...)...)' (max: 1 level of nested parenthesis)
PARENT_REGEX= r'\([^()]*(?:%s)?[^()]*\)' % SUBPARENT_REGEX
IMPORT_GROUP_REGEX = re.compile(r"^(?:import|from) .*?\n\n",
                                re.MULTILINE | re.DOTALL)
IMPORT_NAME_REGEX = re.compile(r"^(?:import|from) (%s)" % IDENTIFIER_REGEX,
                               re.MULTILINE)
IMPORT_SIX_REGEX = re.compile(r"^import six$", re.MULTILINE)
ITERITEMS_REGEX = re.compile(r"(%s)\.iteritems\(\)" % EXPR_REGEX)
ITERVALUES_REGEX = re.compile(r"(%s)\.itervalues\(\)" % EXPR_REGEX)
ITERKEYS_REGEX = re.compile(r"(%s)\.iterkeys\(\)" % EXPR_REGEX)
ITERITEMS_LINE_REGEX = re.compile(r"^.*\biteritems *\(.*$", re.MULTILINE)
ITERVALUES_LINE_REGEX = re.compile(r"^.*\bitervalues *\(.*$", re.MULTILINE)
ITERKEYS_LINE_REGEX = re.compile(r"^.*\biterkeys *\(.*$", re.MULTILINE)
# Match 'gen.next()' and '(...).next()'
NEXT_REGEX = re.compile(r"(%s|%s)\.next\(\)" % (EXPR_REGEX, PARENT_REGEX))
NEXT_LINE_REGEX = re.compile(r"^.*\.next *\(.*$", re.MULTILINE)
DEF_NEXT_LINE_REGEX = re.compile(r"^.*def next *\(.*$", re.MULTILINE)

SIX_MOVES_REGEX = ("(%s)" % '|'.join(sorted(map(re.escape, SIX_MOVES.keys()))))
FROM_REGEX = r"(%s(?:, %s)*)" % (IDENTIFIER_REGEX, IDENTIFIER_REGEX)
IMPORT_REGEX = re.compile(r"^import %s\n\n?" % SIX_MOVES_REGEX, re.MULTILINE)
FROM_IMPORT_REGEX = re.compile(r"^from %s import %s" % (SIX_MOVES_REGEX, FROM_REGEX), re.MULTILINE)
IMPORT_STRINGIO_REGEX = import_regex(r"StringIO")
IMPORT_URLLIB_REGEX = import_regex(r"\burllib2?\b")

# 'urllib2'
URLLIB2_REGEX = re.compile(r"\burllib2\b")
# urllib.attr or urllib2.attr
URLLIB_ATTR_REGEX = re.compile(r"\burllib2?\.(%s)" % IDENTIFIER_REGEX)

# '123L' but not '0123L'
LONG_REGEX = re.compile(r"\b([1-9][0-9]*|0)L")
# '123L', '0123L'
LONG_LINE_REGEX = re.compile(r"^.*\b[0-9]+L.*$", re.MULTILINE)

UNICODE_REGEX = re.compile(r'\bunicode\b')
DEF_REGEX = re.compile(r'^ *def +%s *\(' % IDENTIFIER_REGEX, re.MULTILINE)

# 'raise a, b, c' expr
RAISE3_REGEX = re.compile(r"raise (%s), (%s), (%s)"
                          % (EXPR_REGEX, EXPR_REGEX, EXPR_REGEX))
# 'raise a, b' expr
RAISE2_REGEX = re.compile(r'''raise (%s), (%s|'[^']+'|"[^"]+")$'''
                          % (EXPR_REGEX, EXPR_REGEX), re.MULTILINE)
# 'raise a,' line
RAISE_LINE_REGEX = re.compile(r"^.*raise %s,.*$" % EXPR_REGEX, re.MULTILINE)

# 'xrange(2)'
XRANGE1_REGEX = re.compile(r"xrange\(([0-9]+)\)")
XRANGE2_REGEX = re.compile(r"xrange\(([0-9]+), ([0-9]+)\)")

# basestring
BASESTRING_REGEX = re.compile(r"basestring")


def iteritems_replace(regs):
    return 'six.iteritems(%s)' % regs.group(1)


def itervalues_replace(regs):
    return 'six.itervalues(%s)' % regs.group(1)


def iterkeys_replace(regs):
    return 'six.iterkeys(%s)' % regs.group(1)


def next_replace(regs):
    expr = regs.group(1)
    if expr.startswith('(') and expr.endswith(')'):
        expr = expr[1:-1]
    return 'next(%s)' % expr


def long_replace(regs):
    return regs.group(1)


def raise2_replace(regs):
    return 'raise %s(%s)' % (regs.group(1), regs.group(2))


def raise3_replace(regs):
    exc_type = regs.group(1)
    exc_value = regs.group(2)
    exc_tb = regs.group(3)
    if (exc_type.endswith('[0]')
        and exc_value.endswith('[1]')
        and exc_tb.endswith('[2]')):
        return ('six.reraise(*%s)' % exc_type[:-3])

    return ('six.reraise(%s, %s, %s)'
            % (exc_type, exc_value, exc_tb))


def parse_import_groups(content):
    pos = 0
    import_groups = []
    while True:
        match = IMPORT_GROUP_REGEX.search(content, pos)
        if not match:
            break
        import_group = match.group(0)
        imports = [match.group(1)
                   for match in IMPORT_NAME_REGEX.finditer(import_group)]
        import_groups.append((match.start(), match.end(), set(imports)))
        pos = match.end()
    return import_groups


def parse_import(line):
    line = line.strip()
    if line.startswith("import "):
        return line[7:].split(".")
    elif line.startswith("from "):
        pos = 5
        pos2 = line.find(" import ", pos)
        names = line[pos:pos2].split(".")
        names.append(line[pos2+len(" import "):])
        return names
    else:
        raise SyntaxError("unable to parse import %r" % line)


def replace_urllib(regs):
    text = regs.group(0)
    if text in URLLIB_UNCHANGED :
        return text
    name = regs.group(1)
    try:
        submodule = URLLIB[name]
    except KeyError:
        raise Exception("unknown urllib symbol: %s" % text)
    return 'urllib.%s.%s' % (submodule, name)


def get_line(content, pos):
    eol = content.find("\n", pos)
    return content[pos:eol + 1]


class Patcher(object):
    def __init__(self, path, operations):
        operations = set(operations)
        if 'all' in operations:
            operations |= set(OPERATIONS)
            operations.discard('all')

        self.path = path
        self.operations = operations
        self.warnings = []
        self.current_file = None
        self.max_range = MAX_RANGE

    def walk(self):
        if os.path.isfile(self.path):
            yield self.path
            return

        for dirpath, dirnames, filenames in os.walk(self.path):
            # Don't walk into .tox
            try:
                dirnames.remove(".tox")
            except ValueError:
                pass
            for filename in filenames:
                if filename.endswith(".py"):
                    yield os.path.join(dirpath, filename)

    def _add_import(self, content, import_line, import_names):
        create_new_import_group = None

        import_groups = parse_import_groups(content)
        if not import_groups:
            if content:
                return import_line + '\n\n' + content
            else:
                return import_line

        if import_groups[0][2] == {'__future__'}:
            # Ignore the first import group: from __future__ import ...
            del import_groups[0]
        if len(import_groups) == 3:
            import_group = import_groups[1]
        else:
            # Heuristic to locate the import group of third-party modules
            seen_stdlib_group = False
            for import_group in import_groups:
                start, end, imports = import_group
                if any(name.startswith(THIRD_PARTY_MODULES)
                       for name in imports):
                    # oslo* are third-party modules
                    break
                if any(name in APPLICATION_MODULES for name in imports):
                    # application import, add import six before in a new group
                    create_new_import_group = start
                    break
                if any(name in STDLIB_MODULES for name in imports):
                    seen_stdlib_group = True
            else:
                if seen_stdlib_group:
                    create_new_import_group = end
                else:
                    raise Exception("Unable to locate the import group of "
                                    "third-party modules in %s" % import_groups)

        if create_new_import_group is not None:
            pos = create_new_import_group
            return content[:pos] + import_line + '\n\n' + content[pos:]

        start, end, imports = import_group

        pos = start
        while pos < end:
            line = get_line(content, pos)
            if line == "\n":
                break
            try:
                names = parse_import(line)
            except SyntaxError:
                pass
            else:
                if import_names < names:
                    break
            pos += len(line)

        return content[:pos] + import_line + '\n' + content[pos:]

    def add_import_six(self, content):
        if IMPORT_SIX_REGEX.search(content):
            return content
        return self._add_import(content, 'import six', ['six'])

    def add_import(self, content, line):
        if re.search("^" + re.escape(line) + "$", content, flags=re.MULTILINE):
            return content
        names = parse_import(line)
        return self._add_import(content, line, names)

    def patch_iteritems(self, content):
        new_content = ITERITEMS_REGEX.sub(iteritems_replace, content)
        if new_content == content:
            return (False, content)
        new_content = self.add_import_six(new_content)
        return (True, new_content)

    def patch_itervalues(self, content):
        new_content = ITERVALUES_REGEX.sub(itervalues_replace, content)
        if new_content == content:
            return (False, content)
        new_content = self.add_import_six(new_content)
        return (True, new_content)

    def patch_iterkeys(self, content):
        new_content = ITERKEYS_REGEX.sub(iterkeys_replace, content)
        if new_content == content:
            return (False, content)
        new_content = self.add_import_six(new_content)
        return (True, new_content)

    def warn_line(self, line):
        self.warnings.append("%s: %s"
                             % (self.current_file, line.strip()))

    def check_iteritems(self, content):
        for match in ITERITEMS_LINE_REGEX.finditer(content):
            line = match.group(0)
            if "six.iteritems" not in line:
                self.warn_line(line)

    def check_itervalues(self, content):
        for match in ITERVALUES_LINE_REGEX.finditer(content):
            line = match.group(0)
            if "six.itervalues" not in line:
                self.warn_line(line)

    def check_iterkeys(self, content):
        for match in ITERKEYS_LINE_REGEX.finditer(content):
            line = match.group(0)
            if "six.iterkeys" not in line:
                self.warn_line(line)

    def patch_next(self, content):
        new_content = NEXT_REGEX.sub(next_replace, content)
        return (new_content != content, new_content)

    def check_next(self, content):
        for match in NEXT_LINE_REGEX.finditer(content):
            self.warn_line(match.group(0))
        for match in DEF_NEXT_LINE_REGEX.finditer(content):
            self.warn_line(match.group(0))

    def patch_long(self, content):
        new_content = LONG_REGEX.sub(long_replace, content)
        return (new_content != content, new_content)

    def check_long(self, content):
        for match in LONG_LINE_REGEX.finditer(content):
            self.warn_line(match.group(0))

    def patch_unicode_line(self, line, start, end):
        result = None
        while True:
            match = UNICODE_REGEX.search(line, start, end)
            if not match:
                return result
            line = line[:match.start()] + "six.text_type" + line[match.end():]
            result = line
            start = match.start() + len("six.text_type")
            end += len("six.text_type") - len("unicode")

    def patch_unicode(self, content):
        modified = False
        lines = content.splitlines(True)
        for index, line in enumerate(lines):
            # Ugly heuristic to exclude "import ...", "from ... import ...",
            # function name in "def ...(", comments and strings
            # declared with """
            if line.startswith(("import ", "from ")):
                continue
            start = 0
            end = line.find("#")
            if end < 0:
                end = len(line)

            pos = line.find('"""', start, end)
            if pos != -1:
                end = pos

            match = DEF_REGEX.search(line, start, end)
            if match:
                start = match.end()

            new_line = self.patch_unicode_line(line, start, end)
            if new_line is not None:
                lines[index] = new_line
                modified = True
        if not modified:
            return (False, content)

        content = ''.join(lines)
        content = self.add_import_six(content)
        return (True, content)

    def check_unicode(self, content):
        for line in content.splitlines():
            end = line.find("#")
            if end >= 0:
                match = UNICODE_REGEX.search(line, 0, end)
            else:
                match = UNICODE_REGEX.search(line, 0)
            if match:
                self.warn_line(line)

    def patch_raise(self, content):
        old_content = content
        content = RAISE2_REGEX.sub(raise2_replace, content)
        new_content = RAISE3_REGEX.sub(raise3_replace, content)
        if new_content != content:
            content = self.add_import_six(new_content)
        return (content != old_content, content)

    def check_raise(self, content):
        for match in RAISE_LINE_REGEX.finditer(content):
            self.warn_line(match.group(0))

    def patch_xrange(self, content):
        need_six = False

        def xrange1_replace(regs):
            nonlocal need_six
            end = int(regs.group(1))
            if end > self.max_range:
                need_six = True
            return 'range(%s)' % end

        def xrange2_replace(regs):
            nonlocal need_six
            start = int(regs.group(1))
            end = int(regs.group(2))
            if (end - start) > self.max_range:
                need_six = True
            return 'range(%s, %s)' % (start, end)

        new_content = XRANGE1_REGEX.sub(xrange1_replace, content)
        new_content = XRANGE2_REGEX.sub(xrange2_replace, new_content)

        new_content2 = new_content.replace("xrange(", "range(")
        if new_content2 != new_content:
            need_six = True
        new_content = new_content2

        if need_six:
            new_content = self.add_import(new_content, 'from six.moves import range')
        return (new_content != content, new_content)

    def patch_basestring(self, content):
        new_content = BASESTRING_REGEX.sub('six.string_types', content)
        if new_content == content:
            return (False, content)
        new_content = self.add_import_six(new_content)
        return (True, new_content)

    def check_basestring(self, content):
        for line in content.splitlines():
            if 'basestring' in line:
                self.warn_line(line)

    def check_xrange(self, content):
        for line in content.splitlines():
            if 'xrange' in line:
                self.warn_line(line)

    def patch_six_moves(self, content):
        add_imports = []
        replace = []

        def six_moves_import(regs):
            name = regs.group(1)
            new_name = SIX_MOVES[name]
            line = 'from six.moves import %s' % new_name
            add_imports.append(line)
            replace.append((name, new_name))
            return ''

        def six_moves_from_import(regs):
            new_name = SIX_MOVES[regs.group(1)]
            line = 'from six.moves.%s import %s' % (new_name, regs.group(2))
            add_imports.append(line)
            return ''

        new_content = IMPORT_REGEX.sub(six_moves_import,
                                       content)
        new_content = FROM_IMPORT_REGEX.sub(six_moves_from_import,
                                            new_content)
        for old_name, new_name in replace:
            # Only match words
            regex = r'\b%s\b' % re.escape(old_name)
            new_content = re.sub(regex, new_name, new_content)
        for line in add_imports:
            names = parse_import(line)
            new_content = self._add_import(new_content, line, names)
        return (new_content != content, new_content)

    def check_six_moves(self, content):
        pass

    def patch_stringio(self, content):
        new_content = IMPORT_STRINGIO_REGEX.sub('', content)
        if new_content == content:
            return (False, content)
        new_content = self.add_import_six(new_content)
        new_content = new_content.replace("StringIO.StringIO", "six.StringIO")
        return (True, new_content)

    def check_stringio(self, content):
        pass

    def patch_urllib(self, content):
        if ('from six.moves import urllib' in content
            or 'six.moves.urllib' in content):
            return (False, content)

        new_content = IMPORT_URLLIB_REGEX.sub('', content)
        new_content = URLLIB_ATTR_REGEX.sub(replace_urllib, new_content)
        new_content = URLLIB2_REGEX.sub('urllib', new_content)
        if new_content == content:
            return (False, content)

        new_content = self.add_import(new_content,
                                      "from six.moves import urllib")
        return (True, new_content)

    def check_urllib(self, content):
        pass

    def check(self, content):
        for operation in self.operations:
            checker = getattr(self, "check_" + operation)
            checker(content)

    def patch(self, filename):
        self.current_file = filename

        with tokenize.open(filename) as fp:
            content = fp.read()

        modified = False
        for operation in self.operations:
            patcher = getattr(self, "patch_" + operation)
            op_modified, content = patcher(content)
            modified |= op_modified

        if not modified:
            self.check(content)
            return False

        with open(filename, "rb") as fp:
            encoding, _ = tokenize.detect_encoding(fp.readline)

        print("Patch %s" % filename)
        with open(filename, "w", encoding=encoding) as fp:
            fp.write(content)
        self.check(content)
        return True

    def main(self):
        for filename in self.walk():
            try:
                self.patch(filename)
            except Exception:
                print("ERROR while patching %s" % filename)
                raise

        for warning in self.warnings:
            print("WARNING: %s" % warning)


def usage():
    print("usage: %s <directory> <operation>" % sys.argv[0])
    print()
    print("operations:")
    for operation in sorted(OPERATIONS):
        print("- %s" % operation)
    print()
    print("<operation> can be a list of operations separated by commas")
    print("Example: six_moves,urllib")
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        usage()
    dir = sys.argv[1]
    operations = sys.argv[2].split(',')
    for operation in operations:
        if operation not in OPERATIONS:
            print("invalid operation: %s" % operation)
            print()
            usage()

    Patcher(dir, operations).main()

if __name__ == "__main__":
    main()
