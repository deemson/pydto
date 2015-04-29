PyDto - a Python data conversion and validation library
=======================================================

PyDto is a data conversion library. It can validate data, that comes from
various data serialization formats like JSON, YAML, etc. and convert it to
native Python datatypes. It can also convert native Python objects to described
DTO.

A taste of this library:

>>> schema = Schema({
...     Required('someString1', 'some_string_1'): String(),
...     Optional('someString2', 'some_string_2'): String(),
...     Required('someDict', 'some_dict'): {
...         Required('someInt', 'some_int'): Integer(),
...         Required('someList', 'some_list'): List(Decimal()),
...         Required('someOtherList', 'some_other_list'): List({
...             Required('innerString', 'inner_string'): String(),
...             Required('innerInt', 'inner_int'): Integer()
...         })
...     }
... })
>>> native_object = schema.to_native({
...     'someString1': 'asdf',
...     'someDict': {
...         'someInt': 2,
...         'someList': ['11.5', '12.2'],
...         'someOtherList': [
...             {'innerString': 'is1', 'innerInt': 1},
...             {'innerString': 'is2', 'innerInt': '2'}
...         ]
...     }
... })
>>> assert native_object == {
...     'some_string_1': 'asdf',
...     'some_dict': {
...         'some_int': 2,
...         'some_other_list': [
...             {'inner_int': 1, 'inner_string': 'is1'},
...             {'inner_int': 2, 'inner_string': 'is2'}
...         ],
...         'some_list': [decimal.Decimal('11.5'), decimal.Decimal('12.2')],
...     }
... }

Check out documentation for more detailed review at `Github repo`_.

.. _Github repo: https://github.com/deemson/pydto