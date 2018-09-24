# -*- coding: utf-8 -*-
__author__ = 'Roddy MBOGNING'

from django import forms


class PaymentRequestForm(forms.Form):
    amount = forms.CharField(max_length=30)
    item_id = forms.CharField(max_length=30)
    notification_url = forms.URLField()
    return_url = forms.URLField()
    cancel_url = forms.URLField()