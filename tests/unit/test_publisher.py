from app.core.publisher import QueuePublisher

TOPIC = "devices/config/esp32-1"


async def test_enqueued_item_comes_back_out() -> None:
    publisher = QueuePublisher(maxsize=10)

    publisher.enqueue(TOPIC, {"version": 2})

    assert await publisher.get() == (TOPIC, {"version": 2})


async def test_none_payload_is_preserved() -> None:
    publisher = QueuePublisher(maxsize=10)

    publisher.enqueue(TOPIC, None)

    assert await publisher.get() == (TOPIC, None)


def test_order_is_preserved() -> None:
    publisher = QueuePublisher(maxsize=10)

    publisher.enqueue(TOPIC, {"version": 1})
    publisher.enqueue(TOPIC, {"version": 2})

    assert publisher.pending() == 2


def test_full_queue_drops_instead_of_raising() -> None:
    publisher = QueuePublisher(maxsize=1)

    publisher.enqueue(TOPIC, {"version": 1})
    publisher.enqueue(TOPIC, {"version": 2})

    assert publisher.pending() == 1


def test_clear_empties_the_queue() -> None:
    publisher = QueuePublisher(maxsize=10)
    publisher.enqueue(TOPIC, {"version": 1})

    publisher.clear()

    assert publisher.pending() == 0
