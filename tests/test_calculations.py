from app.calculations import add, subtract, multipy, divide


def test_add():
    print("testing add function")
    assert add(5, 3) == 8


def test_subtract():
    assert subtract(9, 4) == 5
