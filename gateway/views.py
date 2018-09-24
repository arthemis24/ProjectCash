# -*- coding: utf-8 -*-
import json
import random
import string

import datetime
import requests
from datetime import timedelta
from django.conf import settings
from django.http.response import HttpResponseRedirect, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_by_path
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from requests.exceptions import SSLError, Timeout, RequestException

from ikwen.billing.mtnmomo.views import MTN_MOMO

from ikwen.accesscontrol.models import Member
from ikwen.billing.models import MoMoTransaction
from ikwen.billing.orangemoney.views import ORANGE_MONEY, init_web_payment
from ikwen.billing.views import MoMoSetCheckout
# from ikwen.core.tools import generate_random_key

from gateway.forms import PaymentRequestForm
from gateway.models import PaymentRequest, TERMINATED, PENDING

import logging
logger = logging.getLogger('ikwen')


def generate_random_key(length):
    import random
    import string
    generated_key = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits)
                             for _ in range(length)])
    return generated_key


def generate_transaction_token():
    key = generate_random_key(30)
    while True:
        try:
            PaymentRequest.objects.get(token=key)
            key = generate_random_key(30)
        except PaymentRequest.DoesNotExist:
            break
    return key


@csrf_exempt
def request_payment(request, *args, **kwargs):

    form = PaymentRequestForm(request.GET)
    if form.is_valid():
        # TODO: Verifiy and send clear error messages. Use username instead of user_id
        username = request.GET.get('username')
        amount = form.cleaned_data.get('amount')
        merchant_name = form.cleaned_data.get('merchant_name')
        notification_url = form.cleaned_data.get('notification_url')
        return_url = form.cleaned_data.get('return_url')
        cancel_url = form.cleaned_data.get('cancel_url')
        # item_id = form.cleaned_data.get('item_id')

        if not amount.isdigit():
            return HttpResponse("Transaction amount must be a number")

        try:
            user = Member.objects.using('umbrella').get(username=username)
        except Member.DoesNotExist:
            return HttpResponse("User does not exist")
        else:
            payment_request = PaymentRequest(user_id=user.id, amount=amount,
                                         notification_url=notification_url, return_url=return_url,
                                             cancel_url=cancel_url, merchant_name=merchant_name)
            payment_request.token = generate_transaction_token()
            payment_request.save(using='docash')
            # payment_request.save()
            logger.debug("Token %s generated" % payment_request.token)
            response = HttpResponse(json.dumps(
                {'success': True,
                 'token': payment_request.token,
                 }), 'content-type: text/json')
    else:
        error_list = []
        for error in form.errors:
            error_list.append(error)
        response = HttpResponse(json.dumps(
            {
                'message': 'One or more GET parameters was not found in your request',
                'errors': error_list,
             }), 'content-type: text/json')
    return response


class SetCheckout(MoMoSetCheckout):

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        token = kwargs['token']
        # payment_request = get_object_or_404(PaymentRequest, token=token)
        payment_request = PaymentRequest.objects.using('docash').get(token=token)
        token_timeout = getattr(settings, 'TOKEN_TIMEOUT', 5) * 60
        token_expiry = payment_request.created_on + timedelta(seconds=token_timeout)
        now = datetime.datetime.now()
        if not getattr(settings, 'DEBUG', False):
            if now > token_expiry:
                # Token is expired
                return HttpResponse(json.dumps({'error': "expired token; restart your request"}), 'content-type: text/json')
        payment_mean = context['payment_mean']
        signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(16)])
        request.session['signature'] = signature
        path = getattr(settings, 'MOMO_BEFORE_CASH_OUT')
        momo_before_checkout = import_by_path(path)
        http_resp = momo_before_checkout(request, payment_mean, *args, **kwargs)

        if http_resp:
            return http_resp
        if payment_mean.slug == ORANGE_MONEY:
            return init_web_payment(request, *args, **kwargs)
        context['amount'] = request.session['amount']
        return render(request, self.template_name, context)


def set_momo_checkout(request, *args, **kwargs):
    token = kwargs['token']
    # payment_request = PaymentRequest.objects.get(token=token, status=PENDING)
    try:
        payment_request = PaymentRequest.objects.using('docash').get(token=token, status=PENDING)
    except PaymentRequest.DoesNotExist:
        return HttpResponse("Error, PaymentRequest does not exist.")
    else:
        request.session['model_name'] = 'gateway.PaymentRequest'
        request.session['object_id'] = payment_request.token
        request.session['amount'] = payment_request.amount

        request.session['merchant_name'] = payment_request.merchant_name
        request.session['notif_url'] = payment_request.notification_url
        request.session['cancel_url'] = payment_request.cancel_url
        request.session['return_url'] = payment_request.return_url


def after_cashout(request, *args, **kwargs):
    token = request.session['object_id']
    # username = request.user.username
    try:
        payment_request = PaymentRequest.objects.using('docash').get(token=token)
    except PaymentRequest.DoesNotExist:
        logger.debug("The payment request %s was not found" % token, exc_info=True)
    else:
        try:
            transaction = MoMoTransaction.objects.using('wallets').get(object_id=token)
        except MoMoTransaction.DoesNotExist:
            logger.error("MoMoTransaction with object_id: %s was not found" % token, exc_info=True)
        else:
            phone = transaction.phone
            token = payment_request.token
            amount = payment_request.amount
            try:
                payment_request.momo_transaction_id = transaction.id
                payment_request.status = TERMINATED
                payment_request.save(using='docash')
                logger.debug("Request of %dF from %s with token %s Terminated" % (amount, phone, token))
                notification_final_url = payment_request.notification_url +'?status=' + \
                                     payment_request.momo_transaction.status
                logger.debug("Notification URL of the  %dF transaction is %s" % (amount, notification_final_url))
                requests.get(notification_final_url)
            except SSLError:
                logger.error("SSL Error", exc_info=True)
                transaction.message = "SSL Error"
            except Timeout:
                logger.error("Time out" , exc_info=True)
                transaction.message = "Time out"
            except RequestException:
                logger.error("Request exception" , exc_info=True)
                transaction.message = "Request exception"
            except:
                logger.error("Server error" , exc_info=True)
                transaction.message = "Server error"
            else:
                logger.debug("Notification for %dF from %s successfully sent using URL %s" % (amount, token, notification_final_url))
                transaction.message = ("Notification for %dF from %s successfully sent using URL %s" % (amount, token, notification_final_url))
            transaction.save()
        return HttpResponseRedirect(payment_request.return_url)