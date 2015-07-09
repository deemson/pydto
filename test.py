from datetime import datetime
import decimal
from nose.tools import assert_equal, assert_raises, assert_true
from pydto2 import Schema, Required, Optional, MultipleInvalid, List, \
    MakeObject


def test_required_and_optional():
    schema = Schema({
        Required('someString1', 'some_string_1'): str,
        Optional('someString2', 'some_string_2'): str
    })

    # check both required and optional deserialize OK
    assert_equal({'some_string_1': 's1', 'some_string_2': 's2'},
                 schema({'someString1': 's1', 'someString2': 's2'}))
    # check required deserializes OK even when optional is missing
    assert_equal({'some_string_1': 's1'},
                 schema({'someString1': 's1'}))
    # check deserialization fails if the required field is missing
    assert_raises(MultipleInvalid, schema, {})


# test nested dictionaries work correctly
def test_nested_schema():
    schema = Schema({
        Required('someDict', 'some_dict'): {
            Required('someString', 'some_string'): str
        }
    })

    assert_equal({'some_dict': {'some_string': 'asdf'}},
                 schema({'someDict': {'someString': 'asdf'}}))


# test only one error message raises if dict is missing
def test_messages():
    schema = Schema(List({
        Required('aDict'): {
            Required('aString'): str,
            Required('aList'): List({
                Required('anInt'): int
            })
        }
    }))
    try:
        schema([{}])
        assert_true(False, 'should have raised an exception')
    except MultipleInvalid as e:
        assert_equal(1, len(e.errors))
    try:
        schema([{'aDict': {}}])
        assert_true(False, 'should have raised an exception')
    except MultipleInvalid as e:
        assert_equal(2, len(e.errors))


# try different object initialization
def test_object_initializators():
    class Some(object):
        def __init__(self):
            self.some_string = None

        def set_stuff(self, some_string):
            self.some_string = some_string

    schema = Schema(MakeObject(Some, {
        Required('some_string'): str
    }, object_initializator='set_stuff'))

    s = schema({'some_string': 'hello'})
    assert_equal(s.some_string, 'hello')

    schema = Schema(MakeObject(Some, {
        Required('some_string'): str
    }, object_initializator=Some.set_stuff))

    s = schema({'some_string': 'helloagain'})
    assert_equal(s.some_string, 'helloagain')
