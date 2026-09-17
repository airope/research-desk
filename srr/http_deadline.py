"""Wall-clock budgets for synchronous HTTPX streams, including header reception.

Use a fresh connection (no keepalive) so the HTTP core trace exposes the socket
before reading headers. DNS resolution remains subject to the host resolver;
Python cannot safely interrupt a blocked getaddrinfo system call in this thread.
"""

import socket
import threading
import time
from contextlib import contextmanager

import httpx


def raw_chunks(response):
    """Never decode or coalesce wire chunks; callers check budgets before copying.

    Real streaming transports use iter_raw (HTTP core bounds network reads).
    Pre-buffered injected fixtures have no unread stream; their existing bytes
    still pass the caller's budget, without constructing any decoder here.
    """
    if response.is_stream_consumed:
        yield response.content
    else:
        yield from response.iter_raw()


def abort_stream(stream):
    connection = stream.get_extra_info("socket") if stream else None
    if connection is not None:
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


@contextmanager
def bounded_stream(client, method, url, *, seconds=30, **kwargs):
    headers = httpx.Headers(kwargs.pop("headers", None))
    headers["Accept-Encoding"] = "identity"
    kwargs["headers"] = headers
    deadline = time.monotonic() + seconds
    state = {"stream": None, "response": None}

    def check():
        if time.monotonic() >= deadline:
            raise httpx.TimeoutException("The repository exceeded its total request deadline.")

    def abort():
        abort_stream(state["stream"])
        response = state["response"]
        if response is not None:
            try:
                response.close()
            except (OSError, httpx.HTTPError):
                pass

    def trace(event, info):
        # Cleanup must never raise again while unwinding a timed-out iterator.
        if event.endswith(".failed") or "response_closed" in event or "close" in event:
            return
        if event in {"connection.connect_tcp.complete", "connection.start_tls.complete"}:
            state["stream"] = info.get("return_value")
            if time.monotonic() >= deadline:
                abort()
        check()

    timer = threading.Timer(seconds, abort)
    timer.daemon = True
    timer.start()
    try:
        with client.stream(method, url, extensions={"trace": trace}, **kwargs) as response:
            state["response"] = response
            state["stream"] = response.extensions.get("network_stream") or state["stream"]
            check()
            if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
                raise httpx.DecodingError("Encoded upstream responses are not supported.")
            yield response, check
            check()
    finally:
        timer.cancel()
        timer.join(timeout=0.1)
