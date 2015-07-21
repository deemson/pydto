PyDTO - a Python data conversion and validation library
=======================================================

PyDTO is a data conversion library. It can validate data, that comes from
various data serialization formats like JSON, YAML, etc. and convert it to
native Python datatypes. It can also convert native Python objects to described
DTO.

A taste of this library:

>>> from decimal import Decimal
>>> from pydto import Schema, Required, List, Enum
>>> SCHEMA = Schema(List({
...     Required('price'): Decimal,
...     Required('category'): Enum('laptops', 'tablets', 'phones'),
...     Required('quantity'): int,
...     Required('serial'): (str, int)
... }))
>>> result = SCHEMA([
... {'price': '399.99', 'category': 'tablets', 'quantity': '2', 'serial': ['ta', '237']},
... {'price': '899.99', 'category': 'laptops', 'quantity': '1', 'serial': ['ag', '863']},
... {'price': '199.99', 'category': 'phones', 'quantity': '3', 'serial': ['lz', '659']}
])
>>> assert result == [
... {'price': Decimal('399.99'), 'category': 'tablets', 'quantity': 2, 'serial': ['ta', 237]},
... {'price': Decimal('899.99'), 'category': 'laptops', 'quantity': 1, 'serial': ['ag', 863]},
... {'price': Decimal('199.99'), 'category': 'phones', 'quantity': 3, 'serial': ['lz', 659]}
]

Check out documentation for more detailed review at `Github repo`_.

.. _Github repo: https://github.com/deemson/pydto