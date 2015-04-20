# encoding: utf-8
from contextlib import contextmanager


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


class DictInvalid(Invalid):
    """The value found was not a dict."""


class Schema(object):
    def __init__(self, schema):
        self._compiled_schema = self._compile(schema)

    @staticmethod
    def _compile(schema):
        if isinstance(schema, dict):
            return Dict(name=None, inner_schema=schema)._compile()
        elif isinstance(schema, Field):
            return schema._compile()
        else:
            raise Exception()

    def to_primitive(self, data):
        pass

    def to_native(self, data):
        return self._compiled_schema._to_native(data)


class Field(object):
    def __init__(self, name=None):
        self._name = name
        self._required = False

    def required(self):
        self._required = True
        return self

    def optional(self):
        self._required = False
        return self

    def _compile(self):
        raise NotImplementedError()

    def _to_primitive(self, data):
        raise NotImplementedError()

    def _to_native(self, data):
        raise NotImplementedError()


class String(Field):
    """
    >>> schema = Schema({
    ...     'a_field': String('aField')
    ... })
    >>> data = schema.to_native({'aField': 'hello'})
    >>> assert data == {'a_field': 'hello'}


    >>> schema = Schema({
    ...     'a': String().required()
    ... })
    >>> with raises(RequiredFieldInvalid, "required field is missing @ data['a']"):
    ...     data = schema.to_native({})
    """

    def _compile(self):
        return self

    def _to_native(self, data):
        return self._to_primitive(data)

    def _to_primitive(self, data):
        return str(data)


class DateTime(Field):
    def _to_native(self, data):
        pass

    def _to_primitive(self, data):
        pass

    def _validate_required(self, data):
        pass


class Dict(Field):
    """
    >>> schema = Schema({'a': String()})
    >>> schema.to_native([])
    """

    def __init__(self, name, inner_schema):
        super(Dict, self).__init__(name)
        self.inner_schema = inner_schema

    def _compile(self):
        for key, value in self.inner_schema.iteritems():
            self.inner_schema[key] = Schema._compile(value)
        return self

    def _to_native(self, data):
        if not isinstance(data, dict):
            raise DictInvalid('expected a dictionary')
        result = {}
        for key, value in self.inner_schema.iteritems():
            data_key = value._name or key
            if data_key not in data:
                raise RequiredFieldInvalid('required field is missing', [data_key])
            result[key] = value._to_native(data[data_key])
        return result

    def _to_primitive(self, data):
        pass


# class List(Field):
# def __init__(self, name, inner_schema):
