from nose.tools import assert_equal, assert_dict_equal, assert_raises
from pydto import MultipleInvalid
from pydto import Schema, Required, Optional, String


def test_required_and_optional():
    schema = Schema({
        Required('someString1', 'some_string_1'): String(),
        Optional('someString2', 'some_string_2'): String()
    })

    # check both required and optional deserialize OK
    assert_dict_equal({'some_string_1': 's1', 'some_string_2': 's2'},
                      schema.to_native({'someString1': 's1', 'someString2': 's2'}))
    # check required deserializes OK even when optional is missing
    assert_dict_equal({'some_string_1': 's1'},
                      schema.to_native({'someString1': 's1'}))
    # check deserialization fails if the required field is missing
    assert_raises(MultipleInvalid, schema.to_native, {})

    # execute similar assertion for serialization
    assert_dict_equal({'someString1': 's1', 'someString2': 's2'},
                      schema.to_dto({'some_string_1': 's1', 'some_string_2': 's2'}))
    assert_dict_equal({'someString1': 's1'},
                      schema.to_dto({'some_string_1': 's1'}))
    assert_raises(MultipleInvalid, schema.to_native, {})


def test_nested_schema():
    schema = Schema({
        Required('someDict', 'some_dict'): {
            Required('someString', 'some_string'): String()
        }
    })

    assert_dict_equal({'some_dict': {'some_string': 'asdf'}}, schema.to_native({'someDict': {'someString': 'asdf'}}))