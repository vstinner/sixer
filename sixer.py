#!/usr/bin/env python3
import os
import re
import sys
import tokenize

# Maximum range which creates a list on Python 2. For example, xrange(10) can
# be replaced with range(10) without "from six.moves import range".
MAX_RANGE = 1024

OPERATIONS = ("all", "iteritems", "itervalues", "iterkeys", "next",
              "long", "unicode", "raise", "xrange",
              "basestring")

# Modules of the Python standard library
STDLIB_MODULES = ("copy", "re", "sys", "unittest", "heapq", "glob", "os")

# Name prefix of third-party modules (ex: "oslo" matches "osloconfig"
# and "oslo.db")
THIRD_PARTY_MODULES = ("oslo", "webob", "subunit", "testtools")

# Modules of the application
APPLICATION_MODULES = ("nova", "ceilometer", "glance", "neutron", "cinder")

# Ugly regular expressions because I'm too lazy to write a real parser,
# and Match Object are convinient to modify code in-place

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
        raise Exception("unable to parse import %r" % line)


def get_line(content, pos):
    eol = content.find("\n", pos)
    return content[pos:eol + 1]


class Patcher(object):
    def __init__(self, directory, operation):
        self.directory = directory
        self.operation = operation
        self.warnings = []
        self.current_file = None
        self.max_range = MAX_RANGE

    def walk(self):
        for dirpath, dirnames, filenames in os.walk(self.directory):
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
            return import_line + '\n\n' + content

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
            if not line.startswith("#"):
                names = parse_import(line)
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

    def patch_all(self, content):
        modified = False
        for operation in OPERATIONS:
            if operation == 'all':
                continue
            patcher = getattr(self, "patch_" + operation)
            op_modified, content = patcher(content)
            modified |= op_modified
        return modified, content

    def check_all(self, content):
        for operation in OPERATIONS:
            if operation == 'all':
                continue
            checker = getattr(self, "check_" + operation)
            checker(content)

    def patch(self, filename):
        self.current_file = filename

        with tokenize.open(filename) as fp:
            content = fp.read()

        checker = getattr(self, "check_" + self.operation)
        patcher = getattr(self, "patch_" + self.operation)

        modified, content = patcher(content)
        if not modified:
            checker(content)
            return False

        with open(filename, "rb") as fp:
            encoding, _ = tokenize.detect_encoding(fp.readline)

        print("Patch %s" % filename)
        with open(filename, "w", encoding=encoding) as fp:
            fp.write(content)
        checker(content)
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
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        usage()
    dir = sys.argv[1]
    operation = sys.argv[2]
    if operation not in OPERATIONS:
        print("invalid operation: %s" % operation)
        print()
        usage()

    Patcher(dir, operation).main()

if __name__ == "__main__":
    main()
