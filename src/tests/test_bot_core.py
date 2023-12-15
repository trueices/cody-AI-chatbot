from src.tests.utils import setup, ask
from src.bot import Bot
from src.utils import fake_llm


def test_handling_of_exception(setup):
    bot = Bot(username='test')

    # No response provided to the fake_llm. This should raise an exception.
    # And, the bot should raise an exception.
    try:
        bot = ask(bot)
    except:
        pass
    assert len(bot.state.errors) == 1

    # Going for another exception.
    try:
        bot = ask(bot)
    except:
        pass
    assert len(bot.state.errors) == 2
    assert len(bot.state.error_types) == 2

    for i, errors in enumerate(bot.state.errors):
        assert errors[0] == 'IndexError: No more responses\n', \
            'Should have raised an index error.'
        assert bot.state.error_types[i] == 'IndexError', \
            'Type should be properly captured.'
        assert len(errors) <= 4, 'Should have captured only 4 lines of traceback.'


def test_handling_of_timeout(setup):
    bot = Bot(username='test')

    # First timeout.
    fake_llm.responses = ['Timeout']
    bot = ask(bot)
    assert bot.state.timeouts == 1
    assert '\n\n\nSorry, that took too long to process for us. Can you please type that again?'\
        in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        'Doesnt have the timeout message.'
    
    # Second timeout.
    fake_llm.responses += ['Timeout']
    bot = ask(bot)
    assert bot.state.timeouts == 2
    assert '\n\n\nSorry, that took too long to process for us. Can you please type that again?'\
        in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        'Doesnt have the timeout message.'
    
