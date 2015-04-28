PyDto - a Python data conversion and validation library
=======================================================

![Build Status](https://travis-ci.org/deemson/pydto.svg)

PyDto is a library conversion library. It can validate data, that comes from 
various data serialization formats like JSON, YAML, etc. PyDto is heavily
inspired by awesome data validation libraries
[Voluptuos](https://github.com/alecthomas/voluptuous) and 
[Schematics](https://github.com/schematics/schematics).
PyDto tries to take the best from these libraries and add a couple of things
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
data from one naming convention to another (e.g. for JSON camelCase to Python's
snake_case).

## Usage ##

First, you need to create a schema object. Schema describes structure of your 
DTO and types in it. First example is simple:

```python
from datetime import datetime
from pydto import Schema, Required, DateTime

# We define a schema
schema = Schema({
    Required('aDate'): DateTime(datetime_format='%Y-%m-%d %H:%M.%S')
})

# We convert an arbitrary dictionary, that conforms to the schema, to
# Python's native objects
native_obj = schema.to_native({
    'aDate': '2008-12-3 13:05.15'
})

# Check that everything is ok:

assert isinstance(native_obj, dict)
assert native_obj['aDate']
assert datetime(2008, 12, 3, 13, 5, 15) == native_obj['aDate']
```