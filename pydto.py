from datetime import datetime
import decimal
import random
import string
import sys

if sys.version_info >= (3,):
    iteritems = dict.items
else:
    iteritems = dict.iteritems

__author__ = 'Dmitry Kurkin'
__version__ = '0.1'


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


class UnknownInvalid(Invalid):
    """The key was not found in the schema."""


class TypeInvalid(Invalid):
    """The value found was not of required type."""


class DictInvalid(Invalid):
    """The value found was not a dict."""


class ListInvalid(Invalid):
    """The value found was not a list."""


class Schema(object):
    def __init__(self, schema):
        self.schema = self._compile_schema(schema)

    def _compile_schema(self, schema):
        if isinstance(schema, dict):
            return self._compile_dict(schema)
        elif isinstance(schema, Dict):
            schema.inner_schema = self._compile_schema(schema.inner_schema)
            return schema
        elif isinstance(schema, List):
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
                raise SchemaError(
                    'keys in schema should be instances of Marker class')
            schema[key] = self._compile_schema(inner_schema)
        return Dict(schema)

    def to_dto(self, data):
        try:
            return self.schema.to_dto(data)
        except MultipleInvalid:
            raise
        except Invalid as e:
            raise MultipleInvalid([e])

    def to_native(self, data):
        try:
            return self.schema.to_native(data)
        except MultipleInvalid:
            raise
        except Invalid as e:
            raise MultipleInvalid([e])

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
    """

    def to_native(self, data):
        return self.to_dto(data)

    def to_dto(self, data):
        return str(data)

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
    ...     assert False, 'an exception should be raised'
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
    ...     assert False, 'an exception should be raised'
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
    def __init__(self, inner_schema):
        if not isinstance(inner_schema, dict):
            raise SchemaError('expected a dictionary')
        self.inner_schema = inner_schema
        self.to_native_required_fields = {}
        self.to_native_optional_fields = {}
        self.to_dto_required_fields = {}
        self.to_dto_optional_fields = {}
        for key, value in iteritems(inner_schema):
            if isinstance(key, Required):
                self.to_native_required_fields[
                    key.dto_name] = key.native_name, value
                self.to_dto_required_fields[
                    key.native_name] = key.dto_name, value
            elif isinstance(key, Optional):
                self.to_native_optional_fields[
                    key.dto_name] = key.native_name, value
                self.to_dto_optional_fields[
                    key.native_name] = key.dto_name, value

    def to_dto(self, data):
        return self._convert_dict(data, False)

    def to_native(self, data):
        return self._convert_dict(data, True)

    def _convert_dict(self, data, to_native):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary')
        data = dict(data)
        result = {}
        errors = []
        if to_native:
            required_fields = self.to_native_required_fields
            optional_fields = self.to_native_optional_fields
        else:
            required_fields = self.to_dto_required_fields
            optional_fields = self.to_dto_optional_fields
        for key, (substitution_key, converter) in iteritems(required_fields):
            try:
                if key in data:
                    if to_native:
                        result[substitution_key] = converter.to_native(
                            data.pop(key))
                    else:
                        result[substitution_key] = converter.to_dto(
                            data.pop(key))
                else:
                    errors.append(
                        RequiredInvalid('required field is missing', [key]))
            except MultipleInvalid as e:
                errs = [ie for ie in e.errors]
                for e in errs:
                    e.path = [key] + e.path
                errors.extend(errs)
            except Invalid as e:
                e.path = [key] + e.path
                errors.append(e)
        for data_key, data_value in iteritems(data):
            try:
                if data_key not in optional_fields:
                    errors.append(
                        UnknownInvalid('encountered an unknown field',
                                       [data_key]))
                else:
                    substitution_key, converter = optional_fields[data_key]
                    if to_native:
                        result[substitution_key] = converter.to_native(
                            data_value)
                    else:
                        result[substitution_key] = converter.to_dto(data_value)
            except MultipleInvalid as e:
                errs = [ie for ie in e.errors]
                for e in errs:
                    e.path = [data_key] + e.path
                errors.extend(errs)
            except Invalid as e:
                e.path = [data_key] + e.path
                errors.append(e)
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
        for k, converter in self.to_native_required_fields.values():
            result[k] = converter.mock()
        for k, converter in self.to_native_optional_fields.values():
            if random.choice((True, False)):
                result[k] = converter.mock()
        return result


class List(Converter):
    def __init__(self, inner_schema):
        self.inner_schema = inner_schema

    def _convert_list(self, data, to_native):
        if not isinstance(data, list):
            raise ListInvalid('expected a list')
        result = []
        errors = []
        for idx, d in enumerate(data):
            try:
                if to_native:
                    result.append(self.inner_schema.to_native(d))
                else:
                    result.append(self.inner_schema.to_dto(d))
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
        return self._convert_list(data, False)

    def to_native(self, data):
        return self._convert_list(data, True)

    def mock(self):
        """
        >>> mocked_list = Schema(List({
        ...     Required('a'): DateTime(), Optional('b'): String()
        ... })).mock()
        >>> assert isinstance(mocked_list, list)
        """

        return [self.inner_schema.mock() for _ in
                range(random.randrange(3) + 1)]
