from app.memory_capture import extract_memory


def test_remember_requests_become_memories():
    assert extract_memory("Remember that I prefer Celsius.") == ("I prefer Celsius", "preference")
    assert extract_memory("please remember my sister's name is Rima") == ("my sister's name is Rima", "fact")
    assert extract_memory("Don't forget I have a dentist visit tomorrow") == (
        "I have a dentist visit tomorrow", "reminder")


def test_other_sentences_are_not_memories():
    assert extract_memory("What is the weather in Paris?") is None
    assert extract_memory("I remember that trip") is None
    assert extract_memory("remember") is None
