#!/usr/bin/env python3
import collections
import functools
import optparse
import os
import re
import sys
import tokenize
import types

# Maximum range which creates a list on Python 2. For example, xrange(10) can
# be replaced with range(10) without "from six.moves import range".
MAX_RANGE = 1024

# Modules of the Python standard library
STDLIB_MODULES = set((
    "StringIO",
    "copy",
    "csv",
    "datetime",
    "glob",
    "heapq",
    "importlib",
    "itertools",
    "json",
    "logging",
    "os",
    "re",
    "socket",
    "string",
    "sys",
    "textwrap",
    "traceback",
    "types",
    "unittest",
    "urlparse",
))

# Name prefix of third-party modules (ex: "oslo" matches "osloconfig"
# and "oslo.db")
THIRD_PARTY_MODULES = (
    "djanjo",
    "eventlet",
    "keystoneclient",
    "mock",
    "mox3",
    "oslo",
    "selenium",
    "six",
    "subunit",
    "testtools",
    "webob",
    "wsme",
)

# Modules of the application
APPLICATION_MODULES = set((
    "ceilometer",
    "cinder",
    "congress",
    "glance",
    "glance_store",
    "horizon",
    "neutron",
    "nova",
    "openstack_dashboard",
    "swift",
))

# Ugly regular expressions because I'm too lazy to write a real parser,
# and Match objects are convinient to modify code in-place

def import_regex(name):
    return re.compile(r"^import %s\n\n?" % name,
                      re.MULTILINE)

def from_import_regex(module, symbol):
    return re.compile(r"^from %s import %s\n\n?" % (module, symbol),
                      re.MULTILINE)

# 'identifier', 'var3', 'NameCamelCase'
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
IMPORT_GROUP_REGEX = re.compile(r"^(?:import|from) .*\n(?:(?:import|from) .*\n)*\n*",
                                re.MULTILINE)
IMPORT_NAME_REGEX = re.compile(r"^(?:import|from) (%s)" % IDENTIFIER_REGEX,
                               re.MULTILINE)
# 'abc', 'sym1, sym2'
FROM_IMPORT_SYMBOLS_REGEX = r"%s(?:, %s)*" % (IDENTIFIER_REGEX, IDENTIFIER_REGEX)



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
        self.options = patcher.options

    def patch(self, content):
        raise NotImplementedError

    def check(self, content):
        raise NotImplementedError

    def warn_line(self, line):
        message = ("[%s] %s: %s"
                   % (self.NAME, self.patcher.current_file, line.strip()))
        self.patcher.warning(message)


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
                self.warn_line(line)


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
                self.warn_line(line)


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
                self.warn_line(line)


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
            self.warn_line(match.group(0))
        for match in self.DEF_NEXT_LINE_REGEX.finditer(content):
            self.warn_line(match.group(0))


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
            self.warn_line(match.group(0))


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
                self.warn_line(line)


class Xrange(Operation):
    NAME = "xrange"
    DOC = "replace xrange() with range() using 'from six import range'"

    # 'xrange(' but not 'moves.xrange(' or 'from six.moves import xrange'
    XRANGE_REGEX = re.compile("(?<!moves\.)xrange *\(")
    # 'xrange(2)'
    XRANGE1_REGEX = re.compile(r"(?<!moves\.)xrange\(([0-9]+)\)")
    # 'xrange(1, 6)'
    XRANGE2_REGEX = re.compile(r"(?<!moves\.)xrange\(([0-9]+), ([0-9]+)\)")

    def patch(self, content):
        need_six = False

        def xrange1_replace(regs):
            nonlocal need_six
            end = int(regs.group(1))
            if end > self.options.max_range:
                need_six = True
            return 'range(%s)' % end

        def xrange2_replace(regs):
            nonlocal need_six
            start = int(regs.group(1))
            end = int(regs.group(2))
            if (end - start) > self.options.max_range:
                need_six = True
            return 'range(%s, %s)' % (start, end)

        new_content = self.XRANGE1_REGEX.sub(xrange1_replace, content)
        new_content = self.XRANGE2_REGEX.sub(xrange2_replace, new_content)

        new_content2 = self.XRANGE_REGEX.sub("range(", new_content)
        if new_content2 != new_content:
            need_six = True
        new_content = new_content2

        if need_six:
            new_content = self.patcher.add_import(new_content, 'from six.moves import range')
        return new_content

    def check(self, content):
        for line in content.splitlines():
            if self.XRANGE_REGEX.search(line):
                self.warn_line(line)


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
                self.warn_line(line)


class StringIO(Operation):
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
                self.warn_line(line)


class Urllib(Operation):
    NAME = "urllib"
    DOC = "replace urllib, urllib2 and urlparse with six.moves.urllib"

    # 'import urllib', 'import urllib2', 'import urlparse'
    IMPORT_URLLIB_REGEX = import_regex(r"\b(?:urllib2?|urlparse)\b")

    # 'from urlparse import symbol, symbol2'
    FROM_IMPORT_REGEX = re.compile(r"^from (urllib2?|urlparse) import (%s)\n\n?"
                                   % FROM_IMPORT_SYMBOLS_REGEX,
                                   re.MULTILINE)

    # 'from urlparse import'
    FROM_IMPORT_WARN_REGEX = re.compile(r"^from (?:urllib2?|urlparse) import",
                                        re.MULTILINE)

    # urllib2.urlparse.attr or urllib2.urllib.attr
    URLLIB2_MOD_ATTR_REGEX = re.compile(r"\burllib2\.(?:urllib|urlparse)\.(%s)"
                                        % IDENTIFIER_REGEX)

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
            'quote_plus',
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
    # 'urllib.error', 'urllib.parse', 'urllib.request'
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

    def replace_import_from(self, add_imports, regs):
        module = regs.group(1)
        symbols = regs.group(2)
        if 'parse_http_list' in symbols:
            # six has no helper for parse_http_list() yet
            return regs.group(0)

        imports = collections.defaultdict(list)
        for symbol in symbols.split(','):
            name = symbol.strip()
            try:
                submodule = self.URLLIB[name]
            except KeyError:
                raise Exception("unknown urllib symbol: %s.%s"
                                % (module, name))
            imports[submodule].append(name)

        for submodule, names in imports.items():
            line = ('from six.moves.urllib.%s import %s'
                    % (submodule, ', '.join(names)))
            add_imports.add(line)
        return ''

    def patch_import(self, content):
        new_content = self.IMPORT_URLLIB_REGEX.sub('', content)
        if new_content == content:
            return content
        content = new_content

        content = self.URLLIB2_MOD_ATTR_REGEX.sub(self.replace, content)
        content = self.URLLIB_ATTR_REGEX.sub(self.replace, content)
        content = self.URLLIB2_REGEX.sub('urllib', content)
        return self.patcher.add_import(content,
                                       "from six.moves import urllib")

    def patch_from_import(self, content, add_imports):
        replace_cb = functools.partial(self.replace_import_from, add_imports)
        content = self.FROM_IMPORT_REGEX.sub(replace_cb, content)
        return content

    def patch(self, content):
        add_imports = set()
        content = self.patch_import(content)
        content = self.patch_from_import(content, add_imports)
        for line in sorted(add_imports):
            content = self.patcher.add_import(content, line)
        return content

    def check(self, content):
        for line in content.splitlines():
            if 'urllib2.parse_http_list' in line:
                self.warn_line(line)
            elif self.FROM_IMPORT_WARN_REGEX.search(line):
                self.warn_line(line)


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
            self.warn_line(match.group(0))


class Except(Operation):
    NAME = "except"
    DOC = ("replace 'except ValueError, exc:' with "
           "'except ValueError as exc:', replace "
           "'except (TypeError, ValueError), exc:' with "
           "'except (TypeError, ValueError) as exc:'.")

    # 'except ValueError, exc:'
    EXCEPT_REGEX = re.compile(r"except (%s), (%s):"
                              % (IDENTIFIER_REGEX, IDENTIFIER_REGEX))
    # 'except (ValueError, TypeError), exc:'
    EXCEPT2_REGEX = re.compile(r"except (\(%s(?:, *%s)*\)), (%s):"
                               % (IDENTIFIER_REGEX, IDENTIFIER_REGEX,
                                  IDENTIFIER_REGEX))
    EXCEPT_WARN_REGEX = re.compile(r"except [^,()]+, [^:]+:")
    EXCEPT_WARN2_REGEX = re.compile(r"except \([^()]+\), [^:]+:")

    def except_replace(self, regs):
        return 'except %s as %s:' % (regs.group(1), regs.group(2))

    def patch(self, content):
        content = self.EXCEPT_REGEX.sub(self.except_replace, content)
        return self.EXCEPT2_REGEX.sub(self.except_replace, content)

    def check(self, content):
        for line in content.splitlines():
            if (self.EXCEPT_WARN_REGEX.search(line)
                or self.EXCEPT_WARN2_REGEX.search(line)):
                self.warn_line(line)


class SixMoves(Operation):
    NAME = "six_moves"
    DOC = ("replace Python 2 imports with six.moves imports")

    SIX_MODULE_MOVES = {
        # Python 2 import => six.moves import
        'BaseHTTPServer': 'BaseHTTPServer',
        'ConfigParser': 'configparser',
        'Cookie': 'http_cookies',
        'HTMLParser': 'html_parser',
        'Queue': 'queue',
        'SimpleHTTPServer': 'SimpleHTTPServer',
        'SimpleXMLRPCServer': 'xmlrpc_server',
        '__builtin__': 'builtins',
        'cPickle': 'cPickle',
        'cookielib': 'http_cookiejar',
        'htmlentitydefs': 'html_entities',
        'httplib': 'http_client',
        'repr': 'reprlib',
    #    'thread': '_thread',
        'xmlrpclib': 'xmlrpc_client',
    }

    # 'BaseHTTPServer', '__builtin__', 'repr', ...
    SIX_MOVES_REGEX = sorted(map(re.escape, SIX_MODULE_MOVES.keys()))
    SIX_MOVES_REGEX = ("(?:%s)" % '|'.join(SIX_MOVES_REGEX))

    # 'import BaseHTTPServer', 'import repr as reprlib'
    IMPORT_REGEX = re.compile(r"^import (%s)( as %s)?\n\n?"
                              % (SIX_MOVES_REGEX, IDENTIFIER_REGEX),
                              re.MULTILINE)
    # 'from BaseHTTPServer import ...'
    FROM_IMPORT_REGEX = re.compile(r"^from (%s) import (%s)\n\n?"
                                   % (SIX_MOVES_REGEX,
                                      FROM_IMPORT_SYMBOLS_REGEX),
                                   re.MULTILINE)

    # "patch('__builtin__."
    MOCK_REGEX = re.compile(r"""(patch\(['"])(%s)\."""
                            % SIX_MOVES_REGEX, re.MULTILINE)

    SIX_BUILTIN_MOVES = {
        # Python 2 builtin function => six.moves import
        'reduce': 'reduce',
        'reload': 'reload_module',
    }

    # 'reduce(', 'reload(', but not '.reduce(' (exclude 'moves.reduce(...)')
    BUILTIN_REGEX = re.compile(r'(?<!\.)\b(%s)\b( *\()'
                               % '|'.join(SIX_BUILTIN_MOVES))

    def replace_mock(self, regs):
        name = regs.group(2)
        new_name = self.SIX_MODULE_MOVES[name]
        return '%ssix.moves.%s.' % (regs.group(1), new_name)

    def replace_import(self, add_imports, replace_names, regs):
        name = regs.group(1)
        as_name = regs.group(2)
        new_name = self.SIX_MODULE_MOVES[name]
        line = 'from six.moves import %s' % new_name
        if as_name:
            line += as_name
        add_imports.add(line)
        replace_names.add((name, new_name))
        return ''

    def replace_from(self, add_imports, regs):
        new_name = self.SIX_MODULE_MOVES[regs.group(1)]
        symbols = regs.group(2)
        line = 'from six.moves.%s import %s' % (new_name, symbols)
        add_imports.add(line)
        return ''

    def replace_builtin(self, add_imports, regs):
        new_name = self.SIX_BUILTIN_MOVES[regs.group(1)]
        suffix = regs.group(2)
        line = 'from six.moves import %s' % new_name
        add_imports.add(line)
        return new_name + suffix

    def replace_builtins(self, add_imports, content):
        six_builtin_moves = dict(self.SIX_BUILTIN_MOVES)
        for regs in self.BUILTIN_REGEX.finditer(content):
            name = regs.group(1)
            if name not in six_builtin_moves:
                # already removed
                continue
            new_name = six_builtin_moves[name]

            pattern = 'from six.moves import %s\n' % new_name
            if pattern in content:
                # the symbol comes from six.moves, no need to patch it
                del six_builtin_moves[name]

        builtin_regex2 = re.compile(r'(?<!\.)\b(%s)\b( *\()'
                                   % '|'.join(six_builtin_moves))

        replace_cb = functools.partial(self.replace_builtin, add_imports)
        return builtin_regex2.sub(replace_cb, content)

    def patch(self, content):
        add_imports = set()
        replace_names = set()

        replace_cb = functools.partial(self.replace_import,
                                       add_imports, replace_names)
        content = self.IMPORT_REGEX.sub(replace_cb, content)

        replace_cb = functools.partial(self.replace_from, add_imports)
        content = self.FROM_IMPORT_REGEX.sub(replace_cb, content)

        content = self.replace_builtins(add_imports, content)

        for old_name, new_name in replace_names:
            # Only match words
            regex = r'\b%s\b' % re.escape(old_name)
            content = re.sub(regex, new_name, content)
        for line in sorted(add_imports):
            names = parse_import(line)
            content = self.patcher.add_import_names(content, line, names)

        content = self.MOCK_REGEX.sub(self.replace_mock, content)
        return content

    def check(self, content):
        pass


class Itertools(Operation):
    NAME = "itertools"
    DOC = "replace itertools.imap with six.moves.map"

    FUNCTIONS = {
        # itertools function => six.moves function
        'imap': 'map',
        'ifilter': 'filter',
    }
    FUNCTIONS_REGEX = '(?:%s)' % '|'.join(FUNCTIONS)

    # 'from itertools import imap'
    IFUNC_IMPORT_REGEX = from_import_regex(r"itertools", FUNCTIONS_REGEX)

    # 'imap', 'ifilter'
    IFUNC_REGEX = re.compile(r'\b(%s)\b' % FUNCTIONS_REGEX)

    # 'itertools.imap'
    ITERTOOLS_IFUNC_REGEX = re.compile(r'\bitertools\.(%s)\b' % FUNCTIONS_REGEX)

    # 'itertools.'
    ITERTOOLS_REGEX = re.compile(r'\bitertools\.')

    # 'import itertools'
    IMPORT_ITERTOOLS_REGEX = import_regex(r"itertools")

    def replace(self, regs):
        func = regs.group(1)
        six_func = self.FUNCTIONS[func]
        return 'six.moves.%s' % six_func

    def patch_from_import(self, content):
        # Replace itertools.imap with six.moves.map
        new_content = self.IFUNC_IMPORT_REGEX.sub('', content)
        if new_content == content:
            return content

        content = self.patcher.add_import_six(new_content)
        content = self.IFUNC_REGEX.sub(self.replace, content)
        return content

    def patch_import(self, content):
        # Replace itertools.imap with six.moves.map
        new_content = self.ITERTOOLS_IFUNC_REGEX.sub(self.replace, content)
        if new_content == content:
            return content

        content = new_content
        if not self.ITERTOOLS_REGEX.search(content):
            # itertools is no more used, remove it
            content = self.IMPORT_ITERTOOLS_REGEX.sub('', content)

        return self.patcher.add_import_six(content)

    def patch(self, content):
        content = self.patch_from_import(content)
        content = self.patch_import(content)
        return content

    def check(self, content):
        for line in content.splitlines():
            if 'imap' in line:
                self.warn_line(line)


class Dict0(Operation):
    NAME = "dict0"
    DOC = ("replace dict.keys()[0] with list(dict.keys())[0], "
           "same for dict.values()[0] and dict.items()[0]")

    EXPR_REGEX = re.compile(r'(%s\.(?:keys|values|items)\(\))\[0\]'
                            % EXPR_REGEX)

    CHECK_REGEX = re.compile(r'\.(?:keys|values|items)\(\)\[0\]')

    def replace(self, regs):
        return 'list(%s)[0]' % regs.group(1)

    def patch(self, content):
        return self.EXPR_REGEX.sub(self.replace, content)

    def check(self, content):
        for line in content.splitlines():
            if self.CHECK_REGEX.search(line):
                self.warn_line(line)


class DictAdd(Operation):
    NAME = "dict_add"
    DOC = ('replace "dict.keys() + list2" with "list(dict.keys()) + list2", '
           'same for "dict.values() + list2" and "dict.items() + list2"')

    EXPR_REGEX = re.compile(r'(%s\.(?:keys|values|items)\(\))( *\+)'
                            % EXPR_REGEX)

    CHECK_REGEX = re.compile(r'\.(?:keys|values|items)\(\) *\+')

    def replace(self, regs):
        return 'list(%s)%s' % (regs.group(1), regs.group(2))

    def patch(self, content):
        return self.EXPR_REGEX.sub(self.replace, content)

    def check(self, content):
        for line in content.splitlines():
            if self.CHECK_REGEX.search(line):
                self.warn_line(line)


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
    StringIO,
    Urllib,
    Raise,
    Except,
    SixMoves,
    Itertools,
    Dict0,
    DictAdd,
    All,
)
OPERATION_NAMES = set(operation.NAME for operation in OPERATIONS)
OPERATION_BY_NAME = {operation.NAME: operation for operation in OPERATIONS}


class Patcher:
    IMPORT_SIX_REGEX = re.compile(r"^import six$", re.MULTILINE)

    def __init__(self, operations, options=None):
        self.warnings = []
        self.current_file = None
        if options is None:
            options = types.SimpleNamespace()
            options.max_range = MAX_RANGE
            options.to_stdout = False
            options.quiet = False
        self.options = options

        operations = set(operations)
        if All.NAME in operations:
            operations |= set(OPERATION_NAMES)
            operations.discard(All.NAME)
        self.operations = [OPERATION_BY_NAME[name](self)
                           for name in operations]

    def _walk_dir(self, path):
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
            if os.path.isfile(path):
                yield path
            else:
                empty = True
                for filename in self._walk_dir(path):
                    yield filename
                    empty = False
                if empty:
                    if os.path.isdir(path):
                        self.warning("Directory %s doesn't contain any "
                                     ".py file" % path)
                    else:
                        self.warning("Path %s doesn't exist" % path)

    def add_import_names(self, content, import_line, import_names):
        import_line = import_line.rstrip() + '\n'

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
                    create_new_import_group = (start, False)
                    break
                if any(name in STDLIB_MODULES for name in imports):
                    seen_stdlib_group = True
            else:
                if seen_stdlib_group:
                    create_new_import_group = (end, True)
                else:
                    raise Exception("Unable to locate the import group of "
                                    "third-party modules in %s" % import_groups)

        if create_new_import_group is not None:
            pos, last_group = create_new_import_group
            part1 = content[:pos]
            if not part1 or part1.endswith('\n\n'):
                newline1 = ''
            else:
                newline1 = '\n'
            if last_group:
                newline2 = '\n\n'
            else:
                newline2 = '\n'
            return part1 + newline1 + import_line + newline2 + content[pos:]

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

        return content[:pos] + import_line + content[pos:]

    def add_import_six(self, content):
        if self.IMPORT_SIX_REGEX.search(content):
            return content
        return self.add_import_names(content, 'import six', ['six'])

    def add_import(self, content, line):
        if re.search("^" + re.escape(line) + "$", content, flags=re.MULTILINE):
            return content
        names = parse_import(line)
        return self.add_import_names(content, line, names)

    def _display_warning(self, msg):
        print("WARNING: %s" % msg)

    def warning(self, msg):
        self._display_warning(msg)
        self.warnings.append(msg)

    def check(self, content):
        for operation in self.operations:
            operation.check(content)

    def write_stdout(self, content):
        for line in content.splitlines():
            print(line)

    def patch(self, filename):
        self.current_file = filename

        with tokenize.open(filename) as fp:
            content = fp.read()

        modified = set()
        for operation in self.operations:
            new_content = operation.patch(content)
            if new_content == content:
                continue
            modified.add(operation.NAME)
            content = new_content

        if not modified:
            # no change
            self.check(content)
            if self.options.to_stdout:
                self.write_stdout(content)
            return False

        with open(filename, "rb") as fp:
            encoding, _ = tokenize.detect_encoding(fp.readline)

        if not self.options.quiet:
            print("Patch %s with %s" % (filename, ', '.join(sorted(modified))))
        if not self.options.to_stdout:
            with open(filename, "w", encoding=encoding) as fp:
                fp.write(content)
        else:
            self.write_stdout(content)
        self.check(content)
        return True

    @staticmethod
    def usage(parser):
        parser.print_help()
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

    @staticmethod
    def parse_options():
        parser = optparse.OptionParser(
            description=("sixer is a tool adding Python 3 support "
                         "to a Python 2 project"),
            usage="%prog [options] <operation> <file1> <file2> <...>")
        parser.add_option(
            '-c', '--to-stdout', action="store_true",
            help='Write output into stdout instead of modify files in-place '
                 '(imply --quiet option)')
        parser.add_option(
            '--app', type="str",
            help='Name of the application module, used to sort and group '
                 'imports')
        parser.add_option(
            '-q', '--quiet', action="store_true",
            help='Be quiet')
        parser.add_option(
            '--max-range', type="int",
            help=("Don't use six.moves.xrange for ranges smaller than "
                  "MAX_RANGE items (default: %s)" % MAX_RANGE),
            default=MAX_RANGE)

        options, args = parser.parse_args()
        if len(args) < 2:
            Patcher.usage(parser)
            sys.exit(1)

        if options.to_stdout:
            options.quiet = True

        operations = args[0].split(',')
        paths = args[1:]

        for operation in operations:
            if operation not in OPERATION_NAMES:
                print("invalid operation: %s" % operation)
                print()
                Patcher.usage(parser)
                sys.exit(1)

        if options.app:
            APPLICATION_MODULES.add(options.app)

        return options, operations, paths

    def main(self, paths):
        nfiles = 0
        for filename in self.walk(paths):
            try:
                self.patch(filename)
            except Exception:
                print("ERROR while patching %s" % filename)
                raise
            nfiles += 1

        if not self.options.quiet:
            print("Scanned %s files" % nfiles)
        if self.warnings:
            print()
            print("Warnings:")
        for msg in self.warnings:
            self._display_warning(msg)


def main():
    options, operations, paths = Patcher.parse_options()
    Patcher(operations, options).main(paths)

if __name__ == "__main__":
    main()
