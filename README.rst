Sixer
=====

sixer is a tool adding Python 3 support to a Python 2 project. It was written
to produces patches to port OpenStack to Python 3. It is focused on supporting
Python 2.7 and 3.4.

It uses basic regular expressions to find code which needs to be modified. It
emits warnings when code was not patched or looks suspicious.

* `sixer project at Github
  <https://github.com/haypo/sixer>`_ (source, bug tracker)
* `sixer in the Python Cheeseshop (PyPI)
  <https://pypi.python.org/pypi/sixer>`_

See also the `six module documentation <https://pythonhosted.org/six/>`_.


Usage
-----

::

    sixer.py [--write] [options] <all|operation1[,operation2,...]> <directories or filenames>

sixer.py displays the name of patched files. It displays warnings for
suspicious code which may have to be ported manually.

The first parameter can be a list of operations separated by commas. Use
``"all"`` to apply all operations. Operation prefixed by ``-`` are excluded.
For example, ``"all,-iteritems"`` applies all operations except ``iteritems``.

For directories, sixer.py searchs for ``.py`` files in all subdirectories.

By default, sixer uses a dry run: files are not modified. Add ``--write`` (or
``-w``) option to modify files in place. It's better to use sixer in a project
managed by a source control manager (ex: git) to see differences and revert
unwanted changes. The original files are not kept.

Use ``--help`` to see all available options.

See below for the list of available operations.


Operations
----------

- ``all``:

  * combine all operations all together

- ``basestring``:

  * replace ``basestring`` with ``six.string_types``,
    add ``import six``

- ``dict0``:

  * replace ``dict.keys()[0]`` with ``list(dict.keys())[0]``
  * same for ``dict.values()[0]`` and ``dict.items()[0]``

- ``dict_add``:

  * replace ``dict.keys() + list2`` with ``list(dict.keys()) + list2``
  * same for ``dict.values() + list2`` and ``dict.items() + list2``

- ``except``:

  * Replace ``except ValueError, exc:`` with ``except ValueError as exc:``
  * Replace ``except (TypeError, ValueError), exc:`` with
    ``except (TypeError, ValueError) as exc:``

- ``has_key``:

  * Replace ``dict.has_key(key)`` with ``key in dict``

- ``iteritems``:

  * replace ``dict.iteritems()`` with ``six.iteritems(dict)``,
    add ``import six``

- ``itervalues``:

  * replace ``dict.itervalues()`` with ``six.itervalues(dict)``,
    add ``import six``

- ``iterkeys``:

  * Replace ``for key in dict.iterkeys():`` with ``for key in dict:``
  * Replace ``dict.iterkeys()`` with ``six.iterkeys(dict)``,
    add ``import six``

- ``itertools``:

  * replace ``itertools.ifilter`` with ``six.moves.filter``,
    add ``import six``

  * similar change for ``ifilterfalse()``, ``imap()``, ``izip()`` and
    ``izip_longest()`` of the ``itertools`` module

- ``long``:

  * replace ``123L`` with ``123``
  * replace ``(int, long)`` with ``six.integer_types``
  * octal number are unchanged (ex: ``010L``)

- ``next``:

  * replace ``iter.next()`` with ``next(iter)``

- ``print``:

  * Replace ``print msg`` with ``print(msg)``
  * Replace ``print msg,`` with ``print(msg, end=' ')``
    and add ``from __future__ import print_function`` import
  * Replace ``print`` with ``print()``
    and add ``from __future__ import print_function`` import

- ``raise``:

  * replace ``raise exc[0], exc[1], exc[2]``
    with ``six.reraise(*exc)``, add ``import six``
  * replace ``raise exc_type, exc_value, exc_tb``
    with ``six.reraise(exc_type, exc_value, exc_tb)``, add ``import six``
  * replace ``raise exc, msg`` with ``raise exc(msg)``, add ``import six``

- ``six_moves``:

  * replace Python 2 imports with imports from ``six.moves``,
    add ``import six``. Python 2 modules:

    - ``BaseHTTPServer``
    - ``ConfigParser``
    - ``Cookie``
    - ``HTMLParser``
    - ``Queue``
    - ``SimpleHTTPServer``
    - ``SimpleXMLRPCServer``
    - ``__builtin__``
    - ``cPickle``
    - ``cookielib``
    - ``htmlentitydefs``
    - ``httplib``
    - ``repr``
    - ``xmlrpclib``

  * replace Python 2 functions with ``six.moves.<function>``,
    add ``import six``. Python 2 functions:

    - ``raw_input()``
    - ``reduce()``
    - ``reload()``

  * replace ``unichr()`` with ``six.unichr()``, add ``import six``

- ``urllib``:

  * replace Python 2 urllib and urllib2 with ``six.moves.urllib``,
    add ``import six``

- ``stringio``:

  * replace ``StringIO.StringIO`` with ``six.StringIO``,
    add ``import six``
  * replace ``cStringIO.StringIO`` with ``moves.cStringIO``,
    add ``from six import moves``
  * replace ``from StringIO import StringIO`` with ``from six import StringIO``
  * replace ``from cStringIO import StringIO``
    with ``from six.moves import cStringIO as StringIO``
  * later you may have to replace it with ``six.BytesIO`` (or ``io.BytesIO``
    if you don't support Python 2.6) when bytes are expected on Python 3

- ``unicode``:

  * replace ``unicode`` with ``six.text_type``, add ``import six``
  * replace ``(str, unicode)``  with ``six.string_types``, add ``import six``

- ``xrange``:

  * replace ``xrange()`` with ``range()`` and
    add ``from six.moves import range``
  * don't add the import if all ranges have 1024 items or less


Installation
------------

To install sixer, type::

    pip3 install sixer

sixer requires Python 3, it doesn't work on Python 2.


Adding the six import
---------------------

When an operation uses ``six``, ``import six`` may be added. sixer repects
OpenStack coding style rules to add the import: imports grouped by standard
library, third party and application imports; and imports must be are sorted.


Limitations
-----------

Since the project is implemented with regular expressions, it can produce false
positives (invalid changes). For example, some operations replace patterns in
strings, comments or function names even if it doesn't make sense.

Try also the 2to6 project which may be more reliable.


Tests
-----

To run tests, type ``tox``. Type ``pip install -U tox`` to install or update
the ``tox`` program.

Or run tests manually: type ``python3 tests.py``.


Resources to port code to Python 3
----------------------------------

* `six module documentation <https://pythonhosted.org/six/>`_
* `2to6 <https://github.com/limodou/2to6>`_
* `modernize <https://pypi.python.org/pypi/modernize>`_
* Python 3 porting book: `Language differences and workarounds
  <http://python3porting.com/differences.html>`_
* `getpython3 <http://getpython3.com/>`_


Changelog
---------

* Version 1.2

 - add ``print`` operation
 - add ``has_key`` operation: replace ``dict.has_key(key)``
   with ``key in dict``
 - ``long`` now also handles hexadecimal numbers. For example, ``0xffL`` is
   replaced with ``0xff``.
 - ``except`` now handles also exception with dots
   (ex: ``except select.error, exc:``)
 - ``iterkeys`` now replaces ``for key in dict.iterkeys():`` with
   ``for key in dict:`` to avoid the usage of six.

* Version 1.1 (2015-10-22)

 - add ``--third-party`` command line option
 - emit a warning instead of failing with an error if we failed to find the
   best place to add an import
 - fix also code to detect third-party modules, don't check for the prefix
   but the full name (ex: "numpypy" is not detected as third-party if only
   "numpy" is known)

* Version 1.0 (2015-10-16)

 - sixer doesn't modify files by default anymore. Add ``--write`` to really
   modify files inplace.
 - ``long`` operation now also replaces ``(int, long)`` with
   ``six.integer_types``
 - ``itertools`` now also replaces ``ifilterfalse()``, ``izip()`` and
   ``izip_longest()`` of the ``itertools`` module
 - ``six_moves`` now also replaces ``unichr(ch)`` with ``six.unichr(ch)``
 - command line: it's now possible to exclude an operation using ``-`` prefix.
   For example, ``all,-iteritems`` applies all operations except
   ``iteritems``.

* Version 0.8 (2015-10-03)

 - urllib now emits a warning on unknown symbol, instead of raising an
   exception
 - Write warnings to stderr instead of stdout and exit with error code 1
   if a filename doesn't exist or a directory doesn't contain any .py file
 - ``unicode`` operation also replaces ``(str, unicode)`` with
   ``six.string_types``
 - When removing an import, don't remove the empty line following the import
   if the empty line is followed by a second import
 - ``long`` also replaces ``1l`` (lower case L suffix for long numbers)

* Version 0.7 (2015-09-29)

 - Add new ``dict0``, ``dict_add`` and ``except`` operations
 - Add --app command line option to specify the Python module of the
   application, to help sorting imports
 - Code adding new imports respect better OpenStack coding style on imports.
   For example, it adds two empty lines after imports, instead of a single
   line.
 - Display the name of the operation which modified files
 - Display also the name of the operation in warnings
 - ``six_moves`` now also patches ``reduce()`` and ``reload()``. For example,
   ``reduce()`` is replaced with ``six.moves.reduce()``.
 - ``six_moves`` now also patches ``mock.patch()``. For example,
   ``with mock.patch('__builtin__.open'): ...`` is replaced with
   ``with mock.patch('six.moves.builtin.open'): ...``
 - ``urllib`` now also replaces ``from ... import ...`` imports.
   For example, ``from urllib import quote`` is replaced with
   ``from six.moves.urllib.parse import quote``.

* Version 0.6 (2015-09-11)

 - Add "itertools" operation
 - Fix xrange() regex to not modify "from six.moves import xrange" and
   "moves.xrange(n)"
 - Fix urllib for urllib or urlparse module get from the urllib2 module.
   For example, ``urllib2.urlparse.urlparse`` (``import urllib2``) is now
   replaced with ``urllib.parse.urlparse`` (``from six.moves import urllib``).

* Version 0.5 (2015-07-08)

 - six_moves: support "import module as name" syntax and add cPickle module
 - Add --to-stdout, --quiet and --max-range command line options
 - Emit a warning if the directory does not contain any .py file or
   if the path does not exist
 - Test also directly the sixer.py program

* Version 0.4 (2015-06-09)

 - sixer.py now accepts multiple filenames on the command line, but
   operations becomes the first command line parameter
 - the ``stringio`` operation now also replaces cStringIO and
   ``from StringIO import StringIO``
 - urllib: replace also urlparse.symbol
 - six_moves: support more modules: Cookie, HTMLParser, SimpleHTTPServer,
   cookielib, xmlrpclib, etc.
 - Refactor operations as classes to cleanup the code

* Version 0.3.1 (2015-05-27)

 - Fix the "all" operation
 - six_moves knows more modules
 - urllib: add pathname2url, don't touch urllib2.parse_http_list()

* Version 0.3 (2015-05-27)

 - First command line parameter can now be a filename
 - Add "all", "basestring", "iterkeys", "six_moves", "stringio"
   and "urllib" operations
 - Enhance the knownledge tables for modules (stdlib, third parties,
   applications)
 - Ignore unparsable import lines when adding an import

* Version 0.2 (2015-05-12):

 - First public release

