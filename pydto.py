from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
import decimal
import random
import string
import sys

if sys.version_info >= (3,):
    iteritems = dict.items
    strtype = str
else:
    iteritems = dict.iteritems
    # flake8: noqa
    strtype = basestring

__author__ = 'Dmitry Kurkin'
__version__ = '0.3.2'


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


class RequiredInvalid(Invalid):
    """Required field was missing."""


class InclusiveInvalid(Invalid):
    """Inclusive field was missing, while other inclusives were present."""


class UnknownInvalid(Invalid):
    """The key was not found in the schema."""


class TypeInvalid(Invalid):
    """The value found was not of required type."""


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


class Schema(object):
    def __init__(self, schema):
        self.schema = self._compile_schema(schema)

    def _compile_schema(self, schema):
        if isinstance(schema, dict):
            return self._compile_dict(schema)
        elif isinstance(schema, (Dict, Object, List)):
            schema.inner_schema = self._compile_schema(schema.inner_schema)
            return schema
        elif isinstance(schema, Converter):
            return schema
        else:
            raise SchemaError(
                '%s is not a valid value in schema' % type(schema))

    def _compile_dict(self, schema):
        for key, inner_schema in iteritems(schema):
            if not isinstance(key, Marker):
                raise SchemaError('keys in schema should'
                                  ' be instances of Marker class')
            schema[key] = self._compile_schema(inner_schema)
        return Dict(schema)

    @classmethod
    @contextmanager
    def _invalids_in_control(cls):
        try:
            yield
        except MultipleInvalid:
            raise
        except Invalid as e:
            raise MultipleInvalid([e])

    def _populate(self, dict_to_populate, data, retrieval_func):
        if not isinstance(dict_to_populate, dict):
            raise DictInvalid('object to populate should a dictionary')
        with self._invalids_in_control():
            result = retrieval_func(data)
            for k, v in iteritems(result):
                if k in dict_to_populate:
                    raise KeyPopulateInvalid('key is already present'
                                             ' in the dictionary', [k])
                result[k] = v
            dict_to_populate.update(result)

    def to_dto(self, data):
        with self._invalids_in_control():
            return self.schema.to_dto(data)

    def to_native(self, data):
        with self._invalids_in_control():
            return self.schema.to_native(data)

    def populate_dto_dict(self, dto_dict, data):
        """
        Populates an arbitrary dictionary with fields from data, validated and
        converted to DTO by current schema:

        >>> schema = Schema({Required('a_dec'): Decimal()})
        >>> d = {'z': 'zzz'}
        >>> schema.populate_dto_dict(d, {'a_dec': decimal.Decimal(10.5)})
        >>> assert '10.5' == d['a_dec']
        >>> assert 'zzz' == d['z']
        """
        self._populate(dto_dict, data, self.schema.to_dto)

    def populate_native_dict(self, native_dict, data):
        """
        Populates an arbitrary dictionary with fields from data, validated and
        converted to native by current schema:

        >>> schema = Schema({Required('a_dec'): Decimal()})
        >>> d = {'z': 'zzz'}
        >>> schema.populate_native_dict(d, {'a_dec': '10.5'})
        >>> assert decimal.Decimal('10.5') == d['a_dec']
        >>> assert 'zzz' == d['z']
        """
        self._populate(native_dict, data, self.schema.to_native)

    def populate_native_object(self, obj, data):
        """
        Populates an arbitrary object with fields from data, validated and
        converted to native by current schema:

        >>> schema = Schema({Required('a_string'): String()})
        >>> class Some(object):
        ...     pass
        >>> s = Some()
        >>> schema.populate_native_object(s, {'a_string': 'hello'})
        >>> assert 'hello' == s.a_string
        """
        with self._invalids_in_control():
            result = self.schema.to_native(data)
            for k, v in iteritems(result):
                if hasattr(obj, k):
                    raise FieldPopulateInvalid('object %r already has a field'
                                               % obj, [k])
            for k, v in iteritems(result):
                setattr(obj, k, v)

    def mock(self):
        return self.schema.mock()


class Marker(object):
    def __init__(self, dto_name=None, native_name=None):
        if not dto_name and not native_name:
            raise SchemaError('at least one name should be present in a key')
        self._dto_name = dto_name
        self._native_name = native_name

    @property
    def dto_name(self):
        return self._dto_name or self._native_name

    @property
    def native_name(self):
        return self._native_name or self._dto_name


class Required(Marker):
    pass


class Optional(Marker):
    pass


class Inclusive(Marker):
    """
    Marks a field in a schema as inclusive. At least two inclusive fields
    should be present:

    >>> try:
    ...     schema = Schema({
    ...         Inclusive('one'): String()
    ...     })
    ...     assert False, "an error should've been raised"
    ... except SchemaError:
    ...     pass

    When two or more fields are inclusive, it means that either all of them
    are present or all of them are missing:

    >>> schema = Schema({
    ...     Inclusive('one'): String(),
    ...     Inclusive('two'): String()
    ... })
    >>> res = schema.to_native({'one': '1', 'two': '2'})
    >>> assert res == {'one': '1', 'two': '2'}
    >>> assert {} == schema.to_native({})
    >>> try:
    ...     schema.to_native({'one': '1'})
    ...     assert False, "an error should've been raised"
    ... except MultipleInvalid:
    ...     pass
    """

    def __init__(self, dto_name=None, native_name=None, monitor=None):
        self.monitor = monitor
        super(Inclusive, self).__init__(dto_name, native_name)

    def monitor(self, monitor):
        self.monitor = monitor
        return self


class Converter(object):
    def to_dto(self, data):
        raise NotImplementedError()

    def to_native(self, data):
        raise NotImplementedError()

    def mock(self):
        raise NotImplementedError()


class String(Converter):
    """

    Marks a field in a schema as a string field:

    >>> schema = Schema({Required('aString'): String()})
    >>> result = schema.to_native({'aString': 'just a simple string'})
    >>> assert 'aString' in result
    >>> assert result['aString'] == 'just a simple string'

    >>> schema = Schema({Required('aString'): String()})
    >>> try:
    ...     schema.to_native({})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid as e:
    ...     pass
    """

    def to_native(self, data):
        return self.to_dto(data)

    def to_dto(self, data):
        result = str(data)
        if not result:
            return None
        return result

    def mock(self):
        """
        >>> mocked_string = String().mock()
        >>> assert isinstance(mocked_string, str)
        """
        return ''.join(
            random.choice(string.ascii_letters + string.digits) for _ in
            range(10))


class Integer(Converter):
    """

    Marks a field in a schema as an integer number field:

    >>> schema = Schema({Required('anInt'): Integer()})
    >>> result = schema.to_native({'anInt': 5})
    >>> assert 'anInt' in result
    >>> result['anInt']
    5
    >>> result = schema.to_native({'anInt': '5'})
    >>> assert 'anInt' in result
    >>> result['anInt']
    5

    Will raise TypeInvalid when supplied value is not an integer number:

    >>> try:
    ...     result = schema.to_native({'anInt': 'a'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid as e:
    ...     assert isinstance(e.errors[0], TypeInvalid)
    ...     assert e.errors[0].path == ['anInt'], '%r' % e.errors[0].path


    """

    def to_native(self, data):
        return self.to_dto(data)

    def to_dto(self, data):
        try:
            return int(data)
        except (TypeError, ValueError):
            raise TypeInvalid('expected an integer, got %r instead' % data)

    def mock(self):
        """
        >>> mocked_int = Integer().mock()
        >>> assert isinstance(mocked_int, int)
        """
        return random.randint(-1000, 1000)


class Boolean(Converter):
    """

    Marks a field in a schema as a boolean field:

    >>> schema = Schema({Required('aBool'): Boolean()})
    >>> result = schema.to_native({'aBool': True})
    >>> assert 'aBool' in result
    >>> result['aBool']
    True
    >>> result = schema.to_native({'aBool': 'y'})
    >>> assert 'aBool' in result
    >>> result['aBool']
    True

    However if a value is passed to a strict Boolean (which it is by default)
    that not one of TRUTH_VALUES or FALSE_VALUES,
    then a TypeInvalid exception is raised:

    >>> try:
    ...     result = schema.to_native({'aBool': 'a'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid as e:
    ...     assert isinstance(e.errors[0], TypeInvalid)
    ...     assert e.errors[0].path == ['aBool'], '%r' % e.errors[0].path

    """
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

    def to_dto(self, data):
        if self.strict:
            if data not in [True, False]:
                raise TypeInvalid('%r is not a boolean' % data)
            return data
        else:
            return bool(data)

    def to_native(self, data):
        if data in [True, False]:
            return data
        else:
            if self.strict:
                data = str(data)
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
                return bool(data)

    def mock(self):
        """
        >>> mocked_bool = Boolean().mock()
        >>> assert isinstance(mocked_bool, bool)
        """
        return random.choice((True, False))


class DateTime(Converter):
    """

    Marks a field in a schema as a datetime field:

    >>> schema = Schema({Required('aDate'): DateTime('%Y-%m-%d %H:%M.%S')})
    >>> result = schema.to_native({'aDate': '2000-02-14 15:34.40'})
    >>> assert 'aDate' in result
    >>> assert result['aDate'] == datetime(2000, 2, 14, 15, 34, 40)
    >>> result = schema.to_dto({'aDate': datetime(2000, 2, 13, 15, 34, 40)})
    >>> assert 'aDate' in result
    >>> assert result['aDate'] == '2000-02-13 15:34.40'

    Will raise a SchemaError upon initialization if the datetime
    format string is incorrect:

    >>> try:
    ...     schema = Schema({Required('aDate'): DateTime('%#')})
    ...     assert False, 'an exception should be raised'
    ... except SchemaError:
    ...     pass

    Will raise TypeInvalid when supplied with a bad datetime string or
    bad datetime object:

    >>> schema = Schema({Required('aDate'): DateTime('%Y')})
    >>> try:
    ...     result = schema.to_native({'aDate': 'X'})
    ...     assert False, 'an exception should be raised'
    ... except MultipleInvalid as e:
    ...     assert isinstance(e.errors[0], TypeInvalid)
    ...     assert e.errors[0].path == ['aDate'], '%r' % e.errors[0].path
    >>> try:
    ...     result = schema.to_dto({'aDate': None})
    ...     assert False, 'an exception should be raised'
    ... except MultipleInvalid as e:
    ...     assert isinstance(e.errors[0], TypeInvalid)
    ...     assert e.errors[0].path == ['aDate'], '%r' % e.errors[0].path
    """

    def __init__(self, datetime_format='%Y-%m-%d %H:%M.%S'):
        try:
            datetime.strptime(datetime.utcnow().strftime(datetime_format),
                              datetime_format)
        except (TypeError, ValueError) as e:
            raise SchemaError(
                'bad datetime format %r: %r' % (datetime_format, e))
        self.datetime_format = datetime_format

    def to_native(self, data):
        try:
            return datetime.strptime(data, self.datetime_format)
        except (TypeError, ValueError) as e:
            raise TypeInvalid('bad datetime %r: %r' % (data, e))

    def to_dto(self, data):
        if not isinstance(data, datetime):
            raise TypeInvalid('bad datetime object %r ' % data)
        return data.strftime(self.datetime_format)

    def mock(self):
        """
        >>> mocked_dt = DateTime().mock()
        >>> assert isinstance(mocked_dt, datetime)
        """
        return datetime(
            random.randint(2000, 2020),
            random.randint(1, 12),
            random.randint(1, 28),
            random.randint(0, 23),
            random.randint(0, 59),
            random.randint(0, 59)
        )


class Decimal(Converter):
    """

    Marks a field in a schema as a decimal field:

    >>> schema = Schema({Required('aDec'): Decimal()})
    >>> result = schema.to_native({'aDec': '156.15'})
    >>> assert 'aDec' in result
    >>> assert result['aDec'] == decimal.Decimal('156.15')
    >>> result = schema.to_dto({'aDec': decimal.Decimal('123.123')})
    >>> assert 'aDec' in result
    >>> assert result['aDec'] == '123.123'

    Will raise TypeInvalid when supplied with a bad decimal string:

    >>> schema = Schema({Required('aDec'): Decimal()})
    >>> try:
    ...     result = schema.to_native({'aDec': 'asd'})
    ...     assert False, 'an exception should be raised'
    ... except MultipleInvalid as e:
    ...     assert isinstance(e.errors[0], TypeInvalid)
    ...     assert e.errors[0].path == ['aDec'], '%r' % e.errors[0].path
    """

    def to_native(self, data):
        try:
            return decimal.Decimal(data)
        except (TypeError, ValueError, decimal.DecimalException) as e:
            raise TypeInvalid('bad decimal number %r: %r' % (data, e))

    def to_dto(self, data):
        if not isinstance(data, decimal.Decimal):
            raise TypeInvalid('bad decimal number %r' % data)
        return str(data)

    def mock(self):
        """
        >>> mocked_decimal = Decimal().mock()
        >>> assert isinstance(mocked_decimal, decimal.Decimal)
        """
        return decimal.Decimal(random.randrange(10000)) / 100


class Dict(Converter):
    """
    Marks a field in a schema as a dictionary field, containing objects, that
    conform to inner schema:

    >>> schema = Schema({
    ...     Required('aDecimal'): Decimal(),
    ...     Optional('someString'): String(),
    ...     Required('innerDict'): {
    ...         Required('anInt'): Integer()
    ...     }
    ... })
    >>> res = schema.to_native({'aDecimal': '12.3',
    ...                         'innerDict': {'anInt': 5}})
    >>> assert res == {'aDecimal': decimal.Decimal('12.3'),
    ...                'innerDict': {'anInt': 5}}

    It is possible to use just a Python's dictionary literal,
    instead of using this object. So this:

    >>> schema = Schema(Dict({
    ...     Required('aString'): String()
    ... }))

    is effectively the same as:

    >>> schema = Schema({
    ...     Required('aString'): String()
    ... })

    Unknown fields will raise errors:

    >>> schema = Schema({
    ...     Optional('aString'): String()
    ... })
    >>> try:
    ...     schema.to_native({'anUnknownString': 'hello'})
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass

    """

    def __init__(self, inner_schema):
        if not isinstance(inner_schema, dict):
            raise SchemaError('expected a dictionary, got %r instead'
                              % inner_schema)
        self.inner_schema = inner_schema
        self.inclusive_by_dto_name = defaultdict(set)
        self.inclusive_by_native_name = defaultdict(set)
        for marker, converter in iteritems(inner_schema):
            if isinstance(marker, Inclusive):
                self.inclusive_by_dto_name[marker.monitor] \
                    .add(marker.dto_name)
                self.inclusive_by_native_name[marker.monitor] \
                    .add(marker.native_name)
        for monitor, names in iteritems(self.inclusive_by_native_name):
            if len(names) == 1:
                m_name = 'default' if monitor is None else repr(monitor)
                raise SchemaError('only one inclusive field under %s '
                                  'monitor' % m_name)

    def to_dto(self, data):
        return self._convert_dict(data, False)

    def to_native(self, data):
        return self._convert_dict(data, True)

    def _process_value(self, converter, value, name, errors):
        try:
            return converter(value)
        except MultipleInvalid as e:
            errs = [ie for ie in e.errors]
            for e in errs:
                e.path = [name] + e.path
            errors.extend(errs)
        except Invalid as e:
            e.path = [name] + e.path
            errors.append(e)

    def _convert_dict(self, data, to_native):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary, got %r instead'
                              % data)
        # Make a copy of incoming dictionary to pop items
        # without changing incoming data
        data = dict(data)
        result = {}
        inclusive = defaultdict(set)
        errors = []
        for marker, converter in iteritems(self.inner_schema):
            if to_native:
                key, substitution_key = marker.dto_name, marker.native_name
                method = getattr(converter, 'to_native')
            else:
                key, substitution_key = marker.native_name, marker.dto_name
                method = getattr(converter, 'to_dto')
            if key in data:
                value = self._process_value(method, data.pop(key), key, errors)
                if isinstance(marker, Inclusive):
                    inclusive[marker.monitor].add(substitution_key)
                result[substitution_key] = value
            else:
                if isinstance(marker, Required):
                    errors.append(RequiredInvalid('required field is missing',
                                                  [key]))
        if inclusive:
            if to_native:
                reference_inclusive = self.inclusive_by_dto_name
            else:
                reference_inclusive = self.inclusive_by_native_name
            for monitor, inclusive_group in iteritems(inclusive):
                diff = reference_inclusive[monitor] - inclusive_group
                if diff:
                    errors.append(
                        InclusiveInvalid('When %r fields are present, these'
                                         ' fields should be present too:'
                                         % list(inclusive_group),
                                         [list(diff)]))
        if data:
            for unknown_field in data.keys():
                errors.append(UnknownInvalid('unknown field',
                                             [unknown_field]))
        if errors:
            raise MultipleInvalid(errors)
        return result

    def mock(self):
        """
        >>> mocked_dict = Schema(
        ...     {Required('a'): DateTime(), Optional('b'): String()}
        ... ).mock()
        >>> assert isinstance(mocked_dict, dict)
        """
        result = {}
        for marker, converter in iteritems(self.inner_schema):
            if isinstance(marker, Required):
                result[marker.native_name] = converter.mock()
            elif isinstance(marker, Optional):
                if random.choice((True, False)):
                    result[marker.native_name] = converter.mock()
            elif isinstance(marker, Inclusive):
                pass
        return result


class List(Converter):
    """
    Marks a field in a schema as a list field, containing objects, that
    conform to inner schema:

    >>> schema = Schema(List(Decimal()))
    >>> res = schema.to_native([1, '2.5', 3])
    >>> assert res == [decimal.Decimal(1), decimal.Decimal('2.5'),
    ...                decimal.Decimal(3)]
    """

    def __init__(self, inner_schema):
        self.inner_schema = inner_schema

    def _convert_list(self, data, convertor):
        if not isinstance(data, list):
            raise ListInvalid('expected a list, got %r instead' % data)
        result = []
        errors = []
        for idx, d in enumerate(data):
            try:
                result.append(convertor(d))
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

    def to_dto(self, data):
        return self._convert_list(data, self.inner_schema.to_dto)

    def to_native(self, data):
        return self._convert_list(data, self.inner_schema.to_native)

    def mock(self):
        """
        >>> mocked_list = Schema(List({
        ...     Required('a'): DateTime(), Optional('b'): String()
        ... })).mock()
        >>> assert isinstance(mocked_list, list)
        """

        return [self.inner_schema.mock() for _ in
                range(random.randrange(3) + 1)]


class Object(Converter):
    """

    Marks a field in a schema as an object field:

    >>> class User(object):
    ...     def __init__(self, first_name, last_name, birth_date):
    ...         self.first_name = first_name
    ...         self.last_name = last_name
    ...         self.birth_date = birth_date
    >>> schema = Schema(Object(User, {
    ...     Required('first_name'): String(),
    ...     Required('last_name'): String(),
    ...     Required('birth_date'): DateTime('%Y-%m-%d')
    ... }))
    >>> user = schema.to_native({
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
        self.inner_schema = inner_schema

    def to_dto(self, data):
        if not isinstance(data, self.object_class):
            raise ObjectInvalid('expected a %s instance, got %r instead'
                                % (self.object_class, data))
        dict_data = dict([(n.native_name, getattr(data, n.native_name))
                          for n in self.inner_schema.inner_schema.keys()])
        return self.inner_schema.to_dto(dict_data)

    def to_native(self, data):
        dict_data = self.inner_schema.to_native(data)
        if self.object_constructor is None:
            return self.object_class(**dict_data)
        else:
            o = self.object_class()
            self.object_constructor(o, **dict_data)
            return o

    def mock(self):
        """
        >>> class User(object):
        ...     def __init__(self, first_name):
        ...         self.first_name = first_name
        >>> mocked_user = schema = Schema(Object(User, {
        ...     Required('first_name'): String()
        ... })).mock()
        >>> assert isinstance(mocked_user, User)
        """
        kwargs = self.inner_schema.mock()
        if self.object_constructor is None:
            return self.object_class(**kwargs)
        else:
            return self.object_constructor(self.object_class(), **kwargs)


class UnvalidatedDict(Converter):
    """

    Marks a field in a schema as an unvalidated dictionary: a value should be
    a dictionary, but inner schema will not be validated or converted.

    >>> schema = Schema({Required('dict'): UnvalidatedDict()})
    >>> res = schema.to_native({'dict': {'aField': 'hello'}})
    >>> assert res
    >>> assert 'dict' in res
    >>> assert {'aField': 'hello'} == res['dict']
    >>> try:
    ...     schema.to_native(object())
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    """

    def to_dto(self, data):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary, got %r instead'
                              % data)
        return data

    def to_native(self, data):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary, got %r instead'
                              % data)
        return data

    def mock(self):
        return {}


class UnvalidatedList(Converter):
    """

    Marks a field in a schema as an unvalidated list: a value should be
    a list, but inner schema will not be validated or converted.

    >>> schema = Schema({Required('list'): UnvalidatedList()})
    >>> res = schema.to_native({'list': ['hello', 2]})
    >>> assert res
    >>> assert 'list' in res
    >>> assert ['hello', 2] == res['list']
    >>> try:
    ...     schema.to_native(object())
    ...     assert False, "an exception should've been raised"
    ... except MultipleInvalid:
    ...     pass
    """

    def to_dto(self, data):
        if not isinstance(data, list):
            raise ListInvalid('expected a list, got %r instead' % data)
        return data

    def to_native(self, data):
        if not isinstance(data, list):
            raise ListInvalid('expected a list, got %r instead' % data)
        return data

    def mock(self):
        return []
