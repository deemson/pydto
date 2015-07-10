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


Like [Voluptuos](https://github.com/alecthomas/voluptuous), PyDto has 
succinct schema definitions and cool looking API. Like
[Schematics](https://github.com/schematics/schematics), PyDto is able to
perform two-way transformations: from DTOs to Python's native objects and vice
versa. Unlike these two, PyDto can also rename fields, effectively converting 
data from one naming convention to another (e.g. from JSON camelCase
to Python's snake_case).

## Overview ##

Let's look at features of PyDto using a series of small, self-explanatory
examples. 

First example is simple:

```python
from datetime import datetime
from pydto import Schema, Required, DateTime

# We define a schema
schema = Schema({
    Required('aDate'): DateTime(datetime_format='%Y-%m-%d %H:%M.%S')
})

# We convert an arbitrary dictionary, that conforms to the schema, to
# Python's native datatypes
native_obj = schema.to_native({
    'aDate': '2008-12-3 13:05.15'
})

# Check that everything is ok:

assert isinstance(native_obj, dict)
assert native_obj['aDate']
assert datetime(2008, 12, 3, 13, 5, 15) == native_obj['aDate']
```

You need to create a schema object. Schema describes the structure of your 
DTO and types in it. Next you will call one of the two main methods of the
Schema object:

  - `schema.to_dto` method takes a dictionary or a list and converts it to
  DTO datatypes, which can be then serialized into JSON, YAML, etc. without
  any additional fuss.
  - `schema.to_native` works as exact opposite: it takes primitive 
  datatypes, encountered in deserialized objects and converts them to native
  Python objects. Simple datatypes like strings or integers leaved as they are,
  but types like datetimes or decimals will be converted.
  
Data you pass to these method must conform to defined schema, 
otherwise an error will be raised. Let's pass an empty dict to the schema
defined above:

```python
# raises pydto.MultipleInvalid
# str(e) == "required field is missing @ data['aDate']"
native_obj = schema.to_native({
})
```

This code will raise a `pydto.MultipleInvalid` error. This is the only type of
errors, that `to_native` and `to_dto` methods will throw (hopefully :D).
The `pydto.MultipleInvalid` error is an aggregating exception: it will hold
all the exceptions, encountered when converting the data:

```python
schema = Schema({
    Required('aString'): String(),
    Required('anInt'): Integer()
})

try:
    schema.to_native({})
except MultipleInvalid as mi:
    # prints:
    # required field is missing @ data['aString']
    # required field is missing @ data['anInt']
    for e in mi.errors:
        print(str(e))
```

A slightly more complex example, demonstrating more PyDto features - optional
fields, inner dictionaries, lists and field renaming:

```python
schema = Schema({
    Required('someString1', 'some_string_1'): String(),
    Optional('someString2', 'some_string_2'): String(),
    Required('someDict', 'some_dict'): {
        Required('someInt', 'some_int'): Integer(),
        Required('someList', 'some_list'): List(Decimal()),
        Required('someOtherList', 'some_other_list'): List({
            Required('innerString', 'inner_string'): String(),
            Required('innerInt', 'inner_int'): Integer()
        })
    }
})

native_object = schema.to_native({
    'someString1': 'asdf',
    'someDict': {
        'someInt': 2,
        'someList': ['11.5', '12.2'],
        'someOtherList': [
            {'innerString': 'is1', 'innerInt': 1},
            {'innerString': 'is2', 'innerInt': '2'}
        ]
    }
})

assert native_object == {
    'some_string_1': 'asdf',
    'some_dict': {
        'some_int': 2,
        'some_other_list': [
            {'inner_int': 1, 'inner_string': 'is1'},
            {'inner_int': 2, 'inner_string': 'is2'}
        ],
        'some_list': [decimal.Decimal('11.5'), decimal.Decimal('12.2')],
    }
}
```

## Dealing with objects ##

PyDto is also able to convert user defined objects back and forth. Here is an
example:

```python
class User(object):
    def __init__(self, first_name, last_name, birth_date):
        self.first_name = first_name
        self.last_name = last_name
        self.birth_date = birth_date
    
schema = Schema(Object(User, {
    Required('first_name'): String(),
    Required('last_name'): String(),
    Required('birth_date'): DateTime('%Y-%m-%d')
}))

user = schema.to_native({
    'first_name': 'John',
    'last_name': 'Smith',
    'birth_date': '1977-08-5'
})

assert user
assert isinstance(user, User)
assert 'John' == user.first_name
assert 'Smith' == user.last_name
assert user.birth_date.date() == datetime(1977, 8, 5).date()
```

## Partially applying schema to dictionaries and objects ##

What if you need to validate only a portion of dictionary's keys? Or maybe you
do not control your object's creation, but you still need to validate some of
it's fields? Easy! Just use schema's populate_* methods! There are 3 of them:

  - `schema.populate_dto_dict(dto_dict, data)` -- populates DTO dict with 
  key-value pairs from data dictionary, validating and converting it to dto (via
  calling schema.to_dto method internally);
  - `schema.populate_native_dict(native_dict, data)` -- populates native dict with 
  key-value pairs from data dictionary, validating and converting it to native (via
  calling schema.to_native method internally);
  - `schema.populate_native_object(obj, data)` -- populates arbitrary Python object's fields with 
  key-value pairs from data dictionary, validating and converting it to native (via
  calling schema.to_native method internally).
  
Any of these methods will raise an exception if a key/field is present in dict/object.
 
Here is an example for each of the methods:

```python
schema = Schema({Required('a_dec'): Decimal()})
d = {'z': 'zzz'}
schema.populate_dto_dict(d, {'a_dec': decimal.Decimal(10.5)})
assert '10.5' == d['a_dec']
assert 'zzz' == d['z']
```

```python
schema = Schema({Required('a_dec'): Decimal()})
d = {'z': 'zzz'}
schema.populate_native_dict(d, {'a_dec': '10.5'})
assert decimal.Decimal('10.5') == d['a_dec']
assert 'zzz' == d['z']
```

```python
schema = Schema({Required('a_string'): String()})
# Some arbitrary object
class Some(object):
    pass
# Assume you cannot control it's creation or simply do not want to 
# use it in you Schema definition (via Object converter)
s = Some()
schema.populate_native_object(s, {'a_string': 'hello'})
assert 'hello' == s.a_string
```