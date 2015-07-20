PyDto - a Python data conversion and validation library
=======================================================

![Build Status](https://travis-ci.org/deemson/pydto.svg)
![Codecov](https://img.shields.io/codecov/c/github/deemson/pydto.svg)

PyDto is a data conversion library. It can validate data, that comes from 
various data serialization formats like JSON, YAML, etc. PyDto is heavily
inspired by awesome data validation libraries
[Voluptuos](https://github.com/alecthomas/voluptuous) and 
[Schematics](https://github.com/schematics/schematics).
PyDto tries to take the best from these libraries and adds a couple of things
on top of their feature set.

Like both these libraries, PyDto has:

  - support for complex data structures;
  - validation for every field in data;
  - informative error messages.


PyDto can also rename fields, effectively converting 
data from one naming convention to another (e.g. from JSON camelCase
to Python's snake_case).

Let's look at features of PyDto using a series of small, self-explanatory
examples. 

## Simple example ##

Simple example: to use PyDTO you must first define a schema. Then, you pass an
object to a schema in a function-like fashion. Schema returns another object,
which is converted and validated:

```python
from datetime import datetime
from pydto import Schema, Required, Optional, ParseDateTime


# We define a schema:
SCHEMA = Schema({
    Required('firstName', 'first_name'): str,
    Required('lastName', 'last_name'): str,
    Required('birthDate', 'birth_date'): ParseDateTime('%Y %m %d'),
    Optional('favouriteNumber', 'favourite_number'): int
})

# We pass an object (a dictionary) to the schema
result = SCHEMA({
    'firstName': 'John',
    'lastName': 'Smith',
    'birthDate': '1977 02 01'
})

# We retrieve another object (a dictionary too)
assert result == {
    'first_name': 'John',
    'last_name': 'Smith',
    'birth_date': datetime(1977, 2, 1)
}
```

Notes:

Previous example featured the most commonly data structure in DTO objects - 
a dictionary. PyDTO schema accepts native Python dictionary literals (aka '{}'
 symbols) and converts them internally to the Dict object.
 
 Thus, this:

```python
from pydto import Schema, Required

SCHEMA = Schema({
    Required('aString'): str
})
```

...is essentially the same as this:

```python
from pydto import Schema, Required, Dict

SCHEMA = Schema(Dict({
    Required('aString'): str
}))
```

Right now it might be not that obvious why would you want to do that 
substitution, but when we will discuss Extra parameters, it will be much more
clear.

OK, ride on!


## Slightly more complex example ##

```python
from decimal import Decimal
from pydto import Schema, Required, List, Enum

SCHEMA = Schema(List({
    Required('price'): Decimal,
    Required('category'): Enum('laptops', 'tablets', 'phones'),
    Required('quantity'): int,
    Required('serial'): (str, int)
}))

result = SCHEMA([
    {'price': '399.99', 'category': 'tablets', 'quantity': '2', 'serial': ['ta', '237']},
    {'price': '899.99', 'category': 'laptops', 'quantity': '1', 'serial': ['ag', '863']},
    {'price': '199.99', 'category': 'phones', 'quantity': '3', 'serial': ['lz', '659']}
])

assert result == [
    {'price': Decimal('399.99'), 'category': 'tablets', 'quantity': 2, 'serial': ['ta', 237]},
    {'price': Decimal('899.99'), 'category': 'laptops', 'quantity': 1, 'serial': ['ag', 863]},
    {'price': Decimal('199.99'), 'category': 'phones', 'quantity': 3, 'serial': ['lz', 659]}
]
```

In this example we introduced two more schema constructs: Enum and FixedList.
You can see them in schema definition as `Enum('laptops', 'tablets', 'phones')`
and `(str, int)`.

Enums are what you expect them to be: a set of acceptable values.
If the validated value is not equal to any of these values - an exception
will be raised. You can define enums with `set` constructor or set literal (in
Python2.7+), i.e this `Enum('laptops', 'tablets', 'phones')`, this
`set('laptops', 'tablets', 'phones')` and this `{'laptops', 'tablets', 'phones'}`
all define the same enum. However, set function or set literals usage is
discouraged, as it is much less clear what are your intentions are.

Fixed lists are lists of fixed length and fixed types for each
index. If the length of the validated list or any of the value types mismatch
an exceptiona will be raised.
In the example a fixed list of string and integer value used. Tuples and lists
internally converted to FixedList object, i.e. instead of using `(str, int)` in a schema
it is possble to use `[str, int]` or even `FixedList(str, int)`.