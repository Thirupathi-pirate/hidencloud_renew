# -*- coding: utf-8 -*-
import sys
import unittest
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

sys.modules.setdefault("cloudscraper", Mock(create_scraper=Mock(return_value=Mock())))

import main


class FakeResponse:
    def __init__(self, text="", url="https://dash.hidencloud.com/service/147008/renew", status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code


class RenewInvoiceHandlingTests(unittest.TestCase):
    def setUp(self):
        main.BeautifulSoup = BeautifulSoup

    def make_bot(self):
        bot = object.__new__(main.HidenCloudBot)
        bot.index = 1
        bot.base_url = "https://dash.hidencloud.com"
        bot.csrf_token = ""
        bot.processed_invoices = set()
        bot.non_payable_invoices = set()
        bot.retry_needed = False
        bot.messages = []
        bot.log = lambda message: bot.messages.append(message)
        return bot

    def test_non_payable_response_invoice_falls_back_to_service_invoice_poll(self):
        bot = self.make_bot()
        bot.pay_single_invoice = Mock(return_value="non_payable")
        bot.check_and_pay_invoices = Mock(return_value=True)
        response = FakeResponse(
            '<a href="/payment/invoice/old-invoice">old invoice</a>'
        )

        handled, outcome = bot.try_handle_invoice_from_response("147008", response)

        self.assertTrue(handled)
        self.assertEqual(outcome, "invoice_poll")
        bot.pay_single_invoice.assert_called_once_with(
            "https://dash.hidencloud.com/payment/invoice/old-invoice"
        )
        bot.check_and_pay_invoices.assert_called_once_with(
            "147008", is_precheck=False, retries=6, retry_delay=8
        )

    def test_first_pass_does_not_treat_non_payable_response_invoice_as_reject(self):
        bot = self.make_bot()
        bot.pay_single_invoice = Mock(return_value="non_payable")
        bot.check_and_pay_invoices = Mock()
        response = FakeResponse(
            '<a href="/payment/invoice/old-invoice">old invoice</a>'
        )

        handled, outcome = bot.try_handle_invoice_from_response(
            "147008", response, allow_invoice_poll=False
        )

        self.assertFalse(handled)
        self.assertIsNone(outcome)
        bot.check_and_pay_invoices.assert_not_called()

    def test_error_response_is_reported_as_server_reject(self):
        bot = self.make_bot()
        response = FakeResponse('<div class="alert-danger">not allowed</div>')

        handled, outcome = bot.try_handle_invoice_from_response("147008", response)

        self.assertTrue(handled)
        self.assertEqual(outcome, "server_reject")

    def test_perform_pay_from_html_returns_non_payable_and_records_invoice(self):
        bot = self.make_bot()
        invoice_url = "https://dash.hidencloud.com/payment/invoice/old-invoice"

        result = bot.perform_pay_from_html("<html><title>Invoice</title><body>paid</body></html>", invoice_url)

        self.assertEqual(result, "non_payable")
        self.assertIn(invoice_url, bot.non_payable_invoices)

    def test_invoice_poll_only_succeeds_when_an_invoice_is_paid(self):
        bot = self.make_bot()
        bot.request = Mock(return_value=FakeResponse(
            '<table><tr><td>未支付</td><td><a href="/payment/invoice/current">查看</a></td></tr></table>'
        ))
        bot.pay_single_invoice = Mock(return_value="non_payable")

        with patch("main.sleep_random"), patch("main.time.sleep"):
            paid = bot.check_and_pay_invoices("147008", is_precheck=True)

        self.assertFalse(paid)

    def test_pay_single_invoice_skips_known_non_payable_without_request(self):
        bot = self.make_bot()
        invoice_url = "https://dash.hidencloud.com/payment/invoice/old-invoice"
        bot.non_payable_invoices.add(invoice_url)
        bot.request = Mock()

        result = bot.pay_single_invoice(invoice_url)

        self.assertEqual(result, "non_payable")
        bot.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
