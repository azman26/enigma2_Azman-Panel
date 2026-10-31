# -*- coding: utf-8 -*-
"""Przekazywanie wywolan do glownego watku Enigmy2.

Obiekty C++ Enigmy2 (eDVBDB, eEPGCache) nie sa przygotowane na wywolania z
watkow w tle - przeladowanie bukietow albo import EPG rownolegle z GUI potrafi
wywrocic Enigme2. Enigma2 dziala na petli Twisted (e2reactor), a
reactor.callFromThread() to jej oficjalny, bezpieczny wzgledem watkow sposob
na zlecenie pracy glownemu watkowi."""
from __future__ import print_function

import threading


def _run(func, args, logger):
    try:
        func(*args)
    except Exception as error:
        logger("Main thread call failed func=%s error=%s" % (getattr(func, "__name__", func), error))


def call_in_main_thread(func, *args, **kwargs):
    logger = kwargs.get("logger") or (lambda _message: None)
    if threading.current_thread() is threading.main_thread():
        _run(func, args, logger)
        return
    try:
        from twisted.internet import reactor
        reactor.callFromThread(_run, func, args, logger)
    except Exception as error:
        # Bez Twisted (np. testy poza tunerem) zostaje dotychczasowe zachowanie.
        logger("Main thread dispatch unavailable, calling directly error=%s" % error)
        _run(func, args, logger)
