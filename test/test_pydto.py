from pydto import Schema


def test():
    schema = Schema({
        'a_string': String('aSimpleString').required(),
        'an_integer': Integer('lastName').required(),
        'birth_date': Date('birthDate').required(),
        'morning_alarm': Time('morningAlarm').required()
    })