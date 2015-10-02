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
    args = (sys.executable, SIXER, operation) + args
    proc = subprocess.Popen(args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    with proc:
        stdout, stderr = proc.communicate()
        exitcode = proc.wait()

    return (exitcode, os.fsdecode(stdout), os.fsdecode(stderr))


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
        app = kw.pop('app', None)

        patcher = sixer.Patcher((operation,))
        if app:
            patcher.application_modules.add(app)
        for attr, value in kw.items():
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
            app = kw.get('app')
            if app:
                args.append("--app=%s" % app)
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

    def test_raise2(self):
        self.check("raise",
            "raise Exception, 'message'",
            "raise Exception('message')")

    def test_raise3(self):
        self.check("raise",
            "raise a, b, c",
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
            max_range=5,
            # it's not possible to pass max_range=5 on the command line
            check_program=False)

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
            """
            import six


            for value in six.iterkeys(data): pass
            """)

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

        # octal numbers are unchanged
        self.check_unchanged("long",
            "values = (00L, 01L, 012L, 0123L, 01234L, 012345L)",
            warnings=["values = (00L, 01L, 012L, 0123L, 01234L, 012345L)"])

    def test_basestring(self):
        self.check("basestring",
            "isinstance(foo, basestring)",
            """
            import six


            isinstance(foo, six.string_types)
            """)

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

    def test_itertools(self):
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
            """,
            """
            try: func()
            except ValueError as exc: pass
            """)

        # except (ValueError, TypeError)
        self.check("except",
            """
            try: func()
            except (ValueError, TypeError), exc: pass
            """,
            """
            try: func()
            except (ValueError, TypeError) as exc: pass
            """)

        # except (ValueError, TypeError, KeyError)
        self.check("except",
            """
            try: func()
            except (ValueError, TypeError, KeyError), exc: pass
            """,
            """
            try: func()
            except (ValueError, TypeError, KeyError) as exc: pass
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
        expected = ("invalid operation: nonexistent\n"
                    "\n"
                    "Usage: sixer.py [options]")
        self.assertTrue(stdout.startswith(expected), stdout)

if __name__ == "__main__":
    unittest.main()
