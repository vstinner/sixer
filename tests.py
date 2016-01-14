#!/usr/bin/env python3
import contextlib
import io
import os
import shutil
import sixer
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest


SIXER = os.path.join(os.path.dirname(__file__), "sixer.py")


@contextlib.contextmanager
def replace_stream(attr):
    old_stream = getattr(sys, attr)
    try:
        stream = io.StringIO()
        setattr(sys, attr, stream)
        yield stream
    finally:
        setattr(sys, attr, old_stream)


def run_sixer(operation, *args):
    args = (sys.executable, SIXER, '--write', operation) + args
    proc = subprocess.Popen(args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    with proc:
        stdout, stderr = proc.communicate()
        exitcode = proc.wait()

    return (exitcode, os.fsdecode(stdout), os.fsdecode(stderr))


def mock_options(kw):
    options = types.SimpleNamespace()
    options.max_range = kw.pop('max_range', sixer.MAX_RANGE)
    options.to_stdout = False
    options.quiet = False
    options.app = kw.pop('app', None)
    options.third_party = kw.pop('third_party', None)
    options.write = True
    return options


class AddImportTests(unittest.TestCase):
    def check(self, line, before, after, **kw):
        # Keywords: app=None
        before = textwrap.dedent(before).strip() + "\n"
        after = textwrap.dedent(after).strip() + "\n"

        options = mock_options(kw)
        patcher = sixer.Patcher(('print',), options)
        output = patcher.add_import(before, line)

        self.assertEqual(output, after)

    def check_unchanged(self, line, code):
        self.check(line, code, code)

    def test_exiting(self):
        self.check_unchanged('import six', """
            import six  # comment

            code
        """)

        self.check_unchanged('import six', """
            import six

            code
        """)

        self.check_unchanged('from __future__ import print_function', """
            from __future__ import print_function

            code
        """)



    def test_add_import_six(self):
        # no import before
        self.check('import six', """
            code
        """, """
            import six


            code
        """)

        # add to existing group, before existing import
        self.check('import numpy', """
            import six

            code
        """, """
            import numpy
            import six

            code
        """)

        # add to existing group, after existing import
        self.check('import six', """
            import numpy

            code
        """, """
            import numpy
            import six

            code
        """)

        # add new future group before
        self.check('import six', """
            import app

            code
        """, """
            import six

            import app

            code
        """, app='app')


    def test_add_future(self):
        # no import before
        self.check('from __future__ import print_function', """
            code
        """, """
            from __future__ import print_function


            code
        """)

        # add to existing group, before existing import
        self.check('from __future__ import absolute_import', """
            from __future__ import print_function

            code
        """, """
            from __future__ import absolute_import
            from __future__ import print_function

            code
        """)

        # add to existing group, after existing import
        self.check('from __future__ import print_function', """
            from __future__ import absolute_import

            code
        """, """
            from __future__ import absolute_import
            from __future__ import print_function

            code
        """)

        # add new future group before
        self.check('from __future__ import print_function', """
            import sys

            code
        """, """
            from __future__ import print_function

            import sys

            code
        """)


class TestUtils(unittest.TestCase):
    def test_parse_import_groups(self):
        self.assertEqual(sixer.parse_import_groups('import sys\n\nimport six\n'),
                         [(0, 12, {'sys'}), (12, 23, {'six'})])
        self.assertEqual(sixer.parse_import_groups('import sys\n\nimport six\n\nimport nova\n'),
                         [(0, 12, {'sys'}), (12, 24, {'six'}), (24, 36, {'nova'})])
        self.assertEqual(sixer.parse_import_groups('import a\nimport b\nimport c\n'),
                         [(0, 27, {'a', 'b', 'c'})])


class TestOperations(unittest.TestCase):
    def _check(self, operation, before, after, **kw):
        warnings = kw.pop('warnings', None)
        ignore_warnings = kw.pop('ignore_warnings', False)

        options = mock_options(kw)
        patcher = sixer.Patcher((operation,), options)
        for attr, value in kw.items():
            raise ValueError("%r:%r" % (attr, value))
            setattr(patcher.options, attr, value)

        with tempfile.NamedTemporaryFile("w+") as temp:
            temp.write(before)
            temp.flush()
            with replace_stream('stdout'), replace_stream('stderr'):
                patcher.patch(temp.name)
            temp.seek(0)
            code = temp.read()

        self.assertEqual(code, after)
        if not ignore_warnings:
            if warnings:
                self.assertEqual(len(patcher.warnings), len(warnings))
                for index, expected in enumerate(warnings):
                    msg = patcher.warnings[index].split(": ", 1)[1]
                    self.assertEqual(msg, expected)
            else:
                self.assertEqual(patcher.warnings, [])

    def check_program(self, operation, before, after, *args):
        with tempfile.NamedTemporaryFile("w+") as tmp:
            tmp.write(before)
            tmp.flush()

            args = args + (tmp.name,)
            exitcode, stdout, stderr = run_sixer(operation, *args)
            self.assertEqual(exitcode, 0)
            #self.assertEqual(stderr, '')

            tmp.seek(0)
            code = tmp.read()

        self.assertEqual(code, after)

    def check(self, operation, before, after, **kw):
        before = textwrap.dedent(before).strip() + "\n"
        after = textwrap.dedent(after).strip() + "\n"
        check_program = kw.pop('check_program', True)

        # Ensure that the code is patched as expected
        self._check(operation, before, after, **kw)

        # Ensure that after is not modified by fixer
        self._check(operation, after, after, ignore_warnings=True)

        # Test command line
        if check_program:
            args = []
            for key, arg_format in (
                ('app', '--app=%s'),
                ('third_party', '--third-party=%s'),
                ('max_range', '--max-range=%s'),
            ):
                arg = kw.get(key)
                if arg:
                    args.append(arg_format % arg)
            self.check_program(operation, before, after, *args)

    def check_unchanged(self, operation, code, **kw):
        self.check(operation, code, code, **kw)

    def test_add_import(self):
        # import ...
        self.check("urllib",
            """
            import StringIO
            import urllib2

            import cue.tests.functional.fixtures.base as base

            urllib2.urlopen(url)
            """,
            """
            import StringIO

            from six.moves import urllib

            import cue.tests.functional.fixtures.base as base

            urllib.request.urlopen(url)
            """,
            app="cue")

        # from ... import ...
        self.check("urllib",
            """
            import StringIO
            from urllib2 import urlopen

            import cue.tests.functional.fixtures.base as base
            """,
            """
            import StringIO

            from six.moves.urllib.request import urlopen

            import cue.tests.functional.fixtures.base as base
            """,
            app="cue")

        # unable to find the best place
        self.check("unicode",
            """
            import numpypy

            unicode
            """,
            """
            import numpypy

            import six


            six.text_type
            """,
            warnings=["Failed to find the best place to add 'import six': "
                      "put it at the end. Use --app and --third-party "
                      "options."])

        # test third-party option
        self.check("unicode",
            """
            import numpypy

            unicode
            """,
            """
            import numpypy
            import six

            six.text_type
            """,
            third_party="xyz,numpypy")

    def test_raise2(self):
        self.check("raise",
            "raise Exception, 'message'",
            "raise Exception('message')")

        # no space after comma
        self.check("raise",
            "raise Exception,'message'",
            "raise Exception('message')")

    def test_raise3(self):
        self.check("raise",
            "raise a, b, c",
            """
            import six


            six.reraise(a, b, c)
            """)

        # no space after comma
        self.check("raise",
            "raise a,b,c",
            """
            import six


            six.reraise(a, b, c)
            """)

    def test_reraise(self):
        self.check("raise",
            "raise exc[0], exc[1], exc[2]",
            """
            import six


            six.reraise(*exc)
            """)

    def test_xrange(self):
        self.check("xrange",
            "for i in xrange(10): pass",
            "for i in range(10): pass")

        self.check("xrange",
            "for i in xrange(n): pass",
            """
            from six.moves import range


            for i in range(n): pass
            """)

        self.check("xrange",
            "for i in xrange(10): pass",
            """
            from six.moves import range


            for i in range(10): pass
            """,
            max_range=5)

        self.check_unchanged("xrange",
            "from six.moves import xrange")

        self.check_unchanged("xrange",
            """
            from six import moves


            x = list(moves.xrange(n))
            x = list(moves.xrange(5))
            x = list(moves.xrange(1, 9))
            x = list(moves.xrange(0, 10, 2))
            """)


    def test_unicode(self):
        self.check("unicode",
            "value = unicode(data)",
            """
            import six


            value = six.text_type(data)
            """)

        self.check("unicode",
            """
            isinstance('hello', (str,unicode))
            isinstance('hello', (str, unicode))
            """,
            """
            import six


            isinstance('hello', six.string_types)
            isinstance('hello', six.string_types)
            """)

    def test_add_six_import(self):
        # only stdlib
        self.check("unicode",
            """
            import copy

            t = unicode
            """,
            """
            import copy

            import six


            t = six.text_type
            """)

        # only third party
        self.check("unicode",
            """
            import oslo_utils

            t = unicode
            """,
            """
            import oslo_utils
            import six

            t = six.text_type
            """)

        # stdlib+third party
        self.check("unicode",
            """
            import copy

            import oslo_utils

            t = unicode
            """,
            """
            import copy

            import oslo_utils
            import six

            t = six.text_type
            """)

        # only application
        self.check("unicode",
            """
            import nova

            t = unicode
            """,
            """
            import six

            import nova

            t = six.text_type
            """)

    def test_unicode_unchanged(self):
        self.check_unchanged("unicode",
            """
            import unicodedata

            # unicode in comments

            def test_unicode():
                pass
            """)

    def test_iteritems(self):
        self.check("iteritems",
            "for key, value in data.iteritems(): pass",
            """
            import six


            for key, value in six.iteritems(data): pass
            """)

    def test_iteritems_expr(self):
        self.check("iteritems",
            """
            items = obj.data[0].attr.iteritems()
            """,
            """
            import six


            items = six.iteritems(obj.data[0].attr)
            """)

    def test_itervalues(self):
        self.check("itervalues",
            "for value in data.itervalues(): pass",
            """
            import six


            for value in six.itervalues(data): pass
            """)

    def test_iterkeys(self):
        self.check("iterkeys",
            "for value in data.iterkeys(): pass",
            "for value in data: pass")

        self.check("iterkeys",
            "keys = data.iterkeys()",
            """
            import six


            keys = six.iterkeys(data)
            """)

    def test_has_key(self):
        self.check("has_key",
            "dict.has_key(key)",
            "key in dict")

    def test_next(self):
        self.check("next",
            "item = gen.next()",
            "item = next(gen)")

        self.check("next",
            "item = (x+1 for x in data).next()",
            "item = next(x+1 for x in data)")

        self.check("next",
            "item = ((x * 2) for x in data).next()",
            "item = next((x * 2) for x in data)")

    def test_long(self):
        self.check("long",
            "values = (0L, 1L, 12L, 123L, 1234L, 12345L)",
            "values = (0, 1, 12, 123, 1234, 12345)")

        # lower case
        self.check("long",
            "x = 1l",
            "x = 1")

        # hexadecimal
        self.check("long",
            "values = (0x1L, 0x1l, 0xfL, 0x0L)",
            "values = (0x1, 0x1, 0xf, 0x0)")

        # octal
        self.check("long",
            "values = (00L, 000L, 01L, 012L, 0123L, 01234L, 012345L)",
            "values = (0o0, 0o00, 0o1, 0o12, 0o123, 0o1234, 0o12345)")

        # (int, long)
        self.check("long",
            "isinstance(s, (int, long))",
            """
            import six


            isinstance(s, six.integer_types)
            """)

    def test_basestring(self):
        self.check("basestring",
            "isinstance(foo, basestring)",
            """
            import six


            isinstance(foo, six.string_types)
            """)

    def test_octal(self):
        self.check("octal",
            "values = (0123, 00456)",
            "values = (0o123, 0o0456)")

        self.check_unchanged("octal",
            "values = (0, 123, 123L)")

        # zero
        self.check("octal",
            "values = (00, 000, 0000, 00000)",
            "values = (0o0, 0o00, 0o000, 0o0000)")

        # one
        self.check("octal",
            "values = (01, 001, 0001, 00001)",
            "values = (0o1, 0o01, 0o001, 0o0001)")

    def test_six_moves_import(self):
        self.check("six_moves",
            """
            import __builtin__

            __builtin__.open()
            """,
            """
            from six.moves import builtins


            builtins.open()
            """)

        self.check("six_moves",
            """
            import cPickle as pickle

            pickle
            """,
            """
            from six.moves import cPickle as pickle


            pickle
            """)

    def test_six_moves_from_import(self):
        self.check("six_moves",
            """
            from __builtin__ import len, open

            len([])
            """,
            """
            from six.moves.builtins import len, open


            len([])
            """)

    def test_six_moves_builtin(self):
        # patch reload
        self.check("six_moves",
            """
            import sys
            reload(sys)
            """,
            """
            import sys

            from six.moves import reload_module


            reload_module(sys)
            """)

        # patch reduce
        self.check("six_moves",
            """
            reduce(lambda x, y: x*10+y, [1, 2, 3])
            """,
            """
            from six.moves import reduce


            reduce(lambda x, y: x*10+y, [1, 2, 3])
            """)

        # patch reload, don't patch reduce
        self.check("six_moves",
            """
            import sys

            from six.moves import reduce


            print(reduce(lambda x, y: x*10+y, [1, 2, 3]))
            reload(sys)
            """,
            """
            import sys

            from six.moves import reduce
            from six.moves import reload_module


            print(reduce(lambda x, y: x*10+y, [1, 2, 3]))
            reload_module(sys)
            """)

        # don't touch moves.reduce()
        self.check_unchanged("six_moves",
            """
            from six import moves


            print(moves.reduce(lambda x, y: x*10+y, [1, 2, 3]))
            """)

    def test_six_moves_mock_patch(self):
        # mock.patch()
        self.check("six_moves",
            "with mock.patch('__builtin__.open'): pass",
            "with mock.patch('six.moves.builtins.open'): pass")

        # patch()
        self.check("six_moves",
            "with patch('__builtin__.open'): pass",
            "with patch('six.moves.builtins.open'): pass")

    def test_six_moves_functions(self):
        # unichr()
        self.check("six_moves",
            "print(unichr(0x20ac))",
            """
            import six


            print(six.unichr(0x20ac))
            """)

    def test_stringio(self):
        # import StringIO
        self.check("stringio",
            """
            import StringIO

            s = StringIO.StringIO()
            """,
            """
            import six


            s = six.StringIO()
            """)

        # from StringIO import StringIO
        self.check("stringio",
            """
            from StringIO import StringIO

            s = StringIO()
            """,
            """
            from six import StringIO


            s = StringIO()
            """)

        # import cStringIO
        self.check("stringio",
            """
            import cStringIO

            s = cStringIO.StringIO()
            """,
            """
            from six import moves


            s = moves.cStringIO()
            """)

        # import cStringIO as StringIO
        self.check("stringio",
            """
            import cStringIO as StringIO

            s = StringIO.StringIO()
            """,
            """
            from six import moves


            s = moves.cStringIO()
            """)

        # from cStringIO import StringIO
        self.check("stringio",
            """
            from cStringIO import StringIO

            s = StringIO()
            """,
            """
            from six.moves import cStringIO as StringIO


            s = StringIO()
            """)

    def test_urllib_import(self):
        # urllib.urlopen
        self.check("urllib",
            """
            import urllib

            urllib.urlopen(url)
            """,
            """
            from six.moves import urllib


            urllib.request.urlopen(url)
            """)

        # urllib2.urlopen, urllib2.URLError
        self.check("urllib",
            """
            import urllib2

            try:
                urllib2.urlopen(url)
            except urllib2.URLError as exc:
                pass
            """,
            """
            from six.moves import urllib


            try:
                urllib.request.urlopen(url)
            except urllib.error.URLError as exc:
                pass
            """)

        # urllib2.urlparse.urlparse
        self.check("urllib",
            """
            import urllib2

            urllib2.urlparse.urlparse('')
            """,
            """
            from six.moves import urllib


            urllib.parse.urlparse('')
            """)

        # urlparse
        self.check("urllib",
            """
            import urlparse

            urlparse.urlparse(uri)
            """,
            """
            from six.moves import urllib


            urllib.parse.urlparse(uri)
            """)

        # don't touch parse_http_list
        self.check_unchanged("urllib",
            """
            urllib2.parse_http_list()
            """,
            warnings=['urllib2.parse_http_list()'])

    def test_urllib_from_import(self):
        self.check("urllib",
            """
            from urllib import quote, urlopen
            from urllib2 import urlopen, URLError

            quote("abc")
            """,
            """
            from six.moves.urllib.error import URLError
            from six.moves.urllib.parse import quote
            from six.moves.urllib.request import urlopen


            quote("abc")
            """)

        self.check("urllib",
            """
            import sys
            from urllib import quote

            quote("abc")
            """,
            """
            import sys

            from six.moves.urllib.parse import quote


            quote("abc")
            """)

    def test_urllib_unknown_symbol(self):
        self.check("urllib",
            """
            import urllib2

            # urllib2.open
            urllib2.urlopen(url)
            """,
            """
            from six.moves import urllib


            # urllib2.open
            urllib.request.urlopen(url)
            """,
            warnings=['Unknown urllib symbol: urllib2.open'])

    def test_all(self):
        self.check("all",
            """
            values = (0L, 1L, 12L, 123L, 1234L, 12345L)

            for i in xrange(10): pass
            """,
            """
            values = (0, 1, 12, 123, 1234, 12345)

            for i in range(10): pass
            """)

    def test_itertools_from_import(self):
        self.check("itertools",
            """
            from itertools import imap

            for x in imap(str.upper, "abc"):
                print(x)
            """,
            """
            import six


            for x in six.moves.map(str.upper, "abc"):
                print(x)
            """)

        self.check("itertools",
            """
            from itertools import izip

            for x, y in izip(range(3), "abc"):
                print(x, y)
            """,
            """
            import six


            for x, y in six.moves.zip(range(3), "abc"):
                print(x, y)
            """)

    def test_itertools_import(self):
        self.check("itertools",
            """
            import itertools

            for x in itertools.ifilter(str.upper, "abc"):
                print(x)
            """,
            """
            import six


            for x in six.moves.filter(str.upper, "abc"):
                print(x)
            """)

        self.check("itertools",
            """
            import itertools

            for x in itertools.imap(str.upper, "abc"):
                print(x)

            x = itertools.chain
            """,
            """
            import itertools

            import six


            for x in six.moves.map(str.upper, "abc"):
                print(x)

            x = itertools.chain
            """)

    def test_dict0(self):
        self.check("dict0",
            """
            x = {1: 2}
            first_key = x.keys()[0]
            first_value = x.values()[0]
            first_item = x.items()[0]
            """,
            """
            x = {1: 2}
            first_key = list(x.keys())[0]
            first_value = list(x.values())[0]
            first_item = list(x.items())[0]
            """)

    def test_dict_add(self):
        self.check("dict_add",
            """
            x = {1: 2}
            keys = x.keys() + [3]
            values = x.values() + [4]
            items = x.items() + [5]
            """,
            """
            x = {1: 2}
            keys = list(x.keys()) + [3]
            values = list(x.values()) + [4]
            items = list(x.items()) + [5]
            """)

    def test_except(self):
        # except ValueError
        self.check("except",
            """
            try: func()
            except ValueError, exc: pass

            # no space
            try: func()
            except TypeError,exc:pass
            """,
            """
            try: func()
            except ValueError as exc: pass

            # no space
            try: func()
            except TypeError as exc:pass
            """)

        # except (ValueError, TypeError)
        self.check("except",
            """
            try: func()
            except (ValueError, TypeError), exc: pass

            # no space
            try: func()
            except (ValueError,TypeError),exc:pass
            """,
            """
            try: func()
            except (ValueError, TypeError) as exc: pass

            # no space
            try: func()
            except (ValueError,TypeError) as exc:pass
            """)

        # except (ValueError, TypeError, KeyError)
        self.check("except",
            """
            try: func()
            except (ValueError, TypeError, KeyError), exc: pass

            # no space
            try: func()
            except (ValueError,TypeError,KeyError),exc:pass
            """,
            """
            try: func()
            except (ValueError, TypeError, KeyError) as exc: pass

            # no space
            try: func()
            except (ValueError,TypeError,KeyError) as exc:pass
            """)

        # except select.error
        self.check("except",
            """
            try: func()
            except select.error, exc: pass
            """,
            """
            try: func()
            except select.error as exc: pass
            """)

    def test_print(self):
        # print
        self.check("print",
            """
            print
            print#comment
            print # comment
            """,
            """
            from __future__ import print_function


            print()
            print()#comment
            print() # comment
            """)

        # print msg
        self.check("print",
            """
            print "hello"
            print 'hello'
            print msg
            print  msg
            print   msg
            """,
            """
            print("hello")
            print('hello')
            print(msg)
            print (msg)
            print  (msg)
            """)

        # test STRING_REGEX
        self.check("print",
            r"""
            print "tab\tnewline\n>\"<"
            print 'tab\tnewline\n>\'<'
            """,
            r"""
            print("tab\tnewline\n>\"<")
            print('tab\tnewline\n>\'<')
            """)

        # print msg,
        self.check("print",
            """
            import sys

            print "hello",
            print  "hello",
            print   "hello",
            """,
            """
            from __future__ import print_function

            import sys

            print("hello", end=' ')
            print ("hello", end=' ')
            print  ("hello", end=' ')
            """)

        # print arg1,arg2
        self.check_unchanged("print",
            'print "note",note',
            warnings=['print "note",note'])

    def check_print_into(self, before, after):
        self.check("print", '''
            import sys

            %s
        ''' % before, '''
            from __future__ import print_function

            import sys

            %s
        ''' % after)

    def test_print_into(self):
        self.check_print_into('print >>sys.stderr, "hello"',
                              'print("hello", file=sys.stderr)')

        # no space
        self.check_print_into('print>>sys.stderr,"hello"',
                              'print("hello", file=sys.stderr)')

        # 2 spaces before >>
        self.check_print_into('print  >>sys.stderr, "hello"',
                              'print ("hello", file=sys.stderr)')

        # 3 spaces before >>
        self.check_print_into('print   >>sys.stderr, "hello"',
                              'print  ("hello", file=sys.stderr)')

    def test_string(self):
        # upper/lower case
        self.check("string",
            """
            import string

            x = string.lower("ABC")
            x = string.upper("abc")
            x = string.swapcase("ABCdef")
            """,
            """
            x = "ABC".lower()
            x = "abc".upper()
            x = "ABCdef".swapcase()
            """)

        # strip, split
        self.check("string",
            """
            import string

            x = string.strip(" abc ")
            x = string.lstrip(" abc ")
            x = string.rstrip(" abc ")

            x = string.strip(" def ", ' ')
            x = string.lstrip(" def ", ' ')
            x = string.rstrip(" def ", ' ')
            """,
            """
            x = " abc ".strip()
            x = " abc ".lstrip()
            x = " abc ".rstrip()

            x = " def ".strip(' ')
            x = " def ".lstrip(' ')
            x = " def ".rstrip(' ')
            """)

        # string.atoX()
        self.check("string",
            """
            import string

            x = string.atof("1.0")
            x = string.atoi("123")
            x = string.atol("123")
            """,
            """
            x = float("1.0")
            x = int("123")
            x = int("123")
            """)


class TestProgram(unittest.TestCase):
    def run_sixer(self, scanned, *paths):
        exitcode, stdout, stderr = run_sixer("all", *paths)
        self.assertEqual(exitcode, 0)
        msg = 'Scanned %s files\n' % scanned
        self.assertIn(msg, stdout)
        self.assertEqual(stderr, '')
        return stdout

    def test_patch_file(self):
        with tempfile.NamedTemporaryFile("w+", encoding="ASCII") as tmp:
            tmp.write("x = 1L\n")
            tmp.flush()

            stdout = self.run_sixer(1, tmp.name)

            tmp.seek(0)
            code = tmp.read()
            self.assertEqual(code, "x = 1\n")

    def test_patch_dir(self):
        files = []
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path)

        filename = os.path.join(path, "file1.py")
        with open(filename, "w", encoding="ASCII") as f:
            f.write("x = 1L\n")
        files.append((filename, "x = 1\n"))

        filename = os.path.join(path, "file2.py")
        with open(filename, "w", encoding="ASCII") as f:
            f.write("unicode\n")
        files.append((filename, "import six\n\n\nsix.text_type\n"))

        stdout = self.run_sixer(2, path)

        for filename, after in files:
            with open(filename, encoding="ASCII") as f:
                code = f.read()

            self.assertEqual(code, after, "file=%r" % filename)

    def test_empty_dir(self):
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path)

        exitcode, stdout, stderr = run_sixer("all", path)
        self.assertEqual(exitcode, 1)
        self.assertIn('Scanned 0 files\n', stdout)
        msg = "WARNING: Directory %s doesn't contain any .py file\n" % path
        self.assertIn(msg, stderr)

    def test_nonexistent_path(self):
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path)

        filename = os.path.join(path, 'nonexistent')
        exitcode, stdout, stderr = run_sixer("all", filename)
        self.assertEqual(exitcode, 1)
        self.assertIn('Scanned 0 files\n', stdout)

        msg = ("WARNING: Path %s doesn't exist\n"
               % filename)
        self.assertIn(msg, stderr)

    def test_nonexistent_operation(self):
        with tempfile.NamedTemporaryFile("w+", encoding="ASCII") as tmp:
            tmp.write("x = 1L\n")
            tmp.flush()

            exitcode, stdout, stderr = run_sixer("nonexistent", tmp.name)

        self.assertEqual(exitcode, 1)
        self.assertEqual(stderr, '')
        expected = ("invalid operation: 'nonexistent'\n"
                    "\n"
                    "Usage: sixer.py [options]")
        self.assertTrue(stdout.startswith(expected), stdout)

if __name__ == "__main__":
    unittest.main()
