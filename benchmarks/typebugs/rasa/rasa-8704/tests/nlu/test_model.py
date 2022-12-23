import pickle

from rasa.nlu.model import UnsupportedModelError, InvalidModelError


def test_exception_pickling_1():
    exception = UnsupportedModelError("test run")
    cycled_exception = pickle.loads(pickle.dumps(exception))
    assert exception.message == cycled_exception.message

def test_exception_pickling_2():
    exception = InvalidModelError("test run")
    cycled_exception = pickle.loads(pickle.dumps(exception))
    assert exception.message == cycled_exception.message

def test_exception_pickling_1_noassert():
    exception = UnsupportedModelError("test run")
    cycled_exception = pickle.loads(pickle.dumps(exception))
    #assert exception.message == cycled_exception.message

def test_exception_pickling_2_noassert():
    exception = InvalidModelError("test run")
    cycled_exception = pickle.loads(pickle.dumps(exception))
    #assert exception.message == cycled_exception.message


def test_pyfix() :
    pass
