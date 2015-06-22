from datetime import datetime
import decimal
from nose.tools import assert_equal, assert_raises, assert_true
from pydto import MultipleInvalid
from pydto import Schema, Required, Optional, String, List, Decimal, Integer, \
    Object, DateTime


# test that mocks are generating correctly
def test_mock():
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
    schema.to_dto(schema.mock())


# test require and optional markers do what they must
def test_required_and_optional():
    schema = Schema({
        Required('someString1', 'some_string_1'): String(),
        Optional('someString2', 'some_string_2'): String()
    })

    # check both required and optional deserialize OK
    assert_equal({'some_string_1': 's1', 'some_string_2': 's2'},
                 schema.to_native({'someString1': 's1', 'someString2': 's2'}))
    # check required deserializes OK even when optional is missing
    assert_equal({'some_string_1': 's1'},
                 schema.to_native({'someString1': 's1'}))
    # check deserialization fails if the required field is missing
    assert_raises(MultipleInvalid, schema.to_native, {})

    # execute similar assertion for serialization
    assert_equal({'someString1': 's1', 'someString2': 's2'},
                 schema.to_dto({'some_string_1': 's1', 'some_string_2': 's2'}))
    assert_equal({'someString1': 's1'},
                 schema.to_dto({'some_string_1': 's1'}))
    assert_raises(MultipleInvalid, schema.to_native, {})


# test nested dictionaries work correctly
def test_nested_schema():
    schema = Schema({
        Required('someDict', 'some_dict'): {
            Required('someString', 'some_string'): String()
        }
    })

    assert_equal({'some_dict': {'some_string': 'asdf'}},
                 schema.to_native({'someDict': {'someString': 'asdf'}}))


# test only one error message raises if dict is missing
def test_messages():
    schema = Schema(List({
        Required('aDict'): {
            Required('aString'): String(),
            Required('aList'): List({
                Required('anInt'): Integer()
            })
        }
    }))
    try:
        schema.to_native([{}])
        assert_true(False, 'should have raised an exception')
    except MultipleInvalid as e:
        assert_equal(1, len(e.errors))
    try:
        schema.to_native([{'aDict': {}}])
        assert_true(False, 'should have raised an exception')
    except MultipleInvalid as e:
        assert_equal(2, len(e.errors))


# fool-proof test: check that applying `to_dto` and then `to_native` methods
# on an object will return the copy of this object
def test_object_basic_conversion():
    class Some(object):
        def __init__(self, some_dec, some_datetime):
            self.some_dec = some_dec
            self.some_datetime = some_datetime

    schema = Schema(Object(Some, {
        Required('some_dec'): Decimal(),
        Required('some_datetime'): DateTime()
    }))

    s1 = Some(decimal.Decimal('10.5'), datetime(2015, 12, 13, 0, 0, 0))
    s2 = schema.to_native(schema.to_dto(s1))
    assert_equal(s1.some_dec, s2.some_dec)
    assert_equal(s1.some_datetime, s2.some_datetime)


# try different object initialization
def test_object_initializators():
    class Some(object):
        def __init__(self):
            self.some_string = None

        def set_stuff(self, some_string):
            self.some_string = some_string

    schema = Schema(Object(Some, {
        Required('some_string'): String()
    }, object_initializator='set_stuff'))

    s = schema.to_native({'some_string': 'hello'})
    assert_equal(s.some_string, 'hello')

    schema = Schema(Object(Some, {
        Required('some_string'): String()
    }, object_initializator=Some.set_stuff))

    s = schema.to_native({'some_string': 'helloagain'})
    assert_equal(s.some_string, 'helloagain')
