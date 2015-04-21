from contextlib import contextmanager
from datetime import datetime


@contextmanager
def raises(exc, msg=None):
    try:
        yield
    except exc as e:
        if msg is not None:
            assert str(e) == msg, '%r != %r' % (str(e), msg)


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

    def __init__(self, message, path=None, error_message=None, error_type=None):
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


class RequiredFieldInvalid(Invalid):
    """Required field was missing."""


class UnknownFieldInvalid(Invalid):
    """The key was not found in the schema."""


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
        elif isinstance(schema, Converter):
            return schema
        else:
            raise SchemaError('{} is not a valid value in schema'.format(type(schema)))

    def _compile_dict(self, schema):
        for key, inner_schema in schema.iteritems():
            if not isinstance(key, Marker):
                raise SchemaError('keys in schema should be instances of Marker class')
            schema[key] = self._compile_schema(inner_schema)
        return Dict(schema)

    def to_dto(self, data):
        return self.schema.to_dto(data)

    def to_native(self, data):
        return self.schema.to_native(data)


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


class String(Converter):
    """

    Marks a field in a schema as a simple string field:

    >>> schema = Schema({Required('aString'): String()})
    >>> result = schema.to_native({'aString': 'just a simple string'})
    >>> assert 'aString' in result
    >>> assert result['aString'] == 'just a simple string'
    """
    def to_native(self, data):
        return self.to_dto(data)

    def to_dto(self, data):
        return str(data)


class DateTime(Converter):
    """

    Marks a field in a schema as a datetime field:

    >>> schema = Schema({Required('aDate'): DateTime('%Y-%m-%d %H:%M.%S')})
    >>> result = schema.to_native({'aDate': '2000-02-15 15:34.40'})
    >>> assert 'aDate' in result
    >>> assert result['aDate'] == datetime(2000, 2, 15, 15, 34, 40)
    """
    def __init__(self, datetime_format):
        self.datetime_format = datetime_format

    def to_native(self, data):
        return datetime.strptime(data, self.datetime_format)

    def to_dto(self, data):
        return str(data)


class Dict(Converter):
    def __init__(self, inner_schema):
        if not isinstance(inner_schema, dict):
            raise SchemaError('expected a dictionary')
        self.inner_schema = inner_schema
        self.to_native_required_fields = {}
        self.to_native_optional_fields = {}
        self.to_dto_required_fields = {}
        self.to_dto_optional_fields = {}
        for key, value in inner_schema.iteritems():
            if isinstance(key, Required):
                self.to_native_required_fields[key.dto_name] = key.native_name, value
                self.to_dto_required_fields[key.native_name] = key.dto_name, value
            elif isinstance(key, Optional):
                self.to_native_optional_fields[key.dto_name] = key.native_name, value
                self.to_dto_optional_fields[key.native_name] = key.dto_name, value

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
        required_fields = self.to_native_required_fields if to_native else self.to_dto_required_fields
        optional_fields = self.to_native_optional_fields if to_native else self.to_dto_optional_fields
        for key, (substitution_key, converter) in required_fields.iteritems():
            if key in data:
                if to_native:
                    result[substitution_key] = converter.to_native(data.pop(key))
                else:
                    result[substitution_key] = converter.to_dto(data.pop(key))
            else:
                errors.append(RequiredFieldInvalid('required field is missing', [key]))
        for data_key, data_value in data.iteritems():
            if data_key not in optional_fields:
                errors.append(UnknownFieldInvalid('encountered an unknown field', [data_key]))
            else:
                substitution_key, converter = optional_fields[data_key]
                if to_native:
                    result[substitution_key] = converter.to_native(data_value)
                else:
                    result[substitution_key] = converter.to_dto(data_value)
        if errors:
            raise MultipleInvalid(errors)
        return result


class List(Converter):
    def __init__(self, inner_schema):
        self.inner_schema = inner_schema

    def to_dto(self, data):
        if not isinstance(data, dict):
            raise ListInvalid('expected a list')
        return [self.inner_schema.to_dto(d) for d in data]

    def to_native(self, data):
        if not isinstance(data, dict):
            raise ListInvalid('expected a list')
        return [self.inner_schema.to_native(d) for d in data]