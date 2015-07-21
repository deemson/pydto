from collections import defaultdict
import sys
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
__version__ = '0.4.1'


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


class Undefined(object):
    def __nonzero__(self):
        return False

    def __repr__(self):
        return '...'


UNDEFINED = Undefined()


class Extras(object):
    values = ['prevent', 'allow', 'remove']
    PREVENT, ALLOW, REMOVE = values


class Schema(object):
    """
    PyDTO main object.
    """
    PRIMITIVE_TYPES = (strtype, int, decimal.Decimal, float,
                       complex, bool)

    def __init__(self, schema, extras=Extras.PREVENT):
        self.extras = extras
        self._schema = self._compile(schema)

    def __call__(self, data):
        try:
            return self._schema(data)
        except MultipleInvalid:
            raise
        except Invalid as e:
            raise MultipleInvalid([e])
        except Exception as e:
            raise MultipleInvalid([Invalid(str(e))])

    def _compile(self, schema):
        if isinstance(schema, dict):
            return self._compile_dict(schema, self.extras)
        elif isinstance(schema, (list, tuple)):
            return self._compile_fixed_list(schema)
        elif isinstance(schema, Dict):
            extras = schema.extras or self.extras
            return self._compile_dict(schema.inner_schema, extras)
        elif isinstance(schema, List):
            return self._compile_list(schema.inner_schema)
        elif isinstance(schema, FixedList):
            return self._compile_fixed_list(schema.inner_schemas)
        elif isinstance(schema, self.PRIMITIVE_TYPES):
            return self._compile_literal(schema, type(schema))
        elif isinstance(schema, Literal):
            return self._compile_literal(schema.value, schema.converter)
        elif isinstance(schema, set):
            return self._compile_enum(schema)
        elif isinstance(schema, Enum):
            return self._compile_enum(schema.values)
        elif isinstance(schema, MakeObject):
            extras = schema.extras or self.extras
            return self._compile_make_object(schema, extras)
        elif callable(schema):
            return schema
        else:
            raise SchemaError('%s is not a valid value in schema'
                              % type(schema))

    def _compile_dict(self, dict_schema, extras):
        compiled_inner_schema = {}
        inclusive_monitors = defaultdict(set)
        exclusive_monitors = defaultdict(set)
        source_names = set()
        destination_names = set()
        errors = []
        for key, value in iteritems(dict_schema):
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
            try:
                compiled_inner_schema[key] = self._compile(value)
            except MultipleSchemaError as e:
                errs = [ie for ie in e.errors]
                for e in errs:
                    e.path = [key.name] + e.path
                errors.extend(errs)
            except SchemaError as e:
                e.path = [key.name] + e.path
                errors.append(e)
            except Exception as e:
                errors.append(SchemaError(str(e), [key.name]))
            if isinstance(key, Inclusive):
                inclusive_monitors[key._monitor].add(key.name)
            if isinstance(key, Exclusive):
                inclusive_monitors[key._monitor].add(key.name)
        if errors:
            raise MultipleSchemaError(errors)

        def compiled_dict(data):
            if not isinstance(data, dict):
                raise DictInvalid('expected a dictionary, got %r instead'
                                  % data)
            # Make a copy of incoming dictionary to pop items
            # without changing data
            data = dict(data)
            result = {}
            inclusive = defaultdict(set)
            exclusive = defaultdict(set)
            errors = []
            for marker, converter in iteritems(compiled_inner_schema):
                key = marker.name
                substitution_key = marker.rename_to or key
                if key in data:
                    try:
                        if isinstance(marker, Inclusive):
                            inclusive[marker._monitor].add(key)
                        if isinstance(marker, Exclusive):
                            exclusive[marker._monitor].add(key)
                        value = converter(data.pop(key))
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
                        errors.append(Invalid(str(e), [key]))

                else:
                    if isinstance(marker, Required):
                        errors.append(
                            RequiredInvalid('required field is missing',
                                            [key]))
            if inclusive:
                for monitor, values in iteritems(inclusive):
                    missing = inclusive_monitors[monitor] - values
                    if missing:
                        present = inclusive_monitors[monitor].intersection(
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
            if data:
                if extras == Extras.PREVENT:
                    for unknown_field in data.keys():
                        errors.append(UnknownInvalid('unknown field',
                                                     [unknown_field]))
                elif extras == Extras.ALLOW:
                    for unknown_field in data.keys():
                        result[unknown_field] = data[unknown_field]
            if errors:
                raise MultipleInvalid(errors)
            return result

        return compiled_dict

    def _compile_list(self, list_schema):
        compiled_inner_schema = self._compile(list_schema)

        def compiled_list(data):
            if not isinstance(data, list):
                if not isinstance(data, list):
                    raise ListInvalid('expected a list, got %r instead'
                                      % type(data))
            result = []
            errors = []
            for idx, d in enumerate(data):
                try:
                    result.append(compiled_inner_schema(d))
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

        return compiled_list

    def _compile_literal(self, value, converter):
        def compiled_literal(data):
            converted_data = converter(data)
            if value != converted_data:
                raise LiteralInvalid('value %r is not equal to %r'
                                     % (converted_data, value))
            return converted_data

        return compiled_literal

    def _compile_enum(self, values):
        errors = []
        compiled_values = []
        for idx, v in enumerate(values):
            if isinstance(v, self.PRIMITIVE_TYPES):
                compiled_values.append(self._compile_literal(v, type(v)))
            elif isinstance(v, Literal):
                compiled_values.append(self._compile_literal(v.value,
                                                             v.converter))
            else:
                errors.append(SchemaError('only literal values '
                                          'allowed in Enum, got %r' % v))
        if errors:
            raise MultipleSchemaError(errors)

        compiled_values = [self._compile(v) for v in values]

        def compiled_enum(data):
            for v in compiled_values:
                try:
                    return v(data)
                except:
                    pass
            raise EnumInvalid('none of enum values matches %r' % data)

        return compiled_enum

    def _compile_fixed_list(self, fixed_list_schema):
        compiled_inner_schemas = []
        errors = []
        for idx, inn_sch in enumerate(fixed_list_schema):
            try:
                compiled_inner_schemas.append(self._compile(inn_sch))
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

        def compiled_fixed_list(data):
            if not isinstance(data, list):
                raise ListInvalid('expected a list, got %r instead'
                                  % type(data))
            if len(data) != len(compiled_inner_schemas):
                raise FixedListLengthInvalid(
                    'the length of %r must be equal to %d'
                    % (data, len(compiled_inner_schemas)))
            return [c(v) for c, v in zip(compiled_inner_schemas, data)]

        return compiled_fixed_list

    def _compile_make_object(cls, make_object_schema, extras):
        compiled_dict = cls._compile_dict(make_object_schema.inner_schema,
                                          extras)

        def compiled_make_object(data):
            dict_data = compiled_dict(data)
            if make_object_schema.object_constructor is None:
                return make_object_schema.object_class(**dict_data)
            else:
                o = make_object_schema.object_class()
                make_object_schema.object_constructor(o, **dict_data)
                return o

        return compiled_make_object


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


class SpecialForm(object):
    def __call__(self, *args, **kwargs):
        raise SchemaError('special forms must not be called directly. '
                          'You must pass them to PyDTO Schema '
                          'constructor instead')


class Literal(SpecialForm):
    """
    Marks a field in a schema as a literal value:

    >>> schema = Schema({Required('aString'): Literal(str, 'hello')})
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

    def __init__(self, converter, value):
        self.converter = converter
        self.value = value


class Dict(SpecialForm):
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

    def __init__(self, inner_schema, extras=None):
        if not isinstance(inner_schema, dict):
            raise SchemaError('expected a dictionary, got %r instead'
                              % inner_schema)
        self.inner_schema = inner_schema
        self.extras = extras


class List(SpecialForm):
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


class Enum(SpecialForm):
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


class MakeObject(SpecialForm):
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
                 object_initializator='__init__', extras=None):
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
        self.inner_schema = inner_schema
        self.extras = extras


class FixedList(SpecialForm):
    """
    Marks a field in a schema as a list of fixed length. Every element in the
    list has it's own type:

    >>> schema = Schema(FixedList(str, parse_decimal, int))
    >>> res = schema(['asd', '43.7', '8'])
    >>> assert ['asd', decimal.Decimal('43.7'), 8] == res

    You can use Python's list or tuple data types for
    FixedList specification:

    >>> schema = Schema([str, parse_decimal, int])
    >>> res = schema(['asd', '43.7', '8'])
    >>> assert ['asd', decimal.Decimal('43.7'), 8] == res

    >>> schema = Schema((ParseDateTime('%Y-%m-%d %H:%M.%S'), parse_decimal))
    >>> res = schema(['1985-12-1 15:36.21', '12.2'])
    >>> assert datetime(1985, 12, 1, 15, 36, 21) == res[0]
    >>> assert decimal.Decimal('12.2') == res[1]
    """

    def __init__(self, *inner_schemas):
        self.inner_schemas = inner_schemas


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


class NotNone(object):
    """
    A convenience decorator alternative to not_none function:

    >>> schema = Schema(NotNone(int))
    >>> assert 5 == schema('5')
    >>> try:
    ...     schema(None)
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, f):
        if not callable(f):
            raise SchemaError('NotNone is applicable only to callables')
        self._f = f

    def __call__(self, value):
        return self._f(not_none(value))


TRUE_VALUES = ['true', 't', 'yes', 'y', '1']
FALSE_VALUES = ['false', 'f', 'no', 'n', '0']


def strict_boolean(value):
    """
    Consider using this class instead of good ol' bool if you need to ensure,
    that your True and False values are parsed from a narrow set of allowed
    values:

    >>> schema = Schema(strict_boolean)
    >>> assert schema('yes')
    >>> assert not schema('no')
    >>> try:
    ...     schema('blah-blah')
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """
    if value in [True, False]:
        return value
    else:
        value = str(value)
        if value in TRUE_VALUES:
            return True
        elif value in FALSE_VALUES:
            return False
        else:
            raise TypeError('value should be one of %r to be considered '
                            'True or one of %r to be considered False'
                            % (TRUE_VALUES, FALSE_VALUES))


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


class And(object):
    """

    Successively applies a list of callables to a value:

    >>> schema = Schema(And(not_none, int))
    >>> assert 5 == schema('5')
    >>> try:
    ...     schema(None)
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid as e:
    ...     assert isinstance(e.errors[0], NoneInvalid)

    The list of callables must not be empty:

    >>> try:
    ...     schema = Schema(And())
    ...     assert False, "an exception should've been raised"
    ... except SchemaError:
    ...     pass

    And there must be no objects other than callables:

    >>> try:
    ...     schema = Schema(And(1))
    ...     assert False, "an exception should've been raised"
    ... except SchemaError:
    ...     pass

    """

    def __init__(self, *functions):
        if not functions:
            raise SchemaError('no functions provided to And')
        for f in functions:
            if not callable(f):
                raise SchemaError('only callables can be passed to And')
        self._functions = functions

    def __call__(self, data):
        value = data
        for f in self._functions:
            value = f(value)
        return value
