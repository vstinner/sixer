#!/usr/bin/env python3
import os
import re
import sys
import tokenize

# Maximum range which creates a list on Python 2. For example, xrange(10) can
# be replaced with range(10) without "from six.moves import range".
MAX_RANGE = 1024

# Modules of the Python standard library
STDLIB_MODULES = (
    "StringIO",
    "copy",
    "glob",
    "heapq",
    "logging",
    "os",
    "re",
    "socket",
    "string",
    "sys",
    "textwrap",
    "unittest",
    "urlparse",
)

# Name prefix of third-party modules (ex: "oslo" matches "osloconfig"
# and "oslo.db")
THIRD_PARTY_MODULES = (
    "eventlet",
    "mock",
    "oslo",
    "six",
    "subunit",
    "testtools",
    "webob",
)

# Modules of the application
APPLICATION_MODULES = (
    "ceilometer",
    "cinder",
    "glance",
    "glance_store",
    "neutron",
    "nova",
    "swift",
)

# Ugly regular expressions because I'm too lazy to write a real parser,
# and Match objects are convinient to modify code in-place

def import_regex(name):
    return re.compile(r"^import %s\n" % name, re.MULTILINE)

def from_import_regex(module, symbol):
    return re.compile(r"^from %s import %s\n" % (module, symbol), re.MULTILINE)

# 'identifier'
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
PARENT_REGEX = r'\([^()]*(?:%s)?[^()]*\)' % SUBPARENT_REGEX
IMPORT_GROUP_REGEX = re.compile(r"^(?:import|from) .*?\n\n",
                                re.MULTILINE | re.DOTALL)
IMPORT_NAME_REGEX = re.compile(r"^(?:import|from) (%s)" % IDENTIFIER_REGEX,
                               re.MULTILINE)



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


def get_line(content, pos):
    eol = content.find("\n", pos)
    return content[pos:eol + 1]


class Operation:
    NAME = "<name>"
    DOC = "<doc>"

    def __init__(self, patcher):
        self.patcher = patcher

    def patch(self, content):
        raise NotImplementedError

    def check(self, content):
        raise NotImplementedError


class Iteritems(Operation):
    NAME = "iteritems"
    DOC = "replace dict.iteritems() with six.iteritems(dict)"

    REGEX = re.compile(r"(%s)\.iteritems\(\)" % EXPR_REGEX)
    CHECK_REGEX = re.compile(r"^.*\biteritems *\(.*$", re.MULTILINE)

    def replace(self, regs):
        return 'six.iteritems(%s)' % regs.group(1)

    def patch(self, content):
        new_content = self.REGEX.sub(self.replace, content)
        if new_content == content:
            return content
        return self.patcher.add_import_six(new_content)

    def check(self, content):
        for match in self.CHECK_REGEX.finditer(content):
            line = match.group(0)
            if "six.iteritems" not in line:
                self.patcher.warn_line(line)


class Itervalues(Operation):
    NAME = "itervalues"
    DOC = "replace dict.itervalues() with six.itervalues(dict)"

    REGEX = re.compile(r"(%s)\.itervalues\(\)" % EXPR_REGEX)
    CHECK_REGEX = re.compile(r"^.*\bitervalues *\(.*$", re.MULTILINE)

    def replace(self, regs):
        return 'six.itervalues(%s)' % regs.group(1)

    def patch(self, content):
        new_content = self.REGEX.sub(self.replace, content)
        if new_content == content:
            return content
        return self.patcher.add_import_six(new_content)

    def check(self, content):
        for match in self.CHECK_REGEX.finditer(content):
            line = match.group(0)
            if "six.itervalues" not in line:
                self.patcher.warn_line(line)


class Iterkeys(Operation):
    NAME = "iterkeys"
    DOC = "replace dict.iterkeys() with six.iterkeys(dict)"

    REGEX = re.compile(r"(%s)\.iterkeys\(\)" % EXPR_REGEX)
    CHECK_REGEX = re.compile(r"^.*\biterkeys *\(.*$", re.MULTILINE)

    def replace(self, regs):
        return 'six.iterkeys(%s)' % regs.group(1)

    def patch(self, content):
        new_content = self.REGEX.sub(self.replace, content)
        if new_content == content:
            return content
        return self.patcher.add_import_six(new_content)

    def check(self, content):
        for match in self.CHECK_REGEX.finditer(content):
            line = match.group(0)
            if "six.iterkeys" not in line:
                self.patcher.warn_line(line)


class Next(Operation):
    NAME = "next"
    DOC = "replace it.next() with next(it)"

    # Match 'gen.next()' and '(...).next()'
    REGEX = re.compile(r"(%s|%s)\.next\(\)" % (EXPR_REGEX, PARENT_REGEX))

    CHECK_REGEX = re.compile(r"^.*\.next *\(.*$", re.MULTILINE)
    DEF_NEXT_LINE_REGEX = re.compile(r"^.*def next *\(.*$", re.MULTILINE)

    def replace(self, regs):
        expr = regs.group(1)
        if expr.startswith('(') and expr.endswith(')'):
            expr = expr[1:-1]
        return 'next(%s)' % expr

    def patch(self, content):
        return self.REGEX.sub(self.replace, content)

    def check(self, content):
        for match in self.CHECK_REGEX.finditer(content):
            self.patcher.warn_line(match.group(0))
        for match in self.DEF_NEXT_LINE_REGEX.finditer(content):
            self.patcher.warn_line(match.group(0))


class Long(Operation):
    NAME = "long"
    DOC = "replace 123L with 123"

    # '123L' but not '0123L'
    REGEX = re.compile(r"\b([1-9][0-9]*|0)L")

    # '123L', '0123L'
    CHECK_REGEX = re.compile(r"^.*\b[0-9]+L.*$", re.MULTILINE)

    def replace(self, regs):
        return regs.group(1)

    def patch(self, content):
        return self.REGEX.sub(self.replace, content)

    def check(self, content):
        for match in self.CHECK_REGEX.finditer(content):
            self.patcher.warn_line(match.group(0))


class Unicode(Operation):
    NAME = "unicode"
    DOC = "replace unicode with six.text_type"

    UNICODE_REGEX = re.compile(r'\bunicode\b')

    DEF_REGEX = re.compile(r'^ *def +%s *\(' % IDENTIFIER_REGEX, re.MULTILINE)

    def _patch_line(self, line, start, end):
        result = None
        while True:
            match = self.UNICODE_REGEX.search(line, start, end)
            if not match:
                return result
            line = line[:match.start()] + "six.text_type" + line[match.end():]
            result = line
            start = match.start() + len("six.text_type")
            end += len("six.text_type") - len("unicode")

    def patch(self, content):
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

            match = self.DEF_REGEX.search(line, start, end)
            if match:
                start = match.end()

            new_line = self._patch_line(line, start, end)
            if new_line is not None:
                lines[index] = new_line
                modified = True
        if not modified:
            return content

        return self.patcher.add_import_six(''.join(lines))

    def check(self, content):
        for line in content.splitlines():
            end = line.find("#")
            if end >= 0:
                match = self.UNICODE_REGEX.search(line, 0, end)
            else:
                match = self.UNICODE_REGEX.search(line, 0)
            if match:
                self.patcher.warn_line(line)


class Xrange(Operation):
    NAME = "xrange"
    DOC = "replace xrange() with range() using 'from six import range'"

    # 'xrange(2)'
    XRANGE1_REGEX = re.compile(r"xrange\(([0-9]+)\)")
    XRANGE2_REGEX = re.compile(r"xrange\(([0-9]+), ([0-9]+)\)")

    def patch(self, content):
        need_six = False

        def xrange1_replace(regs):
            nonlocal need_six
            end = int(regs.group(1))
            if end > self.patcher.max_range:
                need_six = True
            return 'range(%s)' % end

        def xrange2_replace(regs):
            nonlocal need_six
            start = int(regs.group(1))
            end = int(regs.group(2))
            if (end - start) > self.patcher.max_range:
                need_six = True
            return 'range(%s, %s)' % (start, end)

        new_content = self.XRANGE1_REGEX.sub(xrange1_replace, content)
        new_content = self.XRANGE2_REGEX.sub(xrange2_replace, new_content)

        new_content2 = new_content.replace("xrange(", "range(")
        if new_content2 != new_content:
            need_six = True
        new_content = new_content2

        if need_six:
            new_content = self.patcher.add_import(new_content, 'from six.moves import range')
        return new_content

    def check(self, content):
        for line in content.splitlines():
            if 'xrange' in line:
                self.patcher.warn_line(line)


class Basestring(Operation):
    NAME = "basestring"
    DOC = "replace basestring with six.string_types"

    # match 'basestring' word
    BASESTRING_REGEX = re.compile(r"\bbasestring\b")

    def patch(self, content):
        new_content = self.BASESTRING_REGEX.sub('six.string_types', content)
        if new_content == content:
            return content
        return self.patcher.add_import_six(new_content)

    def check(self, content):
        for line in content.splitlines():
            if 'basestring' in line:
                self.patcher.warn_line(line)


class Stringio(Operation):
    NAME = "stringio"
    DOC = ("replace StringIO.StringIO with six.StringIO"
           " and cStringIO.StringIO with six.moves.cStringIO")

    # 'import StringIO'
    IMPORT_STRINGIO_REGEX = import_regex(r"StringIO")

    # 'from StringIO import StringIO'
    FROM_IMPORT_STRINGIO_REGEX = from_import_regex(r"StringIO", r"StringIO")

    # 'from StringIO import StringIO'
    FROM_IMPORT_CSTRINGIO_REGEX = from_import_regex(r"cStringIO", r"StringIO")

    # 'import cStringIO'
    IMPORT_CSTRINGIO_REGEX = import_regex(r"cStringIO")

    # 'import cStringIO as StringIO'
    IMPORT_CSTRINGIO_AS_REGEX = import_regex(r"cStringIO as StringIO")

    # 'StringIO.', 'cStringIO.', but not 'six.StringIO' or 'six.cStringIO'
    CSTRINGIO_REGEX = re.compile(r'(?<!six\.)\bc?StringIO\.')

    def _patch_stringio1(self, content):
        # Replace 'from StringIO import StringIO'
        # with 'from six import StringIO'
        new_content = self.FROM_IMPORT_STRINGIO_REGEX.sub('', content)
        if new_content == content:
            return content
        return self.patcher.add_import(new_content, 'from six import StringIO')

    def _patch_stringio2(self, content):
        # Replace 'import StringIO' + 'StringIO.StringIO'
        # with 'import six' + 'six.StringIO'
        new_content = self.IMPORT_STRINGIO_REGEX.sub('', content)
        if new_content == content:
            return content

        new_content = self.patcher.add_import_six(new_content)
        return new_content.replace("StringIO.StringIO", "six.StringIO")

    def _patch_cstringio1(self, content):
        # Replace 'from cStringIO import StringIO'
        # with 'from six.moves import cStringIO as StringIO'
        new_content = self.FROM_IMPORT_CSTRINGIO_REGEX.sub('', content)
        if new_content == content:
            return content

        new_content = self.patcher.add_import(new_content,
                                      "from six.moves import cStringIO as StringIO")
        return new_content

    def _patch_cstringio2(self, content):
        # Replace 'import cStringIO' + 'cStringIO.StringIO'
        # with 'from six import moves' + 'moves.cStringIO'
        new_content = self.IMPORT_CSTRINGIO_REGEX.sub('', content)
        if new_content == content:
            return content

        new_content = self.patcher.add_import(new_content, "from six import moves")
        return new_content.replace("cStringIO.StringIO", "moves.cStringIO")

    def _patch_cstringio3(self, content):
        # Replace 'import cStringIO as StringIO' + 'StringIO.StringIO'
        # with 'from six import moves' + 'moves.cStringIO'
        new_content = self.IMPORT_CSTRINGIO_AS_REGEX.sub('', content)
        if new_content == content:
            return content

        new_content = self.patcher.add_import(new_content, "from six import moves")
        return new_content.replace("StringIO.StringIO", "moves.cStringIO")

    def patch(self, content):
        content = self._patch_stringio1(content)
        content = self._patch_stringio2(content)
        content = self._patch_cstringio1(content)
        content = self._patch_cstringio2(content)
        content = self._patch_cstringio3(content)
        return content

    def check(self, content):
        for line in content.splitlines():
            if 'StringIO.StringIO' in line or self.CSTRINGIO_REGEX.search(line):
                self.patcher.warn_line(line)


class Urllib(Operation):
    NAME = "urllib"
    DOC = "replace urllib and urllib2 with six.moves.urllib"

    # 'import urllib', 'import urllib2', 'import urlparse'
    IMPORT_URLLIB_REGEX = import_regex(r"\b(?:urllib2?|urlparse)\b")

    # urllib.attr or urllib2.attr
    URLLIB_ATTR_REGEX = re.compile(r"\b(?:urllib2?|urlparse)\.(%s)"
                                   % IDENTIFIER_REGEX)

    # 'urllib2' but not 'urllib2.parse_http_list'
    URLLIB2_REGEX = re.compile(r"\burllib2\b(?!\.parse_http_list)")

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
            'pathname2url',
            'urlopen',
        ),

        'parse': (
            'parse_qs',
            'parse_qsl',
            'quote',
            'unquote',
            'urlencode',
            'urljoin',
            'urlparse',
            'urlsplit',
            'urlunparse',
            'urlunsplit',
        ),
    }

    URLLIB = {}
    for submodule, symbols in SIX_MOVES_URLLIB.items():
        for symbol in symbols:
            URLLIB[symbol] = submodule
    URLLIB_UNCHANGED = set('urllib.%s' % submodule
                           for submodule in SIX_MOVES_URLLIB)

    def replace(self, regs):
        text = regs.group(0)
        if text in self.URLLIB_UNCHANGED:
            return text
        name = regs.group(1)
        if name == 'parse_http_list':
            # six has no helper for parse_http_list() yet
            return text
        try:
            submodule = self.URLLIB[name]
        except KeyError:
            raise Exception("unknown urllib symbol: %s" % text)
        return 'urllib.%s.%s' % (submodule, name)

    def patch(self, content):
        new_content = self.IMPORT_URLLIB_REGEX.sub('', content)
        new_content = self.URLLIB_ATTR_REGEX.sub(self.replace, new_content)
        new_content = self.URLLIB2_REGEX.sub('urllib', new_content)
        if new_content == content:
            return content

        return self.patcher.add_import(new_content,
                                       "from six.moves import urllib")

    def check(self, content):
        for line in content.splitlines():
            if 'urllib2.parse_http_list' in line:
                self.patcher.warn_line(line)


class Raise(Operation):
    NAME = "raise"
    DOC = ("replace 'raise exc, msg' with 'raise exc(msg)'"
           " and replace 'raise a, b, c' with 'six.reraise(a, b, c)'")

    # 'raise a, b, c' expr
    RAISE3_REGEX = re.compile(r"raise (%s), (%s), (%s)"
                              % (EXPR_REGEX, EXPR_REGEX, EXPR_REGEX))
    # 'raise a, b' expr
    RAISE2_REGEX = re.compile(r'''raise (%s), (%s|'[^']+'|"[^"]+")$'''
                              % (EXPR_REGEX, EXPR_REGEX), re.MULTILINE)
    # 'raise a,' line
    RAISE_LINE_REGEX = re.compile(r"^.*raise %s,.*$" % EXPR_REGEX,
                                  re.MULTILINE)

    def raise2_replace(self, regs):
        return 'raise %s(%s)' % (regs.group(1), regs.group(2))

    def raise3_replace(self, regs):
        exc_type = regs.group(1)
        exc_value = regs.group(2)
        exc_tb = regs.group(3)
        if (exc_type.endswith('[0]')
            and exc_value.endswith('[1]')
            and exc_tb.endswith('[2]')):
            return ('six.reraise(*%s)' % exc_type[:-3])

        return ('six.reraise(%s, %s, %s)'
                % (exc_type, exc_value, exc_tb))

    def patch(self, content):
        old_content = content
        content = self.RAISE2_REGEX.sub(self.raise2_replace, content)
        new_content = self.RAISE3_REGEX.sub(self.raise3_replace, content)
        if new_content != content:
            content = self.patcher.add_import_six(new_content)
        return content

    def check(self, content):
        for match in self.RAISE_LINE_REGEX.finditer(content):
            self.patcher.warn_line(match.group(0))


class SixMoves(Operation):
    NAME = "six_moves"
    DOC = ("replace Python 2 imports with six.moves imports")

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

    SIX_MOVES_REGEX = ("(%s)" % '|'.join(sorted(map(re.escape, SIX_MOVES.keys()))))
    IMPORT_REGEX = re.compile(r"^import %s\n\n?" % SIX_MOVES_REGEX,
                              re.MULTILINE)
    FROM_REGEX = r"(%s(?:, %s)*)" % (IDENTIFIER_REGEX, IDENTIFIER_REGEX)
    FROM_IMPORT_REGEX = re.compile(r"^from %s import %s"
                            % (SIX_MOVES_REGEX, FROM_REGEX),
                            re.MULTILINE)

    def patch(self, content):
        add_imports = []
        replace = []

        def replace_import(regs):
            name = regs.group(1)
            new_name = self.SIX_MOVES[name]
            line = 'from six.moves import %s' % new_name
            add_imports.append(line)
            replace.append((name, new_name))
            return ''

        def replace_from(regs):
            new_name = self.SIX_MOVES[regs.group(1)]
            line = 'from six.moves.%s import %s' % (new_name, regs.group(2))
            add_imports.append(line)
            return ''

        new_content = self.IMPORT_REGEX.sub(replace_import, content)
        new_content = self.FROM_IMPORT_REGEX.sub(replace_from, new_content)
        for old_name, new_name in replace:
            # Only match words
            regex = r'\b%s\b' % re.escape(old_name)
            new_content = re.sub(regex, new_name, new_content)
        for line in add_imports:
            names = parse_import(line)
            new_content = self.patcher.add_import_names(new_content, line,
                                                        names)
        return new_content

    def check(self, content):
        pass


class All(Operation):
    NAME = "all"
    DOC = "apply all available operations"

    def patch(self, content):
        # All is a virtual operation, it's implemented in Patcher.__init__
        return content

    def check(self, content):
        # All is a virtual operation, it's implemented in Patcher.__init__
        pass


OPERATIONS = (
    Iteritems,
    Itervalues,
    Iterkeys,
    Next,
    Long,
    Unicode,
    Xrange,
    Basestring,
    Stringio,
    Urllib,
    Raise,
    SixMoves,
    All,
)
OPERATION_NAMES = set(operation.NAME for operation in OPERATIONS)
OPERATION_BY_NAME = {operation.NAME: operation for operation in OPERATIONS}


class Patcher:
    IMPORT_SIX_REGEX = re.compile(r"^import six$", re.MULTILINE)

    def __init__(self, operations):
        operations = set(operations)
        if All.NAME in operations:
            operations |= set(OPERATION_NAMES)
            operations.discard(All.NAME)
        self.operations = [OPERATION_BY_NAME[name](self)
                           for name in operations]
        self.warnings = []
        self.current_file = None
        self.max_range = MAX_RANGE

    def _walk(self, path):
        if os.path.isfile(path):
            yield path
            return

        for dirpath, dirnames, filenames in os.walk(path):
            # Don't walk into .tox
            try:
                dirnames.remove(".tox")
            except ValueError:
                pass
            for filename in filenames:
                if filename.endswith(".py"):
                    yield os.path.join(dirpath, filename)

    def walk(self, paths):
        for path in paths:
            for filename in self._walk(path):
                yield filename

    def add_import_names(self, content, import_line, import_names):
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
        if self.IMPORT_SIX_REGEX.search(content):
            return content
        return self.add_import_names(content, 'import six', ['six'])

    def add_import(self, content, line):
        if re.search("^" + re.escape(line) + "$", content, flags=re.MULTILINE):
            return content
        names = parse_import(line)
        return self.add_import_names(content, line, names)

    def _display_warning(self, warn):
        msg = "WARNING: %s: %s" % warn
        print(msg)

    def warn_line(self, line):
        warn = (self.current_file, line.strip())
        self._display_warning(warn)
        self.warnings.append(warn)

    def check(self, content):
        for operation in self.operations:
            operation.check(content)

    def patch(self, filename):
        self.current_file = filename

        with tokenize.open(filename) as fp:
            content = fp.read()

        old_content = content
        for operation in self.operations:
            content = operation.patch(content)

        if content == old_content:
            # no change
            self.check(content)
            return False

        with open(filename, "rb") as fp:
            encoding, _ = tokenize.detect_encoding(fp.readline)

        print("Patch %s" % filename)
        with open(filename, "w", encoding=encoding) as fp:
            fp.write(content)
        self.check(content)
        return True

    def main(self, paths):
        for filename in self.walk(paths):
            try:
                self.patch(filename)
            except Exception:
                print("ERROR while patching %s" % filename)
                raise

        if self.warnings:
            print()
            print("Warnings:")
        for warning in self.warnings:
            self._display_warning(warning)


def usage():
    print("usage: %s <operation> <file1> <file2> <...>" % sys.argv[0])
    print()
    print("operations:")
    for name in sorted(OPERATION_NAMES):
        operation = OPERATION_BY_NAME[name]
        print("- %s: %s" % (name, operation.DOC))
    print()
    print("If a directory is passed, sixer finds .py files in subdirectories.")
    print()
    print("<operation> can be a list of operations separated by commas")
    print("Example: six_moves,urllib")
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        usage()
    operations = sys.argv[1].split(',')
    files = sys.argv[2:]
    for operation in operations:
        if operation not in OPERATION_NAMES:
            print("invalid operation: %s" % operation)
            print()
            usage()

    Patcher(operations).main(files)

if __name__ == "__main__":
    main()
