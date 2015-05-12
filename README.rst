Sixer
=====

Program to add Python 3 support for a Python 2 project written for OpenStack.

Use basic regular expressions to find code which needs to be modified. Emit
warnings when code was not patched or looks suspicious.

Homepage: https://github.com/haypo/sixer

Operations
----------

- ``iteritems``:

  * replace ``dict.iteritems()`` with ``six.iteritems(dict)``

- ``itervalues``:

  * replace ``dict.itervalues()`` with ``six.itervalues(dict)``

- ``long``:

  * replace ``123L`` with ``123``
  * replace ``010`` with ``0o10``

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

The project was written in a few hours using regular expressions, it has false
positives. For example, some operations replace patterns in strings, comments
or function names even if it doesn't make sense.

Use the 2to6 project if you need a more reliable tool.


See also
--------

* `Six documentation <https://pythonhosted.org/six/>`_
* `2to6 <https://github.com/limodou/2to6>`_
* Python 3 porting book: `Language differences and workarounds
  <http://python3porting.com/differences.html>`_
* `getpython3 <http://getpython3.com/>`_

