# -*- coding: utf-8 -*-
__author__ = 'Roddy MBOGNING'

from django import forms


class PaymentRequestForm(forms.Form):
    username = forms.CharField(max_length=30)  # Username of partner in the Gateway system. A weblet project_name_slug
    payer_id = forms.CharField(max_length=30, required=False)
    amount = forms.CharField(max_length=30)
    merchant_name = forms.CharField(max_length=150)
    notification_url = forms.URLField()
    return_url = forms.URLField()
    cancel_url = forms.URLField()
