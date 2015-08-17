from collections import defaultdict
from contextlib import contextmanager
import sys
import decimal
from datetime import datetime

if sys.version_info >= (3,):
    iteritems = dict.items
    strtype = str
    PRIMITIVE_TYPES = (str, int, decimal.Decimal, float,
                       complex, bool)
else:
    iteritems = dict.iteritems
    # flake8: noqa
    strtype = basestring
    PRIMITIVE_TYPES = (str, unicode, int, decimal.Decimal, float,
                       complex, bool)

__author__ = 'Dmitry Kurkin'
__version__ = '0.5.1'


@contextmanager
def aggregate_schema_errors(errors_list, path=None):
    path = path or []
    try:
        yield
    except MultipleSchemaError as e:
        errs = [ie for ie in e.errors]
        for e in errs:
            e.path = path + e.path
        errors_list.extend(errs)
    except SchemaError as e:
        e.path = path + e.path
        errors_list.append(e)
    except Exception as e:
        errors_list.append(Invalid(str(e), path))


@contextmanager
def aggregate_invalids(invalids_list, path=None):
    path = path or []
    try:
        yield
    except MultipleInvalid as e:
        errs = [ie for ie in e.errors]
        for e in errs:
            e.path = path + e.path
        invalids_list.extend(errs)
    except Invalid as e:
        e.path = path + e.path
        invalids_list.append(e)
    except Exception as e:
        invalids_list.append(Invalid(str(e), path))


class Error(Exception):
    """Base validation exception."""

    def __init__(self, message, path=None, data_name='data'):
        Exception.__init__(self, message)
        self.path = path or []
        self.data_name = data_name

    @property
    def msg(self):
        return self.args[0]

    def __str__(self):
        if self.path:
            path = ' @ %s[%s]' % (self.data_name,
                                  ']['.join(map(repr, self.path)))
        else:
            path = ''
        output = Exception.__str__(self)
        return output + path


class MultipleError(Error):
    def __init__(self, errors=None):
        self.errors = errors[:] if errors else []

    @classmethod
    def _get_name(cls):
        return cls.__name__

    def __repr__(self):
        return '%s(%r)' % (self._get_name(), self.errors)

    @property
    def msg(self):
        return self.errors[0].msg

    @property
    def path(self):
        return self.errors[0].path

    def add(self, error):
        self.errors.append(error)

    def __str__(self):
        return str(self.errors[0])


class SchemaError(Error):
    """An error was encountered in the schema."""

    def __init__(self, message, path=None):
        Error.__init__(self, message, path, data_name='schema')


class MultipleSchemaError(MultipleError):
    """An aggregator exception for errorsm that
     were encountered in the schema."""

    def __str__(self):
        return '\n%s' % '\n'.join(map(str, self.errors))


class Invalid(Error):
    """The data was invalid."""


class MultipleInvalid(MultipleError):
    """The aggregator exception for the data validation errors."""


class RequiredInvalid(Invalid):
    """Required field was missing."""


class InclusiveInvalid(Invalid):
    """Inclusive field was missing, while other inclusives were present."""


class ExclusiveInvalid(Invalid):
    """Some or all mutually exclusive fields were present."""


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


class NoneInvalid(Invalid):
    """Got None value."""


class LengthInvalid(Invalid):
    """Incorrect length."""


class RangeInvalid(Invalid):
    """Data is not in specified range."""


class Undefined(object):
    def __nonzero__(self):
        return False

    def __repr__(self):
        return '...'


UNDEFINED = Undefined()


class Extras(object):
    values = ['prevent', 'allow', 'remove', 'inherit']
    PREVENT, ALLOW, REMOVE, INHERIT = values


class _Compilable(object):
    def _compile(self, compiler):
        raise NotImplementedError()


class _Mapping(_Compilable):
    def __init__(self, inner_schema,
                 extras=Extras.INHERIT,
                 substitutions=None):
        self.inner_schema = inner_schema
        self.extras = _Compiler._validate_extras(extras)
        self.substitutions = _Compiler._validate_substitutions(substitutions)

    def _compile(self, compiler):
        compiled_inner_schema = {}
        self.inclusive_monitors = defaultdict(set)
        self.exclusive_monitors = defaultdict(set)
        source_names = set()
        destination_names = set()
        errors = []
        for key, value in iteritems(self.inner_schema):
            if not isinstance(key, Marker):
                errors.append(SchemaError('keys in schema dictionaries must'
                                          ' be instances of Marker class',
                                          [repr(key)]))
                continue
            if key.name in source_names:
                errors.append(SchemaError('duplicate names',
                                          [key.name]))
                continue
            if key.rename_to in destination_names:
                errors.append(SchemaError('duplicate names',
                                          [key.rename_to]))
                continue
            source_names.add(key.name)
            destination_names.add(key.rename_to)
            with aggregate_schema_errors(errors, [key.name]):
                compiled_inner_schema[key] = compiler.compile(value)
            if isinstance(key, Inclusive):
                self.inclusive_monitors[key._monitor].add(key.name)
            if isinstance(key, Exclusive):
                self.exclusive_monitors[key._monitor].add(key.name)
        if errors:
            raise MultipleSchemaError(errors)
        self.inner_schema = compiled_inner_schema
        return self

    def prepare_data(self, data):
        raise NotImplementedError()

    def is_key_in_data(self, key, data):
        raise NotImplementedError()

    def get_value(self, key, data):
        raise NotImplementedError()

    def prepare_result(self, result):
        raise NotImplementedError()

    def check_extras(self, data, result):
        errors = []
        if data:
            if self.extras == Extras.PREVENT:
                for unknown_field in data.keys():
                    errors.append(UnknownInvalid('unknown field',
                                                 [unknown_field]))
            elif self.extras == Extras.ALLOW:
                for unknown_field in data.keys():
                    result[unknown_field] = data[unknown_field]
        if errors:
            raise MultipleInvalid(errors)

    def __call__(self, data):
        data = self.prepare_data(data)
        result = {}
        inclusive = defaultdict(set)
        exclusive = defaultdict(set)
        errors = []
        for marker, converter in iteritems(self.inner_schema):
            key = marker.name
            substitution_key = marker.rename_to or key
            if self.is_key_in_data(key, data):
                with aggregate_invalids(errors, [key]):
                    if isinstance(marker, Inclusive):
                        inclusive[marker._monitor].add(key)
                    if isinstance(marker, Exclusive):
                        exclusive[marker._monitor].add(key)
                    value = converter(self.get_value(key, data))
                    result[substitution_key] = value
            else:
                if isinstance(marker, Required):
                    errors.append(
                        RequiredInvalid('required field is missing',
                                        [key]))
        if inclusive:
            for monitor, values in iteritems(inclusive):
                missing = self.inclusive_monitors[monitor] - values
                if missing:
                    present = self.inclusive_monitors[monitor].intersection(
                        values)
                    errors.append(
                        InclusiveInvalid('when fields %r are present, '
                                         'fields %r should be present too'
                                         % (list(missing), list(present))))
        if exclusive:
            for monitor, values in iteritems(exclusive):
                if len(values) > 1:
                    errors.append(
                        ExclusiveInvalid('fields %r are mutually exclusive'
                                         ' and only one of them should be '
                                         'present'
                                         % list(values)))
        with aggregate_invalids(errors):
            self.check_extras(data, result)
        with aggregate_invalids(errors):
            result = self.prepare_result(result)
        if errors:
            raise MultipleInvalid(errors)
        return result


class _Compiler(object):
    def __init__(self, extras, substitutions):
        self.extras = self._validate_extras(extras)
        self.substitutions = self._validate_substitutions(substitutions)

    @classmethod
    def _validate_extras(cls, value):
        if value not in Extras.values:
            raise SchemaError('extras should a one of %r'
                              % Extras.values)
        return value

    @classmethod
    def _validate_substitutions(cls, substitutions):
        if not substitutions:
            substitutions = {}
        processed = {}
        if not isinstance(substitutions, dict):
            raise SchemaError('substitutions should be a dictionary with'
                              'type-to-type mapping')
        for src_type, dst_type, in iteritems(substitutions):
            if isinstance(src_type, type):
                processed[src_type] = dst_type
            elif isinstance(src_type, tuple):
                for t in src_type:
                    if not isinstance(t, type):
                        raise SchemaError('keys in substitution'
                                          ' dictionary should be '
                                          'types or tuples of types')
                    processed[t] = dst_type
            else:
                raise SchemaError('keys in substitution dictionary should be '
                                  'types or tuples of types')
        return processed

    def compile(self, schema):
        if isinstance(schema, _Mapping):
            if schema.extras == Extras.INHERIT:
                schema.extras = self.extras
            else:
                self.extras = schema.extras
            return schema._compile(self)
        elif isinstance(schema, _Compilable):
            return schema._compile(self)
        else:
            for type, substitution_type in iteritems(self.substitutions):
                if isinstance(schema, type):
                    return self.compile(substitution_type(schema))
            if callable(schema):
                return schema
        raise SchemaError('%r is not a valid value in schema' % schema)


class Schema(object):
    """
    PyDTO main object.
    """
    PRIMITIVE_TYPES = (strtype, int, decimal.Decimal, float,
                       complex, bool)

    def __init__(self, schema, extras=Extras.PREVENT):
        if extras == Extras.INHERIT:
            raise SchemaError('top Schema level extras cannot be inherited')
        compiler = _Compiler(extras, substitutions={
            tuple: Chain.from_iterable,
            dict: Dict,
            list: FixedList.from_iterable,
            set: Enum.from_iterable,
            PRIMITIVE_TYPES: Literal
        })
        self.schema = compiler.compile(schema)

    def __call__(self, data):
        try:
            return self.schema(data)
        except MultipleInvalid:
            raise
        except Invalid as e:
            raise MultipleInvalid([e])
        except Exception as e:
            raise MultipleInvalid([Invalid(str(e))])


class Marker(object):
    def __init__(self, name, rename_to=None):
        self.name = name
        self._rename_to = rename_to

    @property
    def rename_to(self):
        return self._rename_to or self.name


class Required(Marker):
    pass


class Optional(Marker):
    pass


class Inclusive(Marker):
    """
    Inclusive is used to make several dictionary values mutually inclusive:

    >>> schema = Schema({
    ...     Inclusive('one'): str,
    ...     Inclusive('two'): str
    ... })
    >>> res = schema({'one': 'hello', 'two': 'world'})
    >>> assert res == {'one': 'hello', 'two': 'world'}
    >>> try:
    ...     schema({'one': 'hello'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> assert {} == schema({})

    It is possible to create multiple independent groups of inclusive fields
    using monitors:

    >>> schema = Schema({
    ...     Inclusive('one-one').monitor(1): str,
    ...     Inclusive('one-two').monitor(1): str,
    ...     Inclusive('two-one').monitor(2): str,
    ...     Inclusive('two-two').monitor(2): str
    ... })
    >>> res = schema({'one-one': 'hello', 'one-two': 'world'})
    >>> assert res == {'one-one': 'hello', 'one-two': 'world'}
    >>> res = schema({'two-one': 'hello', 'two-two': 'world'})
    >>> assert res == {'two-one': 'hello', 'two-two': 'world'}
    >>> assert {} == schema({})
    >>> res = schema({
    ...     'one-one': 'hello', 'one-two': 'world',
    ...     'two-one': 'oh hello', 'two-two': 'another world'
    ... })
    >>> assert res == {
    ...     'one-one': 'hello', 'one-two': 'world',
    ...     'two-one': 'oh hello', 'two-two': 'another world'
    ... }
    >>> try:
    ...     schema({'one-one': 'hello'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> try:
    ...     schema({'two-one': 'hello'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, name, rename_to=None, monitor=None):
        self._monitor = monitor
        super(Inclusive, self).__init__(name, rename_to)

    def monitor(self, monitor):
        self._monitor = monitor
        return self


class Exclusive(Marker):
    """
    Exclusive is used to make several dictionary values mutually exclusive:

    >>> schema = Schema({
    ...     Exclusive('one'): str,
    ...     Exclusive('two'): str
    ... })
    >>> res = schema({'one': 'hello'})
    >>> assert res == {'one': 'hello'}
    >>> res = schema({'two': 'hello'})
    >>> assert res == {'two': 'hello'}
    >>> try:
    ...     schema({'one': 'hello', 'two': 'world'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> assert {} == schema({})

    It is possible to create multiple independent groups of exclusive fields
    using monitors:

    >>> schema = Schema({
    ...     Exclusive('one-one').monitor(1): str,
    ...     Exclusive('one-two').monitor(1): str,
    ...     Exclusive('two-one').monitor(2): str,
    ...     Exclusive('two-two').monitor(2): str
    ... })
    >>> res = schema({'one-one': 'hello', 'two-one': 'world'})
    >>> assert res == {'one-one': 'hello', 'two-one': 'world'}
    >>> res = schema({'two-one': 'hello', 'one-two': 'world'})
    >>> assert res == {'two-one': 'hello', 'one-two': 'world'}
    >>> try:
    ...     schema({'one-one': 'hello', 'one-two': 'world'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> try:
    ...     schema({'two-one': 'hello', 'two-two': 'world'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> assert {} == schema({})

    """

    def __init__(self, name, rename_to=None, monitor=None):
        self._monitor = monitor
        super(Exclusive, self).__init__(name, rename_to)

    def monitor(self, monitor):
        self._monitor = monitor
        return self


class Literal(_Compilable):
    """
    Marks a field in a schema as a literal value:

    >>> schema = Schema({Required('aString'): Literal('hello', str)})
    >>> assert {'aString': 'hello'} == schema({'aString': 'hello'})
    >>> try:
    ...     schema({'aString': 'not hello'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    It is more concise to use simple type literals for simple types
    (string, integer, decimal, boolean and complex):

    >>> schema = Schema({Required('anInt'): 3})
    >>> assert {'anInt': 3} == schema({'anInt': '3'})
    >>> try:
    ...     schema({'anInt': '2'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, value, converter=None):
        self.value = value
        if converter:
            self.converter = converter
        else:
            for primitive_type in PRIMITIVE_TYPES:
                if isinstance(value, primitive_type):
                    self.converter = primitive_type
                    break
            else:
                raise SchemaError('cannot deduce type')

    def __call__(self, data):
        converted_data = self.converter(data)
        if self.value != converted_data:
            raise LiteralInvalid('value %r is not equal to %r'
                                 % (converted_data, self.value))
        return converted_data

    def _compile(self, compiler):
        return self


class Dict(_Mapping):
    """
    Marks a field in a schema as a dictionary field, containing objects, that
    conform to inner schema:

    >>> schema = Schema({
    ...     Required('aDecimal'): parse_decimal,
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

    Unless it is explicitly stated otherwise using Dict object:

    >>> schema = Schema(Dict({
    ...     Required('aString'): str
    ... }, Extras.REMOVE))
    >>> res = schema({'aString': 'hello', 'anUnknownString': 'hello again'})
    >>> assert res == {'aString': 'hello'}

    ...or for the whole Schema:

    >>> schema = Schema({
    ...     Optional('aString'): str
    ... }, extras=Extras.ALLOW)
    >>> res = schema({'anUnknownString': 'hello'})
    >>> assert res == {'anUnknownString': 'hello'}

    """

    def __init__(self, inner_schema, extras=Extras.INHERIT):
        if not isinstance(inner_schema, dict):
            raise SchemaError('expected a dictionary, got %r instead'
                              % inner_schema)
        super(Dict, self).__init__(inner_schema, extras)

    def prepare_data(self, data):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary, got %r instead'
                              % data)
        # Make a copy of incoming dictionary to pop items
        # without changing data
        return dict(data)

    def is_key_in_data(self, key, data):
        return key in data

    def get_value(self, key, data):
        return data.pop(key)

    def prepare_result(self, result):
        return result

    def check_extras(self, data, result):
        errors = []
        if data:
            if self.extras == Extras.PREVENT:
                for unknown_field in data.keys():
                    errors.append(UnknownInvalid('unknown field',
                                                 [unknown_field]))
            elif self.extras == Extras.ALLOW:
                for unknown_field in data.keys():
                    result[unknown_field] = data[unknown_field]
        if errors:
            raise MultipleInvalid(errors)


class List(_Compilable):
    """
    Marks a field in a schema as a list field, containing objects, that
    conform to inner schema:

    >>> schema = Schema(List(parse_decimal))
    >>> res = schema([1, '2.5', 3])
    >>> assert res == [decimal.Decimal(1), decimal.Decimal('2.5'),
    ...                decimal.Decimal(3)]
    """

    def __init__(self, inner_schema):
        self.inner_schema = inner_schema

    def __call__(self, data):
        if not isinstance(data, list):
            if not isinstance(data, list):
                raise ListInvalid('expected a list, got %r instead'
                                  % type(data))
        result = []
        errors = []
        for idx, d in enumerate(data):
            try:
                result.append(self.inner_schema(d))
            except MultipleInvalid as e:
                errs = [ie for ie in e.errors]
                for e in errs:
                    e.path = [idx] + e.path
                errors.extend(errs)
            except Invalid as e:
                e.path = [idx] + e.path
                errors.append(e)
            except Exception as e:
                errors.append(Invalid(str(e), [idx]))
        if errors:
            raise MultipleInvalid(errors)
        return result

    def _compile(self, compiler):
        self.inner_schema = compiler.compile(self.inner_schema)
        return self


class Enum(_Compilable):
    """
    Marks a field in a schema as a value, chosen from a fixed set:

    >>> schema = Schema(Enum('June', 6, 'VI'))
    >>> assert 6 == schema('6')
    >>> assert 'VI' == schema('VI')
    >>> try:
    ...     schema('V')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    Set can be used to mark a field as Enum as well as set literal '{}' in
    Python 2.7+:

    >>> schema = Schema(set(('June', 6, 'VI')))
    >>> assert 'VI' == schema('VI')
    """

    def __init__(self, *values):
        self.values = set(values)

    @classmethod
    def from_iterable(cls, collection_of_values):
        return cls(*collection_of_values)

    def _compile(self, compiler):
        errors = []
        compiled_values = []
        for idx, v in enumerate(self.values):
            if isinstance(v, PRIMITIVE_TYPES):
                compiled_values.append(compiler.compile(v))
            elif isinstance(v, Literal):
                compiled_values.append(compiler.compile(v))
            else:
                errors.append(SchemaError('only literal values '
                                          'allowed in Enum, got %r' % v))
        if errors:
            raise MultipleSchemaError(errors)
        self.values = compiled_values
        return self

    def __call__(self, data):
        for v in self.values:
            try:
                return v(data)
            except:
                pass
        raise EnumInvalid('none of enum values matches %r' % data)


class MakeObject(Dict):
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
                 object_initializator='__init__', extras=Extras.INHERIT):
        """
        :param object_class: an object class
        :param inner_schema: a dictionary with inner object schema
        :param object_initializator: a class method, that should be used
        to initialize object's params. All parsed schema params will be
        passed as \*\*kwargs to this method.
        If none supplied, object's constructor will be used.
        :param extras: a strategy to deal with extra fields. See Schema
         __init__ extras param for reference.
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
            if not self.object_constructor or \
                not callable(self.object_constructor):
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
        super(MakeObject, self).__init__(inner_schema, extras)

    def prepare_result(self, result):
        if self.object_constructor is None:
            return self.object_class(**result)
        else:
            o = self.object_class()
            self.object_constructor(o, **result)
            return o


class FromObject(_Mapping):
    """

    Marks a field in a schema for an object-to-dict conversion:

    >>> class User(object):
    ...     def __init__(self, first_name, last_name, birth_date):
    ...         self.first_name = first_name
    ...         self.last_name = last_name
    ...         self.birth_date = birth_date
    >>> schema = Schema(FromObject(User, {
    ...     Required('first_name'): str,
    ...     Required('last_name'): str,
    ...     Required('birth_date'): FormatDateTime('%Y-%m-%d')
    ... }))
    >>> user = schema(User(
    ...     'John',
    ...     'Smith',
    ...     datetime(1977, 8, 5)
    ... ))
    >>> assert user
    >>> assert isinstance(user, dict)
    >>> assert 'John' == user['first_name']
    >>> assert 'Smith' == user['last_name']
    >>> assert '1977-08-05' == user['birth_date']
    """

    def __init__(self, object_class, inner_schema):
        super(FromObject, self).__init__(inner_schema)
        self.object_class = object_class

    def check_extras(self, data, result):
        pass

    def is_key_in_data(self, key, data):
        return hasattr(data, key)

    def prepare_result(self, result):
        return result

    def get_value(self, key, data):
        return getattr(data, key)

    def prepare_data(self, data):
        return data


class FixedList(_Compilable):
    """
    Marks a field in a schema as a list of fixed length. Every element in the
    list has it's own type:

    >>> schema = Schema(FixedList(str, parse_decimal, int))
    >>> res = schema(['asd', '43.7', '8'])
    >>> assert ['asd', decimal.Decimal('43.7'), 8] == res

    You can use Python's list data type for FixedList specification:

    >>> schema = Schema([str, parse_decimal, int])
    >>> res = schema(['asd', '43.7', '8'])
    >>> assert ['asd', decimal.Decimal('43.7'), 8] == res

    >>> schema = Schema([ParseDateTime('%Y-%m-%d %H:%M.%S'), parse_decimal])
    >>> res = schema(['1985-12-1 15:36.21', '12.2'])
    >>> assert datetime(1985, 12, 1, 15, 36, 21) == res[0]
    >>> assert decimal.Decimal('12.2') == res[1]
    """

    def __init__(self, *inner_schemas):
        self.inner_schemas = inner_schemas

    @classmethod
    def from_iterable(cls, collection_of_values):
        return cls(*collection_of_values)

    def _compile(self, compiler):
        compiled_inner_schemas = []
        errors = []
        for idx, inn_sch in enumerate(self.inner_schemas):
            try:
                compiled_inner_schemas.append(compiler.compile(inn_sch))
            except MultipleSchemaError as e:
                errs = [ie for ie in e.errors]
                for e in errs:
                    e.path = [idx] + e.path
                errors.extend(errs)
            except SchemaError as e:
                e.path = [idx] + e.path
                errors.append(e)
            except Exception as e:
                errors.append(SchemaError(str(e), [idx]))
        if errors:
            raise MultipleSchemaError(errors)
        self.inner_schemas = compiled_inner_schemas
        return self

    def __call__(self, data):
        if not isinstance(data, list):
            raise ListInvalid('expected a list, got %r instead'
                              % type(data))
        if len(data) != len(self.inner_schemas):
            raise FixedListLengthInvalid(
                'the length of %r must be equal to %d'
                % (data, len(self.inner_schemas)))
        return [c(v) for c, v in zip(self.inner_schemas, data)]


def not_none(value):
    """
    This function ensures that passed value is not None:

    >>> schema = Schema(not_none)
    >>> assert 1 == schema(1)
    >>> try:
    ...     schema(None)
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """
    if value is None:
        raise NoneInvalid('value is None')
    else:
        return value


class StrictBoolean(object):
    """
    Consider using this class instead of good ol' bool if you need to ensure,
    that your True and False values are parsed from a narrow set of allowed
    values:

    >>> schema = Schema(StrictBoolean())
    >>> assert schema('yes')
    >>> assert not schema('no')
    >>> try:
    ...     schema('blah-blah')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """
    TRUE_VALUES = ['true', 't', 'yes', 'y', '1']
    FALSE_VALUES = ['false', 'f', 'no', 'n', '0']

    def __init__(self, true_values=TRUE_VALUES, false_values=FALSE_VALUES):
        self.true_values = true_values
        self.false_values = false_values

    def __call__(self, value):
        if value in [True, False]:
            return value
        else:
            value = str(value)
            if value in self.true_values:
                return True
            elif value in self.false_values:
                return False
            else:
                raise TypeError('value should be one of %r to be considered '
                                'True or one of %r to be considered False'
                                % (self.true_values, self.false_values))


def parse_decimal(value):
    """
    Convenience function to parse a decimal from string:

    >>> schema = Schema({Required('dec'): parse_decimal})
    >>> res = schema({'dec': '12.3'})
    >>> assert res
    >>> assert 'dec' in res
    >>> assert res['dec'] == decimal.Decimal('12.3')

    Will raise errors for float arguments:

    >>> schema = Schema({Required('dec'): parse_decimal})
    >>> try:
    ...     schema({'dec': 123.45})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """
    if isinstance(value, float):
        raise TypeInvalid('cannot convert decimal from float: '
                          'possible loss of precision - '
                          'convert a value to string '
                          'to force float conversion')
    try:
        if not isinstance(value, (strtype, int)):
            raise TypeInvalid('value for a decimal can be only one of '
                              '%r, got %r instead'
                              % ((strtype, int), type(value)))
        return decimal.Decimal(value)
    except (TypeError, ValueError, decimal.DecimalException) as e:
        raise TypeInvalid('bad decimal number %r: %r' % (value, e))


class ParseDateTime(object):
    """
    Tries to parse a datetime from a string in a schema:

    >>> schema = Schema({Required('aDateTime'): ParseDateTime()})
    >>> dt = schema({'aDateTime': '2000-05-01 12:36:51'})
    >>> assert dt
    >>> assert 'aDateTime' in dt
    >>> assert isinstance(dt['aDateTime'], datetime)
    >>> assert datetime(2000, 5, 1, 12, 36, 51) == dt['aDateTime']

    Datetime can only be parsed from strings:

    >>> schema = Schema({Required('aDateTime'): ParseDateTime()})
    >>> try:
    ...     schema({'aDateTime': 5})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    Incorrect datetime formats will raise error upon the schema creation:

    >>> try:
    ...     schema = Schema({Required('aDateTime'): ParseDateTime('%123')})
    ...     assert False, "an exception should've been raised"
    ... except SchemaError:
    ...     pass

    """

    def __init__(self, datetime_format='%Y-%m-%d %H:%M:%S'):
        try:
            datetime.strptime(datetime.utcnow().strftime(datetime_format),
                              datetime_format)
        except (TypeError, ValueError) as e:
            raise SchemaError(
                'bad datetime format %r: %r' % (datetime_format, e))
        self.datetime_format = datetime_format

    def __call__(self, value):
        if not isinstance(value, strtype):
            raise TypeInvalid('datetime can only be parsed from string')
        try:
            return datetime.strptime(value, self.datetime_format)
        except (TypeError, ValueError) as e:
            raise TypeInvalid('bad datetime %r: %r' % (value, e))


class FormatDateTime(object):
    """
    Formats datetime into a string:

    >>> schema = Schema({Required('aDateTime'): FormatDateTime()})
    >>> dt = schema({'aDateTime': datetime(2000, 5, 1, 12, 36, 51)})
    >>> assert dt
    >>> assert 'aDateTime' in dt
    >>> assert isinstance(dt['aDateTime'], str)
    >>> assert '2000-05-01 12:36:51' == dt['aDateTime']

    Datetime can only be formatted from datetime objects:

    >>> schema = Schema({Required('aDateTime'): FormatDateTime()})
    >>> try:
    ...     schema({'aDateTime': 5})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    Incorrect datetime formats will raise error upon the schema creation:

    >>> try:
    ...     schema = Schema({Required('aDateTime'): FormatDateTime('%123')})
    ...     assert False, "an exception should've been raised"
    ... except SchemaError:
    ...     pass

    """

    def __init__(self, datetime_format='%Y-%m-%d %H:%M:%S'):
        try:
            datetime.strptime(datetime.utcnow().strftime(datetime_format),
                              datetime_format)
        except (TypeError, ValueError) as e:
            raise SchemaError(
                'bad datetime format %r: %r' % (datetime_format, e))
        self.datetime_format = datetime_format

    def __call__(self, value):
        if not isinstance(value, datetime):
            raise TypeInvalid('datetime can only be parsed from string')
        return value.strftime(self.datetime_format)


class Length(object):
    """
    Ensures that the object validated is of specified length

    >>> schema = Schema(Length(2, 3))
    >>> assert 'as' == schema('as')
    >>> assert [3, 5] == schema([3, 5])
    >>> try:
    ...     schema('a')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> try:
    ...     schema('asdfg')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, min=None, max=None):
        if min is None and max is None:
            raise SchemaError('Length should include at least min or max'
                              'value as a valid integer')
        self.min = int(min) if min else None
        self.max = int(max) if max else None

    def __call__(self, data):
        l = len(data)
        if self.min is not None and l < self.min:
            raise LengthInvalid('data should have a langth at least of %d' % l)
        if self.max is not None and l > self.max:
            raise LengthInvalid('data should have a langth at most of %d' % l)
        return data


class Range(object):
    """
    Ensures that the object validated is in specified range:

    >>> schema = Schema(Range(3, 5))
    >>> assert 4 == schema(4)
    >>> try:
    ...     schema(3)
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> schema = Schema(Range(3, 5, min_inclusive=True))
    >>> assert 3 == schema(3)
    >>> try:
    ...     schema(2)
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, min=None, max=None,
                 min_inclusive=False, max_inclusive=False):
        if min is None and max is None:
            raise SchemaError('Length should include at least min or max'
                              'value as a valid integer')
        self.min = int(min) if min else None
        self.max = int(max) if max else None
        self.min_inclusive = min_inclusive
        self.max_inclusive = max_inclusive

    def __call__(self, data):
        if self.min is not None:
            if self.min_inclusive:
                is_min_ok = data >= self.min
            else:
                is_min_ok = data > self.min
            if not is_min_ok:
                raise Range('data should be at least %r' % self.min)
        if self.max is not None:
            if self.max_inclusive:
                is_max_ok = data <= self.max
            else:
                is_max_ok = data < self.max
            if not is_max_ok:
                raise Range('data should be at most %r' % self.max)
        return data


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


class Chain(_Compilable):
    """
    Convenience object to chain validators:

    >>> schema = Schema(Chain(str, Length(min=5)))
    >>> assert 'asdfg' == schema('asdfg')
    >>> try:
    ...     schema('as')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    >>> schema = Schema(Chain(int, Range(5, 8)))
    >>> assert 6 == schema('6')
    >>> try:
    ...     schema('9')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    >>> try:
    ...     schema('5')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    You can use Python's tuple data type for Chain specification:

    >>> schema = Schema((str, Length(min=5)))
    >>> assert 'asdfg' == schema('asdfg')
    >>> try:
    ...     schema('as')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def _assert_callable(self, f):
        if not callable(f):
            raise SchemaError('only callables should be passed'
                              ' to "To" objects')

    def __init__(self, *validators):
        for f in validators:
            self._assert_callable(f)
        self.validators = validators

    @classmethod
    def from_iterable(cls, validators):
        return cls(*validators)

    def _compile(self, compiler):
        compiled_validators = []
        for f in self.validators:
            compiled_validators.append(compiler.compile(f))
        self.validators = compiled_validators
        return self

    def __call__(self, data):
        for f in self.validators:
            data = f(data)
        return data
