import pytest
from collections import Counter


def pytest_configure(config):
    # store across tests
    config._ab_counts = Counter()
    config._ab_total = 0


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item):
    # let the test run
    outcome = yield

    # if the test populated ab_counts on the node, aggregate them
    ab_counts = getattr(item, "ab_counts", None)
    if ab_counts:
        item.config._ab_counts.update(ab_counts)
        item.config._ab_total += sum(ab_counts.values())


def pytest_sessionfinish(session, exitstatus):
    counts = session.config._ab_counts
    total = session.config._ab_total
    if total <= 0 or not counts:
        return

    def pct(m):
        return 100.0 * counts.get(m, 0) / total

    session.config.pluginmanager.get_plugin("terminalreporter").write(
        "\n\nA/B Distribution (aggregated)\n"
        "--------------------------------\n"
        f"total: {total}\n"
        f"model-a: {counts.get('model-a',0):4d} ({pct('model-a'):5.1f}%)\n"
        f"model-b: {counts.get('model-b',0):4d} ({pct('model-b'):5.1f}%)\n"
        f"model-c: {counts.get('model-c',0):4d} ({pct('model-c'):5.1f}%)\n\n"
    )
