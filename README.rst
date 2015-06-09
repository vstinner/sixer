Sixer
=====

sixer is a tool adding Python 3 support to a Python 2 project.

sixer was written to produces patches to port OpenStack to Python 3.

It uses basic regular expressions to find code which needs to be modified. It
emits warnings when code was not patched or looks suspicious.

* `sixer project at Github
  <https://github.com/haypo/sixer>`_
* `sixer in the Python Cheeseshop (PyPI)
  <https://pypi.python.org/pypi/sixer>`_


Usage
-----

::

    sixer.py <directory or filename> <operation>

sixer.py displays the name of patched files. It displays warnings for code
unchanged but which looks suspicious.

If you pass a directory, sixer.py searchs for ``.py`` files in all
subdirectories.

Warning: sixer.py modifies files inplace without asking for confirmation. It's
better to use it in a project managed by a source control manager (ex: git).

Available operations:

- all
- basestring
- iteritems
- iterkeys
- itervalues
- long
- next
- raise
- six_moves
- stringio
- unicode
- urllib
- xrange


Installation
------------

To install sixer, type::

    pip3 install sixer

sixer requires Python 3, it doesn't work on Python 2.


Operations
----------

- ``all``:

  * combine all operations all together

- ``basestring``:

  * replace ``basestring`` with ``six.string_types``

- ``iteritems``:

  * replace ``dict.iteritems()`` with ``six.iteritems(dict)``

- ``itervalues``:

  * replace ``dict.itervalues()`` with ``six.itervalues(dict)``

- ``iterkeys``:

  * replace ``dict.iterkeys()`` with ``six.iterkeys(dict)``
  * note: ``for key in dict.iterkeys():`` can usually be simplified to
    ``for key in dict:``

- ``long``:

  * replace ``123L`` with ``123``
  * octal number are unchanged (ex: ``010L``)

- ``next``:

  * replace ``iter.next()`` with ``next(iter)``

- ``raise``:

  * replace ``raise exc[0], exc[1], exc[2]``
    with ``six.reraise(*exc)``
  * replace ``raise exc_type, exc_value, exc_tb``
    with ``six.reraise(exc_type, exc_value, exc_tb)``
  * replace ``raise exc, msg``
    with ``raise exc(msg)``

- ``six_moves``:

  * replace Python 2 imports with imports from ``six.moves``
  * Python 2 modules:

    - BaseHTTPServer
    - ConfigParser
    - Cookie
    - HTMLParser
    - Queue
    - SimpleHTTPServer
    - SimpleXMLRPCServer
    - __builtin__
    - cookielib
    - htmlentitydefs
    - httplib
    - repr
    - xmlrpclib

- ``urllib``:

  * replace Python 2 urllib and urllib2 with ``six.moves.urllib``

- ``stringio``:

  * replace ``StringIO.StringIO`` with ``six.StringIO``
  * replace ``cStringIO.StringIO`` with ``moves.cStringIO``
  * replace ``from StringIO import StringIO`` with ``from six import StringIO``
  * replace ``from cStringIO import StringIO``
    with ``from six.moves import cStringIO as StringIO``
  * later you may have to replace it with ``six.BytesIO`` (or ``io.BytesIO``
    if you don't support Python 2.6) when bytes are expected on Python 3

- ``unicode``:

  * replace ``unicode`` with ``six.text_type``

- ``xrange``:

  * replace ``xrange()`` with ``range()`` and
    add ``from six.moves import range``
  * don't add the import if all ranges have 1024 items or less


Adding the six import
---------------------

When an operation uses ``six``, ``import six`` may be added. sixer repects
OpenStack coding style rules to add the import: imports grouped by standard
library, third party and local imports; and imports must be are sorted.

The sixer tool was initially written to produce patches for OpenStack which
respects OpenStack coding style, especially the complex rule to group and sort
imports.


Limitations
-----------

The project is based on regular expressions, it produces false positives
(invalid changes). For example, some operations replace patterns in strings,
comments or function names even if it doesn't make sense.

Try also the 2to6 project which may be more reliable.


Tests
-----

To run tests, type ``tox``. Type ``pip install tox`` to install the ``tox``
program.

Or run tests manually: type ``python3 tests.py``.


Changelog
---------

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


See also
--------

* `Six documentation <https://pythonhosted.org/six/>`_
* `2to6 <https://github.com/limodou/2to6>`_
* Python 3 porting book: `Language differences and workarounds
  <http://python3porting.com/differences.html>`_
* `getpython3 <http://getpython3.com/>`_

