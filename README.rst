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

    sixer.py <directory> <operation>

sixer.py displays the name of patched files. It displays warnings for code
unchanged but which looks suspicious.

Warning: sixer.py modifies files inplace without asking for confirmation.  It's
better to use it in a project managed by a source control manager (ex: git).

Available operations:

- iteritems
- itervalues
- long
- next
- raise
- unicode
- xrange


Installation
------------

To install sixer, type::

    pip install sixer

sixer requires Python 3, it doesn't work on Python 2.


Operations
----------

- ``iteritems``:

  * replace ``dict.iteritems()`` with ``six.iteritems(dict)``

- ``itervalues``:

  * replace ``dict.itervalues()`` with ``six.itervalues(dict)``

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

- ``unicode``:

  * replace ``unicode`` with ``six.text_type``

- ``xrange``:

  * replace ``xrange()`` with ``range()`` and
    add ``from six.moves import range``


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

* 2015-05-12: Version 0.2, first public release


See also
--------

* `Six documentation <https://pythonhosted.org/six/>`_
* `2to6 <https://github.com/limodou/2to6>`_
* Python 3 porting book: `Language differences and workarounds
  <http://python3porting.com/differences.html>`_
* `getpython3 <http://getpython3.com/>`_

