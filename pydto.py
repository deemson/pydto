from collections import defaultdict
import random
import sys
from contextlib import contextmanager
import decimal
from datetime import datetime

if sys.version_info >= (3,):
    iteritems = dict.items
    strtype = str
else:
    iteritems = dict.iteritems
    # flake8: noqa
    strtype = basestring

__author__ = 'Dmitry Kurkin'
__version__ = '0.3.4'


class Error(Exception):
    """Base validation exception."""


class SchemaError(Error):
    """An error was encountered in the schema."""


class Invalid(Error):
    """The data was invalid.

    :attr msg: The error message.
    :attr path: The path to the error, as a list of keys in the source data.
    :attr error_message: The actual error message that was raised, as a
        string.

    """

    def __init__(self, message, path=None, error_message=None,
                 error_type=None):
        Error.__init__(self, message)
        self.path = path or []
        self.error_message = error_message or message
        self.error_type = error_type

    @property
    def msg(self):
        return self.args[0]

    def __str__(self):
        path = ' @ data[%s]' % ']['.join(map(repr, self.path)) \
            if self.path else ''
        output = Exception.__str__(self)
        if self.error_type:
            output += ' for ' + self.error_type
        return output + path


class RequiredInvalid(Invalid):
    """Required field was missing."""


class InclusiveInvalid(Invalid):
    """Inclusive field was missing, while other inclusives were present."""


class UnknownInvalid(Invalid):
    """The key was not found in the schema."""


class TypeInvalid(Invalid):
    """The value found was not of required type."""


class LiteralInvalid(Invalid):
    """Data, passed to literal converter is not equal to the set value."""


class DictInvalid(Invalid):
    """The value found was not a dict."""


class ListInvalid(Invalid):
    """The value found was not a list."""


class ObjectInvalid(Invalid):
    """The value found was not an obejct of required type."""


class KeyPopulateInvalid(Invalid):
    """Tried to populate a dictionary's key, that already exists."""


class FieldPopulateInvalid(Invalid):
    """Tried to populate an object's field, that already exists."""


class FixedListLengthInvalid(Invalid):
    """Data length is not equal to fixed list length."""


class EnumInvalid(Invalid):
    """Enum does not contain value provided."""


class MultipleInvalid(Invalid):
    def __init__(self, errors=None):
        self.errors = errors[:] if errors else []

    def __repr__(self):
        return 'MultipleInvalid(%r)' % self.errors

    @property
    def msg(self):
        return self.errors[0].msg

    @property
    def path(self):
        return self.errors[0].path

    @property
    def error_message(self):
        return self.errors[0].error_message

    def add(self, error):
        self.errors.append(error)

    def __str__(self):
        return str(self.errors[0])


class Undefined(object):
    def __nonzero__(self):
        return False

    def __repr__(self):
        return '...'


UNDEFINED = Undefined()


class Schema(object):
    def __init__(self, schema):
        self._schema = self._compile(schema)

    @classmethod
    def _compile(cls, schema):
        if isinstance(schema, dict):
            return Dict(schema)
        elif isinstance(schema, (Dict, List, Enum, FixedList)):
            return schema
        elif isinstance(schema, strtype):
            return Literal(str, schema)
        elif isinstance(schema, int):
            return Literal(int, schema)
        elif isinstance(schema, bool):
            return Literal(ParseBoolean(), schema)
        elif isinstance(schema, decimal.Decimal):
            return Literal(ParseDecimal(), schema)
        elif isinstance(schema, set):
            return Enum(schema)
        elif isinstance(schema, (list, tuple)):
            return FixedList(schema)
        elif callable(schema):
            return schema
        else:
            raise SchemaError('%s is not a valid value in schema'
                              % type(schema))

    def __call__(self, data):
        try:
            return self._schema(data)
        except MultipleInvalid:
            raise
        except Invalid as e:
            raise MultipleInvalid([e])


class Marker(object):
    def __init__(self, name, rename_to=None):
        self.name = name
        self.rename_to = rename_to


class Required(Marker):
    pass


class Optional(Marker):
    pass


class Inclusive(Marker):
    def __init__(self, name, rename_to=None, monitor=None):
        self.monitor = monitor
        super(Inclusive, self).__init__(name, rename_to)

    def monitor(self, monitor):
        self.monitor = monitor
        return self


class Literal(object):
    """
    Wraps a converter (like String() or Integer()) to be a literal to some
    value:

    >>> schema = Schema({Required('aString'): Literal(str, 'hello')})
    >>> assert {'aString': 'hello'} == schema({'aString': 'hello'})
    >>> try:
    ...     schema({'aString': 'not hello'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    It is more concise to use simple type literals for simple types
    (string, integer, decimal and boolean):

    >>> schema = Schema({Required('anInt'): 3})
    >>> assert {'anInt': 3} == schema({'anInt': '3'})
    >>> try:
    ...     schema({'anInt': '2'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, converter, value):
        self._converter = converter
        self._value = value

    def __call__(self, data):
        converted_data = self._converter(data)
        if converted_data != self._value:
            raise LiteralInvalid('value %r is not equal to %r'
                                 % (converted_data, self._value))
        return converted_data


class Dict(object):
    """
    Marks a field in a schema as a dictionary field, containing objects, that
    conform to inner schema:

    >>> schema = Schema({
    ...     Required('aDecimal'): ParseDecimal(),
    ...     Optional('someString'): str,
    ...     Required('innerDict'): {
    ...         Required('anInt'): int
    ...     }
    ... })
    >>> res = schema({'aDecimal': '12.3',
    ...               'innerDict': {'anInt': 5}})
    >>> assert res == {'aDecimal': decimal.Decimal('12.3'),
    ...                'innerDict': {'anInt': 5}}

    It is possible to use just a Python's dictionary literal,
    instead of using this object. So this:

    >>> schema = Schema(Dict({
    ...     Required('aString'): str
    ... }))

    is effectively the same as:

    >>> schema = Schema({
    ...     Required('aString'): str
    ... })

    Unknown fields will raise errors:

    >>> schema = Schema({
    ...     Optional('aString'): str
    ... })
    >>> try:
    ...     schema({'anUnknownString': 'hello'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, inner_schema):
        if not isinstance(inner_schema, dict):
            raise SchemaError('expected a dictionary, got %r instead'
                              % inner_schema)
        compiled_inner_schema = {}
        for key, value in iteritems(inner_schema):
            if not isinstance(key, Marker):
                raise SchemaError('keys in schema should'
                                  ' be instances of Marker class')
            compiled_inner_schema[key] = Schema._compile(value)
        self._inner_schema = compiled_inner_schema

    def __call__(self, data):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary, got %r instead'
                              % data)
        # Make a copy of incoming dictionary to pop items
        # without changing data
        data = dict(data)
        result = {}
        inclusive = defaultdict(set)
        errors = []
        for marker, converter in iteritems(self._inner_schema):
            key = marker.name
            substitution_key = marker.rename_to or key
            if key in data:
                try:
                    value = converter(data.pop(key))
                    if isinstance(marker, Inclusive):
                        inclusive[marker.monitor].add(key)
                    result[substitution_key] = value
                except MultipleInvalid as e:
                    errs = [ie for ie in e.errors]
                    for e in errs:
                        e.path = [key] + e.path
                    errors.extend(errs)
                except Invalid as e:
                    e.path = [key] + e.path
                    errors.append(e)
                except Exception as e:
                    errors.append(Invalid('error converting value',
                                          [key]))

            else:
                if isinstance(marker, Required):
                    errors.append(RequiredInvalid('required field is missing',
                                                  [key]))
        if data:
            for unknown_field in data.keys():
                errors.append(UnknownInvalid('unknown field',
                                             [unknown_field]))
        if errors:
            raise MultipleInvalid(errors)
        return result


class List(object):
    """
    Marks a field in a schema as a list field, containing objects, that
    conform to inner schema:

    >>> schema = Schema(List(ParseDecimal()))
    >>> res = schema([1, '2.5', 3])
    >>> assert res == [decimal.Decimal(1), decimal.Decimal('2.5'),
    ...                decimal.Decimal(3)]
    """

    def __init__(self, inner_schema):
        self._inner_schema = Schema._compile(inner_schema)

    def __call__(self, data):
        if not isinstance(data, list):
            if not isinstance(data, list):
                raise ListInvalid('expected a list, got %r instead' % data)
        result = []
        errors = []
        for idx, d in enumerate(data):
            try:
                result.append(self._inner_schema(d))
            except MultipleInvalid as e:
                errs = [ie for ie in e.errors]
                for e in errs:
                    e.path = [idx] + e.path
                errors.extend(errs)
            except Invalid as e:
                e.path = [idx] + e.path
                errors.append(e)
        if errors:
            raise MultipleInvalid(errors)
        return result


class ParseBoolean(object):
    TRUTH_VALUES = ['true', 't', 'yes', 'y', '1']
    FALSE_VALUES = ['false', 'f', 'no', 'n', '0']

    def __init__(self, strict=True):
        """
        :param strict: when True, values supplied to this converter
        are expected to be in either TRUE_VALUES or FALSE_VALUES.
        Setting this to False will force Boolean to conform to
        default Python truth rules.
        """
        self.strict = strict

    def __call__(self, value):
        if value in [True, False]:
            return value
        else:
            if self.strict:
                data = str(value)
                if data in self.TRUTH_VALUES:
                    return True
                elif data in self.FALSE_VALUES:
                    return False
                else:
                    raise TypeInvalid(
                        'a strict boolean should be '
                        'either one of %r or one of %r'
                        % (self.TRUTH_VALUES, self.FALSE_VALUES)
                    )
            else:
                return bool(value)


class ParseDecimal(object):
    def __call__(self, value):
        try:
            if not isinstance(value, (strtype, int)):
                raise TypeInvalid('value for a decimal can be only '
                                  'a string or an int, got %r instead'
                                  % value)
            return decimal.Decimal(value)
        except (TypeError, ValueError, decimal.DecimalException) as e:
            raise TypeInvalid('bad decimal number %r: %r' % (value, e))


class ParseDateTime(object):
    def __init__(self, datetime_format='%Y-%m-%d %H:%M.%S'):
        try:
            datetime.strptime(datetime.utcnow().strftime(datetime_format),
                              datetime_format)
        except (TypeError, ValueError) as e:
            raise SchemaError(
                'bad datetime format %r: %r' % (datetime_format, e))
        self.datetime_format = datetime_format

    def __call__(self, value):
        try:
            return datetime.strptime(value, self.datetime_format)
        except (TypeError, ValueError) as e:
            raise TypeInvalid('bad datetime %r: %r' % (value, e))


class MakeObject(object):
    """

    Marks a field in a schema for an object creation:

    >>> class User(object):
    ...     def __init__(self, first_name, last_name, birth_date):
    ...         self.first_name = first_name
    ...         self.last_name = last_name
    ...         self.birth_date = birth_date
    >>> schema = Schema(MakeObject(User, {
    ...     Required('first_name'): str,
    ...     Required('last_name'): str,
    ...     Required('birth_date'): ParseDateTime('%Y-%m-%d')
    ... }))
    >>> user = schema({
    ...     'first_name': 'John',
    ...     'last_name': 'Smith',
    ...     'birth_date': '1977-08-5'
    ... })
    >>> assert user
    >>> assert isinstance(user, User)
    >>> assert 'John' == user.first_name
    >>> assert 'Smith' == user.last_name
    >>> assert user.birth_date.date() == datetime(1977, 8, 5).date()
    """

    def __init__(self, object_class, inner_schema,
                 object_initializator='__init__'):
        """
        :param object_class: an object class
        :param inner_schema: a dictionary with inner object schema
        :param object_initializator: a class method, that should be used
        to initialize object's params. All parsed schema params will be
        passed as \*\*kwargs to this method.
        If none supplied, object's constructor will be used.
        """
        if not isinstance(object_class, type):
            raise SchemaError('expected a class')
        if not isinstance(inner_schema, dict):
            raise SchemaError('expected a dictionary')
        if object_initializator is None or \
                str(object_initializator) == '__init__':
            self.object_constructor = None
        elif isinstance(object_initializator, strtype):
            self.object_constructor = getattr(object_class,
                                              object_initializator)
            if not self.object_constructor:
                raise SchemaError('%s does not have a method named %s'
                                  % (object_class, object_initializator))
        elif callable(object_initializator):
            if not getattr(object_class, object_initializator.__name__):
                raise SchemaError('%s is not %s method'
                                  % (object_class,
                                     object_initializator.__name__))
            self.object_constructor = object_initializator
        else:
            raise SchemaError('expected a %s method or method name'
                              % object_class)

        self.object_class = object_class
        self._inner_schema = Schema._compile(inner_schema)

    def __call__(self, value):
        dict_data = self._inner_schema(value)
        if self.object_constructor is None:
            return self.object_class(**dict_data)
        else:
            o = self.object_class()
            self.object_constructor(o, **dict_data)
            return o


class FixedList(object):
    """
    Marks a field in a schema as a list of fixed length. Every element in the
    list has it's own type. You can use Python's list or tuple data types for
    FixedList specification:

    >>> schema = Schema([str, ParseDecimal(), int])
    >>> res = schema(['asd', '43.7', '8'])
    >>> assert ['asd', decimal.Decimal('43.7'), 8] == res

    >>> schema = Schema((ParseDateTime('%Y-%m-%d %H:%M.%S'), ParseDecimal()))
    >>> res = schema(['1985-12-1 15:36.21', '12.2'])
    >>> assert datetime(1985, 12, 1, 15, 36, 21) == res[0]
    >>> assert decimal.Decimal('12.2') == res[1]
    """

    def __init__(self, inner_schemas):
        if not isinstance(inner_schemas, (list, tuple)):
            raise SchemaError('expected a list or a tuple, got %r '
                              'instead' % inner_schemas)
        self._inner_schemas = tuple(Schema._compile(sch)
                                    for sch in inner_schemas)

    def __call__(self, value):
        if not isinstance(value, list):
            raise ListInvalid('expected a list, got %r instead' % value)
        if len(value) != len(self._inner_schemas):
            raise FixedListLengthInvalid('%r length is not equal to %d'
                                         % (value, len(self._inner_schemas)))
        return [c(v) for c, v in zip(self._inner_schemas, value)]


class Enum(object):
    """
    Marks a field in a schema as a list of fixed length. Every element in the
    list has it's own type. You can use Python's list or tuple data types for
    FixedList specification:

    >>> schema = Schema(set(('June', 6, 'VI')))
    >>> assert 6 == schema('6')
    >>> assert 'VI' == schema('VI')
    >>> try:
    ...     schema('V')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    """

    def __init__(self, values):
        values = set([Schema._compile(v) for v in values])
        for v in values:
            if not isinstance(v, Literal):
                raise SchemaError('only literal values supported in enum')
        self._values = values

    def __call__(self, data):
        for v in self._values:
            try:
                return v(data)
            except:
                pass
        raise EnumInvalid('none of enum values matches %r' % data)


class UnvalidatedDict(object):
    """

    Marks a field in a schema as an unvalidated dictionary: a value should be
    a dictionary, but inner schema will not be validated or converted.

    >>> schema = Schema({Required('dict'): UnvalidatedDict()})
    >>> res = schema({'dict': {'aField': 'hello'}})
    >>> assert res
    >>> assert 'dict' in res
    >>> assert {'aField': 'hello'} == res['dict']
    >>> try:
    ...     schema(object())
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    """

    def __call__(self, data):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary, got %r instead'
                              % data)
        return data


class UnvalidatedList(object):
    """

    Marks a field in a schema as an unvalidated list: a value should be
    a list, but inner schema will not be validated or converted.

    >>> schema = Schema({Required('list'): UnvalidatedList()})
    >>> res = schema({'list': ['hello', 2]})
    >>> assert res
    >>> assert 'list' in res
    >>> assert ['hello', 2] == res['list']
    >>> try:
    ...     schema(object())
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    """

    def __call__(self, data):
        if not isinstance(data, list):
            raise ListInvalid('expected a list, got %r instead' % data)
        return data
