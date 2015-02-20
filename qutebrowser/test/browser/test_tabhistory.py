# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2015 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for webelement.tabhistory."""

import sip
import unittest

from PyQt5.QtCore import QUrl, QPoint
from PyQt5.QtWebKitWidgets import QWebPage

from qutebrowser.browser import tabhistory
from qutebrowser.browser.tabhistory import TabHistoryItem as Item
from qutebrowser.utils import qtutils


class SerializeHistoryTests(unittest.TestCase):

    """Tests for serialize()."""

    def setUp(self):
        self.page = QWebPage()
        self.history = self.page.history()
        self.assertEqual(self.history.count(), 0)

        self.items = [
            Item(QUrl('https://www.heise.de/'), QUrl('http://www.heise.de/'),
                 'heise'),
            Item(QUrl('http://example.com/%E2%80%A6'),
                 QUrl('http://example.com/%E2%80%A6'), 'percent', active=True),
            Item(QUrl('http://example.com/?foo=bar'),
                 QUrl('http://original.url.example.com/'), 'arg',
                 user_data={'foo': 23, 'bar': 42}),
            # From https://github.com/OtterBrowser/otter-browser/issues/709#issuecomment-74749471
            Item(QUrl('http://github.com/OtterBrowser/24/134/2344/otter-browser/issues/709/'),
                 QUrl('http://github.com/OtterBrowser/24/134/2344/otter-browser/issues/709/'),
                 'Page not found | github',
                 user_data={'zoom': 149, 'scroll-pos': QPoint(0, 0)}),
            Item(QUrl('https://mail.google.com/mail/u/0/#label/some+label/234lkjsd0932lkjf884jqwerdf4'),
                 QUrl('https://mail.google.com/mail/u/0/#label/some+label/234lkjsd0932lkjf884jqwerdf4'),
                 '"some label" - email@gmail.com - Gmail"',
                 user_data={'zoom': 120, 'scroll-pos': QPoint(0, 0)}),
        ]
        stream, _data, self.user_data = tabhistory.serialize(self.items)
        qtutils.deserialize_stream(stream, self.history)

    def tearDown(self):
        sip.delete(self.page)
        self.page = None

    def test_count(self):
        """Check if the history's count was loaded correctly."""
        self.assertEqual(self.history.count(), len(self.items))

    def test_valid(self):
        """Check if all items are valid."""
        for i, _item in enumerate(self.items):
            self.assertTrue(self.history.itemAt(i).isValid())

    def test_no_userdata(self):
        """Check if all items have no user data."""
        for i, _item in enumerate(self.items):
            self.assertIsNone(self.history.itemAt(i).userData())

    def test_userdata(self):
        """Check if all user data has been restored to self.user_data."""
        for item, user_data in zip(self.items, self.user_data):
            self.assertEqual(user_data, item.user_data)

    def test_currentitem(self):
        """Check if the current item index was loaded correctly."""
        self.assertEqual(self.history.currentItemIndex(), 1)

    def test_urls(self):
        """Check if the URLs were loaded correctly."""
        for i, item in enumerate(self.items):
            with self.subTest(i=i, item=item):
                self.assertEqual(self.history.itemAt(i).url(), item.url)

    def test_original_urls(self):
        """Check if the original URLs were loaded correctly."""
        for i, item in enumerate(self.items):
            with self.subTest(i=i, item=item):
                self.assertEqual(self.history.itemAt(i).originalUrl(),
                                 item.original_url)

    def test_titles(self):
        """Check if the titles were loaded correctly."""
        for i, item in enumerate(self.items):
            with self.subTest(i=i, item=item):
                self.assertEqual(self.history.itemAt(i).title(), item.title)


class SerializeHistorySpecialTests(unittest.TestCase):

    """Tests for serialize() without items set up in setUp."""

    def setUp(self):
        self.page = QWebPage()
        self.history = self.page.history()
        self.assertEqual(self.history.count(), 0)

    def test_no_active_item(self):
        """Check tabhistory.serialize with no active item."""
        items = [Item(QUrl(), QUrl(), '')]
        with self.assertRaises(ValueError):
            tabhistory.serialize(items)

    def test_two_active_items(self):
        """Check tabhistory.serialize with two active items."""
        items = [Item(QUrl(), QUrl(), '', active=True),
                 Item(QUrl(), QUrl(), ''),
                 Item(QUrl(), QUrl(), '', active=True)]
        with self.assertRaises(ValueError):
            tabhistory.serialize(items)

    def test_empty(self):
        """Check tabhistory.serialize with no items."""
        items = []
        stream, _data, user_data = tabhistory.serialize(items)
        qtutils.deserialize_stream(stream, self.history)
        self.assertEqual(self.history.count(), 0)
        self.assertEqual(self.history.currentItemIndex(), 0)
        self.assertFalse(user_data)


if __name__ == '__main__':
    unittest.main()
