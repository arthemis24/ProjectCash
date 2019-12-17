from django.utils.translation import gettext_lazy as _
from django.db import models

from ikwen.accesscontrol.models import Member
from ikwen.billing.models import MoMoTransaction
from ikwen.core.models import Model, Service


PENDING = 'Pending'
TERMINATED = 'Terminated'

STATUS_CHOICES = (
    (PENDING, _('Pending')),
    (TERMINATED, _('Terminated'))
)


class PaymentRequest(Model):
    user_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    ik_username = models.CharField(max_length=50, db_index=True)
    amount = models.IntegerField(default=0)
    notification_url = models.URLField(blank=True, null=True)
    return_url = models.URLField(blank=True, null=True)
    cancel_url = models.URLField(blank=True, null=True)
    token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=PENDING)
    momo_transaction_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    merchant_name = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    message = models.TextField(blank=True, null=True)

    def _get_momo_transaction(self):
        transaction = MoMoTransaction.objects.using('wallets').get(pk=self.momo_transaction_id)
        return transaction
    momo_transaction = property(_get_momo_transaction)

    def _get_user(self):
        user = Member.objects.using('umbrella').get(pk=self.user_id)
        return user
    user = property(_get_user)
