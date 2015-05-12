#!/usr/bin/env python3
import contextlib
import six
import sixer
import sys
import tempfile
import textwrap
import unittest


@contextlib.contextmanager
def replace_stdout():
    old_stdout = sys.stdout
    try:
        buffer = six.StringIO()
        sys.stdout = buffer
        yield buffer
    finally:
        sys.stdout = old_stdout


class TestOperations(unittest.TestCase):
    # FIXME: test Patcher.walk

    def setUp(self):
        self.patcher = sixer.Patcher('.', "unset")

    def check(self, operation, before, after):
        self.patcher.operation = operation
        with tempfile.NamedTemporaryFile("w+") as temp:
            temp.write(before.strip())
            temp.flush()
            with replace_stdout():
                self.patcher.patch(temp.name)
            temp.seek(0)
            code = temp.read()

        self.assertEqual(code, textwrap.dedent(after).strip())

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

        self.patcher.max_range = 5
        self.check("xrange",
            "for i in xrange(10): pass",
            """
            from six.moves import range

            for i in range(10): pass
            """)

    def test_unicode(self):
        self.check("unicode",
            "value = unicode(data)",
            """
            import six

            value = six.text_type(data)
            """)

    def test_iteritems(self):
        self.check("iteritems",
            "for key, value in data.iteritems(): pass",
            """
            import six

            for key, value in six.iteritems(data): pass
            """)

    def test_itervalues(self):
        self.check("itervalues",
            "for value in data.itervalues(): pass",
            """
            import six

            for value in six.itervalues(data): pass
            """)

    def test_next(self):
        self.check("next",
            "item = gen.next()",
            "item = next(gen)")

    def test_long(self):
        self.check("long",
            "values = (0L, 1L, 12L, 123L, 1234L, 12345L)",
            "values = (0, 1, 12, 123, 1234, 12345)")


if __name__ == "__main__":
    unittest.main()
