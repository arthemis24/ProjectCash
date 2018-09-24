from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from django.utils import unittest
from django.core.management import call_command

from conf import settings
from ikwen.accesscontrol.models import Member
from gateway.models import PaymentRequest
from gateway.views import generate_transaction_token
from django.test.client import Client


class GatewayTestCase(unittest.TestCase):
    fixtures = ['ikw_members.yaml', 'dc_setup_data.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b105')
    def test_payment_request_posted_data(self):
        response = self.client.post(reverse('gateway:request_payment'),
                                    {'amount': 5000, 'product_id': '55d1fa8feb60008099bd4151',
                                     'notification_url': 'http://notifURL.com',
                                     'return_url': 'http://returnURL.fr'}, follow=True)
        self.assertEqual(response.status_code, 200)
        transaction = PaymentRequest.objects.filter(item_id='55d1fa8feb60008099bd4151')[0]
        self.assertEqual(transaction.amount, '5000')
        self.assertEqual(transaction.notification_url, 'http://notifURL.com')
        self.assertEqual(transaction.return_url, 'http://returnURL.fr')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b105')
    def test_set_checkout(self):
        user_id = '56eb6d04b37b3379b531e012'
        member = Member.objects.get(pk=user_id)
        payment_request = PaymentRequest(user=member, amount=5000, item_id='55d1fa8feb60008099bd4151',
                                         notification_url='http://notifURL.com', return_url='http://returnURL.com', )
        payment_request.token = generate_transaction_token()
        payment_request.save()
        response = self.client.get(reverse('gateway:set_checkout', kwargs= {"token": payment_request.token}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session['amount'], payment_request.amount)
        self.assertEqual(self.client.session['token'], payment_request.token)
